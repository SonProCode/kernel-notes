"""Synthetic fixture and live loopback receiver protocol tests; no lab traffic."""
import hashlib
import contextlib
import importlib.util
import io
import http.client
import json
from pathlib import Path
import sys
import threading
import signal
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent/"s5"))
from fixture import PAYLOAD_BYTES, operation_id, payload
from receiver import Receiver

RUN="s5-20261125T010000Z-123"


class FixtureTests(unittest.TestCase):
    def test_fixed_synthetic_size_and_determinism(self):
        a=payload(RUN,operation_id(0))
        self.assertEqual(len(a),65536)
        self.assertTrue(a.startswith(b"GD4-S5-SYNTHETIC-NOT-REAL-DATA"))
        self.assertEqual(a,payload(RUN,operation_id(0)))
        self.assertNotEqual(a,payload(RUN,operation_id(1)))

    def test_unbounded_or_arbitrary_identity_rejected(self):
        for value in (-1,60,True):
            with self.subTest(value=value),self.assertRaises(ValueError):operation_id(value)
        for run,op in (("other",operation_id(0)),(RUN,"../../token"),(RUN,"upload-00060")):
            with self.subTest(run=run,op=op),self.assertRaises(ValueError):payload(run,op)


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.receipts=[]
        self.server=Receiver(("127.0.0.1",0),RUN,2,self.receipts.append)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={"poll_interval":.01},daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def upload(self,extra=None,body=None,path="/upload"):
        body=payload(RUN,operation_id(0)) if body is None else body
        headers={"Content-Type":"application/octet-stream","X-Run-ID":RUN,"X-Operation-ID":operation_id(0),
                 "X-Payload-SHA256":hashlib.sha256(body).hexdigest(),"Content-Length":str(len(body))}
        headers.update(extra or {})
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=3)
        try:
            connection.request("POST",path,body=body,headers=headers)
            response=connection.getresponse();return response.status,json.loads(response.read())
        finally:connection.close()

    def test_valid_upload_ack_matches_receiver_and_only_metadata_is_retained(self):
        status,ack=self.upload();self.assertEqual(status,200)
        self.assertEqual(ack,self.receipts[0]);self.assertEqual(ack["payload_bytes"],PAYLOAD_BYTES)
        self.assertNotIn("payload",ack);self.assertNotIn("body",ack)

    def test_duplicate_operation_rejected_without_second_receive(self):
        self.assertEqual(self.upload()[0],200);self.assertEqual(self.upload()[0],400)
        self.assertEqual(sum(r["kind"]=="received" for r in self.receipts),1)

    def test_wrong_run_rejected(self):self.assertEqual(self.upload({"X-Run-ID":"other"})[0],400)
    def test_wrong_checksum_rejected(self):self.assertEqual(self.upload({"X-Payload-SHA256":"0"*64})[0],400)
    def test_nonsynthetic_body_rejected(self):self.assertEqual(self.upload(body=b"x"*65536)[0],400)
    def test_oversized_body_rejected(self):self.assertEqual(self.upload(body=b"x"*65537)[0],400)
    def test_chunked_framing_rejected(self):self.assertEqual(self.upload({"Transfer-Encoding":"chunked"})[0],400)
    def test_wrong_endpoint_rejected(self):self.assertEqual(self.upload(path="/other")[0],400)

    def test_real_client_obtains_ack_and_leaves_no_pid_file(self):
        spec=importlib.util.spec_from_file_location("s5_client",Path(__file__).parent/"s5/client.py")
        client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
        previous={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
        try:
            with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()) as out:
                root=Path(directory)
                with patch.object(client,"RECEIVER_IP","127.0.0.1"),patch.object(client,"RECEIVER_PORT",self.server.server_port),patch.object(client,"Path",lambda p:root/Path(p).name):
                    client.run(RUN,1)
                receipt=json.loads(out.getvalue())
                self.assertEqual(receipt["outcome"],"received")
                self.assertEqual(receipt["receiver_acknowledgment"],self.receipts[0])
                self.assertFalse((root/"s5-action.pid").exists())
                summary=json.loads((root/"s5-client-summary.json").read_text())
                self.assertEqual(summary["submitted"],1);self.assertGreaterEqual(summary["elapsed_seconds"],1)
        finally:
            for s,h in previous.items():signal.signal(s,h)


if __name__=="__main__":unittest.main()
