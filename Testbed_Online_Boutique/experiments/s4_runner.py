"""Run bounded S4 or its matched S0 control without editing the original workload."""
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from label import normalize, timestamp, write_json
from s4_support import ROOT, Guard, RESOURCE_QUERIES, LOSS_QUERY, command as k, get, now, query


def run_s4(args):
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo python3 experiments/runner.py")
    lock = open("/run/lock/boutique-s0-tetragon.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    original = get("-n", "boutique", "get", "deploy", "loadgenerator")
    if original["spec"]["replicas"] != 0:
        raise RuntimeError("Original loadgenerator must have 0 replicas")
    for deployment in get("-n", "boutique", "get", "deploy")["items"]:
        if deployment["status"].get("availableReplicas", 0) < deployment["spec"].get("replicas", 1):
            raise RuntimeError("An existing deployment is unavailable: " + deployment["metadata"]["name"])
    if get("-n", "boutique", "get", "pods", "-l", "experiment-run")["items"]:
        raise RuntimeError("Previous experiment Pods remain; inspect before running")
    nodes = get("get", "nodes")["items"]
    for name in ("lab-w1", "lab-w2"):
        node = next(n for n in nodes if n["metadata"]["name"] == name)
        if not any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"]["conditions"]):
            raise RuntimeError("Worker not Ready: " + name)
    control = args.s4_control
    scenario = "S0" if control else "S4"
    prefix = "s0-s4-control" if control else "s4"
    run_id = f'{prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{os.getpid()}'
    output = ROOT.parent / "runs" / run_id
    output.mkdir(mode=0o700); (output / "raw").mkdir()
    print("Run:", output, flush=True)
    actor, loadname, config = f"gd4-s4-{os.getpid()}", f"gd4-locust-{os.getpid()}", f"gd4-s4-code-{os.getpid()}"
    labels = {"experiment-run": run_id}
    rate = 0 if control else args.s4_rate
    manifest = {"schema_version": 4, "run_id": run_id, "scenario_id": scenario, "mode": args.mode,
                "status": "setup", "node": args.node, "users": 10, "spawn_rate": 1,
                "warmup_seconds": args.warmup, "pre_seconds": args.pre, "recovery_seconds": args.recovery,
                "s4": {"profile": "control" if control else "bounded_http", "rate": rate,
                       "duration_seconds": args.s4_duration, "concurrency": args.s4_concurrency,
                       "method": "GET", "path": "/", "request_timeout_seconds": 3,
                       "connection_mode": "new_tcp_each_request", "guard_poll_target_seconds": 5},
                "temporary_resources": {"actor": actor, "locust_deployment": loadname, "configmap": config},
                "source_snapshot": "source", "script_sha256": {}}
    manifest["s4"]["verification_contract"] = 2
    for name in ("runner.py", "label.py", "s4_runner.py", "s4_support.py", "s4_verify.py", "s4/client.py", "s4/locust_wrapper.py"):
        content = (ROOT / name).read_bytes()
        manifest["script_sha256"][name] = hashlib.sha256(content).hexdigest()
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(content)
    imported = (ROOT.parent / "telemetry/normalize.py").read_bytes()
    manifest["script_sha256"]["telemetry/normalize.py"] = hashlib.sha256(imported).hexdigest()
    (output / "source/telemetry").mkdir(); (output / "source/telemetry/normalize.py").write_bytes(imported)
    manifest["code_bundle_sha256"] = hashlib.sha256(json.dumps(manifest["script_sha256"], sort_keys=True).encode()).hexdigest()
    write_json(output / "manifest.json", manifest)
    (output / "actor-receipts.ndjson").touch()
    handles, collectors, created = [], [], []
    action, guard, phase = None, None, "setup"

    def mark(value):
        nonlocal phase
        phase = value
        with (output / "timeline.ndjson").open("a") as stream:
            stream.write(json.dumps({"time": now(), "phase": value}) + "\n")
        print(value, flush=True)

    def healthy():
        reason = guard.failure_reason() if guard else None
        if reason:
            manifest["stop_reason"] = reason
            raise KeyboardInterrupt("S4 guard stopped the run: " + str(reason))
        if any(p.poll() is not None for p in collectors):
            raise RuntimeError("A capture stream stopped early")

    def pause(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            healthy(); time.sleep(min(0.2, max(0, deadline - time.monotonic())))

    def capture(filename, arguments, errors):
        stdout = (output / filename).open("w")
        stderr = (output / errors).open("w")
        handles.extend((stdout, stderr))
        collectors.append(subprocess.Popen(["k3s", "kubectl", *arguments], stdout=stdout, stderr=stderr))

    def snapshot(stage):
        for name, arguments in {
            "boutique": ("-n", "boutique", "get", "deploy,pods,svc,endpointslice"),
            "agents": ("-n", "telemetry", "get", "pods", "-l", "app.kubernetes.io/name=tetragon"),
            "nodes": ("get", "nodes"),
            "policies": ("-n", "boutique", "get", "tracingpoliciesnamespaced"),
        }.items():
            write_json(output / f"{name}-{stage}.json", get(*arguments))
        (output / f"top-{stage}.txt").write_text(k("top", "nodes"))
        metrics = {}
        for name, expression in {"agent_up": 'up{service="tetragon"}', "loss_and_export": LOSS_QUERY,
                                 "agent_scrape_age_seconds": 'time()-timestamp(up{service="tetragon"})'}.items():
            try:
                metrics[name] = query("query", query=expression)
            except Exception as error:
                metrics[name] = {"error": type(error).__name__}
        write_json(output / f"metrics-{stage}.json", metrics)

    try:
        service = get("-n", "boutique", "get", "svc", "frontend")
        slices = get("-n", "boutique", "get", "endpointslice", "-l", "kubernetes.io/service-name=frontend")
        aliases, ports = {service["spec"]["clusterIP"]}, {80}
        for item in slices["items"]:
            ports.update(p["port"] for p in item["ports"] if p.get("port"))
            for endpoint in item["endpoints"]:
                if endpoint.get("conditions", {}).get("ready") is not False:
                    aliases.update(endpoint["addresses"])
        if len(aliases) < 2:
            raise RuntimeError("Frontend has no Ready endpoint")
        target = {"service": "frontend", "ip": service["spec"]["clusterIP"], "port": 80,
                  "target_ips": sorted(aliases), "target_ports": sorted(ports)}
        manifest["targets"] = [target]
        cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": config, "namespace": "boutique", "labels": labels},
              "data": {name: (ROOT / "s4" / name).read_text(encoding="utf-8") for name in ("client.py", "locust_wrapper.py")}}
        k("create", "-f", "-", input=json.dumps(cm)); created.append(("configmap", config))
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": actor, "namespace": "boutique", "labels": {**labels, "app": "gd4-actor"}},
               "spec": {"automountServiceAccountToken": False, "restartPolicy": "Never", "activeDeadlineSeconds": 1800, "terminationGracePeriodSeconds": 3,
                        "nodeSelector": {"lab.slot": args.node}, "volumes": [{"name": "s4-code", "configMap": {"name": config}}],
                        "containers": [{"name": "actor", "image": "python:3.12.8-slim-bookworm",
                          "command": ["python3", "-c", "import time;time.sleep(1700)"],
                          "volumeMounts": [{"name": "s4-code", "mountPath": "/s4", "readOnly": True}],
                          "securityContext": {"runAsNonRoot": True, "runAsUser": 10000, "allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                          "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "256Mi"}}}]}}
        k("create", "-f", "-", input=json.dumps(pod)); created.append(("pod", actor))
        k("-n", "boutique", "wait", "--for=condition=Ready", "pod/" + actor, "--timeout=120s", timeout=130)
        actual = get("-n", "boutique", "get", "pod", actor)
        if actual["spec"]["nodeName"] != "lab-" + args.node:
            raise RuntimeError("Unexpected actor placement")
        manifest["actor"] = {"name": actor, "uid": actual["metadata"]["uid"], "ip": actual["status"]["podIP"],
                             "image_id": actual["status"]["containerStatuses"][0]["imageID"]}
        manifest["capture_start"] = now(); manifest["status"] = "running"
        write_json(output / "manifest.json", manifest); mark("setup")
        for node in ("lab-w1", "lab-w2"):
            agents = get("-n", "telemetry", "get", "pods", "-l", "app.kubernetes.io/name=tetragon", "--field-selector", "spec.nodeName=" + node)["items"]
            if len(agents) != 1 or not all(c.get("ready") for c in agents[0]["status"].get("containerStatuses", [])):
                raise RuntimeError("Expected one Ready Tetragon agent per worker")
            capture("raw/" + node + ".ndjson", ["-n", "telemetry", "logs", agents[0]["metadata"]["name"], "-c", "export-stdout", "--since-time=" + manifest["capture_start"], "-f"], "raw/" + node + ".stderr")
        template = copy.deepcopy(original["spec"]["template"])
        template["metadata"] = {"labels": {**labels, "app": loadname}}
        template["spec"]["automountServiceAccountToken"] = False
        template["spec"]["terminationGracePeriodSeconds"] = 15
        template["spec"].setdefault("volumes", []).append({"name": "s4-code", "configMap": {"name": config}})
        main = next(c for c in template["spec"]["containers"] if c["name"] == "main")
        main["command"] = ["locust"]
        main["args"] = ["-f", "/s4/locust_wrapper.py", "--host=http://frontend:80", "--headless", "--users=10", "--spawn-rate=1", "--stop-timeout=3"]
        main.setdefault("env", []).extend([{"name": "PYTHONUNBUFFERED", "value": "1"}, {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"}])
        main.setdefault("volumeMounts", []).append({"name": "s4-code", "mountPath": "/s4", "readOnly": True})
        deployment = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": loadname, "namespace": "boutique", "labels": labels},
                      "spec": {"replicas": 1, "selector": {"matchLabels": {"app": loadname}}, "template": template}}
        write_json(output / "instrumented-locust-deployment.json", deployment)
        k("create", "-f", "-", input=json.dumps(deployment)); created.append(("deployment", loadname))
        k("-n", "boutique", "rollout", "status", "deployment/" + loadname, "--timeout=180s", timeout=190)
        background = get("-n", "boutique", "get", "pods", "-l", "app=" + loadname)["items"][0]
        manifest["locust"] = {"pod": background["metadata"]["name"], "uid": background["metadata"]["uid"],
                              "image_id": background["status"]["containerStatuses"][0]["imageID"], "original_deployment_unchanged": True}
        capture("locust.raw.log", ["-n", "boutique", "logs", background["metadata"]["name"], "-c", "main", "-f"], "locust.stderr")
        deadline = time.monotonic() + 60
        while "All users spawned" not in (output / "locust.raw.log").read_text():
            healthy()
            if time.monotonic() > deadline:
                raise RuntimeError("Instrumented Locust did not spawn users")
            time.sleep(1)
        snapshot("before")
        guard = Guard(output, actor, target, lambda: phase); guard.start()
        mark("warmup"); pause(args.warmup)
        mark("pre_attack"); pause(args.pre)
        mark("measurement" if control else "attack")
        if control:
            pause(args.s4_duration)
        else:
            receipts, errors = (output / "actor-receipts.ndjson").open("w"), (output / "actor.stderr").open("w")
            handles.extend((receipts, errors))
            action = subprocess.Popen(["k3s", "kubectl", "-n", "boutique", "exec", actor, "-c", "actor", "--",
                "python3", "/s4/client.py", "--target", json.dumps(target), "--rate", str(rate), "--duration", str(args.s4_duration),
                "--concurrency", str(args.s4_concurrency)], stdout=receipts, stderr=errors)
            deadline = time.monotonic() + args.s4_duration + 15
            while action.poll() is None:
                healthy()
                if time.monotonic() > deadline:
                    raise RuntimeError("Bounded HTTP actor exceeded deadline")
                time.sleep(0.2)
            if action.returncode:
                raise RuntimeError("S4 actor exited unsuccessfully")
            write_json(output / "s4-client-summary.json", json.loads(k("-n", "boutique", "exec", actor, "-c", "actor", "--", "cat", "/tmp/s4-client-summary.json")))
        mark("recovery"); pause(args.recovery)
        manifest["measurement_end"] = now(); mark("finalize")
        guard.close()
        healthy()
        snapshot("after")
        resources = {}
        for name, expression in RESOURCE_QUERIES.items():
            try:
                resources[name] = query("query_range", query=expression, start=timestamp(manifest["capture_start"]).timestamp(),
                                        end=timestamp(manifest["measurement_end"]).timestamp(), step=5)
            except Exception as error:
                resources[name] = {"error": type(error).__name__}
        write_json(output / "prometheus-resources.json", resources)
        manifest["status"] = "completed"
    except BaseException as error:
        manifest["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        cleanup_errors = []
        if guard:
            guard.stop.set()
        # Delete the actor first: all its request threads stop even after a broken exec/SSH stream.
        for kind, name in sorted(created, key=lambda item: {"pod": 0, "deployment": 1, "configmap": 2}[item[0]]):
            try:
                extra = ["--grace-period=0", "--force"] if kind == "pod" and manifest["status"] != "completed" else []
                k("-n", "boutique", "delete", kind, name, "--ignore-not-found", "--wait=false", *extra)
            except Exception as error:
                cleanup_errors.append(kind + ":" + str(error))
        if guard:
            try:
                guard.close()
            except Exception as error:
                cleanup_errors.append(str(error))
        try:
            k("-n", "boutique", "wait", "--for=delete", "pod", "-l", "experiment-run=" + run_id, "--timeout=25s", timeout=30)
        except Exception as error:
            cleanup_errors.append("pod_cleanup_wait:" + str(error))
        if action and action.poll() is None:
            action.terminate()
            try:
                action.wait(timeout=10)
            except subprocess.TimeoutExpired:
                action.kill(); action.wait()
        time.sleep(3)
        for process in collectors:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        for handle in handles:
            handle.close()
        try:
            remaining = {kind:len(get("-n","boutique","get",kind,"-l","experiment-run="+run_id)["items"])
                         for kind in ("pods","deployments","configmaps")}
            original_now=get("-n","boutique","get","deploy","loadgenerator")["spec"]
            cleanup={"checked_at":now(),"remaining":remaining,"original_loadgenerator_unchanged":original_now==original["spec"]}
            cleanup["passed"]=not any(remaining.values()) and cleanup["original_loadgenerator_unchanged"]
            write_json(output/"cleanup.json",cleanup)
            if not cleanup["passed"]: cleanup_errors.append("Resources remain or original deployment changed")
        except Exception as error:
            cleanup_errors.append("cleanup_verification:"+type(error).__name__)
        manifest["finished"] = now(); manifest["cleanup_errors"] = cleanup_errors
        manifest["guard_triggered"] = bool(guard and guard.triggered.is_set())
        write_json(output / "manifest.json", manifest)
    from s4_verify import verify_s4, extract_locust
    try:
        extract_locust(output)
        normalize(output)
        result = verify_s4(output)
    except Exception as error:
        manifest["dataset_status"] = "failed_validation"
        manifest["postprocess_error"] = f"{type(error).__name__}: {error}"
        write_json(output / "manifest.json", manifest)
        raise
    manifest["dataset_status"] = "validated" if result["passed"] else "failed_validation"
    manifest["s4_verification"] = result
    write_json(output / "manifest.json", manifest)
    if not result["passed"]:
        raise RuntimeError("S4 verification failed; see s4-verification.json")
    print("Completed:", output, flush=True)
