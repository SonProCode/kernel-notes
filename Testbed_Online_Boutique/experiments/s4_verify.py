"""Verify S4 request/native coverage and summarize measured latency by phase."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path

from label import timestamp, write_json


def extract_locust(run):
    metadata, final, records = [], [], []
    for line in (run / "locust.raw.log").read_text(encoding="utf-8").splitlines():
        for prefix, destination in (("S4REQ ", records), ("S4META ", metadata), ("S4FINAL ", final)):
            if line.startswith(prefix):
                destination.append(json.loads(line[len(prefix):]))
                break
    with (run / "locust-requests.ndjson").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")
    write_json(run / "locust-runtime.json", {"metadata": metadata, "final": final})


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)] if values else None


def summarize(records):
    good = [r["duration_ms"] for r in records if r.get("error") is None and r.get("status_code") == 200]
    failures = len(records) - len(good)
    return {"requests": len(records), "failures": failures, "failure_ratio": failures / len(records) if records else None,
            "latency_sample_count": len(good), "p50_ms": percentile(good, 0.50), "p95_ms": percentile(good, 0.95),
            "max_ms": max(good) if good else None, "latency_population": "HTTP 200 and no client exception; nearest-rank percentile"}


def phase_of(moment, timeline, measurement_end):
    if moment >= measurement_end:
        return "finalize"
    return next((item["phase"] for item in reversed(timeline) if timestamp(item["time"]) <= moment), "setup")


def verify_s4(run):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    receipts = rows(run / "actor-receipts.ndjson")
    locust = rows(run / "locust-requests.ndjson")
    runtime = json.loads((run / "locust-runtime.json").read_text(encoding="utf-8"))
    timeline = rows(run / "timeline.ndjson")
    end = timestamp(manifest["measurement_end"])
    phases, by_path = {}, {}
    for record in locust:
        begin_phase = phase_of(timestamp(record["started"]), timeline, end)
        end_phase = phase_of(timestamp(record["ended"]), timeline, end)
        phase = begin_phase if begin_phase == end_phase else "boundary"
        phases.setdefault(phase, []).append(record)
        by_path.setdefault((phase, record["method"], record["path"]), []).append(record)
    phase_summary = {name: summarize(items) for name, items in phases.items()}
    for i, item in enumerate(timeline):
        phase = item["phase"]
        if phase in phase_summary:
            stop = timestamp(timeline[i + 1]["time"]) if i + 1 < len(timeline) else end
            seconds = max(0, (min(stop, end) - timestamp(item["time"])).total_seconds())
            phase_summary[phase]["phase_seconds"] = seconds
            phase_summary[phase]["achieved_rps"] = phase_summary[phase]["requests"] / seconds if seconds else None
    normalized = rows(run / "normalized.ndjson")
    references = {}
    matched = Counter()
    for event in normalized:
        if event.get("operation_id"):
            references[(event["raw_file"], event["raw_line"])] = event
    receipt_map = {r["operation_id"]: r for r in receipts}
    native_verified = 0
    for node in ("lab-w1", "lab-w2"):
        relative = f"raw/{node}.ndjson"
        for number, line in enumerate((run / relative).open(encoding="utf-8"), 1):
            event = references.get((relative, number))
            if event is None:
                continue
            original = json.loads(line)
            payload = original["process_kprobe"]
            receipt = receipt_map[event["operation_id"]]
            assert payload["function_name"] in ("tcp_connect", "tcp_sendmsg")
            assert payload["process"]["pod"]["uid"] == manifest["actor"]["uid"] == event["pod_uid"]
            sock = next(a["sock_arg"] for a in payload["args"] if "sock_arg" in a)
            address = ipaddress.ip_address(sock["daddr"])
            address = str(address.ipv4_mapped) if getattr(address, "ipv4_mapped", None) else str(address)
            assert address in receipt["target_ips"] and sock["dport"] in receipt["target_ports"]
            assert sock["sport"] == receipt["source_port"]
            assert timestamp(receipt["started"]) <= timestamp(original["time"]) <= timestamp(receipt["ended"])
            matched[receipt["operation_id"]] += 1
            native_verified += 1
    count = len(locust)
    log_complete = (len(runtime["metadata"]) == len(runtime["final"]) == 1
                    and [r["sequence"] for r in locust] == list(range(1, count + 1))
                    and runtime["final"][0]["recorded_requests"] == runtime["final"][0]["locust_num_requests"] == count)
    quality = json.loads((run / "quality.json").read_text())
    metrics = {}
    metric_ok = True
    for stage in ("before", "after"):
        snapshot = json.loads((run / f"metrics-{stage}.json").read_text())
        up = snapshot.get("agent_up", {}).get("data", {}).get("result", [])
        counters = snapshot.get("loss_and_export", {}).get("data", {}).get("result", [])
        metric_ok = metric_ok and len(up) == 2 and all(float(r["value"][1]) == 1 for r in up) and len(counters) == 8
        metrics[stage] = {(r["metric"]["__name__"], r["metric"]["node"]): float(r["value"][1]) for r in counters}
    deltas = {name + "@" + node: metrics["after"].get((name, node), -1) - value for (name, node), value in metrics["before"].items()}
    metric_ok = metric_ok and len(deltas) == 8 and all(v == 0 for v in deltas.values())
    guards = rows(run / "guard.ndjson")
    target_phase = "measurement" if manifest["s4"]["profile"] == "control" else "attack"
    latency_complete = all(phase_summary.get(name, {}).get("requests", 0) > 0 for name in ("pre_attack", target_phase, "recovery"))
    resources = json.loads((run / "prometheus-resources.json").read_text())
    resource_ok = all(value.get("status") == "success" and value.get("data", {}).get("result")
                      and any(row.get("values") for row in value["data"]["result"]) for value in resources.values()) and len(resources) == 4
    resource_summary = {}
    for name, value in resources.items():
        per_phase = {}
        for row in value.get("data", {}).get("result", []):
            for epoch, amount in row.get("values", []):
                amount = float(amount)
                if math.isfinite(amount):
                    phase = phase_of(datetime.fromtimestamp(float(epoch), timezone.utc), timeline, end)
                    per_phase.setdefault(phase, []).append(amount)
        resource_summary[name] = {phase: {"samples": len(samples), "mean": sum(samples) / len(samples), "max": max(samples)}
                                  for phase, samples in per_phase.items()}
    client, requests_valid = None, not receipts
    if target_phase == "attack":
        client = json.loads((run / "s4-client-summary.json").read_text())
        requests_valid = (len(receipts) > 0 and len(receipt_map) == len(receipts) == client["submitted"]
                          and client["scheduled"] == manifest["s4"]["rate"] * manifest["s4"]["duration_seconds"]
                          and client["submitted"] + client["skipped_busy"] + client["skipped_late"] == client["scheduled"]
                          and not client["interrupted"] and set(matched) == set(receipt_map))
        transitions = sorted([(timestamp(r["started"]), 1) for r in receipts] + [(timestamp(r["ended"]), -1) for r in receipts])
        active, peak = 0, 0
        for _, delta in transitions:
            active += delta; peak = max(peak, active)
        requests_valid = requests_valid and peak <= manifest["s4"]["concurrency"]
        client["observed_peak_concurrency"] = peak
        client["achieved_rps_over_configured_window"] = len(receipts) / manifest["s4"]["duration_seconds"]
        client["http_summary"] = summarize(receipts)
    result = {"passed": False, "profile": manifest["s4"]["profile"], "configured_rate": manifest["s4"]["rate"],
              "http_operations": len(receipts), "operations_with_native_event": len(matched), "native_records_verified": native_verified,
              "request_checks_passed": bool(requests_valid), "locust_log_complete": log_complete, "locust_requests": count,
              "locust_phase_samples_present": latency_complete, "locust_by_phase": phase_summary,
              "locust_by_route": [{"phase": p, "method": m, "path": path, **summarize(items)} for (p, m, path), items in by_path.items()],
              "client": client, "guard_samples": len(guards), "guard_checks_passed": bool(guards) and all(not g["reasons"] for g in guards),
              "metric_checks_passed": bool(metric_ok), "loss_counter_deltas": deltas,
              "resource_series_present": bool(resource_ok), "resources_by_phase": resource_summary,
              "capture_checks_passed": quality["capture_checks_passed"], "locust_capture_stderr_empty": not (run / "locust.stderr").read_text().strip(),
              "cleanup_errors": manifest.get("cleanup_errors", []), "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "Functional bounded-load pilot and observed impact; no detector or rate-limiting effectiveness claim"}
    result["passed"] = bool(requests_valid and log_complete and latency_complete and metric_ok and resource_ok
                            and result["guard_checks_passed"] and quality["capture_checks_passed"]
                            and result["locust_capture_stderr_empty"] and not result["cleanup_errors"])
    write_json(run / "s4-verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    result = verify_s4(args.run)
    print(json.dumps({k: v for k, v in result.items() if k not in ("locust_by_route", "resources_by_phase")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
