"""Verify every S1 TCP attempt against receipts and native Tetragon records."""
import argparse
from collections import Counter
import ipaddress
import json
from pathlib import Path

from label import timestamp, write_json


def address(value):
    value = ipaddress.ip_address(value)
    return str(value.ipv4_mapped) if getattr(value, "ipv4_mapped", None) else str(value)


def verify_s1(run):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest["scenario_id"] != "S1":
        raise ValueError("Expected an S1 run")
    receipts = [json.loads(x) for x in (run / "actor-receipts.ndjson").read_text(encoding="utf-8").splitlines() if x]
    targets = manifest["targets"]
    expected = {f"connect-{i:04d}" for i in range(len(targets))}
    by_id = {r["operation_id"]: r for r in receipts}
    receipt_valid = len(by_id) == len(receipts) == len(targets) and set(by_id) == expected and 0 < len(targets) <= 40
    for index, target in enumerate(targets):
        receipt = by_id.get(f"connect-{index:04d}", {})
        receipt_valid = receipt_valid and all(receipt.get(k) == target[k] for k in ("service", "ip", "port"))
        receipt_valid = receipt_valid and receipt.get("kind") == "tcp_connect"
        receipt_valid = receipt_valid and ipaddress.ip_address(target["ip"]) in ipaddress.ip_network("10.43.0.0/16")
        outcome = receipt.get("outcome", "")
        receipt_valid = receipt_valid and (outcome in ("connected", "timeout") or outcome.startswith("os_error_"))
    references = {}
    for line in (run / "normalized.ndjson").open(encoding="utf-8"):
        event = json.loads(line)
        if event.get("operation_id") and event["event_type"] == "tcp_connect_attempt":
            relative = event["raw_file"].replace("\\", "/")
            if relative not in ("raw/lab-w1.ndjson", "raw/lab-w2.ndjson"):
                raise ValueError("Unexpected raw reference")
            key = relative, event["raw_line"]
            if key in references:
                raise ValueError("Duplicate native-record reference")
            references[key] = event
    linked = Counter()
    native_valid = True
    verified = 0
    for node in ("lab-w1", "lab-w2"):
        relative = f"raw/{node}.ndjson"
        for number, line in enumerate((run / relative).open(encoding="utf-8"), 1):
            event = references.get((relative, number))
            if event is None:
                continue
            original = json.loads(line)
            payload = original.get("process_kprobe", {})
            process = payload.get("process", {})
            sock = next((a["sock_arg"] for a in payload.get("args", []) if "sock_arg" in a), {})
            receipt = by_id.get(event["operation_id"])
            valid = bool(receipt and payload.get("function_name") == "tcp_connect"
                         and (process.get("pod") or {}).get("uid") == manifest["actor"]["uid"] == event["pod_uid"]
                         and (process.get("pod") or {}).get("namespace") == "boutique"
                         and sock.get("daddr") and address(sock["daddr"]) == receipt["ip"]
                         and sock.get("dport") == receipt["port"]
                         and timestamp(receipt["started"]) <= timestamp(original["time"]) <= timestamp(receipt["ended"]))
            native_valid = native_valid and valid
            if valid:
                linked[event["operation_id"]] += 1
            verified += 1
    quality = json.loads((run / "quality.json").read_text(encoding="utf-8"))
    result = {
        "expected_operations": len(targets), "receipts": len(receipts),
        "operations_with_native_event": len(linked), "native_records_verified": verified,
        "receipt_targets_valid": bool(receipt_valid), "native_records_valid": native_valid and verified == len(references),
        "unmatched_operations": sorted(expected - set(linked)),
        "outcomes": dict(Counter(r["outcome"] for r in receipts)),
        "capture_checks_passed": quality["capture_checks_passed"],
        "meaning": "Coverage of executed TCP attempts; not detector recall or proof of application requests",
    }
    result["passed"] = bool(receipt_valid and result["native_records_valid"] and set(linked) == expected
                            and quality["capture_checks_passed"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, help="Optional report; raw data and historical manifest are unchanged")
    args = parser.parse_args()
    result = verify_s1(args.run)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
