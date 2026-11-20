"""Prepare a pinned offline gRPC client inside the temporary actor Pod."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent

BOOTSTRAP = """
import hashlib, importlib.metadata, json, os, pathlib, subprocess, sys, tarfile
root=pathlib.Path('/tmp/gd4-s2')
root.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as source:
    source.extractall(root, filter='data')
deps=root/'deps'
subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-cache-dir',
                '--disable-pip-version-check','--require-hashes',
                '--find-links',str(root/'wheels'),'--target',str(deps),
                '-r',str(root/'requirements.lock')],check=True)
sys.path.insert(0,str(deps))
from grpc_tools import protoc
api=root/'api'
api.mkdir()
code=protoc.main(['grpc_tools.protoc','-I'+str(root/'protos'),
                 '--python_out='+str(api),'--grpc_python_out='+str(api),
                 str(root/'protos/demo.proto')])
if code:
    raise RuntimeError('protoc failed')
print(json.dumps({
    'versions':{name:importlib.metadata.version(name) for name in
                ('grpcio','grpcio-tools','protobuf','setuptools','typing_extensions')},
    'generated_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in api.glob('*.py')}
}))
"""


def prepare_s2(actor_name, output):
    source = ROOT / "s2"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                arcname = "gd4_s2_client.py" if path.name == "client.py" else path.relative_to(source).as_posix()
                bundle.add(path, arcname=arcname)
    payload = stream.getvalue()
    result = subprocess.run(
        ["k3s", "kubectl", "-n", "boutique", "exec", "-i", actor_name,
         "-c", "actor", "--", "python3", "-c", BOOTSTRAP],
        input=payload, capture_output=True, timeout=180)
    (output / "s2-setup.log").write_bytes(result.stdout + result.stderr)
    result.check_returncode()
    runtime = json.loads(result.stdout.decode().strip().splitlines()[-1])
    runtime["bundle_sha256"] = hashlib.sha256(payload).hexdigest()
    runtime["proto_sha256"] = hashlib.sha256((source / "protos/demo.proto").read_bytes()).hexdigest()
    (output / "s2-runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
    return runtime
