"""Build a pinned Debian tool bundle in an isolated temporary Pod."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
BUILD = r"""
import hashlib,json,pathlib,re,shutil,subprocess,tarfile
subprocess.run(['apt-get','-o','Acquire::Retries=2','-o','Acquire::http::Timeout=20','update'],check=True)
subprocess.run(['apt-get','install','-y','--no-install-recommends','curl','wget','netcat-openbsd','nmap'],check=True)
root=pathlib.Path('/tmp/gd4-tools')
(root/'bin').mkdir(parents=True)
(root/'lib').mkdir()
(root/'share').mkdir()
(root/'licenses').mkdir()
binaries={'curl':'/usr/bin/curl','wget':'/usr/bin/wget','nc':'/bin/nc.openbsd','nmap':'/usr/bin/nmap'}
hashes={}
glibc=('libc.so','libm.so','libpthread.so','libdl.so','librt.so','ld-linux')
for name,filename in binaries.items():
    source=pathlib.Path(filename).resolve()
    shutil.copy2(source,root/'bin'/name)
    hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    output=subprocess.check_output(['ldd',str(source)],text=True)
    for filename in re.findall(r'=> (/[^ ]+)',output):
        path=pathlib.Path(filename)
        if path.name.startswith(glibc):continue
        shutil.copy2(path,root/'lib'/path.name)
shutil.copytree('/usr/share/nmap',root/'share/nmap')
packages=subprocess.check_output(['dpkg-query','-W','-f','${binary:Package} ${Version}\n'],text=True)
for package in ('curl','wget','netcat-openbsd','nmap','nmap-common'):
    copyright=pathlib.Path('/usr/share/doc')/package/'copyright'
    if copyright.exists():shutil.copy2(copyright,root/'licenses'/(package+'.copyright'))
for path in (root/'lib').iterdir():
    result=subprocess.run(['dpkg-query','-S',str(pathlib.Path('/lib/x86_64-linux-gnu')/path.name)],text=True,capture_output=True)
    for line in result.stdout.splitlines():
        package=line.split(':',1)[0]
        copyright=pathlib.Path('/usr/share/doc')/package/'copyright'
        if copyright.exists():shutil.copy2(copyright,root/'licenses'/(package+'.copyright'))
with tarfile.open('/tmp/s3-tools.tar.gz','w:gz') as out:
    for path in sorted(root.iterdir()):out.add(path,arcname=path.name)
print(json.dumps({'packages':packages,'binary_sha256':hashes,
                  'scope':'curl/wget/nc/nmap with non-glibc libraries and nmap data'}))
"""


def k(*args, **kwargs):
    return subprocess.run(["k3s","kubectl",*args],check=True,text=True,capture_output=True,timeout=360,**kwargs).stdout


def main():
    if os.geteuid() != 0:
        raise SystemExit("Use sudo python3 experiments/s3/build_tools.py")
    bundle=ROOT/"tools.tar.gz"
    metadata=ROOT/"tools-provenance.json"
    if bundle.exists() and metadata.exists():
        info=json.loads(metadata.read_text())
        assert hashlib.sha256(bundle.read_bytes()).hexdigest()==info["bundle_sha256"]
        print("Using existing hash-verified S3 tool bundle")
        return
    name=f"gd4-s3-builder-{os.getpid()}"
    pod={"apiVersion":"v1","kind":"Pod","metadata":{"name":name,"namespace":"telemetry",
         "labels":{"app":"gd4-s3-builder"}},"spec":{
         "automountServiceAccountToken":False,"restartPolicy":"Never","activeDeadlineSeconds":600,
         "nodeSelector":{"lab.slot":"w1"},"containers":[{
             "name":"builder","image":"python:3.12.8-slim-bookworm",
             "command":["python3","-c","import time; time.sleep(590)"],
             "securityContext":{"runAsUser":0,"allowPrivilegeEscalation":False},
             "resources":{"requests":{"cpu":"100m","memory":"128Mi"},
                          "limits":{"cpu":"1","memory":"512Mi"}}}]}}
    created=False
    try:
        k("create","-f","-",input=json.dumps(pod));created=True
        k("-n","telemetry","wait","--for=condition=Ready",f"pod/{name}","--timeout=120s")
        proc=subprocess.run(["k3s","kubectl","-n","telemetry","exec",name,"-c","builder","--",
                             "python3","-c",BUILD],text=True,capture_output=True,timeout=360)
        (ROOT/"build.log").write_text(proc.stdout+proc.stderr)
        proc.check_returncode()
        info=json.loads(proc.stdout.strip().splitlines()[-1])
        data=subprocess.check_output(["k3s","kubectl","-n","telemetry","exec",name,"-c","builder",
                                      "--","python3","-c",
                                      "import pathlib,sys;sys.stdout.buffer.write(pathlib.Path('/tmp/s3-tools.tar.gz').read_bytes())"],timeout=60)
        bundle.write_bytes(data);bundle.chmod(0o644)
        actual=json.loads(k("-n","telemetry","get","pod",name,"-o","json"))
        info["builder_image_id"]=actual["status"]["containerStatuses"][0]["imageID"]
        info["bundle_sha256"]=hashlib.sha256(data).hexdigest()
        metadata.write_text(json.dumps(info,indent=2)+"\n");metadata.chmod(0o644)
        print("Built S3 tool bundle:",len(data),"bytes",info["bundle_sha256"],flush=True)
    finally:
        if created:k("-n","telemetry","delete","pod",name,"--ignore-not-found","--wait=false")


if __name__=="__main__":
    main()
