"""Install the pinned S3 tools into an unprivileged temporary actor."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
BOOTSTRAP = """
import hashlib,json,os,pathlib,subprocess,sys,tarfile
root=pathlib.Path('/tmp/gd4-s3')
root.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as source:
    source.extractall(root,filter='data')
bundle=root/'tools.tar.gz'
metadata=json.loads((root/'tools-provenance.json').read_text())
assert hashlib.sha256(bundle.read_bytes()).hexdigest()==metadata['bundle_sha256']
with tarfile.open(bundle) as tools:
    tools.extractall(root,filter='data')
env=os.environ.copy()
env['LD_LIBRARY_PATH']=str(root/'lib')
env['NMAPDIR']=str(root/'share/nmap')
versions={}
for name in ('curl','wget','nc','nmap'):
    binary=root/'bin'/name
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==metadata['binary_sha256'][name]
    result=subprocess.run([str(binary),'-h' if name=='nc' else '--version'],env=env,text=True,capture_output=True,timeout=10)
    output=(result.stdout+result.stderr).strip()
    if result.returncode and name!='nc':
        raise RuntimeError('S3 tool dependency check failed: '+name)
    if name=='nc' and 'OpenBSD' not in output:
        raise RuntimeError('Netcat dependency check failed')
    versions[name]=output.splitlines()[0]
print(json.dumps({'tool_versions':versions,'bundle_sha256':metadata['bundle_sha256']}))
"""


def prepare_s3(actor_name, output):
    source = ROOT/"s3"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name in ("client.py", "tools.tar.gz", "tools-provenance.json"):
            bundle.add(source/name, arcname=name)
    payload = buffer.getvalue()
    result = subprocess.run(["k3s", "kubectl", "-n", "boutique", "exec", "-i", actor_name,
                             "-c", "actor", "--", "python3", "-c", BOOTSTRAP],
                            input=payload, capture_output=True, timeout=120)
    (output/"s3-setup.log").write_bytes(result.stdout+result.stderr)
    result.check_returncode()
    runtime = json.loads(result.stdout.decode().strip().splitlines()[-1])
    (output/"s3-runtime.json").write_text(json.dumps(runtime, indent=2)+"\n")
    return runtime
