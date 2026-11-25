"""Corrupt only a temporary copy of a bundled S5 smoke; keep captured data intact."""
import json
from pathlib import Path
import tempfile
import unittest

from audit_scenarios import unpack_copy
from s5_verify import verify_s5


class S5IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]/"runs"
        sources=[p.parent for p in sorted(root.glob('s5-*/manifest.json')) if (m:=json.loads(p.read_text()))["mode"]=="smoke" and m.get("dataset_status")=="validated"]
        if not sources:raise unittest.SkipTest("Bundled S5 smoke required")
        cls.temporary=tempfile.TemporaryDirectory(prefix="s5-negative-");cls.root=Path(cls.temporary.name)
        unpack_copy(sources[0],cls.root)
        assert verify_s5(cls.root)["passed"]
        cls.saved={p.name:p.read_bytes() for p in cls.root.iterdir() if p.is_file()}

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def setUp(self):
        for name,data in self.saved.items():(self.root/name).write_bytes(data)

    def edit(self,name,change):
        value=json.loads(self.saved[name]);change(value)
        (self.root/name).write_text(json.dumps(value),encoding="utf-8")

    def edit_rows(self,name,change):
        values=[json.loads(line) for line in self.saved[name].splitlines()];change(values)
        (self.root/name).write_text('\n'.join(json.dumps(v) for v in values)+'\n',encoding="utf-8")

    def rejected(self):self.assertFalse(verify_s5(self.root)["passed"])

    def test_real_smoke_passes(self):self.assertTrue(verify_s5(self.root)["passed"])
    def test_missing_receiver_receipt(self):
        self.edit_rows("receiver.ndjson",lambda r:r.pop(next(i for i,v in enumerate(r) if v["kind"]=="received")));self.rejected()
    def test_receiver_payload_size_tampered(self):
        self.edit_rows("receiver.ndjson",lambda r:next(v for v in r if v["kind"]=="received").update(payload_bytes=1));self.rejected()
    def test_client_ack_tampered(self):
        self.edit_rows("actor-receipts.ndjson",lambda r:r[0]["receiver_acknowledgment"].update(payload_sha256="0"*64));self.rejected()
    def test_duplicate_operation(self):
        self.edit_rows("actor-receipts.ndjson",lambda r:r.append(r[0]));self.rejected()
    def test_external_target_tampered(self):
        self.edit_rows("actor-receipts.ndjson",lambda r:r[0].update(ip="8.8.8.8"));self.rejected()
    def test_native_socket_tampered(self):
        self.edit_rows("normalized.ndjson",lambda r:next(v for v in r if v.get("operation_id"))["socket"].update(dport=443));self.rejected()
    def test_background_feature_tampered(self):
        self.edit_rows("normalized.ndjson",lambda r:next(v for v in r if not v.get("operation_id")).update(binary="/fake/binary"));self.rejected()
    def test_window_label_tampered(self):
        self.edit_rows("labeled-windows.ndjson",lambda r:r[0].update(label="attack"));self.rejected()
    def test_live_receiver_after_cleanup_rejected(self):
        self.edit("cleanup.json",lambda d:d.update(receiver_port_closed=False));self.rejected()
    def test_nonfinite_resources(self):
        def mutate(d):
            for v in d.values():
                for r in v["data"]["result"]:r["values"]=[[t,"NaN"] for t,n in r["values"]]
        self.edit("prometheus-resources.json",mutate);self.rejected()
    def test_missing_guard_phase(self):
        self.edit_rows("guard.ndjson",lambda r:r.__setitem__(slice(None),[v for v in r if v["phase"]!="attack"]));self.rejected()
    def test_official_short_run_rejected(self):
        self.edit("manifest.json",lambda d:d.update(mode="official"));self.rejected()
    def test_loss_counter_increased(self):
        self.edit("metrics-after.json",lambda d:d["loss_and_export"]["data"]["result"][0].update(value=[0,"100"]));self.rejected()
    def test_stale_scrape(self):
        self.edit("metrics-after.json",lambda d:d["agent_scrape_age_seconds"]["data"]["result"][0].update(value=[0,"120"]));self.rejected()
    def test_receiver_root_identity_rejected(self):
        self.edit_rows("receiver.ndjson",lambda r:next(v for v in r if v["kind"]=="receiver_ready").update(uid=0));self.rejected()
    def test_failed_guard_probes_with_reset_streak_rejected(self):
        def change(rows):
            for r in rows:r.update(probe_ok=False,consecutive_probe_failures=0)
        self.edit_rows("guard.ndjson",change);self.rejected()
    def test_missing_guard_probe_result_rejected(self):
        self.edit_rows("guard.ndjson",lambda r:r[0].pop("probe_ok"));self.rejected()
    def test_negative_guard_streak_rejected(self):
        self.edit_rows("guard.ndjson",lambda r:r[0].update(consecutive_probe_failures=-1));self.rejected()
    def test_actor_image_must_match_captured_pod(self):
        self.edit("manifest.json",lambda d:d["actor"].update(image_id="docker.io/library/python@sha256:"+"0"*64));self.rejected()
    def test_locust_image_must_match_captured_pod(self):
        self.edit("manifest.json",lambda d:d["locust"].update(image_id="fake-image"));self.rejected()
    def test_actor_ip_must_match_captured_pod(self):
        self.edit("manifest.json",lambda d:d["actor"].update(ip="10.42.0.254"));self.rejected()
    def test_unhealthy_node_snapshot_rejected(self):
        def mutate(d):
            for c in d["items"][0]["status"]["conditions"]:
                if c["type"]=="MemoryPressure":c["status"]="True"
        self.edit("nodes-after.json",mutate);self.rejected()
    def test_reversed_resource_timestamps_rejected(self):
        def mutate(d):
            for v in d.values():v["data"]["result"][0]["values"].reverse()
        self.edit("prometheus-resources.json",mutate);self.rejected()
    def test_wrong_resource_result_type_rejected(self):
        self.edit("prometheus-resources.json",lambda d:d["frontend_cpu_cores"]["data"].update(resultType="vector"));self.rejected()
    def test_source_hash_tampered(self):
        p=self.root/"source/s5/client.py";original=p.read_bytes()
        try:p.write_bytes(b"changed");self.rejected()
        finally:p.write_bytes(original)


if __name__=="__main__":unittest.main()
