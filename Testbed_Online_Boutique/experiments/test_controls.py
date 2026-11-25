"""Reject incomparable historical pairs without changing captured evidence."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from review_controls import compare_pair,protocol_errors

ROOT=Path(__file__).resolve().parents[1]/'runs'
CONTROL=ROOT/'s0-s4-control-20261123T045647Z-1848096'
ATTACK=ROOT/'s4-20261123T045922Z-1853277'
OTHER_NODE=ROOT/'s4-20261123T050725Z-1869684'


class ControlPairTests(unittest.TestCase):
    def setUp(self):
        if not (CONTROL/'manifest.json').exists():self.skipTest('Bundled S4 control required')

    def clone(self,source,destination):
        destination.mkdir()
        for name in ('manifest.json','boutique-before.json','policies-before.json','locust-runtime.json'):
            shutil.copyfile(source/name,destination/name)

    def test_original_same_node_pair_is_configuration_compatible(self):
        self.assertTrue(compare_pair(CONTROL,ATTACK)['passed'])

    def test_predeclared_control_cannot_be_replaced_with_intervention(self):
        m=json.loads((ATTACK/'manifest.json').read_text())
        args=['--scenario','S0','--s4-control','--mode','smoke','--s4-duration','99']
        errors=protocol_errors(args,m,[])
        self.assertIn('Manifest differs from protocol: scenario_id',errors)
        self.assertIn('Control family differs from protocol: --s4-control',errors)
        self.assertIn('Manifest differs from protocol: --s4-duration',errors)

    def test_worker_placement_difference_is_not_a_matched_pair(self):
        proof=compare_pair(CONTROL,OTHER_NODE)
        self.assertFalse(proof['passed']);self.assertIn('actor_node',proof['mismatched_fields'])

    def test_source_change_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'attack';self.clone(ATTACK,copy)
            p=copy/'manifest.json';m=json.loads(p.read_text());m['code_bundle_sha256']='different';p.write_text(json.dumps(m))
            proof=compare_pair(CONTROL,copy);self.assertFalse(proof['passed']);self.assertIn('source_bundle',proof['mismatched_fields'])

    def test_diagnostic_control_cannot_replace_pure_control(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'control';self.clone(CONTROL,copy)
            (copy/'normal-admin.json').write_text('{}')
            proof=compare_pair(copy,ATTACK);self.assertFalse(proof['passed']);self.assertFalse(proof['is_proper_no_intervention_control'])

    def test_observed_seed_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'attack';self.clone(ATTACK,copy)
            p=copy/'locust-runtime.json';m=json.loads(p.read_text());m['metadata'][0]['random_seed']=99;p.write_text(json.dumps(m))
            proof=compare_pair(CONTROL,copy);self.assertFalse(proof['passed']);self.assertIn('seed_observed',proof['mismatched_fields'])

    def test_same_image_with_different_environment_is_not_matched(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'attack';self.clone(ATTACK,copy)
            m=json.loads((copy/'manifest.json').read_text());p=copy/'boutique-before.json';s=json.loads(p.read_text())
            pod=next(i for i in s['items'] if i['kind']=='Pod' and i['metadata']['uid']==m['locust']['uid'])
            pod['spec']['containers'][0].setdefault('env',[]).append({'name':'DIFFERENT_CONFIG','value':'1'})
            p.write_text(json.dumps(s));proof=compare_pair(CONTROL,copy)
            self.assertFalse(proof['passed']);self.assertIn('locust_spec_sha256',proof['mismatched_fields'])

    def test_actor_resource_budget_difference_is_not_matched(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'attack';self.clone(ATTACK,copy)
            m=json.loads((copy/'manifest.json').read_text());p=copy/'boutique-before.json';s=json.loads(p.read_text())
            pod=next(i for i in s['items'] if i['kind']=='Pod' and i['metadata']['uid']==m['actor']['uid'])
            pod['spec']['containers'][0]['resources']['limits']['cpu']='2'
            p.write_text(json.dumps(s));proof=compare_pair(CONTROL,copy)
            self.assertFalse(proof['passed']);self.assertIn('actor_spec_sha256',proof['mismatched_fields'])
