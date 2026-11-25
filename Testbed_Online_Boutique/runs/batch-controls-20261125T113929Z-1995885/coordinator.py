"""Run the predeclared pilot controls serially and retain each result and failure."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def save(path,data):path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol",type=Path,default=ROOT/"controls-protocol.json")
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error("Use sudo python3 experiments/run_controls.py")
    lock=open('/run/lock/boutique-controls-batch.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    plan=json.loads(args.protocol.read_text(encoding="utf-8"))
    output=ROOT.parent/'runs'/f'batch-controls-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{os.getpid()}'
    output.mkdir(mode=0o700)
    shutil.copyfile(args.protocol,output/'protocol.json');shutil.copyfile(__file__,output/'coordinator.py')
    state={'protocol_id':plan['protocol_id'],'status':'running','protocol_sha256':hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
           'coordinator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[]}
    save(output/'batch.json',state);print('Batch:',output,flush=True)
    try:
        for case in plan['cases']:
            for name,digest in plan['source_sha256'].items():
                if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source changed: '+name)
            item={'case_id':case['case_id'],'purpose':case['purpose'],'args':case['args'],'status':'running'}
            state['cases'].append(item);save(output/'batch.json',state)
            print('Starting:',case['case_id'],flush=True)
            with (output/(case['case_id']+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run([sys.executable,str(ROOT/'runner.py'),*case['args']],stdout=log,stderr=subprocess.STDOUT)
            item['return_code']=result.returncode
            lines=(output/(case['case_id']+'.log')).read_text(encoding='utf-8').splitlines()
            run_line=next((line[5:].strip() for line in lines if line.startswith('Run: ')),None)
            if run_line:
                run=Path(run_line);manifest=json.loads((run/'manifest.json').read_text())
                item.update(run_id=manifest['run_id'],dataset_status=manifest.get('dataset_status'),run_status=manifest['status'])
            item['status']='completed' if result.returncode==0 and item.get('dataset_status')=='validated' else 'failed'
            save(output/'batch.json',state)
            print(case['case_id'],item['status'],item.get('run_id'),flush=True)
            if item['status']!='completed':raise RuntimeError('Case failed; retain logs: '+case['case_id'])
        state['status']='completed'
    except BaseException as error:
        state.update(status='failed',error=type(error).__name__+': '+str(error));raise
    finally:
        state['finished']=datetime.now(timezone.utc).isoformat();save(output/'batch.json',state)


if __name__=='__main__':main()
