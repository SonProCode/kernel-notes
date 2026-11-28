"""Audit the finished part of a stopped repeat batch without promoting interrupted cases."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from audit_scenarios import unpack_copy
from repeat_review import verify_case
from repeat_support import now, save, source_digest
from s5_verify import verify_s5


def hashes(paths):
    return {str(p):source_digest(p) for root in paths for p in root.rglob("*") if p.is_file()}


def review(batch):
    batch=Path(batch).resolve();state=json.loads((batch/"batch.json").read_text())
    plan=json.loads((batch/"protocol.json").read_text())
    originals=[batch,*[batch.parent/c["run_id"] for c in state["cases"] if c.get("run_id")]]
    before=hashes(originals);cases=[]
    for case in state["cases"]:
        if not case.get("run_id"):continue
        original=batch.parent/case["run_id"]
        item={"case_id":case["case_id"],"run_id":case["run_id"],"batch_status":case["status"],"counted_as_completed":case["status"]=="completed"}
        try:
            with tempfile.TemporaryDirectory(prefix="partial-repeat-") as temp:
                temp=Path(temp);unpack_copy(original,temp)
                if case["status"]=="completed":
                    integrity=json.loads((original/"archive-integrity.json").read_text())
                    assert source_digest(original/"dataset.tar.gz")==integrity["archive_sha256"]
                    assert all(source_digest(temp/n)==h for n,h in integrity["verified_member_sha256"].items())
                    item.update(verify_case(temp,case,plan))
                elif "s5" in json.loads((temp/"manifest.json").read_text()):
                    item.update(posthoc_verification=verify_s5(temp),disposition="Historical stopped case retained; posthoc proof never changes original status")
        except Exception as error:item.update(passed=False,error=type(error).__name__+": "+str(error))
        cases.append(item);print(item["case_id"],item.get("passed"),item.get("posthoc_verification",{}).get("passed"),flush=True)
    unchanged=before==hashes(originals)
    finished=[c for c in cases if c["counted_as_completed"]]
    return {"checked_at":now(),"batch":batch.name,"historical_batch_status":state["status"],
            "completed_cases_reviewed":len(finished),"completed_cases_passed":sum(c.get("passed") is True for c in finished),
            "original_evidence_unchanged":unchanged,"passed":bool(finished) and unchanged and all(c.get("passed") for c in finished),
            "cohort_complete":False,"cases":cases,"analysis_sha256":source_digest(Path(__file__)),
            "scope":"Partial batch evidence audit; not certification of the planned 24-run cohort"}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("batch",type=Path);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(a.batch.resolve().parent):p.error("Keep new analysis outside historical runs/")
    result=review(a.batch);save(a.output,result)
    print(json.dumps({k:v for k,v in result.items() if k!="cases"},ensure_ascii=False,indent=2))
    raise SystemExit(not result["passed"])


if __name__=="__main__":main()
