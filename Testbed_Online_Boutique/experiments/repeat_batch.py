"""Run the frozen 24-case protocol as a durable, bounded VM batch."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

from repeat_support import archive_run, check_sources, now, save, source_digest

ROOT = Path(__file__).resolve().parent
STOP = False


def interrupt(signum, frame):
    global STOP
    STOP = True


def k(*args):
    return json.loads(subprocess.check_output(["k3s", "kubectl", *args, "-o", "json"], timeout=12))


def stable_pods(items):
    return {p["metadata"]["uid"]: {
        "name": p["metadata"]["name"], "node": p["spec"].get("nodeName"),
        "phase":p.get("status",{}).get("phase"),
        "ready":bool(p.get("status",{}).get("containerStatuses")) and all(c.get("ready") for c in p.get("status",{}).get("containerStatuses",[])),
        "containers": sorted((c["name"], c.get("imageID"), c.get("restartCount", 0))
                             for c in p.get("status", {}).get("containerStatuses", []))}
        for p in items}


def snapshot():
    nodes = k("get", "nodes")["items"]
    pods = k("-n", "boutique", "get", "pods")["items"]
    agents = k("-n", "telemetry", "get", "pods", "-l", "app.kubernetes.io/name=tetragon")["items"]
    deployment = k("-n", "boutique", "get", "deployment", "loadgenerator")
    policies = k("-n", "boutique", "get", "tracingpoliciesnamespaced")["items"]
    persistent = [p for p in pods if not p["metadata"].get("labels", {}).get("experiment-run")
                  and p["metadata"].get("labels", {}).get("app") != "loadgenerator"]
    spec = copy.deepcopy(deployment["spec"])
    replicas = spec.pop("replicas")
    return {"timestamp": now(),
            "nodes": {n["metadata"]["name"]: {c["type"]: c["status"] for c in n["status"]["conditions"]} for n in nodes},
            "application_pods": stable_pods(persistent), "agents": stable_pods(agents),
            "loadgenerator_spec": spec, "loadgenerator_replicas": replicas,
            "loadgenerator_pods": stable_pods([p for p in pods if p["metadata"].get("labels", {}).get("app") == "loadgenerator"]),
            "policies": sorted([{"name": p["metadata"]["name"], "spec": p["spec"]} for p in policies], key=lambda p:p["name"]),
            "temporary_pods": [p["metadata"]["name"] for p in pods if p["metadata"].get("labels", {}).get("experiment-run")],
            "disk_free_bytes": shutil.disk_usage(ROOT.parent).free}


def read_snapshot():
    """Retry one timed-out read; never substitute cached health or hide both failures."""
    timeouts=[]
    for attempt in (1,2):
        try:
            current=snapshot()
            current["read_timeouts"]=timeouts
            return current
        except subprocess.TimeoutExpired as error:
            timeouts.append({"attempt":attempt,"time":now(),"command":error.cmd,"timeout_seconds":error.timeout})
            if attempt==2:
                raise
            time.sleep(1)


def carry_forward(plan,initial):
    cases=[{**case,"status":"pending"} for case in plan["cases"]]
    carry=plan.get("carry_forward")
    if not carry:
        return cases
    batch=(ROOT.parent/"runs"/carry["batch"]).resolve()
    if batch.parent!=(ROOT.parent/"runs").resolve():
        raise ValueError("Escaped source batch")
    audit_path=(ROOT/carry["audit_path"]).resolve()
    if not audit_path.is_relative_to((ROOT/"audits").resolve()) or source_digest(audit_path)!=carry["audit_sha256"]:
        raise ValueError("Carry-forward audit checksum mismatch")
    audit=json.loads(audit_path.read_text(encoding="utf-8"))
    if not audit["passed"] or not audit["original_evidence_unchanged"] or audit["batch"]!=batch.name:
        raise ValueError("Source cases have not passed independent partial audit")
    old=json.loads((batch/"batch.json").read_text(encoding="utf-8"))
    previous=json.loads((batch/"environment-after.json").read_text(encoding="utf-8"))
    differences=health_errors(initial,previous,plan["minimum_disk_free_bytes"])
    if differences:
        raise ValueError("Environment differs from source batch: "+"; ".join(differences))
    accepted={c["case_id"]:c for c in audit["cases"] if c.get("counted_as_completed") and c.get("passed")}
    indexed={c["case_id"]:c for c in old["cases"]}
    for case_id in carry["case_ids"]:
        target=next(c for c in cases if c["case_id"]==case_id)
        source=indexed[case_id]
        if case_id not in accepted or source["status"]!="completed" or source["run_id"]!=accepted[case_id]["run_id"] or source["args"]!=target["args"]:
            raise ValueError("Carry-forward case is incomplete, unaudited or changed: "+case_id)
        run=ROOT.parent/"runs"/source["run_id"]
        manifest=json.loads((run/"manifest.json").read_text(encoding="utf-8"))
        if manifest.get("dataset_status")!="validated" or source_digest(run/"dataset.tar.gz")!=source["archive"]:
            raise ValueError("Carried run is not intact: "+case_id)
        for name,value in manifest["script_sha256"].items():
            plan_name="../telemetry/normalize.py" if name=="telemetry/normalize.py" else name
            if plan["source_sha256"].get(plan_name)!=value:
                raise ValueError("Carried runtime source differs: "+case_id+"/"+name)
        for key in ("run_id","return_code","archive","started","finished","dataset_status","run_status"):
            if key in source:target[key]=source[key]
        target.update(status="completed",source_batch=batch.name,carried_forward=True)
    return cases


def health_errors(current, initial, disk_min):
    errors = []
    if len(current["nodes"]) != 3:
        errors.append("Expected three nodes")
    for node, conditions in current["nodes"].items():
        if conditions.get("Ready") != "True" or any(conditions.get(p) == "True" for p in ("MemoryPressure", "DiskPressure", "PIDPressure")):
            errors.append("Unhealthy node: " + node)
    if len(current["agents"]) != 2:
        errors.append("Expected two Tetragon agents")
    if any(p["phase"]!="Running" or not p["ready"] for p in [*current["application_pods"].values(),*current["agents"].values()]):
        errors.append("An application or agent container is not ready")
    if current["disk_free_bytes"] < disk_min:
        errors.append("Disk below protocol minimum")
    if initial:
        for field in ("application_pods", "agents", "loadgenerator_spec", "policies"):
            # Live tuples and the same values restored as JSON lists are equivalent.
            if json.dumps(current[field],sort_keys=True) != json.dumps(initial[field],sort_keys=True):
                errors.append("Environment changed: " + field)
    return errors


def stop_child(child):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise RuntimeError("Runner required SIGKILL; inspect cleanup")


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=ROOT/"repeat-protocol.json")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run on lab-cp with sudo")
    os.umask(0o077)
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    lock = open("/run/lock/boutique-controls-batch.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = json.loads(args.protocol.read_text(encoding="utf-8"))
    check_sources(ROOT, plan["source_sha256"])
    out = ROOT.parent/"runs"/f"batch-repeats-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"
    out.mkdir(mode=0o700)
    shutil.copyfile(args.protocol, out/"protocol.json")
    shutil.copyfile(__file__, out/"coordinator.py")
    initial = read_snapshot()
    save(out/"environment-before.json", initial)
    errors = health_errors(initial, None, plan["minimum_disk_free_bytes"])
    if initial["loadgenerator_replicas"] or initial["temporary_pods"]:
        errors.append("Another workload experiment is active")
    state = {"protocol_id": plan["protocol_id"], "status": "preflight",
             "protocol_sha256": source_digest(out/"protocol.json"),
             "coordinator_sha256": source_digest(out/"coordinator.py"), "started": now(),
             "cases": carry_forward(plan,initial)}
    state["carried_forward_cases"]=sum(bool(c.get("carried_forward")) for c in state["cases"])
    state["new_cases_planned"]=len(state["cases"])-state["carried_forward_cases"]
    save(out/"batch.json", state)
    print("Batch:", out, flush=True)
    child = None
    try:
        if errors:
            raise RuntimeError("; ".join(errors))
        state["status"] = "running"
        save(out/"batch.json", state)
        frontend = k("-n", "boutique", "get", "service", "frontend")["spec"]["clusterIP"]
        for case in state["cases"]:
            if case.get("carried_forward"):
                continue
            if STOP:
                raise KeyboardInterrupt("Batch stop requested")
            check_sources(ROOT, plan["source_sha256"])
            # Wait for asynchronous deletion from the previous core runner.
            deadline = time.monotonic()+90
            while k("-n", "boutique", "get", "pods", "-l", "experiment-run")["items"]:
                if STOP or time.monotonic() > deadline:
                    raise RuntimeError("Experiment Pods remain between cases")
                time.sleep(2)
            current = read_snapshot()
            errors = health_errors(current, initial, plan["minimum_disk_free_bytes"])
            if errors:
                raise RuntimeError("; ".join(errors))
            case.update(status="running", started=now())
            state["current_case"] = case["case_id"]
            save(out/"batch.json", state)
            print("Starting:", case["case_id"], flush=True)
            failures = 0
            with (out/(case["case_id"]+".log")).open("w", encoding="utf-8") as log, (out/(case["case_id"]+"-guard.ndjson")).open("w", encoding="utf-8") as guard:
                child = subprocess.Popen([sys.executable, str(ROOT/"runner.py"), *case["args"]],
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                begin = time.monotonic()
                try:
                    while child.poll() is None:
                        if STOP:
                            raise KeyboardInterrupt("Batch stop requested")
                        if time.monotonic()-begin > case["timeout_seconds"]:
                            raise RuntimeError("Case deadline exceeded")
                        current = read_snapshot()
                        errors = health_errors(current, initial, plan["minimum_disk_free_bytes"])
                        try:
                            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://"+frontend+":80/_healthz", timeout=3) as response:
                                probe = response.status == 200
                        except Exception:
                            probe = False
                        failures = 0 if probe else failures+1
                        if failures >= 3:
                            errors.append("Three consecutive host health probes failed")
                        record = {**current, "case_id":case["case_id"], "probe_ok":probe,
                                  "consecutive_probe_failures":failures, "reasons":errors}
                        guard.write(json.dumps(record)+"\n")
                        guard.flush()
                        state["heartbeat"] = now()
                        state["case_elapsed_seconds"] = round(time.monotonic()-begin, 1)
                        save(out/"batch.json", state)
                        if errors:
                            raise RuntimeError("; ".join(errors))
                        for _ in range(15):
                            if child.poll() is not None or STOP:
                                break
                            time.sleep(1)
                    case["return_code"] = child.wait()
                finally:
                    stop_child(child)
            lines = (out/(case["case_id"]+".log")).read_text(encoding="utf-8").splitlines()
            run = next((Path(line[5:].strip()) for line in lines if line.startswith("Run: ")), None)
            if run is None or run.resolve().parent != (ROOT.parent/"runs").resolve():
                raise RuntimeError("Runner did not create an owned run")
            manifest = json.loads((run/"manifest.json").read_text(encoding="utf-8"))
            case.update(run_id=manifest["run_id"], run_status=manifest["status"],
                        dataset_status=manifest.get("dataset_status"))
            if case["return_code"] or manifest["status"] != "completed" or manifest.get("dataset_status") != "validated":
                raise RuntimeError("Case failed; retain all partial evidence: "+case["case_id"])
            check_sources(ROOT, plan["source_sha256"])
            # Capture application failures without deleting or retrying the case.
            diagnostics = {}
            for name in ("frontend", "paymentservice"):
                p = subprocess.run(["k3s", "kubectl", "-n", "boutique", "logs", "deployment/"+name,
                                    "--since-time="+manifest["capture_start"], "--timestamps=true"],
                                   text=True, capture_output=True, timeout=30)
                diagnostics[name] = {"return_code":p.returncode, "stdout":p.stdout, "stderr":p.stderr}
            save(run/"application-diagnostics.json", diagnostics)
            case["archive"] = archive_run(run, ROOT.parent/"runs")["archive_sha256"]
            case.update(status="completed", finished=now())
            save(out/"batch.json", state)
            print("Completed:", case["case_id"], case["run_id"], flush=True)
        state["status"] = "reviewing"
        save(out/"batch.json", state)
        child=subprocess.Popen([sys.executable, str(ROOT/"repeat_review.py"), str(out)],start_new_session=True)
        review_deadline=time.monotonic()+3600
        while child.poll() is None:
            if STOP:
                raise KeyboardInterrupt("Stopped during final cohort review")
            if time.monotonic()>review_deadline:
                raise RuntimeError("Cohort review deadline exceeded")
            time.sleep(1)
        if child.returncode:
            raise RuntimeError("Final cohort review failed; retain runs")
        state["status"] = "completed"
    except BaseException as error:
        stop_child(child)
        active = next((c for c in state["cases"] if c["status"] == "running"), None)
        if active:
            active.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=type(error).__name__+": "+str(error), finished=now())
            # Even an interrupted action must remain discoverable in the batch index.
            log_path=out/(active["case_id"]+".log")
            if log_path.exists():
                candidate=next((Path(line[5:].strip()) for line in log_path.read_text(encoding="utf-8").splitlines() if line.startswith("Run: ")),None)
                if candidate and candidate.resolve().parent==(ROOT.parent/"runs").resolve() and (candidate/"manifest.json").exists():
                    partial=json.loads((candidate/"manifest.json").read_text(encoding="utf-8"))
                    active.update(run_id=partial["run_id"],run_status=partial["status"],dataset_status=partial.get("dataset_status"))
        state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=type(error).__name__+": "+str(error))
        raise
    finally:
        state["finished"] = now()
        try:
            final = read_snapshot()
            save(out/"environment-after.json", final)
            state["final_environment_errors"] = health_errors(final, initial, plan["minimum_disk_free_bytes"])
            if final["temporary_pods"] or final["loadgenerator_replicas"]:
                state["final_environment_errors"].append("Experiment workload still present at final checkpoint")
            if state["final_environment_errors"] and state["status"] == "completed":
                state["status"] = "failed_final_environment"
        except Exception as error:
            state["final_environment_error"] = str(error)
        save(out/"batch.json", state)
        print("Final status:", state["status"], flush=True)


if __name__ == "__main__":
    main()
