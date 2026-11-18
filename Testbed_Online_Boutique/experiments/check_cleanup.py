"""Prove SIGTERM cleanup using a short S0 setup on the lab."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
started = {p.name for p in (root / "runs").iterdir() if p.is_dir()}
log = root / "runs" / ("cleanup-check-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".log")
with log.open("w") as stream:
    process = subprocess.Popen(["python3", str(root / "experiments/runner.py"),
                                "--scenario", "S0", "--mode", "smoke",
                                "--warmup", "300", "--measurement", "1"],
                               stdout=stream, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 100
        run = None
        while time.monotonic() < deadline:
            candidates = [p for p in (root / "runs").glob("s0-*") if p.name not in started]
            if candidates:
                run = sorted(candidates)[-1]
                timeline = run / "timeline.ndjson"
                if timeline.exists() and '"warmup"' in timeline.read_text():
                    break
            if process.poll() is not None:
                raise RuntimeError(log.read_text())
            time.sleep(2)
        else:
            raise RuntimeError("Runner did not reach warmup")
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
print("SIGTERM cleanup verified", run.name, "loadgenerator=0", "status=interrupted")
