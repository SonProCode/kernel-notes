"""Prove SIGTERM cleanup for S0, S2, S3 or S4 on the lab."""
from datetime import datetime, timezone
import json
import argparse
from pathlib import Path
import subprocess
import time

def find_owned_run(root, scenario, started, pid):
    return next((p for p in (root / "runs").glob(scenario.lower()+"-*")
                 if p.is_dir() and p.name not in started and p.name.endswith("-"+str(pid))
                 and (p / "manifest.json").is_file()), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["S0", "S2", "S3", "S4"], default="S0")
    parser.add_argument("--at-phase", choices=["warmup", "attack"], default="warmup")
    args = parser.parse_args()
    if args.at_phase == "attack" and args.scenario != "S4":
        parser.error("Attack-phase cleanup test is supported for S4")
    root = Path(__file__).resolve().parents[1]
    started = {p.name for p in (root / "runs").iterdir() if p.is_dir()}
    log = root / "runs" / ("cleanup-check-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".log")
    with log.open("w") as stream:
        command = ["python3", str(root / "experiments/runner.py"),
                   "--scenario", args.scenario, "--mode", "smoke",
                   "--warmup", "5" if args.at_phase == "attack" else "300", "--measurement", "1"]
        if args.scenario == "S4":
            command += ["--pre", "5", "--recovery", "5", "--s4-duration", "90"]
        if args.scenario == "S3":
            command += ["--s3-profile", "runtime", "--s3-rounds", "1"]
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 180
            run = None
            while time.monotonic() < deadline:
                candidate = find_owned_run(root, args.scenario, started, process.pid)
                if candidate:
                    run = candidate
                    timeline = run / "timeline.ndjson"
                    if timeline.exists() and ('"' + args.at_phase + '"') in timeline.read_text():
                        receipts=run/"actor-receipts.ndjson"
                        if args.at_phase!="attack" or (receipts.exists() and receipts.read_text().strip()):
                            break
                if process.poll() is not None:
                    raise RuntimeError(log.read_text())
                time.sleep(2)
            else:
                raise RuntimeError("Runner did not reach requested phase with evidence: "+args.at_phase)
            process.terminate()
            process.wait(timeout=40)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=40)
    replicas = subprocess.check_output(["k3s","kubectl","-n","boutique","get","deploy","loadgenerator",
                                        "-o","jsonpath={.spec.replicas}"], text=True)
    manifest = json.loads((run / "manifest.json").read_text())
    assert replicas == "0", replicas
    assert manifest["status"] == "interrupted", manifest
    if args.scenario in ("S2","S3", "S4"):
        for kind in (("pods", "deployments", "configmaps") if args.scenario == "S4" else ("pods", "serviceaccounts")):
            deadline = time.monotonic() + 60
            while True:
                response = json.loads(subprocess.check_output(
                    ["k3s","kubectl","-n","boutique","get",kind,
                     "-l","experiment-run="+manifest["run_id"],"-o","json"],text=True))
                if not response["items"]:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError(f"Resources remain after cleanup: {kind}")
                time.sleep(2)

    print("SIGTERM cleanup verified", run.name, "loadgenerator=0", "status=interrupted")


if __name__ == "__main__": main()
