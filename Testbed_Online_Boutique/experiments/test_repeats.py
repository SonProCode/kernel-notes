"""Schedule, stop conditions and lossless evidence packaging tests without lab mutations."""
from collections import Counter
import copy
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from repeat_batch import health_errors
from repeat_support import archive_run, check_sources, make_cases, save, source_digest
from repeat_review import replay_v4
from audit_scenarios import unpack_copy


class ScheduleTests(unittest.TestCase):
    def test_three_core_repetitions_and_six_controls(self):
        cases=make_cases()
        self.assertEqual(len(cases),24)
        self.assertEqual(len({c["case_id"] for c in cases}),24)
        core=Counter(c["family"] for c in cases if c["variant"]=="action")
        self.assertEqual(core,{f"S{i}":3 for i in range(6)})
        self.assertEqual(sum(c["variant"]=="control" for c in cases),6)
        self.assertEqual([next(c["actor_node"] for c in cases if c["round"]==i and c["family"]=="S1") for i in (1,2,3)],["w1","w2","w1"])

    def test_schedule_is_reproducible_and_pair_configuration_matches(self):
        self.assertEqual(make_cases(42),make_cases(42))
        self.assertNotEqual(make_cases(42),make_cases(43))
        for i in (1,2,3):
            for f in ("S4","S5"):
                pair=[c for c in make_cases() if c["round"]==i and c["family"]==f]
                for flag in ("--node","--loadgen-node","--locust-seed","--warmup","--pre","--recovery"):
                    self.assertEqual(pair[0]["args"][pair[0]["args"].index(flag)+1],pair[1]["args"][pair[1]["args"].index(flag)+1])
                self.assertEqual(pair[0]["variant"],"action" if i==2 else "control")

    def test_changed_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/"runner.py").write_text("first")
            frozen={"runner.py":source_digest(root/"runner.py")}
            check_sources(root,frozen);(root/"runner.py").write_text("changed")
            with self.assertRaisesRegex(RuntimeError,"source changed"):check_sources(root,frozen)


class ArchiveTests(unittest.TestCase):
    def fixture(self,root):
        run=root/"s1-test";run.mkdir()
        save(run/"manifest.json",{"status":"completed","dataset_status":"validated"})
        (run/"raw").mkdir();(run/"raw/lab-w1.ndjson").write_bytes(b'{"event":1}\n')
        (run/"source").mkdir();(run/"source/actor.py").write_bytes(b"pass\n")
        (run/"normalized.ndjson").write_bytes(b'{"normal":true}\n')
        return run

    def test_archive_round_trip_preserves_raw_and_source_before_releasing_disk(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=self.fixture(root)
            proof=archive_run(run,root)
            self.assertTrue(proof["plain_files_released_after_verification"])
            self.assertFalse((run/"raw").exists())
            with tarfile.open(run/"dataset.tar.gz") as t:
                self.assertEqual(t.extractfile("raw/lab-w1.ndjson").read(),b'{"event":1}\n')
                self.assertEqual(t.extractfile("source/actor.py").read(),b"pass\n")

    def test_failed_run_not_repacked_and_raw_retained(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=self.fixture(root);save(run/"manifest.json",{"status":"failed"})
            with self.assertRaises(ValueError):archive_run(run,root)
            self.assertTrue((run/"raw/lab-w1.ndjson").exists())

    def test_preexisting_archive_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=self.fixture(root);(run/"dataset.tar.gz").write_bytes(b"existing")
            with self.assertRaises(FileExistsError):archive_run(run,root)
            self.assertEqual((run/"dataset.tar.gz").read_bytes(),b"existing")
            self.assertTrue((run/"raw/lab-w1.ndjson").exists())

    def test_archive_hash_failure_retains_plain_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=self.fixture(root)
            with patch("repeat_support.source_digest",return_value="bad"):
                with self.assertRaisesRegex(RuntimeError,"content mismatch"):archive_run(run,root)
            self.assertTrue((run/"raw/lab-w1.ndjson").exists())
            self.assertFalse((run/"dataset.tar.gz").exists())

    def test_escaped_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=self.fixture(root);other=root/"other";other.mkdir()
            with self.assertRaises(ValueError):archive_run(run,other)


class HealthTests(unittest.TestCase):
    def fixture(self):
        pod={"phase":"Running","ready":True}
        return {"nodes":{n:{"Ready":"True","MemoryPressure":"False","DiskPressure":"False","PIDPressure":"False"} for n in ("lab-cp","lab-w1","lab-w2")},
            "application_pods":{"app":pod},"agents":{"a":pod,"b":pod},"disk_free_bytes":100,
            "loadgenerator_spec":{},"policies":[]}

    def test_healthy_unchanged_cluster_passes(self):
        s=self.fixture();self.assertEqual(health_errors(s,s,10),[])

    def test_memory_pressure_disk_and_agent_restart_stop_batch(self):
        initial=self.fixture();changed=copy.deepcopy(initial)
        changed["nodes"]["lab-w1"]["MemoryPressure"]="True";changed["disk_free_bytes"]=1
        changed["agents"]["a"]["restarts"]=1
        errors=health_errors(changed,initial,10)
        self.assertIn("Unhealthy node: lab-w1",errors)
        self.assertIn("Disk below protocol minimum",errors)
        self.assertIn("Environment changed: agents",errors)

    def test_not_ready_application_is_rejected_even_at_initial_checkpoint(self):
        s=self.fixture();s["application_pods"]["app"]["ready"]=False
        self.assertTrue(health_errors(s,None,10))


class ReplayCompatibilityTests(unittest.TestCase):
    def test_new_review_replays_real_v4_without_changing_archived_run(self):
        runs=Path(__file__).resolve().parents[1]/"runs"
        source=runs/"s0-20261125T113929Z-1995886"
        if not source.exists():self.skipTest("Bundled normal reference required")
        before={p.relative_to(source).as_posix():source_digest(p) for p in source.rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);unpack_copy(source,d);self.assertTrue(replay_v4(d))
        self.assertEqual({p.relative_to(source).as_posix():source_digest(p) for p in source.rglob("*") if p.is_file()},before)


if __name__=="__main__":unittest.main()
