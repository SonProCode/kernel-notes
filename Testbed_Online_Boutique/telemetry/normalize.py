"""Convert Tetragon stdout JSON to the Boutique baseline schema."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import re
from pathlib import Path


NODES = ("lab-w1", "lab-w2")
TCP_EVENTS = {"tcp_connect": "tcp_connect_attempt", "tcp_sendmsg": "tcp_send"}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing event timestamp")
    # Ubuntu's Python 3.10 accepts six fractional digits, while Tetragon emits up to nine.
    compatible = re.sub(r"\.(\d+)(?=Z|[+-]\d{2}:\d{2}$)", lambda match: "." + match[1][:6].ljust(6, "0"), value)
    result = datetime.fromisoformat(compatible.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Missing timestamp offset")
    return result.astimezone(timezone.utc)


def event_fields(raw):
    for key in ("process_exec", "process_exit", "process_kprobe"):
        payload = raw.get(key)
        if not isinstance(payload, dict):
            continue
        if key == "process_kprobe" and (
            payload.get("function_name") not in TCP_EVENTS
            or payload.get("policy_name") != "boutique-tcp-connect"
        ):
            continue
        process = payload.get("process") or {}
        pod = process.get("pod") or {}
        if pod.get("namespace") == "boutique":
            kind = TCP_EVENTS[payload["function_name"]] if key == "process_kprobe" else key
            return kind, payload, process, pod
    return None


def read_json_lines(path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
                yield record if isinstance(record, dict) else None
            except json.JSONDecodeError:
                yield None


def smoke(path, pod_name):
    found = set()
    for raw in read_json_lines(path):
        info = event_fields(raw) if raw else None
        if info and info[3].get("name") == pod_name:
            found.add(info[0])
    return {"process_exec", *TCP_EVENTS.values()}.issubset(found)


def agent_states(path):
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    return {
        pod["spec"]["nodeName"]: (
            pod["metadata"]["uid"],
            {item["name"]: item["restartCount"]
             for item in pod["status"].get("containerStatuses", [])},
        )
        for pod in snapshot["items"]
        if pod["status"].get("phase") == "Running"
    }


def normalize(run):
    start = timestamp((run / "measure-start.txt").read_text().strip())
    end = timestamp((run / "measure-end.txt").read_text().strip())
    if end <= start:
        raise ValueError("Measurement end must be later than start")
    events, workloads, agents, quality = Counter(), Counter(), Counter(), Counter()
    tcp_by_node = {event: Counter() for event in TCP_EVENTS.values()}
    with (run / "telemetry.ndjson").open("w", encoding="utf-8") as target:
        for node in NODES:
            for raw in read_json_lines(run / "raw" / f"{node}.ndjson"):
                if raw is None:
                    quality["invalid_json"] += 1
                    continue
                try:
                    when = timestamp(raw.get("time"))
                except ValueError:
                    quality["invalid_timestamp"] += 1
                    continue
                if not start <= when < end:
                    quality["outside_window"] += 1
                    continue
                info = event_fields(raw)
                if not info:
                    quality["other_event"] += 1
                    continue
                kind, payload, process, pod = info
                socket = None
                bytes_requested = None
                if kind in tcp_by_node:
                    tcp_by_node[kind][node] += 1
                    args = payload.get("args", [])
                    sock = next((arg["sock_arg"] for arg in args
                                 if isinstance(arg.get("sock_arg"), dict)), {})
                    socket = {
                        "src_ip": sock.get("saddr"),
                        "src_port": sock.get("sport"),
                        "dst_ip": sock.get("daddr"),
                        "dst_port": sock.get("dport"),
                    }
                    if not socket["dst_ip"] or not socket["dst_port"]:
                        quality["tcp_missing_destination"] += 1
                    if kind == "tcp_send":
                        bytes_requested = next((arg["int_arg"] for arg in args if "int_arg" in arg), None)
                        if bytes_requested is None:
                            quality["tcp_send_missing_bytes"] += 1
                record = {
                    "schema_version": 2,
                    "timestamp": raw["time"],
                    "source": "tetragon",
                    "scenario": "S0",
                    "run_id": run.name,
                    "event_type": kind,
                    "node": node,
                    "namespace": pod["namespace"],
                    "workload": pod.get("workload"),
                    "pod": pod.get("name"),
                    "pod_uid": pod.get("uid"),
                    "container": (pod.get("container") or {}).get("name"),
                    "binary": process.get("binary"),
                    "exec_id": process.get("exec_id"),
                    "policy": payload.get("policy_name"),
                    "socket": socket,
                    "bytes_requested": bytes_requested,
                }
                target.write(json.dumps(record, ensure_ascii=False) + "\n")
                events[kind] += 1
                agents[node] += 1
                workloads[pod.get("workload") or "unknown"] += 1
    before = agent_states(run / "agents-before.json")
    after = agent_states(run / "agents-after.json")
    same_agents = all(node in before and before[node] == after.get(node) for node in NODES)
    no_capture_errors = all((run / "raw" / f"{node}.stderr").stat().st_size == 0 for node in NODES)
    complete = (all(tcp_by_node["tcp_send"][node] for node in NODES) and same_agents
                and no_capture_errors and not quality["invalid_json"]
                and not quality["invalid_timestamp"])
    with (run / "summary.json").open("w", encoding="utf-8") as output:
        json.dump({
            "run_id": run.name,
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "total_events": sum(events.values()),
            "events_by_type": events,
            "events_by_node": {node: agents[node] for node in NODES},
            "tcp_connect_attempts_by_node": {node: tcp_by_node["tcp_connect_attempt"][node] for node in NODES},
            "tcp_sends_by_node": {node: tcp_by_node["tcp_send"][node] for node in NODES},
            "events_by_workload": workloads,
            "quality_counts": quality,
            "agent_uids_and_restart_counts_unchanged": same_agents,
            "capture_stderr_empty": no_capture_errors,
            "basic_capture_checks_passed": complete,
        }, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return complete


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="?")
    parser.add_argument("--smoke", nargs=2, metavar=("LOG", "POD"))
    args = parser.parse_args()
    if args.smoke:
        raise SystemExit(0 if smoke(Path(args.smoke[0]), args.smoke[1]) else 1)
    if args.run is None:
        parser.error("provide a run directory")
    raise SystemExit(0 if normalize(args.run) else 1)
