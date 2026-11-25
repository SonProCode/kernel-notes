"""Real control evidence and negative cases on temporary archive copies."""
import json
from pathlib import Path
import tempfile
import unittest

from audit_scenarios import unpack_copy
from review_controls import verify_business, service_graph
from s5_verify import verify_s5
from label import timestamp

RUNS=Path(__file__).resolve().parents[1]/'runs'


class BusinessControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidates=[p.parent for p in RUNS.glob('s0-*/manifest.json') if json.loads(p.read_text(encoding='utf-8')).get('normal_profile')=='business_reference']
        if not candidates:raise unittest.SkipTest('New business S0 archive required')
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);unpack_copy(candidates[-1],cls.root)
        cls.saved={p.name:p.read_bytes() for p in cls.root.iterdir() if p.is_file()}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        for name,data in self.saved.items():(self.root/name).write_bytes(data)
    def test_business_reference_has_expected_graph_and_checkout(self):
        p=verify_business(self.root);self.assertTrue(p['passed']);self.assertEqual(p['service_graph']['expected_edges_observed'],16);self.assertGreater(p['locust_checkout']['requests'],0)
    def test_actor_receipt_rejected_in_pure_business_baseline(self):
        (self.root/'actor-receipts.ndjson').write_text(json.dumps({'kind':'normal_diagnostic','operation_id':'unexpected'})+'\n')
        self.assertFalse(verify_business(self.root)['passed'])
    def test_missing_checkout_log_not_silently_accepted(self):
        (self.root/'locust.log').write_text('');self.assertFalse(verify_business(self.root)['passed'])
    def test_false_attack_label_in_normal_measurement_rejected(self):
        p=self.root/'normalized.ndjson';values=[json.loads(s) for s in p.read_text().splitlines()]
        next(v for v in values if v['phase']=='measurement')['label']='attack'
        p.write_text('\n'.join(json.dumps(v) for v in values)+'\n');self.assertFalse(verify_business(self.root)['passed'])


class S5ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidates=[p.parent for p in RUNS.glob('s0-s5-control-*/manifest.json') if (m:=json.loads(p.read_text(encoding='utf-8'))).get('dataset_status')=='validated' and m.get('normal_admin',{}).get('enabled')]
        if not candidates:raise unittest.SkipTest('Authorized administrative control required')
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);unpack_copy(sorted(candidates)[0],cls.root)
        cls.saved={p.name:p.read_bytes() for p in cls.root.iterdir() if p.is_file()}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        for name,data in self.saved.items():(self.root/name).write_bytes(data)
    def test_authorized_shell_python_control_is_normal(self):
        p=verify_s5(self.root);self.assertTrue(p['passed'],p['errors']);self.assertEqual(p['uploads'],0);self.assertEqual(p['received'],0);self.assertNotIn('attack',p['events_by_label'])
    def test_pure_receiver_present_control_has_no_uploads(self):
        candidates=[p.parent for p in RUNS.glob('s0-s5-control-*/manifest.json') if (m:=json.loads(p.read_text(encoding='utf-8'))).get('dataset_status')=='validated' and not m.get('normal_admin',{}).get('enabled')]
        if not candidates:self.skipTest('Paired pure control required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);unpack_copy(sorted(candidates)[-1],root);proof=verify_s5(root)
            self.assertTrue(proof['passed'],proof['errors']);self.assertEqual(proof['uploads'],0);self.assertEqual(proof['received_payload_bytes'],0)
    def test_missing_admin_receipt_rejected(self):
        (self.root/'normal-admin.json').unlink();self.assertFalse(verify_s5(self.root)['passed'])
    def test_diagnostic_without_authorized_context_rejected(self):
        p=self.root/'manifest.json';m=json.loads(p.read_text());m['normal_admin']['purpose']='other';p.write_text(json.dumps(m));self.assertFalse(verify_s5(self.root)['passed'])
    def test_receiver_upload_cannot_hide_in_zero_upload_control(self):
        p=self.root/'receiver.ndjson';values=[json.loads(s) for s in p.read_text().splitlines()]
        values.insert(1,{'kind':'received','operation_id':'upload-00000','payload_bytes':65536,'peer_ip':'192.168.141.143'})
        p.write_text('\n'.join(json.dumps(v) for v in values)+'\n');self.assertFalse(verify_s5(self.root)['passed'])
    def test_native_traffic_to_receiver_invalidates_control_even_without_receipts(self):
        m=json.loads((self.root/'manifest.json').read_text());timeline=[json.loads(s) for s in (self.root/'timeline.ndjson').read_text().splitlines()]
        lo=timestamp(next(p['time'] for p in timeline if p['phase']=='measurement'));hi=timestamp(next(p['time'] for p in timeline if p['phase']=='recovery'))
        changed=False
        for path in (self.root/'raw').glob('*.ndjson'):
            original=path.read_bytes();records=[json.loads(s) for s in original.splitlines()]
            for row in records:
                p=row.get('process_kprobe',{})
                if p.get('process',{}).get('pod',{}).get('uid')==m['actor']['uid'] and lo<=timestamp(row['time'])<hi:
                    sock=next((a['sock_arg'] for a in p.get('args',[]) if 'sock_arg' in a),None)
                    if sock:
                        sock.update(daddr='192.168.141.142',dport=18080);changed=True;break
            if changed:
                try:
                    path.write_text('\n'.join(json.dumps(v) for v in records)+'\n')
                    proof=verify_s5(self.root);self.assertFalse(proof['passed']);self.assertIn('Control actor sent traffic to the receiver',proof['errors'])
                finally:path.write_bytes(original)
                break
        self.assertTrue(changed)


class GraphDirectionTests(unittest.TestCase):
    def test_server_response_is_not_a_reverse_service_call(self):
        snapshot=[{'kind':'Service','metadata':{'name':'frontend'},'spec':{'clusterIP':'10.43.0.1','ports':[{'port':80}]}},
                  {'kind':'Service','metadata':{'name':'paymentservice'},'spec':{'clusterIP':'10.43.0.2','ports':[{'port':50051}]}}]
        events=[{'event_type':'tcp_send','workload':'frontend','socket':{'daddr':'::ffff:10.43.0.2','dport':50051}},
                {'event_type':'tcp_send','workload':'paymentservice','socket':{'daddr':'10.43.0.1','dport':54000}}]
        g=service_graph(snapshot,events)
        self.assertEqual([(r['source'],r['destination']) for r in g['edges']],[('frontend','paymentservice')]);self.assertEqual(g['unresolved_or_reverse_direction_sends'],1)
