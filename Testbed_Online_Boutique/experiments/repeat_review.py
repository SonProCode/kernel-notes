"""Read-only final review of the repeated cohort; outputs only into its batch directory."""
import argparse
from collections import Counter
import contextlib
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import statistics
import tempfile

from audit_scenarios import unpack_copy, check_metrics, check_rpc_native
from label import normalize, timestamp
from repeat_support import now, save, source_digest
from review_controls import compare_pair, protocol_errors, service_graph
from s1_verify import verify_s1
from s2_verify import verify_run as verify_s2
from s2_audit import audit as audit_s2
from s3_verify import verify_s3
from s4_verify import verify_s4
from s5_verify import verify_s5


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def stream(path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def same_rows(a, b):
    return all(x == y for x, y in itertools.zip_longest(stream(a), stream(b), fillvalue=None))


def replay_v4(run):
    previous_quality = read(run/"quality.json")
    for name in ("normalized.ndjson", "labeled-windows.ndjson"):
        (run/name).rename(run/("archived-"+name))
    with contextlib.redirect_stdout(io.StringIO()):
        quality = normalize(run)
    return quality == previous_quality and quality["capture_checks_passed"] and all(
        same_rows(run/name, run/("archived-"+name)) for name in ("normalized.ndjson", "labeled-windows.ndjson"))


def verify_s0(run):
    m = read(run/"manifest.json")
    errors = []
    if not replay_v4(run):
        errors.append("Raw/normalized/quality replay differs")
    timeline = list(stream(run/"timeline.ndjson"))
    if [p["phase"] for p in timeline] != ["setup", "warmup", "measurement", "finalize"]:
        errors.append("Unexpected S0 phases")
    duration = (timestamp(m["measurement_end"])-timestamp(timeline[2]["time"])).total_seconds()
    if duration < 900 or m["measurement_seconds"] != 900:
        errors.append("S0 must measure at least 900 seconds")
    measured = (e for e in stream(run/"normalized.ndjson") if e["phase"] == "measurement")
    counts = Counter()
    labels = Counter()
    for event in measured:
        counts[event["node"]] += 1
        labels[event["label"]] += 1
    if set(counts) != {"lab-w1", "lab-w2"} or set(labels) != {"normal"}:
        errors.append("Normal measurement missing workers or labels")
    if list(stream(run/"actor-receipts.ndjson")) or m.get("actor"):
        errors.append("Pure business S0 contains actor actions")
    graph = service_graph(read(run/"boutique-before.json")["items"],
                          (e for e in stream(run/"normalized.ndjson") if e["phase"] == "measurement"))
    text = (run/"locust.log").read_text(encoding="utf-8")
    matches = re.findall(r"\bPOST\s+/cart/checkout\s+(\d+)\s+(\d+)\(", text)
    checkout = {"requests": int(matches[-1][0]), "failures": int(matches[-1][1]),
                "scope":"Last cumulative Locust table includes warm-up"} if matches else None
    if not checkout or checkout["requests"] <= checkout["failures"]:
        errors.append("No successful normal checkout")
    metrics = check_metrics(run)
    if not metrics["passed"]:
        errors.append("Agent/loss metrics failed")
    return {"passed":not errors, "errors":errors, "measurement_seconds":duration,
            "events_by_node":dict(counts), "events_by_label":dict(labels),
            "service_graph":graph, "checkout":checkout, "metrics":metrics,
            "scope":"Business normal reference; application errors retained, no request-level S0 latency claim"}


def verify_case(directory, case, plan):
    m = read(directory/"manifest.json")
    errors = protocol_errors(case["args"], m, read(directory/"boutique-before.json")["items"])
    if m["mode"] != "official" or m["status"] != "completed" or m.get("dataset_status") != "validated":
        errors.append("Not a completed validated official run")
    hashes = m["script_sha256"]
    for name, value in hashes.items():
        if source_digest(directory/"source"/name) != value:
            errors.append("Source snapshot mismatch: "+name)
        plan_name = "../telemetry/normalize.py" if name == "telemetry/normalize.py" else name
        if plan["source_sha256"].get(plan_name) != value:
            errors.append("Source differs from frozen protocol: "+name)
    if hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest() != m["code_bundle_sha256"]:
        errors.append("Source bundle mismatch")
    if "s5" in m:
        proof = verify_s5(directory)
    elif "s4" in m:
        proof = verify_s4(directory)
    elif m["scenario_id"] == "S0":
        proof = verify_s0(directory)
    else:
        if not replay_v4(directory):
            errors.append("V4 raw/normalized/quality replay differs")
        if m["scenario_id"] == "S1":
            proof = verify_s1(directory)
        elif m["scenario_id"] == "S2":
            proof = verify_s2(directory)
            native = check_rpc_native(directory,m)
            proof["independent_native_audit"] = native
            proof["identity_audit"] = audit_s2(directory)
        else:
            proof = verify_s3(directory)
        metrics = check_metrics(directory)
        proof["loss_metrics"] = metrics
        if metrics["passed"] is not True:
            errors.append("Agent/loss metrics failed")
    return {"passed":proof["passed"] and not errors, "errors":errors, "proof":proof,
            "source_bundle":m["code_bundle_sha256"]}


def review(batch):
    record, plan = read(batch/"batch.json"), read(batch/"protocol.json")
    errors, cases, pairs = [], [], []
    if record["protocol_sha256"] != source_digest(batch/"protocol.json"):
        errors.append("Protocol hash mismatch")
    if record["coordinator_sha256"] != source_digest(batch/"coordinator.py"):
        errors.append("Coordinator hash mismatch")
    if [c["case_id"] for c in record["cases"]] != [c["case_id"] for c in plan["cases"]]:
        errors.append("Case schedule differs")
    for case, expected in zip(record["cases"],plan["cases"]):
        item = {"case_id":case["case_id"], "run_id":case.get("run_id"),
                "source_batch":case.get("source_batch",batch.name),"carried_forward":bool(case.get("carried_forward"))}
        try:
            if case["args"] != expected["args"] or case["status"] != "completed":
                raise ValueError("Incomplete or changed case")
            original = batch.parent/case["run_id"]
            archive = read(original/"archive-integrity.json")
            if source_digest(original/"dataset.tar.gz") != archive["archive_sha256"]:
                raise ValueError("Archive checksum mismatch")
            with tempfile.TemporaryDirectory(prefix="repeat-review-") as temp:
                directory = Path(temp);unpack_copy(original,directory)
                for name, value in archive["verified_member_sha256"].items():
                    if source_digest(directory/name) != value:
                        raise ValueError("Archived member changed: "+name)
                item.update(verify_case(directory,case,plan))
        except Exception as error:
            item.update(passed=False,error=type(error).__name__+": "+str(error))
        if not item.get("passed"):
            errors.append("Case review failed: "+case["case_id"])
        cases.append(item)
        print("Reviewed:",item["case_id"],item.get("passed"),flush=True)
    indexed={c["case_id"]:c for c in record["cases"]}
    for round_index in (1,2,3):
        for family in ("s4","s5"):
            c,a=(indexed[f"r{round_index}-{family}-{v}"] for v in ("control","action"))
            try:
                with tempfile.TemporaryDirectory(prefix="repeat-pair-") as temp:
                    temp=Path(temp);cp=temp/"control";ap=temp/"action";cp.mkdir();ap.mkdir()
                    unpack_copy(batch.parent/c["run_id"],cp);unpack_copy(batch.parent/a["run_id"],ap)
                    pair=compare_pair(cp,ap)
                pairs.append({"round":round_index,**pair})
                if not pair["passed"]:
                    errors.append(f"Unmatched pair r{round_index}-{family}")
            except Exception as error:
                errors.append(f"Pair unreadable r{round_index}-{family}: {error}")
    statistics_by_family = {}
    for family in ("S4","S5"):
        values=[]
        for case,item in zip(record["cases"],cases):
            if case["family"] != family or case["variant"] != "action" or not item.get("passed"):
                continue
            phases=item["proof"].get("locust_by_phase",{})
            if phases.get("attack",{}).get("p95_ms") is not None:
                values.append(phases["attack"]["p95_ms"])
        if values:
            statistics_by_family[family]={"run_count":len(values),"p95_ms_per_run":values,
                "mean_of_run_p95_ms":statistics.mean(values),"min_run_p95_ms":min(values),
                "max_run_p95_ms":max(values),"note":"Descriptive across runs; not pooled p95 or a causal confidence interval"}
    return {"checked_at":now(),"protocol_id":plan["protocol_id"],"passed":not errors,
            "carried_forward_cases":sum(bool(c.get("carried_forward")) for c in record["cases"]),
            "new_cases_executed":sum(c["status"]=="completed" and not c.get("carried_forward") for c in record["cases"]),
            "errors":errors,"cases":cases,"pairs":pairs,"descriptive_statistics":statistics_by_family,
            "review_source_sha256":source_digest(Path(__file__)),
            "scope":"Repeated labelled cohort and matched configurations; detector, mitigation and overhead effectiveness not certified",
            "limitations":["Three repetitions, actor placement w1/w2/w1 is unbalanced",
                "S0/S1-S3 use original Locust without per-request latency; matched performance pairs are S4/S5",
                "PRNG seed does not make concurrent HTTP journeys identical",
                "Normal HTTP errors are retained and must be interpreted with diagnostics",
                *(["Continuation spans a stopped batch and a revised observer; source batches are retained, not a single uninterrupted acquisition"] if plan.get("carry_forward") else [])]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("batch",type=Path);args=p.parse_args()
    result=review(args.batch.resolve())
    save(args.batch/"cohort-review.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("cases","pairs")},ensure_ascii=False,indent=2))
    raise SystemExit(not result["passed"])


if __name__=="__main__":
    main()
