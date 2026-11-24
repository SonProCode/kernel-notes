"""Verify S4 request/native coverage and summarize measured latency by phase."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path

from label import timestamp, write_json, agent_states, text_lines

LOSS_NAMES = {"tetragon_observer_ringbuf_events_lost_total", "tetragon_observer_ringbuf_queue_events_lost_total",
              "tetragon_events_export_failed_total", "tetragon_export_ratelimit_events_dropped_total"}
RESOURCE_NAMES = {"frontend_cpu_cores", "frontend_memory_bytes", "boutique_cpu_cores", "boutique_memory_bytes"}
WORKERS = {"lab-w1", "lab-w2"}


def read_locust_raw(run):
    metadata, final, records = [], [], []
    for line in text_lines(run / "locust.raw.log"):
        for prefix, destination in (("S4REQ ", records), ("S4META ", metadata), ("S4FINAL ", final)):
            if line.startswith(prefix):
                if prefix == "S4REQ " and final:
                    raise ValueError("Locust request appears after final counter")
                destination.append(json.loads(line[len(prefix):]))
                break
    return metadata, final, records


def extract_locust(run):
    metadata, final, records = read_locust_raw(run)
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


def input_integrity(run, manifest, receipts, locust, runtime, timeline):
    """Validate evidence independently before trusting derived summaries."""
    errors = []
    def check(condition, message):
        if not condition: errors.append(message)
    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    def nonnegative_int(value):
        return type(value) is int and value >= 0
    try:
        config = manifest["s4"]
        control = config["profile"] == "control"
        check(config["profile"] in ("control", "bounded_http"), "Unknown S4 profile")
        check(manifest["scenario_id"] == ("S0" if control else "S4"), "Scenario/profile mismatch")
        check(manifest["status"] == "completed" and not manifest.get("guard_triggered"), "Run is incomplete or guard-triggered")
        check(config["rate"] in ((0,) if control else (3, 6, 10)), "Invalid configured rate")
        check(type(config["duration_seconds"]) is int and 1 <= config["duration_seconds"] <= 90, "Invalid duration")
        check(type(config["concurrency"]) is int and 1 <= config["concurrency"] <= 4, "Invalid concurrency")
        target_phase = "measurement" if control else "attack"
        check([item["phase"] for item in timeline] == ["setup", "warmup", "pre_attack", target_phase, "recovery", "finalize"], "Timeline phases/order invalid")
        moments = [timestamp(item["time"]) for item in timeline]
        check(all(a < b for a, b in zip(moments, moments[1:])), "Timeline timestamps not strictly increasing")
        end = timestamp(manifest["measurement_end"])
        check(abs((moments[-1] - end).total_seconds()) <= 2, "measurement_end/finalize mismatch")
        check(timestamp(manifest["capture_start"]) <= moments[0], "Capture begins after setup")
        bounds = {item["phase"]: (moments[i], moments[i+1] if i+1 < len(moments) else timestamp(manifest["finished"]))
                  for i, item in enumerate(timeline)}
        check((bounds[target_phase][1] - bounds[target_phase][0]).total_seconds() >= config["duration_seconds"] - 0.5, "Measurement shorter than configured")
        raw_meta, raw_final, raw_requests = read_locust_raw(run)
        check(raw_requests == locust and raw_meta == runtime["metadata"] and raw_final == runtime["final"], "Derived Locust data differs from raw log")
        check(len(raw_meta) == len(raw_final) == 1, "Missing/duplicate Locust metadata or final counter")
        check([r["sequence"] for r in locust] == list(range(1, len(locust)+1)), "Locust sequence missing/duplicated")
        if len(raw_final) == 1:
            check(all(nonnegative_int(raw_final[0][k]) for k in ("recorded_requests","locust_num_requests","locust_num_failures")), "Invalid Locust final counter types")
            check(raw_final[0]["recorded_requests"] == raw_final[0]["locust_num_requests"] == len(locust), "Locust final request counter mismatch")
            check(raw_final[0]["locust_num_failures"] == sum(r.get("error") is not None for r in locust), "Locust final failure counter mismatch")
        for record in locust + receipts:
            begin, finish = timestamp(record["started"]), timestamp(record["ended"])
            check(begin <= finish, "Request ends before start")
            latency = record["duration_ms"]
            check(finite(latency) and latency >= 0, "Negative/non-finite request latency")
            check(finite(latency) and latency <= (finish-begin).total_seconds()*1000+50, "Latency inconsistent with request timestamps")
            status = record.get("status_code")
            check(status is None or (type(status) is int and 100 <= status <= 599), "Invalid HTTP status")
            check(nonnegative_int(record.get("response_bytes")), "Invalid response byte count")
        before = json.loads((run/"boutique-before.json").read_text(encoding="utf-8"))
        after = json.loads((run/"boutique-after.json").read_text(encoding="utf-8"))
        service = next(item for item in before["items"] if item["kind"] == "Service" and item["metadata"]["name"] == "frontend")
        target = manifest["targets"][0]
        check(target["ip"] == service["spec"]["clusterIP"] and target["port"] == 80, "Manifest target is not captured frontend")
        endpoints = {target["ip"]}
        ports = {80}
        for item in before["items"]:
            if item["kind"] == "EndpointSlice" and item["metadata"].get("labels", {}).get("kubernetes.io/service-name") == "frontend":
                ports.update(p["port"] for p in item["ports"] if p.get("port"))
                for endpoint in item["endpoints"]:
                    if endpoint.get("conditions", {}).get("ready") is not False: endpoints.update(endpoint["addresses"])
        check(set(target["target_ips"]) == endpoints and set(target["target_ports"]) == ports, "Manifest target aliases differ from topology")
        ids = [r["operation_id"] for r in receipts]
        check(len(ids) == len(set(ids)), "Duplicate HTTP operation IDs")
        for record in receipts:
            check(record["kind"] == "http_request" and record["method"] == "GET" and record["path"] == "/", "Unexpected actor HTTP operation")
            check(record["ip"] == target["ip"] and record["port"] == 80 and set(record["target_ips"]) == endpoints and set(record["target_ports"]) == ports, "Receipt target differs from frontend topology")
            check(type(record["source_port"]) is int and 1 <= record["source_port"] <= 65535, "Missing/invalid source port")
            check(bounds[target_phase][0] <= timestamp(record["started"]) <= timestamp(record["ended"]) <= bounds[target_phase][1], "Actor request outside attack phase")
            outcome = "http_success" if record["status_code"] == 200 and record.get("error") is None else "http_error"
            check(record["outcome"] == outcome, "HTTP outcome inconsistent with status/error")
        if control:
            check(not receipts, "Control contains actor requests")
        else:
            client = json.loads((run/"s4-client-summary.json").read_text(encoding="utf-8"))
            check(all(nonnegative_int(client[k]) for k in ("scheduled", "submitted", "skipped_busy", "skipped_late")), "Negative/non-integer client counters")
            check(client["configured_rate"] == config["rate"] and client["duration_seconds"] == config["duration_seconds"] and client["concurrency"] == config["concurrency"], "Client configuration differs from manifest")
            check(finite(client["elapsed_seconds"]) and config["duration_seconds"] <= client["elapsed_seconds"] <= config["duration_seconds"]+15, "Client duration outside bounded window")
            for operation in ids:
                check(operation.startswith("http-") and operation[5:].isdigit() and 0 <= int(operation[5:]) < client["scheduled"], "Operation ID outside schedule")
        def state(snapshot):
            return {item["metadata"]["uid"]: sum(c.get("restartCount",0) for c in item.get("status",{}).get("containerStatuses",[]))
                    for item in snapshot["items"] if item["kind"] == "Pod"}
        check(state(before) == state(after), "Pod UID/restart state changed between snapshots")
        original = [next(item for item in snap["items"] if item["kind"] == "Deployment" and item["metadata"]["name"] == "loadgenerator")["spec"] for snap in (before,after)]
        check(original[0] == original[1] and original[1]["replicas"] == 0, "Original loadgenerator changed")
        agent_before,agent_after=agent_states(run/"agents-before.json"),agent_states(run/"agents-after.json")
        check(set(agent_before)==WORKERS and agent_before==agent_after, "Agent UID/restart state missing or changed")
        guards = rows(run/"guard.ndjson")
        check(bool(guards), "Guard log empty")
        guard_times = [timestamp(g["timestamp"]) for g in guards]
        check(all(a < b and (b-a).total_seconds() <= 35 for a,b in zip(guard_times,guard_times[1:])), "Guard heartbeat gap/order invalid")
        if guards:
            check((guard_times[0]-bounds["warmup"][0]).total_seconds() <= 35 and (end-guard_times[-1]).total_seconds() <= 35, "Guard coverage does not bracket measurement")
        for phase in ("warmup", "pre_attack", target_phase, "recovery"):
            check(any(g["phase"] == phase for g in guards), "No guard sample in phase: "+phase)
        failed_probes = 0
        baseline = state(before)
        for g in guards:
            if g.get("phase") not in bounds:
                check(False, "Unknown guard phase")
            else:
                low,high=bounds[g["phase"]]
                moment=timestamp(g["timestamp"])
                check(low.timestamp()-0.5<=moment.timestamp()<=high.timestamp()+0.5, "Guard timestamp outside declared phase")
            check(not g["reasons"], "Guard reported stop reasons")
            failed_probes = 0 if g.get("probe_ok") is True else failed_probes+1
            check(g.get("consecutive_probe_failures") == failed_probes and failed_probes < 3, "Guard probe counters invalid")
            observed = {uid:p["restarts"] for uid,p in g.get("pods",{}).items()}
            check(observed == baseline, "Guard pod state differs from initial snapshot")
        resources = json.loads((run/"prometheus-resources.json").read_text(encoding="utf-8"))
        check(set(resources) == RESOURCE_NAMES, "Missing/unexpected resource query names")
        for name,value in resources.items():
            check(value.get("status") == "success" and value.get("data",{}).get("resultType") == "matrix", "Resource query failed: "+name)
            series = value.get("data",{}).get("result",[])
            check(len(series) == 1, "Expected one aggregated resource series: "+name)
            points = series[0].get("values",[]) if len(series)==1 else []
            parsed = [(float(epoch),float(amount)) for epoch,amount in points]
            check(bool(parsed) and all(math.isfinite(t) and math.isfinite(v) and v>=0 for t,v in parsed), "Non-finite/negative/empty resource samples: "+name)
            check(all(a[0]<b[0] and b[0]-a[0]<=35 for a,b in zip(parsed,parsed[1:])), "Resource time series gap/order invalid: "+name)
            for phase in ("pre_attack",target_phase,"recovery"):
                check(any(bounds[phase][0].timestamp()<=t<bounds[phase][1].timestamp() and math.isfinite(v) for t,v in parsed), "Resource samples missing in phase: "+name+"/"+phase)
        for stage in ("before","after"):
            metrics = json.loads((run/f"metrics-{stage}.json").read_text())
            check(all(metrics.get(k,{}).get("status")=="success" for k in ("agent_up","loss_and_export")), "Agent/loss metric query returned an error")
            up = metrics.get("agent_up",{}).get("data",{}).get("result",[])
            check(len(up)==2 and {r["metric"].get("node") for r in up}==WORKERS and all(float(r["value"][1])==1 for r in up), "Wrong/missing worker identities in up metrics")
            counters=metrics.get("loss_and_export",{}).get("data",{}).get("result",[])
            expected={(name,node) for name in LOSS_NAMES for node in WORKERS}
            check(len(counters)==8 and {(r["metric"]["__name__"],r["metric"]["node"]) for r in counters}==expected, "Wrong loss/export counter identities")
            check(all(math.isfinite(float(r["value"][1])) and float(r["value"][1])>=0 for r in counters), "Invalid loss/export counter value")
        if config.get("verification_contract",1)>=2:
            for stage in ("before","after"):
                snapshot=json.loads((run/f"metrics-{stage}.json").read_text())
                age=snapshot.get("agent_scrape_age_seconds",{}).get("data",{}).get("result",[])
                check(snapshot.get("agent_scrape_age_seconds",{}).get("status")=="success"
                      and len(age)==2 and {r["metric"].get("node") for r in age}==WORKERS
                      and all(math.isfinite(float(r["value"][1])) and 0<=float(r["value"][1])<=60 for r in age), "Stale/missing agent scrape evidence")
            cleanup=json.loads((run/"cleanup.json").read_text())
            check(cleanup.get("passed") is True and all(v==0 for v in cleanup["remaining"].values()) and set(cleanup["remaining"])=={"pods","deployments","configmaps"}, "Cleanup evidence invalid")
            check(cleanup["original_loadgenerator_unchanged"] is True, "Original deployment not restored after cleanup")
    except (KeyError, ValueError, TypeError, OSError, StopIteration, IndexError) as error:
        errors.append("Malformed/missing evidence: "+type(error).__name__+": "+str(error))
    return list(dict.fromkeys(errors))


def verify_s4(run):
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    receipts = rows(run / "actor-receipts.ndjson")
    locust = rows(run / "locust-requests.ndjson")
    runtime = json.loads((run / "locust-runtime.json").read_text(encoding="utf-8"))
    timeline = rows(run / "timeline.ndjson")
    integrity = input_integrity(run, manifest, receipts, locust, runtime, timeline)
    if integrity:
        result = {"passed": False, "input_integrity_passed": False, "input_integrity_errors": integrity,
                  "http_operations": len(receipts), "operations_with_native_event": 0, "native_records_verified": 0,
                  "profile": manifest["s4"]["profile"], "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        write_json(run / "s4-verification.json", result)
        return result
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
    native_errors = []
    matched = Counter()
    for event in normalized:
        if event.get("operation_id"):
            reference = event["raw_file"], event["raw_line"]
            if reference in references:
                native_errors.append("Duplicate native reference")
            if reference[0] not in ("raw/lab-w1.ndjson", "raw/lab-w2.ndjson") or type(reference[1]) is not int or reference[1]<1:
                native_errors.append("Invalid native reference")
            references[reference] = event
    receipt_map = {r["operation_id"]: r for r in receipts}
    native_verified = 0
    for node in ("lab-w1", "lab-w2"):
        relative = f"raw/{node}.ndjson"
        for number, line in enumerate(text_lines(run / relative), 1):
            try:
                original = json.loads(line)
                if not isinstance(original,dict): raise ValueError("Expected raw object")
                timestamp(original.get("time"))
            except (ValueError,TypeError):
                native_errors.append("Invalid raw JSON record")
                continue
            event = references.get((relative, number))
            if event is None:
                continue
            native_verified += 1
            try:
                payload = original["process_kprobe"]
                receipt = receipt_map[event["operation_id"]]
                process = payload["process"]
                sock = next(a["sock_arg"] for a in payload["args"] if "sock_arg" in a)
                address = ipaddress.ip_address(sock["daddr"])
                address = str(address.ipv4_mapped) if getattr(address, "ipv4_mapped", None) else str(address)
                expected_type={"tcp_connect":"tcp_connect_attempt","tcp_sendmsg":"tcp_send"}.get(payload["function_name"])
                pod = process["pod"]
                native_fields = {"node": node, "namespace": pod.get("namespace"), "pod": pod.get("name"),
                                 "workload": pod.get("workload"), "socket": sock,
                                 "container_id": (pod.get("container") or {}).get("id"),
                                 "container_pid": (pod.get("container") or {}).get("pid"),
                                 "binary": process.get("binary"), "pid": process.get("pid"),
                                 "exec_id": process.get("exec_id"), "arguments": process.get("arguments"),
                                 "parent_exec_id": (payload.get("parent") or {}).get("exec_id"),
                                 "kernel_return": payload.get("return"),
                                 "file_path": next((a["file_arg"].get("path") for a in payload.get("args",[]) if "file_arg" in a),None)}
                fields_match = all(key in event and event[key] == value for key,value in native_fields.items())
                receipt_fields_match = (event.get("api_method_from_receipt") == receipt["method"]
                                        and event.get("http_status_from_receipt") == receipt["status_code"]
                                        and event.get("grpc_code_from_receipt") is None)
                valid = (expected_type is not None and event["event_type"]==expected_type
                         and fields_match and receipt_fields_match
                         and process["pod"]["uid"]==manifest["actor"]["uid"]==event["pod_uid"]
                         and process["pod"]["namespace"]=="boutique"
                         and process["pod"]["container"]["pid"]==receipt["container_pid"]
                         and address in receipt["target_ips"] and sock["dport"] in receipt["target_ports"]
                         and sock["sport"]==receipt["source_port"]
                         and timestamp(receipt["started"])<=timestamp(original["time"])<=timestamp(receipt["ended"])
                         and timestamp(event["timestamp"])==timestamp(original["time"])
                         and event["phase"]=="attack"
                         and event["label"]==("unknown" if manifest["mode"]=="smoke" else "attack"))
                if valid: matched[receipt["operation_id"]] += 1
                else: native_errors.append("Native identity/socket/time/label mismatch")
            except (KeyError,ValueError,TypeError,StopIteration):
                native_errors.append("Malformed native correlation")
    if native_verified!=len(references): native_errors.append("Unresolvable raw references")
    count = len(locust)
    log_complete = (len(runtime["metadata"]) == len(runtime["final"]) == 1
                    and [r["sequence"] for r in locust] == list(range(1, count + 1))
                    and runtime["final"][0]["recorded_requests"] == runtime["final"][0]["locust_num_requests"] == count)
    quality = json.loads((run / "quality.json").read_text())
    derived_quality_valid = (dict(Counter(e["event_type"] for e in normalized))==quality["events_by_type"]
                             and dict(Counter(e["label"] for e in normalized))==quality["events_by_label"]
                             and dict(Counter(e["node"] for e in normalized))==quality["events_by_node"]
                             and quality["operations"]==len(receipts)
                             and quality["operations_with_matched_event"]==len(matched)
                             and sorted(quality["unmatched_operations"])==sorted(set(receipt_map)-set(matched)))
    for event in normalized:
        expected_phase=phase_of(timestamp(event["timestamp"]),timeline,end)
        is_actor=event.get("pod_uid")==manifest["actor"]["uid"]
        expected_label="unknown"
        if expected_phase in ("pre_attack","recovery") and not is_actor: expected_label="normal"
        if manifest["scenario_id"]=="S0" and expected_phase=="measurement": expected_label="normal"
        if event.get("operation_id"): expected_label="unknown" if manifest["mode"]=="smoke" else "attack"
        if (event["phase"]!=expected_phase or event["label"]!=expected_label or event["schema_version"]!=5
            or event["label_version"]!="v5" or event["run_id"]!=manifest["run_id"] or event["scenario_id"]!=manifest["scenario_id"]):
            native_errors.append("Normalized phase/label/schema/run mismatch")
            break
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
              "input_integrity_passed": True, "input_integrity_errors": [],
              "native_integrity_passed": not native_errors, "native_integrity_errors": list(dict.fromkeys(native_errors)),
              "derived_quality_counts_match": derived_quality_valid, "verification_contract": manifest["s4"].get("verification_contract",1),
              "per_run_cleanup_evidence": (run/"cleanup.json").exists(),
              "legacy_evidence_limits": [] if manifest["s4"].get("verification_contract",1)>=2 else ["No per-run cleanup.json or scrape-age snapshot in historical v1; use the dated cohort checkpoint for cleanup evidence"],
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
                            and not native_errors and derived_quality_valid
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
