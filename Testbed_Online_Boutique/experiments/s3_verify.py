"""Verify S3 shell/tool lineage, network operations and projected-token reads."""
import argparse
from collections import Counter
import ipaddress
import json
from pathlib import Path
import re

from label import timestamp, write_json


def verify_s3(run):
    manifest = json.loads((run/"manifest.json").read_text())
    assert manifest["scenario_id"] == "S3" and manifest["s3"]["profile"] == "runtime"
    receipts = [json.loads(line) for line in (run/"actor-receipts.ndjson").read_text().splitlines() if line]
    expected = {f"r{i}-{step}" for i in range(manifest["s3"]["rounds"])
                for step in ("shell","curl","wget","nc","nmap","token")}
    actor = manifest["actor"]
    selected, executions = {}, {}
    for line in (run/"normalized.ndjson").open():
        event = json.loads(line)
        if event.get("pod_uid") != actor["uid"]:
            continue
        if event["event_type"] == "process_exec" and event.get("container_pid") is not None:
            executions[event["container_pid"]] = event
        if event.get("operation_id"):
            selected.setdefault(event["operation_id"], []).append(event)
    references = {(e["raw_file"],e["raw_line"]):e for group in selected.values() for e in group}
    native = {}
    # No buffer contents are traced by the policies. Check exported text for accidental credential output.
    jwt = re.compile(rb"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
    for node in ("lab-w1","lab-w2"):
        relative=f"raw/{node}.ndjson"
        for number,line in enumerate((run/relative).open("rb"),1):
            if jwt.search(line):
                raise RuntimeError("Credential-like text in raw export; stop dataset publication")
            if (relative,number) in references:
                native[(relative,number)]=json.loads(line)
    for name in ("actor-receipts.ndjson","actor.stderr","s3-setup.log"):
        path=run/name
        if path.exists() and jwt.search(path.read_bytes()):
            raise RuntimeError("Credential-like text in exported metadata; stop publication")
    metrics={}
    metric_valid=True
    for stage in ("before","after"):
        try:
            snapshot=json.loads((run/f"metrics-{stage}.json").read_text())
            up=snapshot["agent_up"]["data"]["result"]
            counters=snapshot["loss_and_export"]["data"]["result"]
            metric_valid = metric_valid and len(up)==2 and all(float(row["value"][1])==1 for row in up)
            metric_valid = metric_valid and len(counters)==8
            metrics[stage]={(row["metric"]["__name__"],row["metric"]["node"]):float(row["value"][1]) for row in counters}
        except (OSError,ValueError,KeyError,TypeError):
            metric_valid=False
            metrics[stage]={}
    deltas={name+"@"+node:metrics["after"].get((name,node),-1)-value
            for (name,node),value in metrics["before"].items()}
    metric_valid=metric_valid and len(deltas)==8 and all(delta==0 for delta in deltas.values())
    results=[]
    for receipt in receipts:
        events=selected.get(receipt["operation_id"],[])
        types=Counter(e["event_type"] for e in events)
        checks={"operation_completed":receipt["outcome"] in ("completed","read_completed"),
                "has_correlated_event":bool(events)}
        for event in events:
            raw=native[(event["raw_file"],event["raw_line"])]
            payload=raw.get("process_exec") or raw.get("process_kprobe")
            process=payload["process"]
            assert process["pod"]["uid"] == actor["uid"]
            assert process["pod"]["container"]["pid"] == receipt["container_pid"]
            assert timestamp(receipt["started"]) <= timestamp(raw["time"]) <= timestamp(receipt["ended"])
            if event["event_type"] == "process_exec":
                assert process["binary"] in receipt.get("binary_aliases", [receipt["binary"]])
            elif event["event_type"] == "file_read_permission":
                file_arg=next(a["file_arg"] for a in payload["args"] if "file_arg" in a)
                assert file_arg["path"] in receipt["file_aliases"]
                assert payload["return"]["int_arg"] == 0
            else:
                socket=next(a["sock_arg"] for a in payload["args"] if "sock_arg" in a)
                address=ipaddress.ip_address(socket["daddr"])
                address=str(address.ipv4_mapped) if getattr(address,"ipv4_mapped",None) else str(address)
                assert address in receipt["target_ips"] and socket["dport"] in receipt["target_ports"]
        parent=executions.get(receipt["parent_container_pid"])
        if receipt["kind"] in ("process_exec","runtime_tool"):
            child=next((e for e in events if e["event_type"]=="process_exec"),None)
            checks["process_exec_observed"]=bool(child)
            checks["parent_lineage"]=bool(child and parent and child["parent_exec_id"]==parent["exec_id"])
        if receipt["kind"]=="runtime_tool":
            shell=executions.get(receipt["shell_container_pid"])
            checks["helper_is_shell_child"]=bool(parent and shell and parent["parent_exec_id"]==shell["exec_id"])
            checks["tcp_connect_observed"]=types["tcp_connect_attempt"]>0
        if receipt["kind"]=="file_read":
            flags=receipt["token_metadata"]
            checks["projected_token_claims"]=all(flags.get(k) is True for k in
                ("jwt_shape","audience_matches","subject_matches","not_expired"))
            checks["file_read_observed"]=types["file_read_permission"]>0
            helper=executions.get(receipt["container_pid"])
            checks["helper_lineage"]=bool(helper and parent and helper["parent_exec_id"]==parent["exec_id"])
            checks["bytes_read_positive"]=receipt["byte_count"]>0
        results.append({"operation_id":receipt["operation_id"],"kind":receipt["kind"],
                        "tool":receipt.get("tool"),"checks":checks,"event_types":dict(types),
                        "raw_references":[{"file":e["raw_file"],"line":e["raw_line"]} for e in events],
                        "passed":all(checks.values())})
    topology=json.loads((run/"boutique-before.json").read_text())
    pod=next(item for item in topology["items"] if item["kind"]=="Pod" and item["metadata"]["uid"]==actor["uid"])
    projection=next(source["serviceAccountToken"] for volume in pod["spec"]["volumes"]
                    for source in volume.get("projected",{}).get("sources",[]) if "serviceAccountToken" in source)
    volume_valid=(projection["audience"]=="gd4-s3-lab" and projection["expirationSeconds"]==600
                  and pod["spec"]["automountServiceAccountToken"] is False
                  and pod["spec"]["serviceAccountName"]==actor["name"])
    quality=json.loads((run/"quality.json").read_text())
    result={"expected_operations":len(expected),"receipts":len(receipts),
            "operations_passed":sum(r["passed"] for r in results),
            "shell_operations":sum(r["kind"]=="process_exec" for r in receipts),
            "network_tool_operations":sum(r["kind"]=="runtime_tool" for r in receipts),
            "token_reads":sum(r["kind"]=="file_read" for r in receipts),
            "projected_token_configuration_valid":volume_valid,
            "credential_export_scan_passed":True,"native_records_verified":len(native),
            "agent_and_loss_metric_checks_passed":metric_valid,"loss_counter_deltas":deltas,
            "operations":results}
    result["passed"]=(set(r["operation_id"] for r in receipts)==expected
                      and len(receipts)==len(expected) and all(r["passed"] for r in results)
                      and volume_valid and metric_valid and quality["capture_checks_passed"])
    write_json(run/"s3-verification.json",result)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    args=parser.parse_args()
    result=verify_s3(args.run)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["passed"] else 1)
