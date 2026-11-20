"""Independently audit S2 identity, source snapshots and raw Tetragon evidence."""
import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import tarfile

from label import timestamp, write_json


def audit(run):
    manifest = json.loads((run / "manifest.json").read_text())
    topology = json.loads((run / "boutique-before.json").read_text())
    actor = next(item for item in topology["items"]
                 if item["kind"] == "Pod" and item["metadata"]["uid"] == manifest["actor"]["uid"])
    checkout = next(item for item in topology["items"]
                    if item["kind"] == "Pod" and item["metadata"]["name"].startswith("checkoutservice-"))
    assert manifest["scenario_id"] == "S2" and manifest["status"] == "completed"
    assert actor["spec"]["serviceAccountName"] != checkout["spec"]["serviceAccountName"]
    assert actor["spec"]["automountServiceAccountToken"] is False
    assert actor["metadata"]["labels"]["experiment-run"] == manifest["run_id"]
    receipts = {r["operation_id"]: r for line in (run / "actor-receipts.ndjson").read_text().splitlines()
                if (r := json.loads(line))}
    proof = json.loads((run / "s2-verification.json").read_text())
    assert proof["passed"]
    linked = Counter()
    with ExitStack() as stack:
        archive = stack.enter_context(tarfile.open(run / "dataset.tar.gz")) if (run / "dataset.tar.gz").exists() else None

        def read(name):
            if archive is None:
                return (run / name).read_bytes()
            return archive.extractfile(name).read()

        for relative, digest in manifest["script_sha256"].items():
            assert hashlib.sha256(read("source/" + relative)).hexdigest() == digest, relative
        matrix = csv.DictReader(io.StringIO(read("source/expected-communications.csv").decode("utf-8")))
        allowed = {row["source"] for row in matrix if row["destination"] == "paymentservice"}
        assert allowed == {"checkoutservice"}, allowed
        raw = {node: read(f"raw/{node}.ndjson").splitlines() for node in ("lab-w1", "lab-w2")}
        for line in read("normalized.ndjson").splitlines():
            event = json.loads(line)
            if event["label"] != "attack":
                continue
            receipt = receipts[event["operation_id"]]
            original = json.loads(raw[event["node"]][event["raw_line"] - 1])
            payload = original["process_kprobe"]
            assert payload["process"]["pod"]["uid"] == actor["metadata"]["uid"] == event["pod_uid"]
            assert payload["function_name"] in ("tcp_connect", "tcp_sendmsg")
            socket = next(arg["sock_arg"] for arg in payload["args"] if "sock_arg" in arg)
            address = ipaddress.ip_address(socket["daddr"])
            destination = str(address.ipv4_mapped) if getattr(address, "ipv4_mapped", None) else str(address)
            assert destination in receipt["target_ips"] and socket["dport"] == 50051
            assert timestamp(receipt["started"]) <= timestamp(original["time"]) <= timestamp(receipt["ended"])
            assert receipt["method"] == "/hipstershop.PaymentService/Charge"
            assert receipt["grpc_code"] == "OK"
            linked[receipt["operation_id"]] += 1
    assert set(linked) == set(receipts)
    result = {
        "run_id": manifest["run_id"], "mode": manifest["mode"],
        "actor_service_account": actor["spec"]["serviceAccountName"],
        "legitimate_service_account": checkout["spec"]["serviceAccountName"],
        "expected_callers_in_captured_matrix": sorted(allowed),
        "source_hashes_verified": len(manifest["script_sha256"]),
        "raw_network_events_verified": sum(linked.values()),
        "rpc_operations_verified": len(linked),
        "warmup_seconds": manifest["warmup_seconds"], "pre_seconds": manifest["pre_seconds"],
        "recovery_seconds": manifest["recovery_seconds"],
        "functional_pilot_checks_passed": True,
        "research_scope": "S2 GĐ4 pilot; detector and mitigation effectiveness are assessed in later phases",
    }
    write_json(run / "s2-audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.run), ensure_ascii=False, indent=2))
