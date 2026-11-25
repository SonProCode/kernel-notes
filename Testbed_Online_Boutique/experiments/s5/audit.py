"""Audit archived S5 smoke/pilots read-only; require matching pilots on both workers."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_scenarios import unpack_copy
from s5_verify import verify_s5


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root",type=Path,default=Path(__file__).resolve().parents[2]/"runs")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(args.runs_root.resolve()):parser.error("Write audit outside runs/")
    results=[]
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.runs_root.glob('s5-*/*') if p.is_file()}
    for p in sorted(args.runs_root.glob('s5-*/manifest.json')):
        m=json.loads(p.read_text(encoding="utf-8"))
        item={"run_id":m["run_id"],"mode":m["mode"],"node":m["node"],"status":m["status"],"included":m["status"]=="completed" and m.get("dataset_status")=="validated"}
        if item["included"]:
            try:
                with tempfile.TemporaryDirectory(prefix="s5-audit-") as directory:
                    unpack_copy(p.parent,Path(directory));proof=verify_s5(Path(directory))
                item.update(passed=proof["passed"],errors=proof["errors"],uploads=proof.get("uploads"),received=proof.get("received"),
                    payload_bytes=proof.get("received_payload_bytes"),native_counts=proof.get("native_event_counts"),
                    kernel_send_bytes_requested=proof.get("kernel_send_bytes_requested"),locust_requests=proof.get("locust_requests"),
                    locust_by_phase=proof.get("locust_by_phase"),events_by_label=proof.get("events_by_label"),
                    receiver_peer_ips=proof.get("receiver_peer_ips"),code_bundle_sha256=m["code_bundle_sha256"],
                    actor_image_id=m["actor"]["image_id"],locust_image_id=m["locust"]["image_id"],calls=m["s5"]["calls"])
            except Exception as error:item.update(passed=False,error=f"{type(error).__name__}: {error}")
        results.append(item)
    pilots=[r for r in results if r["included"] and r["mode"]=="pilot"]
    same=bool(pilots) and all(len({p.get(key) for p in pilots})==1 for key in ("code_bundle_sha256","actor_image_id","locust_image_id"))
    unchanged=all(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in originals.items())
    report={"runs":results,"analysis_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "verifier_sha256":hashlib.sha256((Path(__file__).resolve().parents[1]/"s5_verify.py").read_bytes()).hexdigest(),
        "pilots_reviewed":len(pilots),"same_pilot_sources_and_images":same,"historical_evidence_unchanged":unchanged,
        "pilot_uploads":sum(r.get("uploads",0) or 0 for r in pilots),"pilot_received_payload_bytes":sum(r.get("payload_bytes",0) or 0 for r in pilots),
        "passed":bool(pilots) and {r["node"] for r in pilots}=={"w1","w2"} and all(r.get("calls")==60 and r.get("passed") for r in pilots) and same and unchanged,
        "scope":"Functional pilot and labelled synthetic uploads; official cohort/detector/mitigation not certified"}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({k:v for k,v in report.items() if k!="runs"},indent=2))
    for r in results:print(r["run_id"],r.get("passed","excluded"),r.get("errors",[]))
    raise SystemExit(not report["passed"])


if __name__=="__main__":main()
