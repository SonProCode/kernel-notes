"""Schema v3 and evidence-based labels for GĐ4 pilot runs."""
from collections import Counter
import ipaddress
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "telemetry"))
from normalize import timestamp, event_fields, agent_states


def ip(value):
    address = ipaddress.ip_address(value)
    return str(address.ipv4_mapped) if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else str(address)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(run):
    manifest = json.loads((run / "manifest.json").read_text())
    actor = manifest.get("actor", {})
    receipts = [json.loads(line) for line in (run / "actor-receipts.ndjson").read_text().splitlines() if line]
    phases = [json.loads(line) for line in (run / "timeline.ndjson").read_text().splitlines()]
    counts, labels, quality, nodes, coverage = Counter(), Counter(), Counter(), Counter(), Counter()
    windows = {}
    index = {}
    for receipt in receipts:
        if receipt["kind"] == "grpc_call":
            keys = [(ip(address), receipt["port"]) for address in receipt["target_ips"]]
        elif receipt["kind"] == "tcp_connect":
            keys = [(ip(receipt["ip"]), receipt["port"])]
        else:
            keys = [receipt["path"]]
        for key in keys:
            index.setdefault(key, []).append(receipt)
    with (run / "normalized.ndjson").open("w", encoding="utf-8") as out:
        for node in ("lab-w1", "lab-w2"):
            path = run / "raw" / f"{node}.ndjson"
            for number, line in enumerate(path.open(encoding="utf-8"), 1):
                try:
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise ValueError("Expected JSON object")
                    when = timestamp(raw.get("time"))
                except (ValueError, TypeError):
                    quality["invalid_record"] += 1
                    continue
                candidates = [p for p in phases if timestamp(p["time"]) <= when]
                phase = candidates[-1]["phase"] if candidates else "setup"
                if manifest.get("measurement_end") and when >= timestamp(manifest["measurement_end"]):
                    phase = "finalize"

                info = event_fields(raw)
                if not info:
                    payload = raw.get("process_kprobe", {})
                    if payload.get("policy_name") != "boutique-file-read":
                        quality["unselected_event"] += 1
                        continue
                    process = payload.get("process") or {}
                    pod = process.get("pod") or {}
                    if pod.get("namespace") != "boutique":
                        continue
                    kind = "file_read_permission"
                else:
                    kind, payload, process, pod = info
                sock = next((a["sock_arg"] for a in payload.get("args", []) if "sock_arg" in a), None)
                file_arg = next((a["file_arg"] for a in payload.get("args", []) if "file_arg" in a), {})
                file_path = file_arg.get("path")
                lookup = (ip(sock["daddr"]), sock["dport"]) if sock else file_path
                operation = next((r for r in index.get(lookup, [])
                                  if timestamp(r["started"]) <= when <= timestamp(r["ended"])), None)
                is_actor = pod.get("uid") == actor.get("uid")
                label, evidence = "unknown", None
                if phase in ("pre_attack", "recovery") and not is_actor:
                    label, evidence = "normal", "background_outside_action"
                if manifest["scenario_id"] == "S0" and phase == "measurement":
                    label, evidence = "normal", "normal_run"
                if is_actor and operation and (
                    (kind == "tcp_connect_attempt" and operation["kind"] == "tcp_connect")
                    or (kind == "file_read_permission" and operation["kind"] == "file_read")
                    or (kind in ("tcp_connect_attempt", "tcp_send") and operation["kind"] == "grpc_call")
                ):
                    label = "attack" if manifest["mode"] != "smoke" else "unknown"
                    evidence = ("actor_uid_rpc_time_target" if operation["kind"] == "grpc_call"
                                else "actor_uid_operation_time_target")
                    coverage[operation["operation_id"]] += 1
                labels[label] += 1
                counts[kind] += 1
                nodes[node] += 1
                record = {
                    "schema_version": 3, "run_id": manifest["run_id"],
                    "scenario_id": manifest["scenario_id"], "phase": phase,
                    "timestamp": raw["time"], "event_type": kind, "node": node,
                    "namespace": pod.get("namespace"), "pod": pod.get("name"),
                    "pod_uid": pod.get("uid"), "workload": pod.get("workload"),
                    "container_id": (pod.get("container") or {}).get("id"),
                    "binary": process.get("binary"), "pid": process.get("pid"),
                    "exec_id": process.get("exec_id"),
                    "parent_exec_id": (payload.get("parent") or {}).get("exec_id"),
                    "socket": sock, "file_path": file_path,
                    "kernel_return": payload.get("return"),
                    "label": label, "evidence": evidence, "label_version": "v3",
                    "operation_id": operation["operation_id"] if is_actor and operation else None,
                    "raw_file": path.relative_to(run).as_posix(), "raw_line": number,
                    "api_method_from_receipt": operation.get("method") if is_actor and operation else None,
                    "grpc_code_from_receipt": operation.get("grpc_code") if is_actor and operation else None,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                offset = int((when - timestamp(manifest["capture_start"])).total_seconds() // 10)
                key = (pod.get("uid"), offset)
                window = windows.setdefault(key, {"pod_uid": pod.get("uid"), "window_index": offset,
                                                  "normal": 0, "attack": 0, "unknown": 0})
                window[label] += 1
    with (run / "labeled-windows.ndjson").open("w", encoding="utf-8") as out:
        for window in windows.values():
            window["label"] = "attack" if window["attack"] else "unknown" if window["unknown"] else "normal"
            out.write(json.dumps(window) + "\n")
    before = agent_states(run / "agents-before.json")
    after = agent_states(run / "agents-after.json")
    stable = all(node in before and before[node] == after.get(node) for node in ("lab-w1", "lab-w2"))
    errors = {node: (run / "raw" / f"{node}.stderr").read_text()
              for node in ("lab-w1", "lab-w2")}
    summary = {"events_by_type": counts, "events_by_label": labels,
               "events_by_node": nodes, "quality": quality,
               "agent_state_unchanged": stable, "collector_stderr": errors,
               "operations": len(receipts), "operations_with_matched_event": len(coverage),
               "unmatched_operations": [r["operation_id"] for r in receipts if r["operation_id"] not in coverage]}
    summary["api_successes"] = sum(r.get("outcome") == "api_success" for r in receipts)
    summary["grpc_status_counts"] = dict(Counter(r["grpc_code"] for r in receipts if "grpc_code" in r))
    metrics = {}
    for stage in ("before", "after"):
        metric_path = run / f"metrics-{stage}.json"
        metrics[stage] = json.loads(metric_path.read_text()) if metric_path.exists() else None
    summary["prometheus_snapshots_present"] = all(metrics.values())
    # Missing counters and query errors remain visible in the raw responses.
    summary["capture_checks_passed"] = bool(nodes["lab-w1"] and nodes["lab-w2"] and stable
                                           and not any(errors.values()) and not quality["invalid_record"])
    write_json(run / "quality.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
