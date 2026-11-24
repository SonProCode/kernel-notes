"""Read-only S4 acceptance review, including smoke provenance and phase metrics."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_scenarios import unpack_copy
from label import normalize, timestamp
from s4_verify import percentile, rows, summarize, verify_s4


def phase_metrics(records, timeline, measurement_end):
    """Count starts and completions separately; do not silently drop boundaries."""
    output = {}
    for i, phase in enumerate(timeline[:-1]):
        low = timestamp(phase["time"])
        high = min(timestamp(timeline[i + 1]["time"]), timestamp(measurement_end))
        seconds = (high - low).total_seconds()
        if seconds <= 0:
            continue
        started = [r for r in records if low <= timestamp(r["started"]) < high]
        finished = [r for r in records if low <= timestamp(r["ended"]) < high]
        inside = [r for r in started if timestamp(r["ended"]) < high]
        successful = [r["duration_ms"] for r in inside if r.get("error") is None and r.get("status_code") == 200]
        output[phase["phase"]] = {
            **summarize(inside), "p99_ms": percentile(successful, .99),
            "phase_seconds": seconds, "request_starts": len(started),
            "request_completions": len(finished), "started_rps": len(started) / seconds,
            "completed_rps": len(finished) / seconds,
            "crossing_out_requests": len(started) - len(inside),
            "crossing_in_requests": len(finished) - len(inside),
            "latency_population": "Only successful HTTP 200 requests wholly inside phase; crossings counted separately",
            "p99_is_max_for_fewer_than_100_successes": 0 < len(successful) < 100,
        }
    return output


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def review(runs_root):
    before = hashes(runs_root)
    results = []
    for manifest_path in sorted(runs_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if "s4" not in manifest:
            continue
        item = {"run_id": manifest["run_id"], "mode": manifest["mode"], "status": manifest["status"],
                "dataset_status": manifest.get("dataset_status"),
                "contract": manifest["s4"].get("verification_contract", 1)}
        item["included"] = manifest["status"] == "completed" and manifest.get("dataset_status") == "validated"
        if not item["included"]:
            item["excluded_reason"] = "Not a completed validated dataset; retained for debugging/cleanup evidence"
            results.append(item)
            continue
        item["required_for_acceptance"] = manifest["mode"] == "pilot" or item["contract"] >= 2
        try:
            with tempfile.TemporaryDirectory(prefix="s4-review-") as tmp:
                run = Path(tmp)
                unpack_copy(manifest_path.parent, run)
                proof = verify_s4(run)
                item["current_gate_passed"] = proof["passed"]
                item["input_errors"] = proof.get("input_integrity_errors", [])
                item["native_errors"] = proof.get("native_integrity_errors", [])
                item["source_snapshot_valid"] = bool(manifest["script_sha256"]) and all(
                    hashlib.sha256((run / "source" / name).read_bytes()).hexdigest() == digest
                    for name, digest in manifest["script_sha256"].items())
                item["bundle_hash_valid"] = hashlib.sha256(json.dumps(manifest["script_sha256"], sort_keys=True).encode()).hexdigest() == manifest["code_bundle_sha256"]
                old_records = rows(run / "normalized.ndjson")
                old_windows = rows(run / "labeled-windows.ndjson")
                with contextlib.redirect_stdout(io.StringIO()):
                    normalize(run)
                item["normalized_replay_matches"] = rows(run / "normalized.ndjson") == old_records
                item["window_labels_replay_match"] = rows(run / "labeled-windows.ndjson") == old_windows
                locust = rows(run / "locust-requests.ndjson")
                receipts = rows(run / "actor-receipts.ndjson")
                item["locust_by_phase"] = phase_metrics(locust, rows(run / "timeline.ndjson"), manifest["measurement_end"])
                item["actor_requests"] = len(receipts)
                item["actor_http_errors"] = summarize(receipts)["failures"]
                item["code_bundle_sha256"] = manifest["code_bundle_sha256"]
                item["passed"] = all(item.get(k) is True for k in (
                    "current_gate_passed", "source_snapshot_valid", "bundle_hash_valid",
                    "normalized_replay_matches", "window_labels_replay_match"))
        except Exception as error:
            item.update(passed=False, error=f"{type(error).__name__}: {error}")
        results.append(item)
    required = [r for r in results if r.get("required_for_acceptance")]
    unchanged = hashes(runs_root) == before
    return {"review_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "verifier_sha256": hashlib.sha256((Path(__file__).resolve().parents[1]/"s4_verify.py").read_bytes()).hexdigest(),
            "runs": results, "required_runs": len(required),
            "required_runs_passed": sum(r.get("passed") is True for r in required),
            "original_evidence_unchanged": unchanged,
            "passed": bool(required) and unchanged and all(r.get("passed") for r in required),
            "official_dataset_ready": False,
            "official_gaps": ["No completed official 90-second S4 runs with repeated matched S0 controls",
                              "No fixed recorded schedule/seed and sufficient independent repetitions",
                              "30-second pilot CPU rate uses a 60-second window; phases overlap in measurement",
                              "p99 on small phase samples is descriptive, not a stable tail-latency estimate"],
            "later_stage_work_not_blocking_gd4": ["Detector effectiveness in GD5", "Mitigation effectiveness in GD6"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parents[2]/"runs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.runs_root.resolve()):
        parser.error("Write the report outside runs/ to preserve captured evidence")
    result = review(args.runs_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({k:v for k,v in result.items() if k != "runs"}, ensure_ascii=False, indent=2))
    for r in result["runs"]:
        print(r["run_id"], r.get("passed", "excluded"), r.get("input_errors", []), r.get("error", ""))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
