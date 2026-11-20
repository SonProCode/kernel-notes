"""Verify S2 receipts and correlate them with mock PaymentService handler logs."""
import argparse
import hashlib
from datetime import timedelta
import json
from pathlib import Path
import uuid

from label import timestamp, write_json


PREFIX = "PaymentService#Charge invoked with request "


def fingerprint(request):
    amount, card = request["amount"], request["credit_card"]
    return (amount["currency_code"], int(amount["units"]), int(amount["nanos"]),
            card["credit_card_number"], int(card["credit_card_cvv"]),
            int(card["credit_card_expiration_year"]), int(card["credit_card_expiration_month"]))


def verify_run(run):
    manifest = json.loads((run / "manifest.json").read_text())
    if manifest["scenario_id"] != "S2":
        raise ValueError("Expected S2 manifest")
    receipts = [json.loads(line) for line in (run / "actor-receipts.ndjson").read_text().splitlines() if line]
    fixture_path = run / "source/s2/fixture.json"
    if not fixture_path.exists():
        fixture_path = Path(__file__).resolve().parent / "s2/fixture.json"
    fixture = json.loads(fixture_path.read_text())
    server = []
    for number, line in enumerate((run / "paymentservice.log").read_text().splitlines(), 1):
        time_part, _, body = line.partition(" ")
        try:
            record = json.loads(body)
            message = record.get("message", "")
            if not message.startswith(PREFIX):
                continue
            request = json.loads(message[len(PREFIX):])
            server.append({"line": number, "time": time_part,
                           "fingerprint": fingerprint(request)})
        except (ValueError, KeyError, TypeError):
            continue
    matches = []
    valid_api = 0
    transaction_ids = set()
    for receipt in receipts:
        if receipt.get("grpc_code") == "OK" and receipt.get("outcome") == "api_success":
            transaction_ids.add(str(uuid.UUID(receipt["transaction_id"])))
            valid_api += 1
        request = {"amount": receipt["amount"], "credit_card": fixture["credit_card"]}
        expected = fingerprint(request)
        # Cross-node clocks and log emission can differ. Record the tolerance explicitly.
        low = timestamp(receipt["started"]) - timedelta(seconds=2)
        high = timestamp(receipt["ended"]) + timedelta(seconds=2)
        candidates = [entry for entry in server
                      if entry["fingerprint"] == expected and low <= timestamp(entry["time"]) <= high]
        matches.append({"operation_id": receipt["operation_id"],
                        "method": receipt["method"],
                        "grpc_code": receipt["grpc_code"],
                        "transaction_id": receipt.get("transaction_id"),
                        "server_log": "paymentservice.log",
                        "server_log_lines": [entry["line"] for entry in candidates],
                        "server_times": [entry["time"] for entry in candidates],
                        "evidence": "synthetic_payload_and_time",
                        "clock_tolerance_seconds": 2})
    with (run / "server-matches.ndjson").open("w", encoding="utf-8") as output:
        for match in matches:
            output.write(json.dumps(match) + "\n")
    quality = json.loads((run / "quality.json").read_text())
    expected_calls = manifest["s2"]["calls"]
    result = {
        "expected_calls": expected_calls, "receipts": len(receipts),
        "api_successes": valid_api, "unique_transaction_ids": len(transaction_ids),
        "rpc_operations_with_network_event": quality["operations_with_matched_event"],
        "uniquely_correlated_server_calls": sum(len(m["server_log_lines"]) == 1 for m in matches),
        "uncorrelated_operations": [m["operation_id"] for m in matches if not m["server_log_lines"]],
        "ambiguous_operations": [m["operation_id"] for m in matches if len(m["server_log_lines"]) > 1],
        "clock_tolerance_seconds": 2,
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    result["passed"] = (
        len(receipts) == valid_api == len(transaction_ids) == expected_calls
        and quality["capture_checks_passed"]
        and quality["operations_with_matched_event"] == expected_calls
        and result["uniquely_correlated_server_calls"] == expected_calls
    )
    write_json(run / "s2-verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    result = verify_run(args.run)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
