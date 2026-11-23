"""Replay completed S4/control pilot verification from archives in temporary directories."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_scenarios import unpack_copy
from s4_verify import verify_s4
from label import write_json,normalize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parents[2] / "runs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for run in sorted(p for p in args.runs_root.iterdir() if p.is_dir() and (p / "manifest.json").exists()):
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        if "s4" not in manifest:
            continue
        item = {"run_id": run.name, "mode": manifest["mode"], "status": manifest["status"], "included": False}
        if manifest["mode"] != "pilot" or manifest["status"] != "completed" or manifest.get("dataset_status") != "validated":
            results.append(item); continue
        item["included"] = True
        try:
            with tempfile.TemporaryDirectory(prefix="s4-audit-") as directory:
                directory = Path(directory); unpack_copy(run, directory)
                for name, digest in manifest["script_sha256"].items():
                    if hashlib.sha256((directory / "source" / name).read_bytes()).hexdigest()!=digest:
                        raise ValueError("Source snapshot hash mismatch: "+name)
                archived=[json.loads(line) for line in (directory/"normalized.ndjson").read_text(encoding="utf-8").splitlines()]
                old_quality=json.loads((directory/"quality.json").read_text(encoding="utf-8"))
                with contextlib.redirect_stdout(io.StringIO()): rebuilt_quality=normalize(directory)
                rebuilt=[json.loads(line) for line in (directory/"normalized.ndjson").read_text(encoding="utf-8").splitlines()]
                if archived!=rebuilt: raise ValueError("Archived normalized records differ from raw replay")
                for field in ("events_by_type","events_by_label","events_by_node","operations","operations_with_matched_event","unmatched_operations"):
                    if old_quality[field]!=rebuilt_quality[field]: raise ValueError("Derived quality mismatch: "+field)
                proof = verify_s4(directory)
                before = json.loads((directory / "boutique-before.json").read_text())
                after = json.loads((directory / "boutique-after.json").read_text())
                original_before = next(i for i in before["items"] if i["kind"] == "Deployment" and i["metadata"]["name"] == "loadgenerator")
                original_after = next(i for i in after["items"] if i["kind"] == "Deployment" and i["metadata"]["name"] == "loadgenerator")
                if original_before["spec"]!=original_after["spec"] or original_after["spec"]["replicas"]!=0:
                    raise ValueError("Original loadgenerator changed")
                item.update(passed=proof["passed"], source_hashes_verified=len(manifest["script_sha256"]),
                            native_records_verified=proof["native_records_verified"],
                            operations_verified=proof["operations_with_native_event"],
                            original_loadgenerator_spec_unchanged=True, code_bundle_sha256=manifest["code_bundle_sha256"],
                            normalized_replayed_from_raw=True, strict_verifier_sha256=proof["verifier_sha256"],
                            legacy_evidence_limits=proof.get("legacy_evidence_limits",[]),
                            actor_image_id=manifest["actor"]["image_id"], locust_image_id=manifest["locust"]["image_id"],
                            locust_original_sha256=json.loads((directory / "locust-runtime.json").read_text())["metadata"][0]["original_locustfile_sha256"])
        except Exception as error:
            item.update(passed=False, error=f"{type(error).__name__}: {error}")
        results.append(item)
    included = [r for r in results if r["included"]]
    same = bool(included) and all(len({r.get(key) for r in included}) == 1 for key in
                                 ("code_bundle_sha256", "actor_image_id", "locust_image_id", "locust_original_sha256"))
    report = {"runs": results, "pilots_reviewed": len(included), "same_sources_and_images": same,
              "analysis_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "passed": bool(included) and same and all(r.get("passed") for r in included)}
    if any(args.output.resolve().is_relative_to((args.runs_root / r["run_id"]).resolve()) for r in results):
        parser.error("Output must be outside the historical run directories")
    args.output.parent.mkdir(parents=True, exist_ok=True); write_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}, indent=2))
    for result in results: print(result["run_id"], result.get("passed", "excluded"), result.get("error", ""))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__": main()
