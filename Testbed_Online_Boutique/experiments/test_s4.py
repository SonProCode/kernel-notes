"""Bounded-client and guard failure tests; no cluster or external traffic required."""
import contextlib
import copy
import importlib.util
import io
import itertools
import json
from pathlib import Path
import signal
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import s4_support
import label

spec = importlib.util.spec_from_file_location("s4_client", Path(__file__).parent / "s4/client.py")
client = importlib.util.module_from_spec(spec); spec.loader.exec_module(client)


class S4Tests(unittest.TestCase):
    def run_fake(self, rate, concurrency, delay):
        ports = itertools.count(40000)

        class Connection:
            def __init__(self, *args, **kwargs):
                self.sock = SimpleNamespace(getsockname=lambda: ("10.42.1.1", next(ports)))

            def connect(self): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return SimpleNamespace(status=200, read=self.read)
            def read(self, size): time.sleep(delay); return b"example"
            def close(self): pass

        old = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as stdout:
                root = Path(directory)
                with patch.object(client, "Path", lambda name: root / Path(name).name), patch.object(client.http.client, "HTTPConnection", Connection):
                    client.run({"ip": "10.43.0.1", "target_ips": ["10.43.0.1"], "target_ports": [80]}, rate, 1, concurrency)
                records = [json.loads(line) for line in stdout.getvalue().splitlines()]
                summary = json.loads((root / "s4-client-summary.json").read_text())
                self.assertFalse((root / "s4-action.pid").exists())
                return records, summary
        finally:
            for sig, handler in old.items(): signal.signal(sig, handler)

    def test_paced_requests_have_unique_ports_and_receipts(self):
        records, summary = self.run_fake(3, 2, 0.02)
        self.assertEqual(len(records), 3)
        self.assertEqual(summary["submitted"], 3)
        self.assertEqual(len({r["source_port"] for r in records}), 3)
        self.assertTrue(all(r["outcome"] == "http_success" for r in records))

    def test_slow_target_skips_work_instead_of_queueing_a_burst(self):
        records, summary = self.run_fake(10, 1, 0.35)
        self.assertGreater(summary["skipped_busy"], 0)
        self.assertLessEqual(len(records), 3)
        self.assertEqual(summary["submitted"] + summary["skipped_busy"] + summary["skipped_late"], 10)

    def test_external_target_rejected(self):
        with self.assertRaises(ValueError): client.run({"ip": "8.8.8.8"}, 3, 1, 1)

    def test_background_socket_without_source_port_stays_unmatched(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory); (root / "raw").mkdir()
            manifest = {"run_id": "test", "scenario_id": "S4", "mode": "pilot", "s4": {"rate": 3},
                        "actor": {"uid": "actor"}, "capture_start": "2026-01-01T00:00:00Z"}
            receipt = {"operation_id": "http-00000", "kind": "http_request", "source_port": 40000,
                       "target_ips": ["10.43.0.1"], "target_ports": [80], "started": "2026-01-01T00:00:01Z", "ended": "2026-01-01T00:00:03Z"}
            (root / "manifest.json").write_text(json.dumps(manifest))
            (root / "actor-receipts.ndjson").write_text(json.dumps(receipt) + "\n")
            (root / "timeline.ndjson").write_text(json.dumps({"time": manifest["capture_start"], "phase": "attack"}) + "\n")
            for node, uid, sport in (("lab-w1", "actor", 40000), ("lab-w2", "background", None)):
                sock = {"daddr": "10.43.0.1", "dport": 80}
                if sport: sock["sport"] = sport
                native = {"time": "2026-01-01T00:00:02Z", "process_kprobe": {"function_name": "tcp_sendmsg", "policy_name": "boutique-tcp-connect",
                          "process": {"pod": {"namespace": "boutique", "uid": uid}}, "args": [{"sock_arg": sock}]}}
                (root / "raw" / (node + ".ndjson")).write_text(json.dumps(native) + "\n")
                (root / "raw" / (node + ".stderr")).write_text("")
            with patch.object(label, "agent_states", return_value={"lab-w1": 1, "lab-w2": 2}):
                quality = label.normalize(root)
            events = [json.loads(x) for x in (root / "normalized.ndjson").read_text().splitlines()]
            self.assertEqual(quality["operations_with_matched_event"], 1)
            self.assertEqual(events[0]["operation_id"], "http-00000")
            self.assertIsNone(events[1]["operation_id"])
            self.assertEqual(events[1]["label"], "unknown")

    def guard_sample(self, change=None, bad_probe=False, samples=1):
        pod = {"metadata": {"uid": "p1", "name": "frontend-test"},
               "status": {"containerStatuses": [{"restartCount": 0, "state": {"running": {}}}]}}
        nodes = [{"metadata": {"name": "lab-w1"}, "status": {"conditions": [
            {"type": "Ready", "status": "True"}, {"type": "MemoryPressure", "status": "False"}]}}]
        with tempfile.TemporaryDirectory() as directory, patch.object(s4_support, "get", return_value={"items": [copy.deepcopy(pod)]}):
            guard = s4_support.Guard(Path(directory), "actor", {"ip": "10.43.0.1"}, lambda: "attack")
            pods = [pod]
            if change: change(pods, nodes)

            def command(*args, **kwargs):
                if args[:2] == ("get", "nodes"): return json.dumps({"items": nodes})
                if "get" in args: return json.dumps({"items": pods})
                if bad_probe: raise s4_support.subprocess.SubprocessError("test timeout")
                return "200"

            with patch.object(s4_support, "command", command):
                return [guard.sample() for _ in range(samples)]

    def test_healthy_guard(self): self.assertEqual(self.guard_sample()[0]["reasons"], [])
    def test_memory_pressure(self):
        self.assertTrue(self.guard_sample(lambda p, n: n[0]["status"]["conditions"][1].update(status="True"))[0]["reasons"])
    def test_restart(self):
        self.assertTrue(self.guard_sample(lambda p, n: p[0]["status"]["containerStatuses"][0].update(restartCount=1))[0]["reasons"])
    def test_oom_without_restart(self):
        self.assertTrue(self.guard_sample(lambda p, n: p[0]["status"]["containerStatuses"][0].update(state={"terminated": {"reason": "OOMKilled"}}))[0]["reasons"])
    def test_three_failed_probes(self):
        result = self.guard_sample(bad_probe=True, samples=3)
        self.assertFalse(result[0]["reasons"])
        self.assertFalse(result[1]["reasons"])
        self.assertIn("three_consecutive_frontend_probe_failures", result[2]["reasons"])


if __name__ == "__main__": unittest.main()
