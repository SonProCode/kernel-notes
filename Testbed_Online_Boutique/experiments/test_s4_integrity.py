"""Adversarial S4 evidence tests on a temporary copy of a bundled real pilot."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_scenarios import unpack_copy
from s4_verify import verify_s4, percentile, summarize
from s4_support import Guard
from check_cleanup import find_owned_run


class IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix="s4-negative-")
        cls.root=Path(cls.temporary.name)
        source=Path(__file__).resolve().parents[1]/"runs/s4-20261123T050441Z-1864262"
        if not (source/"manifest.json").exists(): raise unittest.SkipTest("Bundled pilot evidence is required")
        unpack_copy(source,cls.root)
        proof=verify_s4(cls.root)
        if not proof["passed"]: raise AssertionError(proof)
        cls.saved={p.relative_to(cls.root).as_posix():p.read_bytes() for p in cls.root.iterdir() if p.is_file()}

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def setUp(self):
        for p in self.root.iterdir():
            if p.is_file() and p.name not in self.saved: p.unlink()
        for name,data in self.saved.items(): (self.root/name).write_bytes(data)

    def edit(self,name,change):
        value=json.loads(self.saved[name]);change(value)
        (self.root/name).write_text(json.dumps(value),encoding="utf-8")

    def rejected(self): self.assertFalse(verify_s4(self.root)["passed"])

    def edit_locust(self,change):
        values=[json.loads(x) for x in self.saved["locust-requests.ndjson"].splitlines()]
        change(values[0])
        (self.root/"locust-requests.ndjson").write_text("\n".join(json.dumps(v) for v in values)+"\n",encoding="utf-8")
        index=0;output=[]
        for line in self.saved["locust.raw.log"].decode().splitlines():
            if line.startswith("S4REQ "): line="S4REQ "+json.dumps(values[index]);index+=1
            output.append(line)
        (self.root/"locust.raw.log").write_text("\n".join(output)+"\n",encoding="utf-8")

    def test_original_real_pilot(self): self.assertTrue(verify_s4(self.root)["passed"])
    def test_final_before_last_request_rejected_even_if_counters_match(self):
        lines=self.saved["locust.raw.log"].decode().splitlines()
        final=next(line for line in lines if line.startswith("S4FINAL "))
        lines.remove(final)
        index=next(i for i,line in enumerate(lines) if line.startswith("S4REQ "))
        lines.insert(index,final)
        (self.root/"locust.raw.log").write_text("\n".join(lines)+"\n")
        self.rejected()
    def test_nan_resource_series(self):
        def mutate(d):
            for v in d.values():
                for row in v["data"]["result"]: row["values"]=[[t,"NaN"] for t,a in row["values"]]
        self.edit("prometheus-resources.json",mutate);self.rejected()
    def test_resource_missing_measurement_points(self):
        def mutate(d):
            for v in d.values():
                for row in v["data"]["result"]:row["values"]=row["values"][:1]
        self.edit("prometheus-resources.json",mutate);self.rejected()
    def test_one_guard_sample(self):
        (self.root/"guard.ndjson").write_bytes(self.saved["guard.ndjson"].splitlines()[0]+b"\n");self.rejected()
    def test_guard_missing_recovery(self):
        records=[x for x in self.saved["guard.ndjson"].splitlines() if json.loads(x)["phase"]!="recovery"]
        (self.root/"guard.ndjson").write_bytes(b"\n".join(records)+b"\n");self.rejected()
    def test_guard_gap(self):
        records=self.saved["guard.ndjson"].splitlines()
        (self.root/"guard.ndjson").write_bytes(b"\n".join([records[0],*records[8:]])+b"\n");self.rejected()
    def test_negative_latency_even_when_raw_and_derived_agree(self):
        self.edit_locust(lambda r:r.update(duration_ms=-1));self.rejected()
    def test_nan_latency(self):
        self.edit_locust(lambda r:r.update(duration_ms=float("nan")));self.rejected()
    def test_invalid_http_status(self):
        self.edit_locust(lambda r:r.update(status_code=-1));self.rejected()
    def test_reversed_request_time(self):
        self.edit_locust(lambda r:r.update(ended="2000-01-01T00:00:00Z"));self.rejected()
    def test_derived_locust_tampered(self):
        records=[json.loads(x) for x in self.saved["locust-requests.ndjson"].splitlines()];records[0]["duration_ms"]=999
        (self.root/"locust-requests.ndjson").write_text("\n".join(json.dumps(r) for r in records)+"\n");self.rejected()
    def test_locust_failure_counter_mismatch(self):
        runtime=json.loads(self.saved["locust-runtime.json"]);runtime["final"][0]["locust_num_failures"]=1
        (self.root/"locust-runtime.json").write_text(json.dumps(runtime))
        lines=["S4FINAL "+json.dumps(runtime["final"][0]) if x.startswith("S4FINAL ") else x for x in self.saved["locust.raw.log"].decode().splitlines()]
        (self.root/"locust.raw.log").write_text("\n".join(lines)+"\n");self.rejected()
    def test_duplicate_worker_up(self):
        self.edit("metrics-before.json",lambda d:d["agent_up"]["data"].update(result=[d["agent_up"]["data"]["result"][0]]*2));self.rejected()
    def test_wrong_loss_counter_names(self):
        def mutate(d):d["loss_and_export"]["data"]["result"][0]["metric"]["__name__"]="unrelated_counter"
        self.edit("metrics-before.json",mutate);self.rejected()
    def test_counter_increase(self):
        self.edit("metrics-after.json",lambda d:d["loss_and_export"]["data"]["result"][0].update(value=[0,"1"]));self.rejected()
    def test_negative_skip_counter(self):
        self.edit("s4-client-summary.json",lambda d:d.update(skipped_busy=-1,skipped_late=6));self.rejected()
    def test_client_configuration_mismatch(self):
        self.edit("s4-client-summary.json",lambda d:d.update(configured_rate=3));self.rejected()
    def test_wrong_request_target(self):
        lines=[json.loads(x) for x in self.saved["actor-receipts.ndjson"].splitlines()];lines[0]["ip"]="10.43.0.99"
        (self.root/"actor-receipts.ndjson").write_text("\n".join(json.dumps(x) for x in lines)+"\n");self.rejected()
    def contract2(self):
        self.edit("manifest.json",lambda m:m["s4"].update(verification_contract=2))
        (self.root/"cleanup.json").write_text(json.dumps({"passed":True,"remaining":{"pods":0,"deployments":0,"configmaps":0},"original_loadgenerator_unchanged":True}))
        for stage in ("before","after"):
            def mutate(d):
                values=[{"metric":{"node":node},"value":[0,"5"]} for node in ("lab-w1","lab-w2")]
                d["agent_scrape_age_seconds"]={"status":"success","data":{"result":values}}
            self.edit("metrics-"+stage+".json",mutate)
    def test_new_contract_accepts_complete_mock_cleanup_and_freshness(self):
        self.contract2();self.assertTrue(verify_s4(self.root)["passed"])
    def test_new_contract_rejects_missing_cleanup(self):
        self.contract2();(self.root/"cleanup.json").unlink();self.rejected()
    def test_new_contract_rejects_remaining_pod(self):
        self.contract2();d=json.loads((self.root/"cleanup.json").read_text());d["remaining"]["pods"]=1
        (self.root/"cleanup.json").write_text(json.dumps(d));self.rejected()
    def test_new_contract_rejects_stale_scrape(self):
        self.contract2();p=self.root/"metrics-after.json";d=json.loads(p.read_text());d["agent_scrape_age_seconds"]["data"]["result"][0]["value"][1]="120"
        p.write_text(json.dumps(d));self.rejected()
    def test_timeline_order(self):
        lines=self.saved["timeline.ndjson"].splitlines();lines[1],lines[2]=lines[2],lines[1]
        (self.root/"timeline.ndjson").write_bytes(b"\n".join(lines)+b"\n");self.rejected()
    def test_duplicate_native_reference(self):
        lines=self.saved["normalized.ndjson"].splitlines();line=next(x for x in lines if json.loads(x).get("operation_id"))
        (self.root/"normalized.ndjson").write_bytes(b"\n".join([*lines,line])+b"\n");self.rejected()
    def test_unresolvable_native_reference(self):
        lines=[json.loads(x) for x in self.saved["normalized.ndjson"].splitlines()]
        next(x for x in lines if x.get("operation_id"))["raw_line"]=100000000
        (self.root/"normalized.ndjson").write_text("\n".join(json.dumps(x) for x in lines)+"\n");self.rejected()
    def test_quality_counts_tampered(self):
        self.edit("quality.json",lambda d:d.update(operations=999));self.rejected()
    def test_normalized_labels_tampered(self):
        lines=[json.loads(x) for x in self.saved["normalized.ndjson"].splitlines()];lines[0]["label"]="attack" if lines[0]["label"]!="attack" else "normal"
        (self.root/"normalized.ndjson").write_text("\n".join(json.dumps(x) for x in lines)+"\n");self.rejected()


class StatisticAndGuardTests(unittest.TestCase):
    def test_cleanup_selector_ignores_transcript_file(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/"runs").mkdir()
            (root/"runs/s4-strict-regression.log").write_text("transcript")
            own=root/"runs/s4-20261123T120000Z-123";own.mkdir();(own/"manifest.json").write_text("{}")
            self.assertEqual(find_owned_run(root,"S4",set(),123),own)
    def test_cleanup_selector_ignores_unrelated_runner(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/"runs").mkdir()
            other=root/"runs/s4-20261123T120000Z-999";other.mkdir();(other/"manifest.json").write_text("{}")
            self.assertIsNone(find_owned_run(root,"S4",set(),123))
    def test_nearest_rank_p95(self):self.assertEqual(percentile(list(range(1,21)),.95),19)
    def test_errors_not_silently_counted_as_low_latency_success(self):
        r=summarize([{"duration_ms":1,"error":"HTTPError","status_code":500},{"duration_ms":50,"error":None,"status_code":200}])
        self.assertEqual(r["failures"],1);self.assertEqual(r["p95_ms"],50)
    def test_dead_guard_detected(self):
        g=object.__new__(Guard)
        import threading
        g.triggered=threading.Event();g.stop=threading.Event();g.thread=type("Thread",(),{"is_alive":lambda _:False})();g.reason=None
        self.assertEqual(g.failure_reason(),["guard_thread_not_alive"])
    def test_guard_write_failure_fails_closed(self):
        g=object.__new__(Guard)
        import threading
        g.output=Path("unused");g.triggered=threading.Event();g.stop=threading.Event();g.reason=None
        with patch("pathlib.Path.open",side_effect=OSError("disk full")):g.loop()
        self.assertTrue(g.triggered.is_set());self.assertIn("guard_thread_error",g.reason[0])
    def test_stale_guard_detected(self):
        g=object.__new__(Guard)
        import threading
        g.triggered=threading.Event();g.stop=threading.Event();g.thread=type("Thread",(),{"is_alive":lambda _:True})()
        g.reason=None;g.started_monotonic=1;g.last_sample_monotonic=2
        with patch("s4_support.time.monotonic",return_value=100):self.assertEqual(g.failure_reason(),["guard_heartbeat_stale"])


if __name__=="__main__":unittest.main()
