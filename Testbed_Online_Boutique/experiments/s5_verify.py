"""S5 acceptance: client + receiver + raw kernel evidence, labels and cleanup."""
import argparse
from collections import Counter
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

from label import agent_states, ip, timestamp, write_json
from s4_verify import LOSS_NAMES, RESOURCE_NAMES, WORKERS, read_locust_raw, rows, summarize
from s5_normalize import normalize_s5

sys.path.insert(0,str(Path(__file__).resolve().parent/"s5"))
from fixture import FIXTURE_ID, PAYLOAD_BYTES, RECEIVER_IP, RECEIVER_PORT, operation_id, payload


def verify_s5(run):
    errors=[]
    def check(condition,message):
        if not condition:errors.append(message)
    def finite(value):return type(value) in (int,float) and math.isfinite(value)
    result={"passed":False,"scope":"Synthetic exfiltration pilot; not real data theft or egress-policy enforcement",
            "verifier_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        manifest=json.loads((run/"manifest.json").read_text(encoding="utf-8"))
        calls=manifest["s5"]["calls"]
        check(manifest["scenario_id"]=="S5" and manifest["mode"] in ("smoke","pilot","official"),"Wrong scenario/mode")
        check(manifest["status"]=="completed" and not manifest.get("guard_triggered") and not manifest.get("cleanup_errors"),"Incomplete/guard-triggered run")
        check(type(calls) is int and 1<=calls<=60,"Invalid call count")
        check(manifest["mode"]!="official" or calls==60,"Official S5 requires 60 uploads under the recorded protocol")
        check(manifest["s5"]["rate"]==1 and manifest["s5"]["payload_bytes"]==PAYLOAD_BYTES and manifest["s5"]["fixture_id"]==FIXTURE_ID,"Wrong fixture/profile")
        check(manifest["s5"]["receiver_ip"]==RECEIVER_IP and manifest["s5"]["receiver_port"]==RECEIVER_PORT,"Wrong receiver target")
        check(manifest["targets"]==[{"ip":RECEIVER_IP,"port":RECEIVER_PORT,"target_ips":[RECEIVER_IP],"target_ports":[RECEIVER_PORT]}],"Target aliases changed")
        check(manifest["s5"]["topology"]=="host_receiver_outside_pod_network","Unexpected receiver topology")
        check(manifest["receiver"]["uid"]>0,"Receiver ran as root")
        check(manifest["s5"]["cross_host_clock_tolerance_seconds"]==2,"Clock tolerance changed")
        timeline=rows(run/"timeline.ndjson")
        check([p["phase"] for p in timeline]==["setup","warmup","pre_attack","attack","recovery","finalize"],"Invalid phases/order")
        times=[timestamp(p["time"]) for p in timeline]
        check(all(a<b for a,b in zip(times,times[1:])),"Timeline not increasing")
        bounds={p["phase"]:(times[i],times[i+1]) for i,p in enumerate(timeline[:-1])}
        check(abs((timestamp(manifest["measurement_end"])-times[-1]).total_seconds())<2,"Measurement end mismatch")
        check((bounds["attack"][1]-bounds["attack"][0]).total_seconds()>=calls,"Attack shorter than configured window")
        receipts=rows(run/"actor-receipts.ndjson")
        receiver=rows(run/"receiver.ndjson")
        received=[r for r in receiver if r["kind"]=="received"]
        ready=[r for r in receiver if r["kind"]=="receiver_ready"]
        stopped=[r for r in receiver if r["kind"]=="receiver_stopped"]
        check(not any(r["kind"]=="rejected" for r in receiver),"Receiver rejected a request")
        check(len(ready)==len(stopped)==1,"Missing/duplicate receiver lifecycle records")
        if ready:
            check(ready[0]["pid"]==manifest["receiver"]["pid"] and ready[0]["uid"]==manifest["receiver"]["uid"] and ready[0]["uid"]>0,"Receiver process identity mismatch")
            check(ready[0]["bind_ip"]==RECEIVER_IP and ready[0]["port"]==RECEIVER_PORT and ready[0]["run_id"]==manifest["run_id"] and ready[0]["max_calls"]==calls,"Receiver bind/profile mismatch")
        check(bool(stopped) and stopped[0]["received"]==calls,"Receiver stopped with wrong receive count")
        expected=[operation_id(i) for i in range(calls)]
        check([r["operation_id"] for r in receipts]==expected,"Missing/duplicate/reordered client operations")
        check([r["operation_id"] for r in received]==expected,"Missing/duplicate/reordered receiver operations")
        receiver_map={r["operation_id"]:r for r in received}
        check(len({r["source_port"] for r in receipts})==calls,"Source ports missing or reused")
        check(len({r["container_pid"] for r in receipts})==1,"Client process changed")
        for r in receipts:
            start,end=timestamp(r["started"]),timestamp(r["ended"])
            check(bounds["attack"][0]<=start<=end<=bounds["attack"][1],"Client operation outside attack")
            check(finite(r["duration_ms"]) and 0<=r["duration_ms"]<=(end-start).total_seconds()*1000+50,"Invalid latency")
            check(type(r["source_port"]) is int and 1<=r["source_port"]<=65535 and type(r["container_pid"]) is int and r["container_pid"]>0,"Invalid socket/PID")
            check(r["ip"]==RECEIVER_IP and r["port"]==RECEIVER_PORT and r["target_ips"]==[RECEIVER_IP] and r["target_ports"]==[RECEIVER_PORT],"Client target mismatch")
            check(r["kind"]=="http_upload" and r["method"]=="POST" and r["path"]=="/upload" and r["run_id"]==manifest["run_id"],"Invalid client identity/method")
            digest=hashlib.sha256(payload(manifest["run_id"],r["operation_id"])).hexdigest()
            check(r["fixture_id"]==FIXTURE_ID and r["payload_bytes"]==PAYLOAD_BYTES and r["payload_sha256"]==digest,"Client synthetic fixture mismatch")
            check(r["status_code"]==200 and r["error"] is None and r["outcome"]=="received","Upload did not succeed")
            ack=receiver_map.get(r["operation_id"])
            check(ack is not None and r["receiver_acknowledgment"]==ack,"Client acknowledgment differs from receiver log")
            if ack:
                check(ack["run_id"]==manifest["run_id"] and ack["payload_bytes"]==PAYLOAD_BYTES and ack["payload_sha256"]==digest and ack["fixture_id"]==FIXTURE_ID,"Receiver bytes/checksum mismatch")
                check(ack["receiver_ip"]==RECEIVER_IP and ack["receiver_port"]==RECEIVER_PORT,"Receiver address mismatch")
                check(start-timedelta(seconds=2)<=timestamp(ack["started"])<=timestamp(ack["ended"])<=end+timedelta(seconds=2),"Cross-host receipt time outside tolerance")
        check(all((timestamp(b["started"])-timestamp(a["started"])).total_seconds()>=.95 for a,b in zip(receipts,receipts[1:])),"Uploads exceeded paced 1 RPS profile")
        client=json.loads((run/"s5-client-summary.json").read_text())
        check(client["run_id"]==manifest["run_id"] and client["scheduled"]==client["submitted"]==calls and client["skipped_late"]==0 and not client["interrupted"],"Client schedule incomplete")
        check(client["rate"]==1 and client["payload_bytes"]==PAYLOAD_BYTES and finite(client["elapsed_seconds"]) and calls<=client["elapsed_seconds"]<=calls+15,"Invalid client limits/duration")
        normalized=rows(run/"normalized.ndjson")
        by_op={r["operation_id"]:[] for r in receipts}
        native_counts=Counter();native_bytes=Counter()
        references=set()
        raw={n:[json.loads(line) for line in (run/"raw"/(n+".ndjson")).read_text(encoding="utf-8").splitlines()] for n in WORKERS}
        for e in normalized:
            if not e.get("operation_id"):continue
            reference=(e["raw_file"],e["raw_line"])
            check(reference not in references,"Duplicate native reference");references.add(reference)
            r=next(r for r in receipts if r["operation_id"]==e["operation_id"])
            check(e["node"]=="lab-"+manifest["node"] and e["raw_file"]==f"raw/{e['node']}.ndjson" and type(e["raw_line"]) is int and e["raw_line"]>0,"Invalid raw source reference")
            original=raw[e["node"]][e["raw_line"]-1];p=original["process_kprobe"];process=p["process"];pod=process["pod"]
            sock=next(a["sock_arg"] for a in p["args"] if "sock_arg" in a)
            kind={"tcp_connect":"tcp_connect_attempt","tcp_sendmsg":"tcp_send"}.get(p["function_name"])
            check(p["policy_name"]=="boutique-tcp-connect" and kind==e["event_type"] and kind is not None,"Wrong native hook/policy")
            check(pod["uid"]==manifest["actor"]["uid"]==e["pod_uid"] and pod["namespace"]==e["namespace"]=="boutique" and pod["container"]["pid"]==r["container_pid"]==e["container_pid"],"Native Pod/PID mismatch")
            check(ip(sock["daddr"])==r["ip"] and sock["dport"]==r["port"] and sock["sport"]==r["source_port"] and sock==e["socket"],"Native socket differs from client/normalized")
            check(timestamp(r["started"])<=timestamp(original["time"])<=timestamp(r["ended"]) and timestamp(e["timestamp"])==timestamp(original["time"]),"Native time mismatch")
            check(e["phase"]=="attack" and e["label"]==("unknown" if manifest["mode"]=="smoke" else "attack"),"Incorrect attack label")
            by_op[r["operation_id"]].append(kind);native_counts[kind]+=1
            if kind=="tcp_send":
                size=next(a["int_arg"] for a in p["args"] if "int_arg" in a)
                check(type(size) is int and size>0 and e["bytes_requested"]==size,"Invalid kernel bytes_requested")
                native_bytes[r["operation_id"]]+=size
        check(bool(by_op) and all({"tcp_connect_attempt","tcp_send"}<=set(v) for v in by_op.values()),"Missing connect/send evidence for an upload")
        # Independent replay also protects all background features and 10-second window labels.
        with tempfile.TemporaryDirectory(prefix="s5-replay-") as directory:
            directory=Path(directory)
            for name in ("manifest.json","actor-receipts.ndjson","timeline.ndjson","agents-before.json","agents-after.json"):
                shutil.copyfile(run/name,directory/name)
            shutil.copytree(run/"raw",directory/"raw")
            replay_quality=normalize_s5(directory)
            check(rows(directory/"normalized.ndjson")==normalized,"Normalized features differ from raw replay")
            check(rows(directory/"labeled-windows.ndjson")==rows(run/"labeled-windows.ndjson"),"Window labels differ from replay")
            check(replay_quality==json.loads((run/"quality.json").read_text()),"Quality counts differ from replay")
            check(replay_quality["capture_checks_passed"],"Capture quality failed")
        metadata,final,locust=read_locust_raw(run)
        check(locust==rows(run/"locust-requests.ndjson") and {"metadata":metadata,"final":final}==json.loads((run/"locust-runtime.json").read_text()),"Derived Locust differs from raw")
        check(len(metadata)==len(final)==1 and [r["sequence"] for r in locust]==list(range(1,len(locust)+1)),"Locust export incomplete")
        for r in locust:
            begin,end=timestamp(r["started"]),timestamp(r["ended"])
            check(begin<=end and finite(r["duration_ms"]) and 0<=r["duration_ms"]<=(end-begin).total_seconds()*1000+50,"Invalid Locust request time/latency")
            check(r["status_code"] is None or (type(r["status_code"]) is int and 100<=r["status_code"]<=599),"Invalid Locust HTTP status")
            check(type(r["response_bytes"]) is int and r["response_bytes"]>=0,"Invalid Locust response size")
        if final:check(final[0]["recorded_requests"]==final[0]["locust_num_requests"]==len(locust) and final[0]["locust_num_failures"]==sum(r["error"] is not None for r in locust),"Locust final counters mismatch")
        locust_phases={}
        for name in ("pre_attack","attack","recovery"):
            lo,hi=bounds[name]
            sample=[r for r in locust if lo<=timestamp(r["started"])<=timestamp(r["ended"])<hi]
            check(bool(sample),"No Locust samples in "+name)
            check(all(finite(r["duration_ms"]) and r["duration_ms"]>=0 for r in sample),"Invalid Locust latency")
            locust_phases[name]=summarize(sample)
        def pod_state(stage):
            snapshot=json.loads((run/f"boutique-{stage}.json").read_text())
            state={p["metadata"]["uid"]:sum(c["restartCount"] for c in p.get("status",{}).get("containerStatuses",[])) for p in snapshot["items"] if p["kind"]=="Pod"}
            original=next(p["spec"] for p in snapshot["items"] if p["kind"]=="Deployment" and p["metadata"]["name"]=="loadgenerator")
            return state,original
        before,original=pod_state("before");after,original_after=pod_state("after")
        check(before==after and original==original_after and original["replicas"]==0,"Workload replaced/restarted or original loadgenerator changed")
        guard=rows(run/"guard.ndjson")
        check(all(any(g["phase"]==p for g in guard) for p in ("warmup","pre_attack","attack","recovery")),"Guard phase coverage missing")
        guard_times=[timestamp(g["timestamp"]) for g in guard]
        check(bool(guard_times) and all(0<(b-a).total_seconds()<=35 for a,b in zip(guard_times,guard_times[1:])) and (times[-1]-guard_times[-1]).total_seconds()<=35,"Guard heartbeat missing/gapped")
        for g in guard:
            check(not g["reasons"] and g["consecutive_probe_failures"]<3 and {uid:v["restarts"] for uid,v in g["pods"].items()}==before,"Guard detected unhealthy workload")
            moment=timestamp(g["timestamp"])
            check(g["phase"] in bounds,"Unknown guard phase")
            if g["phase"] in bounds:
                lo,hi=bounds[g["phase"]]
                check(lo-timedelta(seconds=.5)<=moment<=hi+timedelta(seconds=.5),"Guard timestamp/phase mismatch")
        a,b=agent_states(run/"agents-before.json"),agent_states(run/"agents-after.json")
        check(set(a)==WORKERS and a==b,"Agent restarted/replaced")
        counters=[]
        for stage in ("before","after"):
            metrics=json.loads((run/f"metrics-{stage}.json").read_text())
            for key in ("agent_up","agent_scrape_age_seconds","loss_and_export"):
                check(metrics[key].get("status")=="success","Metric query failed: "+key)
            up=metrics["agent_up"]["data"]["result"];age=metrics["agent_scrape_age_seconds"]["data"]["result"]
            check(len(up)==2 and {r["metric"]["node"] for r in up}==WORKERS and all(float(r["value"][1])==1 for r in up),"Wrong/missing agent up")
            check(len(age)==2 and {r["metric"]["node"] for r in age}==WORKERS and all(math.isfinite(float(r["value"][1])) and 0<=float(r["value"][1])<=60 for r in age),"Stale/missing scrape")
            loss=metrics["loss_and_export"]["data"]["result"]
            values={(r["metric"]["__name__"],r["metric"]["node"]):float(r["value"][1]) for r in loss}
            check(len(loss)==8 and set(values)=={(name,node) for name in LOSS_NAMES for node in WORKERS} and all(math.isfinite(v) and v>=0 for v in values.values()),"Loss/export counters invalid")
            counters.append(values)
        check(counters[0]==counters[1],"Loss/export counters changed")
        resources=json.loads((run/"prometheus-resources.json").read_text())
        check(set(resources)==RESOURCE_NAMES,"Resource queries missing")
        for name,value in resources.items():
            series=value.get("data",{}).get("result",[])
            check(value.get("status")=="success" and len(series)==1,"Invalid resource series: "+name)
            points=[(float(t),float(v)) for t,v in series[0]["values"]] if len(series)==1 else []
            check(bool(points) and all(math.isfinite(t) and math.isfinite(v) and v>=0 for t,v in points),"Nonfinite/negative resource: "+name)
            for phase in ("pre_attack","attack","recovery"):
                lo,hi=bounds[phase];check(any(lo.timestamp()<=t<hi.timestamp() for t,v in points),"Resource phase missing: "+name+"/"+phase)
        cleanup=json.loads((run/"cleanup.json").read_text())
        check(cleanup["passed"] and set(cleanup["remaining"])=={"pods","deployments","configmaps"} and all(v==0 for v in cleanup["remaining"].values()) and cleanup["original_loadgenerator_unchanged"] and cleanup["receiver_process_stopped"] and cleanup["receiver_port_closed"],"Cleanup evidence incomplete")
        for name in ("receiver.stderr","actor.stderr","locust.stderr"):
            check(not (run/name).read_text().strip(),"Nonempty capture stderr: "+name)
        check(bool(manifest["script_sha256"]) and all(hashlib.sha256((run/"source"/name).read_bytes()).hexdigest()==digest for name,digest in manifest["script_sha256"].items()),"Source snapshot mismatch")
        expected_sources={"runner.py","label.py","s5_runner.py","s5_normalize.py","s5_verify.py","s4_support.py","s4_verify.py","s5/client.py","s5/fixture.py","s5/receiver.py","s4/locust_wrapper.py","telemetry/normalize.py"}
        check(set(manifest["script_sha256"])==expected_sources,"Missing/unexpected source provenance")
        check(hashlib.sha256(json.dumps(manifest["script_sha256"],sort_keys=True).encode()).hexdigest()==manifest["code_bundle_sha256"],"Source bundle hash mismatch")
        result.update(run_id=manifest["run_id"],mode=manifest["mode"],uploads=len(receipts),received=len(received),
            received_payload_bytes=sum(r["payload_bytes"] for r in received),operations_with_native_evidence=sum({"tcp_connect_attempt","tcp_send"}<=set(v) for v in by_op.values()),
            native_event_counts=dict(native_counts),kernel_send_bytes_requested=sum(native_bytes.values()),
            kernel_bytes_by_operation=dict(native_bytes),locust_requests=len(locust),locust_by_phase=locust_phases,
            normalized_events=len(normalized),events_by_label=dict(Counter(e["label"] for e in normalized)),
            receiver_peer_ips=sorted({r["peer_ip"] for r in received}),raw_normalized_and_windows_replay_match=not any("replay" in e for e in errors))
    except (KeyError,ValueError,TypeError,OSError,StopIteration,IndexError) as error:
        errors.append("Malformed/missing evidence: "+type(error).__name__+": "+str(error))
    result["errors"]=list(dict.fromkeys(errors));result["passed"]=not errors
    write_json(run/"s5-verification.json",result)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("run",type=Path)
    result=verify_s5(parser.parse_args().run);print(json.dumps(result,indent=2));raise SystemExit(not result["passed"])
