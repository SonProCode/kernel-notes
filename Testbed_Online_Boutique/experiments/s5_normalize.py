"""S5 schema v6: raw socket identity, synthetic receipts and independent labels."""
from collections import Counter
import json

from label import agent_states, event_fields, ip, text_lines, timestamp, write_json


def normalize_s5(run):
    manifest = json.loads((run/"manifest.json").read_text(encoding="utf-8"))
    receipts = [json.loads(line) for line in text_lines(run/"actor-receipts.ndjson") if line.strip()]
    timeline = [json.loads(line) for line in text_lines(run/"timeline.ndjson")]
    actor = manifest["actor"]["uid"]
    index = {}
    for r in receipts:
        index.setdefault((r["ip"],r["port"],r["source_port"],r["container_pid"]),[]).append(r)
    counts, labels, nodes, quality, coverage = (Counter() for _ in range(5))
    types, windows = {}, {}
    with (run/"normalized.ndjson").open("w",encoding="utf-8") as output:
        for node in ("lab-w1","lab-w2"):
            for number,line in enumerate(text_lines(run/"raw"/(node+".ndjson")),1):
                try:
                    raw=json.loads(line)
                    if not isinstance(raw,dict):raise ValueError("Invalid raw object")
                    when=timestamp(raw.get("time"))
                except (ValueError,TypeError):
                    quality["invalid_record"]+=1;continue
                info=event_fields(raw)
                if not info:
                    quality["unselected_event"]+=1;continue
                kind,payload,process,pod=info
                phase=next((p["phase"] for p in reversed(timeline) if timestamp(p["time"])<=when),"setup")
                if manifest.get("measurement_end") and when>=timestamp(manifest["measurement_end"]):phase="finalize"
                sock=next((a["sock_arg"] for a in payload.get("args",[]) if "sock_arg" in a),None)
                requested=next((a["int_arg"] for a in payload.get("args",[]) if "int_arg" in a),None) if kind=="tcp_send" else None
                is_actor=pod.get("uid")==actor
                operation=None
                if is_actor and sock and kind in ("tcp_connect_attempt","tcp_send"):
                    key=(ip(sock["daddr"]),sock["dport"],sock.get("sport"),(pod.get("container") or {}).get("pid"))
                    candidates=[r for r in index.get(key,[]) if timestamp(r["started"])<=when<=timestamp(r["ended"])]
                    if len(candidates)==1:operation=candidates[0]
                label="normal" if phase in ("pre_attack","recovery") and not is_actor else "unknown"
                if manifest["scenario_id"]=="S0" and phase=="measurement":label="normal"
                if operation:
                    label="unknown" if manifest["mode"]=="smoke" else "attack"
                    coverage[operation["operation_id"]]+=1
                    types.setdefault(operation["operation_id"],set()).add(kind)
                record={"schema_version":6,"label_version":"v6","run_id":manifest["run_id"],"scenario_id":manifest["scenario_id"],
                    "timestamp":raw["time"],"phase":phase,"node":node,"namespace":pod.get("namespace"),
                    "pod":pod.get("name"),"pod_uid":pod.get("uid"),"workload":pod.get("workload"),
                    "container_id":(pod.get("container") or {}).get("id"),"container_pid":(pod.get("container") or {}).get("pid"),
                    "binary":process.get("binary"),"pid":process.get("pid"),"exec_id":process.get("exec_id"),
                    "parent_exec_id":(payload.get("parent") or {}).get("exec_id"),"event_type":kind,
                    "socket":sock,"bytes_requested":requested,"kernel_return":payload.get("return"),
                    "operation_id":operation["operation_id"] if operation else None,"label":label,
                    "evidence":"actor_uid_pid_socket_time_receipt" if operation else "normal_control_measurement" if manifest["scenario_id"]=="S0" and phase=="measurement" else "background_outside_action" if label=="normal" else None,
                    "payload_bytes_from_receipt":operation["payload_bytes"] if operation else None,
                    "payload_sha256_from_receipt":operation["payload_sha256"] if operation else None,
                    "http_status_from_receipt":operation["status_code"] if operation else None,
                    "raw_file":f"raw/{node}.ndjson","raw_line":number}
                output.write(json.dumps(record,ensure_ascii=False)+"\n")
                counts[kind]+=1;labels[label]+=1;nodes[node]+=1
                offset=int((when-timestamp(manifest["capture_start"])).total_seconds()//10)
                window=windows.setdefault((pod.get("uid"),offset),{"pod_uid":pod.get("uid"),"window_index":offset,"normal":0,"attack":0,"unknown":0})
                window[label]+=1
    with (run/"labeled-windows.ndjson").open("w",encoding="utf-8") as output:
        for window in windows.values():
            window["label"]="attack" if window["attack"] else "unknown" if window["unknown"] else "normal"
            output.write(json.dumps(window)+"\n")
    before,after=agent_states(run/"agents-before.json"),agent_states(run/"agents-after.json")
    stderr={n:(run/"raw"/(n+".stderr")).read_text() for n in ("lab-w1","lab-w2")}
    summary={"events_by_type":counts,"events_by_label":labels,"events_by_node":nodes,"quality":quality,
        "operations":len(receipts),"operations_with_matched_event":len(coverage),
        "event_types_by_operation":{k:sorted(v) for k,v in types.items()},
        "unmatched_operations":[r["operation_id"] for r in receipts if r["operation_id"] not in coverage],
        "agent_state_unchanged":set(before)=={"lab-w1","lab-w2"} and before==after,"collector_stderr":stderr}
    summary["capture_checks_passed"]=bool(nodes["lab-w1"] and nodes["lab-w2"] and summary["agent_state_unchanged"] and not any(stderr.values()) and not quality["invalid_record"])
    write_json(run/"quality.json",summary)
    return summary
