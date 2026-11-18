#!/usr/bin/env python3
"""Run a bounded S0/S1 pilot or S3 file smoke test on lab-cp."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import time
from urllib.parse import urlencode

from label import normalize, write_json

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def k(*args, **kwargs):
    return subprocess.run(["k3s", "kubectl", *args], check=True,
                          text=True, capture_output=True, timeout=180, **kwargs).stdout


def get(*args):
    return json.loads(k(*args, "-o", "json"))


def run(args):
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo python3 experiments/runner.py")
    lock = open("/run/lock/boutique-s0-tetragon.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if get("-n", "boutique", "get", "deploy", "loadgenerator")["spec"]["replicas"] != 0:
        raise RuntimeError("loadgenerator must have 0 replicas before the run")
    nodes = {node["metadata"]["name"]: node for node in get("get", "nodes")["items"]}
    for node_name in ("lab-w1", "lab-w2"):
        node = nodes.get(node_name, {})
        if not any(c["type"] == "Ready" and c["status"] == "True"
                   for c in node.get("status", {}).get("conditions", [])):
            raise RuntimeError(f"Node is not Ready: {node_name}")
    run_id = f'{args.scenario.lower()}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{os.getpid()}'
    output = ROOT.parent / "runs" / run_id
    output.mkdir(mode=0o700)
    (output / "raw").mkdir()
    print(f"Run: {output}", flush=True)
    actor_name = f"gd4-{os.getpid()}"
    collectors, handles = [], []
    scaled, created = False, False
    manifest = {
        "schema_version": 3, "run_id": run_id, "scenario_id": args.scenario,
        "mode": args.mode, "status": "setup", "node": args.node,
        "users": 10, "spawn_rate": 1,
        "warmup_seconds": args.warmup, "pre_seconds": args.pre,
        "recovery_seconds": args.recovery, "measurement_seconds": args.measurement,
        "limits": {"max_targets": 40, "connection_timeout_seconds": 1, "max_attempts_per_second": 5},
        "script_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (ROOT / "runner.py", ROOT / "actor.py", ROOT / "label.py")},
    }
    try:
        manifest["git_commit"] = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        manifest["git_commit"] = None
    write_json(output / "manifest.json", manifest)
    (output / "actor-receipts.ndjson").touch()

    def mark(phase):
        with (output / "timeline.ndjson").open("a") as stream:
            stream.write(json.dumps({"time": now(), "phase": phase}) + "\n")
        print(phase, flush=True)

    def pause(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in collectors):
                raise RuntimeError("Collector stopped early")
            time.sleep(min(2, max(0, deadline - time.monotonic())))

    def snapshot(stage):
        for name, command in {
            "boutique": ["-n", "boutique", "get", "deploy,pods,svc,endpointslice"],
            "agents": ["-n", "telemetry", "get", "pods", "-l", "app.kubernetes.io/name=tetragon"],
            "nodes": ["get", "nodes"],
        }.items():
            write_json(output / f"{name}-{stage}.json", get(*command))
        (output / f"top-{stage}.txt").write_text(k("top", "nodes"))
        policies = get("-n", "boutique", "get", "tracingpoliciesnamespaced")
        write_json(output / f"policies-{stage}.json", policies)
        endpoint = "/api/v1/namespaces/monitoring/services/monitoring-kube-prometheus-prometheus:http-web/proxy/api/v1/query?"
        queries = {
            "agent_up": 'up{service="tetragon"}',
            "loss_and_export": 'sum by (__name__,node) ({__name__=~"tetragon_observer_ringbuf_events_lost_total|tetragon_observer_ringbuf_queue_events_lost_total|tetragon_events_export_failed_total|tetragon_export_ratelimit_events_dropped_total",service="tetragon"})',
        }
        metrics = {}
        for name, query in queries.items():
            try:
                metrics[name] = json.loads(k("get", "--raw", endpoint + urlencode({"query": query})))
            except (subprocess.SubprocessError, ValueError) as error:
                metrics[name] = {"error": str(error)}
        write_json(output / f"metrics-{stage}.json", metrics)


    try:
        if args.scenario != "S0":
            actor = {
                "apiVersion": "v1", "kind": "Pod", "metadata": {
                    "name": actor_name, "namespace": "boutique",
                    "labels": {"app": "gd4-actor", "experiment-run": run_id}},
                "spec": {"automountServiceAccountToken": False,
                         "restartPolicy": "Never", "activeDeadlineSeconds": 1800,
                         "nodeSelector": {"lab.slot": args.node},
                         "containers": [{
                             "name": "actor", "image": "python:3.12.8-slim-bookworm",
                             "command": ["python3", "-c",
                                         "from pathlib import Path; import time; p=Path('/tmp/gd4-fixture'); p.mkdir(); (p/'token').write_text('GD4-SYNTHETIC-TOKEN'); time.sleep(1700)"],
                             "securityContext": {"runAsUser": 10000, "runAsNonRoot": True,
                                                 "allowPrivilegeEscalation": False,
                                                 "capabilities": {"drop": ["ALL"]}},
                             "resources": {"requests": {"cpu": "20m", "memory": "32Mi"},
                                           "limits": {"cpu": "200m", "memory": "96Mi"}}}]}}
            k("create", "-f", "-", input=json.dumps(actor))
            created = True
            k("-n", "boutique", "wait", "--for=condition=Ready", f"pod/{actor_name}", "--timeout=120s")
            actual = get("-n", "boutique", "get", "pod", actor_name)
            if actual["spec"]["nodeName"] != f"lab-{args.node}":
                raise RuntimeError("Actor placement differs from requested node")

            manifest["actor"] = {"name": actor_name, "uid": actual["metadata"]["uid"],
                                 "ip": actual["status"]["podIP"],
                                 "image_id": actual["status"]["containerStatuses"][0]["imageID"]}
        snapshot("before")
        targets = []
        if args.scenario == "S1":
            for svc in get("-n", "boutique", "get", "svc")["items"]:
                for port in (svc["spec"]["ports"][0]["port"], 65000):
                    targets.append({"service": svc["metadata"]["name"],
                                    "ip": svc["spec"]["clusterIP"], "port": port})
            manifest["targets"] = targets
        manifest["capture_start"] = now()
        manifest["status"] = "running"
        write_json(output / "manifest.json", manifest)
        mark("setup")
        for node in ("lab-w1", "lab-w2"):
            pods = get("-n", "telemetry", "get", "pods", "-l", "app.kubernetes.io/name=tetragon",
                       "--field-selector", f"spec.nodeName={node},status.phase=Running")["items"]
            if len(pods) != 1:
                raise RuntimeError(f"Expected one agent on {node}")
            if not all(c.get("ready") for c in pods[0]["status"].get("containerStatuses", [])):
                raise RuntimeError(f"Agent containers are not Ready on {node}")

            stdout = (output / "raw" / f"{node}.ndjson").open("w")
            stderr = (output / "raw" / f"{node}.stderr").open("w")
            handles.extend([stdout, stderr])
            collectors.append(subprocess.Popen(
                ["k3s", "kubectl", "-n", "telemetry", "logs", pods[0]["metadata"]["name"],
                 "-c", "export-stdout", f'--since-time={manifest["capture_start"]}', "-f"],
                stdout=stdout, stderr=stderr))
        loadgen = get("-n", "boutique", "get", "deploy", "loadgenerator")
        env = {e["name"]: e.get("value") for e in loadgen["spec"]["template"]["spec"]["containers"][0]["env"]}
        if env.get("USERS") != "10" or env.get("RATE") != "1":
            raise RuntimeError("Expected USERS=10 and RATE=1")
        k("-n", "boutique", "scale", "deployment/loadgenerator", "--current-replicas=0", "--replicas=1")
        scaled = True
        k("-n", "boutique", "rollout", "status", "deployment/loadgenerator", "--timeout=180s")
        deadline = time.monotonic() + 180
        while "All users spawned" not in k("-n", "boutique", "logs", "deployment/loadgenerator", "-c", "main"):
            if time.monotonic() > deadline:
                raise RuntimeError("Locust did not spawn users")
            pause(3)
        mark("warmup")
        pause(args.warmup)
        if args.scenario == "S0":
            mark("measurement")
            pause(args.measurement)
        else:
            mark("pre_attack")
            pause(args.pre)
            mark("attack")
            command = ["-n", "boutique", "exec", "-i", actor_name, "-c", "actor",
                       "--", "python3", "-", args.scenario, "--targets", json.dumps(targets)]
            # Capture the action stream even if the remote process fails partway.
            with (output / "actor-receipts.ndjson").open("w") as receipts, (output / "actor.stderr").open("w") as errors:
                result = subprocess.run(["k3s", "kubectl", *command],
                                        input=(ROOT / "actor.py").read_text(encoding="utf-8"),
                                        text=True, stdout=receipts, stderr=errors, timeout=120)
            if result.returncode:
                raise RuntimeError("Actor failed. See actor.stderr and partial receipts")
            mark("recovery")
            pause(args.recovery)
        manifest["measurement_end"] = now()
        mark("finalize")
        (output / "locust.log").write_text(k("-n", "boutique", "logs", "deployment/loadgenerator", "-c", "main", "--timestamps"))
        manifest["status"] = "completed"
    except BaseException as error:
        manifest["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        try:
            if scaled:
                k("-n", "boutique", "scale", "deployment/loadgenerator", "--replicas=0")
            time.sleep(2)
            for process in collectors:
                process.terminate()
            for process in collectors:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for handle in handles:
                handle.close()
            snapshot("after")
        finally:
            manifest["finished"] = now()
            write_json(output / "manifest.json", manifest)
            if created:
                k("-n", "boutique", "delete", "pod", actor_name, "--ignore-not-found", "--wait=false")
    quality = normalize(output)
    valid_capture = quality["capture_checks_passed"]
    has_evidence = args.scenario == "S0" or quality["operations_with_matched_event"] > 0
    manifest["dataset_status"] = "validated" if valid_capture and has_evidence else "failed_validation"
    manifest["matched_operations"] = quality["operations_with_matched_event"]
    write_json(output / "manifest.json", manifest)
    if not quality["capture_checks_passed"]:
        raise RuntimeError("Capture checks failed. See quality.json")
    if args.scenario != "S0" and quality["operations_with_matched_event"] == 0:
        raise RuntimeError("No operations matched. See quality.json")
    print(f"Completed: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=["S0", "S1", "S3"])
    parser.add_argument("--mode", choices=["pilot", "smoke", "official"], default="pilot")
    parser.add_argument("--node", choices=["w1", "w2"], default="w1")
    parser.add_argument("--warmup", type=int, default=400)
    parser.add_argument("--pre", type=int, default=120)
    parser.add_argument("--recovery", type=int, default=120)
    parser.add_argument("--measurement", type=int, default=900)
    args = parser.parse_args()
    if args.scenario == "S3" and args.mode != "smoke":
        parser.error("S3 currently implements the file smoke test. Use --mode smoke.")
    if min(args.warmup, args.pre, args.recovery, args.measurement) < 0:
        parser.error("Durations must be nonnegative")
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    os.umask(0o077)
    run(args)
