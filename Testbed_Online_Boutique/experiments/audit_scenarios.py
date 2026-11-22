"""Read-only audit of archived S1/S2/S3 pilots; write a separate audit report."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

from label import timestamp, write_json
from s1_verify import verify_s1
from s2_verify import verify_run
from s2_audit import audit as audit_s2
from s3_verify import verify_s3


def unpack_copy(run, destination):
    for item in run.iterdir():
        if item.is_file() and item.suffix in (".json", ".ndjson", ".log", ".stderr", ".txt"):
            shutil.copyfile(item, destination / item.name)
    archive = run / "dataset.tar.gz"
    if archive.exists():
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError("Unsafe archive member")
                if member.isfile():
                    target = destination.joinpath(*name.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.extractfile(member).read())
    else:
        for name in ("raw", "source"):
            if (run / name).is_dir():
                shutil.copytree(run / name, destination / name)


def check_rpc_native(run, manifest):
    receipts = {r["operation_id"]: r for line in (run / "actor-receipts.ndjson").read_text(encoding="utf-8").splitlines()
                if (r := json.loads(line))}
    linked = Counter()
    raw = {node: (run / "raw" / f"{node}.ndjson").read_text(encoding="utf-8").splitlines()
           for node in ("lab-w1", "lab-w2")}
    seen = set()
    for line in (run / "normalized.ndjson").open(encoding="utf-8"):
        event = json.loads(line)
        if not event.get("operation_id"):
            continue
        receipt = receipts[event["operation_id"]]
        reference = event["raw_file"].replace("\\", "/"), event["raw_line"]
        assert reference[0] == f"raw/{event['node']}.ndjson" and reference not in seen
        seen.add(reference)
        payload = json.loads(raw[event["node"]][event["raw_line"] - 1])
        original_time = payload["time"]
        payload = payload["process_kprobe"]
        assert payload["function_name"] in ("tcp_connect", "tcp_sendmsg")
        assert payload["process"]["pod"]["uid"] == manifest["actor"]["uid"] == event["pod_uid"]
        sock = next(a["sock_arg"] for a in payload["args"] if "sock_arg" in a)
        ip = ipaddress.ip_address(sock["daddr"])
        destination = str(ip.ipv4_mapped) if getattr(ip, "ipv4_mapped", None) else str(ip)
        assert destination in receipt["target_ips"] and sock["dport"] == receipt["port"] == 50051
        assert timestamp(receipt["started"]) <= timestamp(original_time) <= timestamp(receipt["ended"])
        assert receipt["method"] == "/hipstershop.PaymentService/Charge" and receipt["grpc_code"] == "OK"
        linked[event["operation_id"]] += 1
    assert set(linked) == set(receipts)
    return {"operations": len(linked), "native_records": sum(linked.values())}


def check_metrics(run):
    snapshots = {}
    ready = True
    for stage in ("before", "after"):
        path = run / f"metrics-{stage}.json"
        if not path.exists():
            return {"available": False, "passed": None, "reason": "No complete before/after Prometheus snapshot pair"}
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        up = snapshot.get("agent_up", {}).get("data", {}).get("result", [])
        counters = snapshot.get("loss_and_export", {}).get("data", {}).get("result", [])
        ready = ready and len(up) == 2 and all(float(row["value"][1]) == 1 for row in up)
        ready = ready and len(counters) == 8
        snapshots[stage] = {(row["metric"]["__name__"], row["metric"]["node"]): float(row["value"][1])
                            for row in counters}
    before, after = snapshots["before"], snapshots["after"]
    deltas = {name + "@" + node: after.get((name, node), -1) - value for (name, node), value in before.items()}
    valid = ready and before.keys() == after.keys() and len(deltas) == 8 and all(v == 0 for v in deltas.values())
    return {"available": True, "passed": bool(valid), "counter_deltas": deltas,
            "meaning": "Two scrape snapshots and eight observed counter series; not proof of zero loss at every layer"}


def review(run):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    result = {"run_id": run.name, "scenario": manifest["scenario_id"], "mode": manifest["mode"],
              "status": manifest["status"], "dataset_status": manifest.get("dataset_status")}
    if manifest["status"] != "completed" or manifest.get("dataset_status") == "failed_validation":
        return dict(result, disposition="excluded_incomplete_or_failed", included=False)
    if manifest["mode"] != "pilot":
        return dict(result, disposition="excluded_non_pilot", included=False)
    if manifest["scenario_id"] == "S3" and manifest.get("s3", {}).get("profile") != "runtime":
        return dict(result, disposition="excluded_legacy_file_smoke", included=False)
    result["included"] = True
    try:
        with tempfile.TemporaryDirectory(prefix="gd4-audit-") as directory:
            temporary = Path(directory)
            unpack_copy(run, temporary)
            available = bool(manifest.get("source_snapshot"))
            count = 0
            if available:
                for name, digest in manifest["script_sha256"].items():
                    assert hashlib.sha256((temporary / "source" / name).read_bytes()).hexdigest() == digest, name
                    count += 1
            result["source_snapshot_available"] = available
            result["source_hashes_verified"] = count
            result["limitations"] = [] if available else ["Historical source snapshot absent; recorded source hashes cannot be independently reconstructed from this archive."]
            result["metrics"] = check_metrics(temporary)
            if not result["metrics"]["available"]:
                result["limitations"].append("Prometheus before/after loss-counter evidence is unavailable for this historical run.")
            quality = json.loads((temporary / "quality.json").read_text(encoding="utf-8"))
            normalized = [json.loads(x) for x in (temporary / "normalized.ndjson").read_text(encoding="utf-8").splitlines()]
            assert len(normalized) == sum(quality["events_by_type"].values())
            result["events"] = len(normalized)
            result["label_versions"] = dict(Counter(e["label_version"] for e in normalized))
            if manifest["scenario_id"] == "S1":
                proof = verify_s1(temporary)
            elif manifest["scenario_id"] == "S2":
                proof = verify_run(temporary)
                result["native_rpc_evidence"] = check_rpc_native(temporary, manifest)
                if available:
                    result["identity_and_matrix_audit"] = audit_s2(temporary)
            else:
                proof = verify_s3(temporary)
            result["verification"] = proof
            result["passed"] = proof["passed"] and result["metrics"]["passed"] is not False
            result["disposition"] = "functional_pilot_verified" if result["passed"] else "audit_failed"
    except Exception as error:
        result.update(passed=False, disposition="audit_failed", error=f"{type(error).__name__}: {error}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", type=Path, help="Optional individual run directories")
    parser.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parents[1] / "runs")
    parser.add_argument("--output", type=Path, required=True, help="Write a new report outside historical run directories")
    args = parser.parse_args()
    paths = args.runs or sorted(p for p in args.runs_root.iterdir()
                               if p.is_dir() and (p / "manifest.json").exists()
                               and p.name.startswith(("s1-", "s2-", "s3-")))
    results = [review(p) for p in paths]
    included = [r for r in results if r["included"]]
    sources = ("audit_scenarios.py", "s1_verify.py", "s2_verify.py", "s2_audit.py", "s3_verify.py", "label.py")
    report = {"scope": "GĐ4 functional pilot audit; historical datasets are not modified",
              "checked_at": datetime.now(timezone.utc).isoformat(),
              "clock_source": "analysis host UTC; per-run event timestamps retain the original lab clocks",
              "audit_source_sha256": {name: hashlib.sha256((Path(__file__).resolve().parent / name).read_bytes()).hexdigest()
                                      for name in sources},
              "runs": results, "pilots_reviewed": len(included),
              "pilots_passed": sum(r.get("passed", False) for r in included),
              "passed": bool(included) and all(r["passed"] for r in included)}
    if any(args.output.resolve().is_relative_to(p.resolve()) for p in paths):
        parser.error("Choose an output path outside the historical run directories")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}, ensure_ascii=False, indent=2))
    for result in results:
        print(result["run_id"], result["disposition"], result.get("error", ""))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
