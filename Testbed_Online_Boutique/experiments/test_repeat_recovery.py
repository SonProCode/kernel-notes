"""Regression coverage for bounded snapshot retries, streamed raw access and explicit continuation."""
import json
from pathlib import Path
import subprocess
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

import repeat_batch
from repeat_support import save,source_digest
from s5_verify import RawEventFile


class StreamingRawTests(unittest.TestCase):
    def test_byte_offsets_handle_unicode_and_random_access(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"raw.ndjson";values=[{"path":"đường/dẫn","index":i} for i in range(4)]
            p.write_text("".join(json.dumps(v,ensure_ascii=False)+"\n" for v in values),encoding="utf-8",newline="\n")
            records=RawEventFile(p)
            self.assertEqual(list(records),values)
            self.assertEqual(records[2],values[2])
            self.assertEqual(records[-1],values[-1])
            with self.assertRaises(IndexError):records[4]

    def test_invalid_json_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"raw";p.write_bytes(b'{"ok":1}\nnot-json\n')
            records=RawEventFile(p)
            with self.assertRaises(json.JSONDecodeError):list(records)

    def test_index_memory_is_bounded_by_line_count_not_payload_size(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"raw"
            with p.open("wb") as out:
                line=json.dumps({"payload":"x"*2048}).encode()+b"\n"
                for _ in range(10000):out.write(line)
            tracemalloc.start()
            try:
                records=RawEventFile(p);_,peak=tracemalloc.get_traced_memory()
            finally:tracemalloc.stop()
            self.assertEqual(len(records),10000)
            self.assertLess(peak,2*1024**2)
            self.assertEqual(records[5000]["payload"],"x"*2048)


class ReadRetryTests(unittest.TestCase):
    def timeout(self):return subprocess.TimeoutExpired(["k3s","kubectl","get","nodes"],12)

    def test_single_timeout_is_recorded_then_fresh_read_is_returned(self):
        with patch.object(repeat_batch,"snapshot",side_effect=[self.timeout(),{"nodes":{"fresh":True}}]),patch.object(repeat_batch.time,"sleep"):
            state=repeat_batch.read_snapshot()
        self.assertEqual(state["nodes"],{"fresh":True})
        self.assertEqual(len(state["read_timeouts"]),1)

    def test_two_timeouts_fail_closed(self):
        with patch.object(repeat_batch,"snapshot",side_effect=[self.timeout(),self.timeout()]),patch.object(repeat_batch.time,"sleep"):
            with self.assertRaises(subprocess.TimeoutExpired):repeat_batch.read_snapshot()

    def test_non_timeout_errors_are_not_hidden_by_retry(self):
        with patch.object(repeat_batch,"snapshot",side_effect=PermissionError("denied")) as read:
            with self.assertRaises(PermissionError):repeat_batch.read_snapshot()
            self.assertEqual(read.call_count,1)


class EnvironmentRoundTripTests(unittest.TestCase):
    def state(self):
        pod={"phase":"Running","ready":True,"containers":[("main","image@sha256:original",0)]}
        return {"nodes":{n:{"Ready":"True"} for n in ("lab-cp","lab-w1","lab-w2")},
                "agents":{"a":pod,"b":pod},"application_pods":{"p":pod},
                "loadgenerator_spec":{},"policies":[],"disk_free_bytes":100}

    def test_json_round_trip_does_not_change_environment_identity(self):
        live=self.state();saved=json.loads(json.dumps(live))
        self.assertEqual(repeat_batch.health_errors(live,saved,10),[])

    def test_changed_image_is_still_rejected_after_json_round_trip(self):
        live=self.state();saved=json.loads(json.dumps(live))
        saved["application_pods"]["p"]["containers"][0][1]="changed-image"
        self.assertIn("Environment changed: application_pods",repeat_batch.health_errors(live,saved,10))


class ContinuationTests(unittest.TestCase):
    def fixture(self,base):
        exp=base/"experiments";exp.mkdir();(exp/"audits").mkdir()
        old=base/"runs"/"batch-old";old.mkdir(parents=True)
        run=base/"runs"/"run-one";run.mkdir();(run/"dataset.tar.gz").write_bytes(b"immutable")
        args=["--scenario","S1","--mode","official"]
        state={"nodes":{n:{"Ready":"True"} for n in ("lab-cp","lab-w1","lab-w2")},
               "agents":{n:{"phase":"Running","ready":True} for n in ("a","b")},
               "application_pods":{"p":{"phase":"Running","ready":True}},
               "loadgenerator_spec":{},"policies":[],"disk_free_bytes":100}
        save(old/"environment-after.json",state)
        save(run/"manifest.json",{"dataset_status":"validated","script_sha256":{"runner.py":"expected"}})
        save(old/"batch.json",{"cases":[{"case_id":"r1-s1-action","args":args,"status":"completed","run_id":"run-one","archive":source_digest(run/"dataset.tar.gz"),"return_code":0}]})
        audit=exp/"audits"/"partial.json"
        save(audit,{"passed":True,"original_evidence_unchanged":True,"batch":"batch-old","cases":[{"case_id":"r1-s1-action","run_id":"run-one","counted_as_completed":True,"passed":True}]})
        plan={"minimum_disk_free_bytes":10,"source_sha256":{"runner.py":"expected"},
              "cases":[{"case_id":"r1-s1-action","args":args},{"case_id":"r1-s5-control","args":[]}],
              "carry_forward":{"batch":"batch-old","audit_path":"audits/partial.json","audit_sha256":source_digest(audit),"case_ids":["r1-s1-action"]}}
        return exp,state,plan

    def test_only_audited_completed_case_is_inherited_and_other_case_stays_pending(self):
        with tempfile.TemporaryDirectory() as d:
            exp,state,plan=self.fixture(Path(d))
            with patch.object(repeat_batch,"ROOT",exp):cases=repeat_batch.carry_forward(plan,state)
            self.assertTrue(cases[0]["carried_forward"]);self.assertEqual(cases[0]["source_batch"],"batch-old")
            self.assertEqual(cases[1]["status"],"pending")

    def test_changed_runtime_source_blocks_carry_forward(self):
        with tempfile.TemporaryDirectory() as d:
            exp,state,plan=self.fixture(Path(d));plan["source_sha256"]["runner.py"]="different"
            with patch.object(repeat_batch,"ROOT",exp):
                with self.assertRaisesRegex(ValueError,"runtime source differs"):repeat_batch.carry_forward(plan,state)

    def test_changed_audit_checksum_blocks_carry_forward(self):
        with tempfile.TemporaryDirectory() as d:
            exp,state,plan=self.fixture(Path(d));plan["carry_forward"]["audit_sha256"]="bad"
            with patch.object(repeat_batch,"ROOT",exp):
                with self.assertRaisesRegex(ValueError,"audit checksum"):repeat_batch.carry_forward(plan,state)


if __name__=="__main__":unittest.main()
