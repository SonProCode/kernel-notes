"""Audit S0 references, paired pilot controls and a predeclared control batch read-only."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import itertools
import csv
import re
import json
from pathlib import Path
import shutil
import tempfile

from audit_scenarios import unpack_copy, check_metrics
from label import normalize, timestamp, ip
from s4_verify import verify_s4,rows
from s5_verify import verify_s5


def read(path):return json.loads(path.read_text(encoding="utf-8"))


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def service_graph(snapshot,events):
    """Request-direction candidates by destination service port; exclude reverse replies."""
    targets={}
    for item in snapshot:
        if item['kind']=='Service':
            for p in item['spec']['ports']:
                targets.setdefault((item['spec']['clusterIP'],p['port']),set()).add(item['metadata']['name'])
        if item['kind']=='EndpointSlice':
            service=item['metadata'].get('labels',{}).get('kubernetes.io/service-name')
            for endpoint in item.get('endpoints',[]):
                for address in endpoint['addresses']:
                    for p in item.get('ports',[]):
                        if service and p.get('port'):targets.setdefault((address,p['port']),set()).add(service)
    edges=Counter();unresolved=0
    for event in events:
        sock=event.get('socket')
        if event['event_type']!='tcp_send' or not sock:continue
        dest=targets.get((ip(sock['daddr']),sock['dport']),set())
        if len(dest)==1 and event.get('workload'):edges[(event['workload'],next(iter(dest)))]+=1
        else:unresolved+=1
    return {'edges':[{'source':a,'destination':b,'tcp_send_events':n} for (a,b),n in sorted(edges.items())],
            'unresolved_or_reverse_direction_sends':unresolved,'meaning':'Socket direction candidates; counts are TCP sends, not HTTP/gRPC request counts.'}


def verify_business(run):
    """Business S0 is a qualitative S1-S3 reference, not a request-latency pair."""
    m=read(run/'manifest.json');errors=[]
    def check(ok,message):
        if not ok:errors.append(message)
    check(m['scenario_id']=='S0' and 's4' not in m and 's5' not in m,'Wrong baseline family')
    check(m['status']=='completed' and m.get('dataset_status')=='validated','Incomplete baseline')
    check(not rows(run/'actor-receipts.ndjson') and not m.get('actor'),'Business reference contains actor/action')
    timeline=rows(run/'timeline.ndjson');check([p['phase'] for p in timeline]==['setup','warmup','measurement','finalize'],'Wrong baseline phases')
    start=timestamp(timeline[2]['time']);end=timestamp(m['measurement_end'])
    check((end-start).total_seconds()>=m['measurement_seconds'],'Baseline shorter than configured')
    old=rows(run/'normalized.ndjson');old_quality=read(run/'quality.json')
    with tempfile.TemporaryDirectory(prefix='s0-replay-') as directory:
        directory=Path(directory)
        for name in ('manifest.json','actor-receipts.ndjson','timeline.ndjson','agents-before.json','agents-after.json','metrics-before.json','metrics-after.json'):
            shutil.copyfile(run/name,directory/name)
        shutil.copytree(run/'raw',directory/'raw')
        # normalize prints a large summary; the report retains its structured result.
        import contextlib,io
        with contextlib.redirect_stdout(io.StringIO()):quality=normalize(directory)
        check(rows(directory/'normalized.ndjson')==old,'Baseline normalized differs from raw replay')
        check(quality==old_quality and quality['capture_checks_passed'],'Baseline capture quality failed')
    measured=[e for e in old if e['phase']=='measurement']
    check(bool(measured) and all(e['label']=='normal' for e in measured),'Measurement labels not normal')
    check({e['node'] for e in measured}=={'lab-w1','lab-w2'},'Baseline missing a worker')
    metrics=check_metrics(run);check(metrics['passed'] is True,'Baseline agent/loss metrics failed')
    for stage in ('before','after'):
        for node in read(run/f'nodes-{stage}.json')['items']:
            conditions={c['type']:c['status'] for c in node['status']['conditions']}
            check(conditions.get('Ready')=='True' and conditions.get('MemoryPressure')=='False','Unhealthy baseline node')
    graph=service_graph(read(run/'boutique-before.json')['items'],measured)
    with (Path(__file__).parent/'expected-communications.csv').open(encoding='utf-8-sig',newline='') as source:
        allowed={(r['source'],r['destination']) for r in csv.DictReader(source) if r['deployed']=='True'}
    observed={(e['source'],e['destination']) for e in graph['edges']}
    graph['expected_edges_observed']=len(observed&allowed);graph['configured_deployed_edges']=len(allowed)
    graph['unexpected_mapped_edges']=[list(e) for e in sorted(observed-allowed)]
    graph['checkout_to_payment_observed']=('checkoutservice','paymentservice') in observed
    check(graph['checkout_to_payment_observed'],'Normal checkout-to-payment edge not observed')
    stats=re.findall(r'\bPOST\s+/cart/checkout\s+(\d+)\s+(\d+)\(', (run/'locust.log').read_text(encoding='utf-8'))
    checkout={'requests':int(stats[-1][0]),'failures':int(stats[-1][1]),'scope':'Latest cumulative Locust table, includes warm-up'} if stats else None
    check(bool(checkout) and checkout['requests']>0 and checkout['failures']==0,'No successful checkout evidence in normal Locust table')
    sources=m.get('script_sha256',{})
    source_ok=bool(sources) and m.get('source_snapshot')=='source' and all((run/'source'/name).is_file() and hashlib.sha256((run/'source'/name).read_bytes()).hexdigest()==h for name,h in sources.items())
    check(source_ok,'Baseline source snapshot missing/mismatched')
    check(digest(sources)==m.get('code_bundle_sha256'),'Baseline bundle hash mismatched')
    return {'passed':not errors,'errors':errors,'measurement_seconds':(end-start).total_seconds(),'normal_events':len(measured),
            'normal_by_node':dict(Counter(e['node'] for e in measured)), 'normal_workload':m.get('normal_workload'),
            'service_graph':graph,'locust_checkout':checkout,'process_exec_by_binary':dict(Counter(e['binary'] for e in measured if e['event_type']=='process_exec')),
            'scope':'Qualitative business reference for S1-S3; original Locust, no per-request latency or continuous guard; not official S0 15-minute cohort'}


def review_legacy_s0(runs_root):
    """Replay old GĐ3 baselines as their original schema; never silently promote failures."""
    import normalize as baseline_normalizer
    reports=[]
    for original in sorted(runs_root.glob('s0-tetragon-*')):
        if not (original/'summary.json').exists():continue
        saved=read(original/'summary.json')
        item={'run_id':original.name,'recorded_basic_capture_passed':saved.get('basic_capture_checks_passed'),
              'recorded_events':saved.get('total_events'),'eligible_legacy_reference':False}
        try:
            with tempfile.TemporaryDirectory(prefix='legacy-s0-') as directory:
                # Legacy normalizer derives run_id from the directory basename.
                # Preserve it inside the temporary workspace for a valid replay.
                directory=Path(directory)/original.name;directory.mkdir();unpack_copy(original,directory)
                archived=directory/'telemetry-archived.ndjson';shutil.copyfile(directory/'telemetry.ndjson',archived)
                passed=baseline_normalizer.normalize(directory);new=read(directory/'summary.json')
                equal=True
                with archived.open(encoding='utf-8') as a,(directory/'telemetry.ndjson').open(encoding='utf-8') as b:
                    for x,y in itertools.zip_longest(a,b):
                        if x is None or y is None or json.loads(x)!=json.loads(y):equal=False;break
                item.update(replayed_basic_capture_passed=passed,normalized_replay_matches=equal,events=new['total_events'],
                            duration_seconds=(timestamp(new['end_utc'])-timestamp(new['start_utc'])).total_seconds(),
                            eligible_legacy_reference=bool(passed and equal and saved.get('basic_capture_checks_passed')))
        except Exception as error:item['error']=type(error).__name__+': '+str(error)
        item['scope']='Historical GĐ3 reference only; not a source/observer-matched control for current S1-S5'
        reports.append(item)
    return reports


def fingerprint(run):
    m=read(run/'manifest.json');snapshot=read(run/'boutique-before.json')['items']
    pods=[p for p in snapshot if p['kind']=='Pod']
    actor=next(p for p in pods if p['metadata']['uid']==m['actor']['uid'])
    locust=next(p for p in pods if p['metadata']['uid']==m['locust']['uid'])
    apps=sorted([{'name':p['metadata']['name'],'uid':p['metadata']['uid'],'node':p['spec']['nodeName'],
                  'images':sorted(c['imageID'] for c in p['status'].get('containerStatuses',[]))}
                 for p in pods if not p['metadata'].get('labels',{}).get('experiment-run') and not p['metadata']['name'].startswith('loadgenerator-')],key=lambda p:p['name'])
    policy=read(run/'policies-before.json')['items']
    spec=sorted([{'name':p['metadata']['name'],'spec':p['spec']} for p in policy],key=lambda p:p['name'])
    family='S5' if 's5' in m else 'S4'
    duration=m['s5']['calls'] if family=='S5' else m['s4']['duration_seconds']
    meta=read(run/'locust-runtime.json')['metadata'][0]
    dynamic={m['temporary_resources']['configmap']:'<experiment-code>',m['temporary_resources']['actor']:'<observer>',m['temporary_resources']['locust_deployment']:'<locust>'}
    def canonical(value):
        if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
        if isinstance(value,list):return [canonical(v) for v in value]
        if isinstance(value,str):return dynamic.get(value,value)
        return value
    return {'family':family,'source_bundle':m['code_bundle_sha256'],'actor_node':actor['spec']['nodeName'],
            'actor_image':m['actor']['image_id'],'locust_node':locust['spec']['nodeName'],'locust_image':m['locust']['image_id'],
            'locust_original_sha256':meta['original_locustfile_sha256'],'locust_version':meta['locust_version'],
            'seed':m.get('locust_seed'),'seed_observed':meta.get('random_seed'),
            'users':m['users'],'spawn_rate':m['spawn_rate'],'warmup':m['warmup_seconds'],'pre':m['pre_seconds'],
            'recovery':m['recovery_seconds'],'configured_measurement_seconds':duration,'policy_sha256':digest(spec),
            'application_placement_and_images_sha256':digest(apps),'targets':m['targets'],
            'actor_spec_sha256':digest(canonical(actor['spec'])),'locust_spec_sha256':digest(canonical(locust['spec'])),
            'admin_enabled':m.get('normal_admin',{}).get('enabled',False),'admin_receipt_present':(run/'normal-admin.json').exists()}


def compare_pair(control,attack):
    a,b=fingerprint(control),fingerprint(attack)
    mismatches=[key for key in a if a[key]!=b[key]]
    ma,mb=read(control/'manifest.json'),read(attack/'manifest.json')
    family=a['family']
    profile=ma.get('s5',ma.get('s4',{})).get('profile','upload')
    proper=ma['scenario_id']=='S0' and mb['scenario_id']==family and profile=='control' and not a['admin_enabled'] and not a['admin_receipt_present']
    return {'control_run':ma['run_id'],'intervention_run':mb['run_id'],'family':family,'configurations_match':not mismatches,
            'mismatched_fields':mismatches,'is_proper_no_intervention_control':proper,'passed':not mismatches and proper,
            'fingerprint':a,'limit':'Same declared configuration and placement; timing/routes still vary. One pair is descriptive, not causal/statistical proof.'}


def review_batch(batch,runs_root):
    record=read(batch/'batch.json');plan=read(batch/'protocol.json')
    errors=[]
    if record['status']!='completed':errors.append('Batch not completed')
    if hashlib.sha256((batch/'protocol.json').read_bytes()).hexdigest()!=record['protocol_sha256']:errors.append('Protocol hash mismatch')
    if hashlib.sha256((batch/'coordinator.py').read_bytes()).hexdigest()!=record['coordinator_sha256']:errors.append('Coordinator hash mismatch')
    if [c['case_id'] for c in record['cases']]!=[c['case_id'] for c in plan['cases']]:errors.append('Case order differs from predeclared protocol')
    cases=[];paths={}
    for case in record['cases']:
        item=dict(case);expected=next(p for p in plan['cases'] if p['case_id']==case['case_id'])
        if case['args']!=expected['args']:errors.append('Case args changed: '+case['case_id'])
        if case['status']!='completed' or case.get('return_code')!=0:errors.append('Case failed: '+case['case_id'])
        try:
            original=runs_root/case['run_id'];paths[case['case_id']]=original
            with tempfile.TemporaryDirectory(prefix='controls-check-') as directory:
                directory=Path(directory);unpack_copy(original,directory);m=read(directory/'manifest.json')
                contract_errors=protocol_errors(case['args'],m,read(directory/'boutique-before.json')['items'])
                item['protocol_errors']=contract_errors
                errors.extend(case['case_id']+': '+e for e in contract_errors)
                for name,h in m['script_sha256'].items():
                    plan_name='../telemetry/normalize.py' if name=='telemetry/normalize.py' else name
                    if plan_name in plan['source_sha256'] and h!=plan['source_sha256'][plan_name]:errors.append('Run source differs from frozen protocol: '+case['case_id']+'/'+name)
                if 's5' in m:proof=verify_s5(directory)
                elif 's4' in m:proof=verify_s4(directory)
                else:proof=verify_business(directory)
                item.update(verification=proof,passed=proof['passed'] and not contract_errors)
                if not proof['passed']:errors.append('Verification failed: '+case['case_id'])
        except Exception as error:
            item.update(passed=False,error=type(error).__name__+': '+str(error));errors.append('Evidence unreadable: '+case['case_id'])
        cases.append(item)
    pairs=[]
    for c,a in (('s0-s4-w2','s4-w2'),('s0-s5-w1','s5-w1')):
        try:
            with tempfile.TemporaryDirectory(prefix='pair-') as directory:
                directory=Path(directory);cp=directory/'control';ap=directory/'attack';cp.mkdir();ap.mkdir()
                unpack_copy(paths[c],cp);unpack_copy(paths[a],ap);pair=compare_pair(cp,ap)
            pairs.append(pair)
            if not pair['passed']:errors.append('Control pair not comparable: '+c)
        except Exception as error:errors.append('Pair unreadable: '+str(error))
    return {'protocol_id':record['protocol_id'],'cases':cases,'pairs':pairs,'passed':not errors,'errors':errors,
            'scope':'Supplementary pilot controls: business reference, matched comparison smokes, separate authorized administration. Official dataset is not certified.',
            'official_ready':False,'remaining':['Repeated official runs including long S0','Run-level train/test split and common raw-derived feature schema','Repeated matched controls for causal/overhead evaluation and later protection ON/OFF comparisons']}


def protocol_errors(argv,manifest,snapshot):
    """Bind actual manifest and placement to the predeclared command, not only batch.json."""
    values={};flags=set();i=0
    while i<len(argv):
        key=argv[i]
        if i+1<len(argv) and not argv[i+1].startswith('--'):values[key]=argv[i+1];i+=2
        else:flags.add(key);i+=1
    errors=[]
    checks={'--scenario':'scenario_id','--mode':'mode','--node':'node','--locust-seed':'locust_seed',
            '--warmup':'warmup_seconds','--pre':'pre_seconds','--recovery':'recovery_seconds','--measurement':'measurement_seconds'}
    for key,field in checks.items():
        if key in values and str(manifest.get(field))!=values[key]:errors.append('Manifest differs from protocol: '+field)
    family='s5' if 's5' in manifest else 's4' if 's4' in manifest else None
    for key,field in (('--s4-duration','duration_seconds'),('--s4-rate','rate'),('--s4-concurrency','concurrency'),('--s5-calls','calls')):
        if key in values and str(manifest.get(family,{}).get(field))!=values[key]:errors.append('Manifest differs from protocol: '+key)
    for flag,f in (('--s4-control','s4'),('--s5-control','s5')):
        actual=f in manifest and manifest[f].get('profile')=='control'
        if actual!=(flag in flags):errors.append('Control family differs from protocol: '+flag)
    if bool(manifest.get('normal_admin',{}).get('enabled'))!=('--normal-admin' in flags):errors.append('Administration differs from protocol')
    if '--loadgen-node' in values:
        pod=next(p for p in snapshot if p['kind']=='Pod' and p['metadata']['uid']==manifest['locust']['uid'])
        if pod['spec']['nodeName']!='lab-'+values['--loadgen-node']:errors.append('Actual Locust placement differs from protocol')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-root',type=Path,default=Path(__file__).resolve().parents[1]/'runs')
    parser.add_argument('--batch',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--include-legacy',action='store_true')
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(args.runs_root.resolve()):parser.error('Keep analysis outside captured runs/')
    batch=args.batch or max(args.runs_root.glob('batch-controls-*'),key=lambda p:p.name)
    originals={p.relative_to(args.runs_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in args.runs_root.rglob('*') if p.is_file()}
    report=review_batch(batch,args.runs_root)
    if args.include_legacy:report['legacy_s0']=review_legacy_s0(args.runs_root)
    after={p.relative_to(args.runs_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in args.runs_root.rglob('*') if p.is_file()}
    report['original_evidence_unchanged']=originals==after;report['passed']=report['passed'] and originals==after
    report['analysis_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','pairs')},ensure_ascii=False,indent=2))
    for case in report['cases']:print(case['case_id'],case.get('passed'),case.get('run_id'),case.get('error',''))
    for pair in report['pairs']:print(pair['family'],pair['passed'],pair['mismatched_fields'])
    raise SystemExit(not report['passed'])


if __name__=='__main__':main()
