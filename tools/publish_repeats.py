"""Finish the finite repeat-batch export and publication; SSH password is read from stdin only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import paramiko


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.STDOUT)


def sudo(ssh, password, command, script=None):
    i,o,e=ssh.exec_command("sudo -S -p '' "+command,timeout=600)
    i.write(password+"\n"+(script or ""));i.flush();i.channel.shutdown_write()
    result=o.read().decode();error=e.read().decode()
    if o.channel.recv_exit_status():
        raise RuntimeError(error or result)
    return result


def export_script(batch):
    return """
import json,os,re,shutil,tarfile,tempfile
from pathlib import Path
batch=Path(BATCH).resolve();runs=batch.parent
state=json.loads((batch/'batch.json').read_text())
out=Path(tempfile.mkdtemp(prefix='repeats-export-',dir='/tmp'))
target=out/'runs';target.mkdir()
shutil.copytree(batch,target/batch.name)
for run_id in dict.fromkeys(c['run_id'] for c in state['cases'] if c.get('run_id') and not c.get('carried_forward')):
 if not re.fullmatch(r'(s[0-5]|s0-s[45]-control)-[0-9]{8}T[0-9]{6}Z-[0-9]+',run_id):raise ValueError('Invalid run ID')
 source=(runs/run_id).resolve()
 if source.parent!=runs:raise ValueError('Escaped run')
 destination=target/run_id;destination.mkdir()
 for p in source.iterdir():
  if p.is_file() and p.name not in ('normalized.ndjson','labeled-windows.ndjson') and not p.name.endswith('.partial'):
   shutil.copyfile(p,destination/p.name)
 if not (destination/'dataset.tar.gz').exists():
  with tarfile.open(destination/'dataset.tar.gz','w:gz',compresslevel=3) as archive:
   for name in ('raw','source','normalized.ndjson','labeled-windows.ndjson'):
    if (source/name).exists():archive.add(source/name,arcname=name)
for p in [out,*out.rglob('*')]:
 os.chown(p,1000,1000);p.chmod(0o700 if p.is_dir() else 0o600)
print(out)
""".replace("BATCH",repr(batch))


def render(state, review):
    done=[c for c in state["cases"] if c["status"]=="completed"]
    text=["# Trạng thái batch đo lặp ngày 26/11/2026","",
          f"Trạng thái cuối: **{state['status']}**. Hoàn tất **{len(done)}/{len(state['cases'])}** lượt đã lên lịch.",
          f"Batch: {state['batch_name']}. Protocol: {state['protocol_id']}.",
          f"Kết thúc UTC: {state.get('finished','chưa có')}.",""]
    if state.get("error"):
        text.extend(["Lỗi được giữ nguyên: "+state["error"],""])
    if state.get("carried_forward_cases"):
        text.extend([f"Trong số lượt hoàn tất có **{state['carried_forward_cases']} lượt kế thừa đã hậu kiểm từ batch cũ**; số lượt mới hoàn tất là {sum(c['status']=='completed' and not c.get('carried_forward') for c in state['cases'])}. Batch cũ và lượt lỗi không bị ghi lại hoặc đổi trạng thái.",""])
    if review:
        text.extend([f"Hậu kiểm cohort: **{'đạt' if review['passed'] else 'chưa đạt'}**. Đây là kiểm chứng dữ liệu và cấu hình, không phải kết quả precision/recall hoặc giảm thiểu.",""])
        for error in review.get("errors",[]):
            text.append("- "+error)
    text.extend(["", "| Case | Trạng thái | Bằng chứng |","| --- | --- | --- |"])
    for c in state["cases"]:
        link=f"[{c['run_id']}](../runs/{c['run_id']}/manifest.json)" if c.get("run_id") else "Chưa tạo run"
        text.append(f"| {c['case_id']} | {c['status']} | {link} |")
    text.extend(["",f"[Batch và thứ tự thực hiện](../runs/{state['batch_name']}/batch.json)."])
    if review:
        text.extend(["",f"[Report hậu kiểm đầy đủ](../runs/{state['batch_name']}/cohort-review.json).","",
                     "Các lỗi ứng dụng, lượt chưa đạt và dữ liệu unknown được giữ để phân tích. Không cộng pilot cũ vào cohort này."])
        for family,value in review.get("descriptive_statistics",{}).items():
            text.extend(["",f"{family}: p95 từng run (ms) = "+", ".join(f"{v:.2f}" for v in value["p95_ms_per_run"])+". Đây là mô tả giữa các run, không phải p95 gộp."])
    text.extend(["","[Hướng dẫn lịch, giới hạn và cách tự kiểm tra](REPEATS.md).",""])
    return "\n".join(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,required=True)
    parser.add_argument("--batch",required=True)
    parser.add_argument("--host-key-sha256",required=True)
    args=parser.parse_args();password=sys.stdin.readline().strip();repo=args.repo.resolve()
    if not password:raise ValueError("SSH password required on stdin")
    class PinnedHostKey(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self,client,hostname,key):
            if hashlib.sha256(key.asbytes()).hexdigest()!=args.host_key_sha256:
                raise paramiko.SSHException("Lab host key differs from launch checkpoint")
    if not re.fullmatch(r"/home/sonth32/Testbed_Online_Boutique/runs/batch-repeats-[0-9]{8}T[0-9]{6}Z-[0-9]+",args.batch):
        raise ValueError("Unexpected batch path")
    deadline=time.monotonic()+9*3600
    while True:
        if time.monotonic()>deadline:raise TimeoutError("Finite batch publication deadline reached")
        try:
            with paramiko.SSHClient() as ssh:
                ssh.load_system_host_keys();ssh.set_missing_host_key_policy(PinnedHostKey())
                ssh.connect("192.168.141.142",username="sonth32",password=password,allow_agent=False,look_for_keys=False,timeout=10)
                state=json.loads(sudo(ssh,password,"cat "+args.batch+"/batch.json"))
                print(datetime.now(timezone.utc).isoformat(),state["status"],state.get("current_case"),
                      sum(c["status"]=="completed" for c in state["cases"]),flush=True)
                if state["status"] not in ("preflight","running","reviewing"):
                    remote=sudo(ssh,password,"python3 -",export_script(args.batch)).strip()
                    if not remote.startswith("/tmp/repeats-export-"):raise ValueError("Unexpected export path")
                    staging=Path(tempfile.mkdtemp(prefix="kernel-repeats-export-"))
                    with ssh.open_sftp() as sftp:
                        def download(source,target):
                            target.mkdir(parents=True,exist_ok=True)
                            for entry in sftp.listdir_attr(source):
                                if entry.filename in (".","..") or "/" in entry.filename or "\\" in entry.filename:
                                    raise ValueError("Unsafe export name")
                                if entry.st_mode & 0o170000 == 0o040000:
                                    download(source+"/"+entry.filename,target/entry.filename)
                                else:
                                    destination=target/entry.filename
                                    sftp.get(source+"/"+entry.filename,str(destination))
                                    with sftp.open(source+"/"+entry.filename,"rb") as stream:
                                        h=hashlib.sha256()
                                        while block:=stream.read(1024*1024):h.update(block)
                                    if hashlib.sha256(destination.read_bytes()).digest()!=h.digest():raise ValueError("Download checksum failed")
                        download(remote,staging)
                    break
        except (paramiko.SSHException,OSError,TimeoutError) as error:
            print("Transient read failure:",type(error).__name__,flush=True)
        time.sleep(60)
    # Export safely before touching the working repository; never include unrelated user edits.
    if git(repo,"status","--porcelain").strip():
        raise RuntimeError("Repository changed; export retained at "+str(staging))
    lab=repo/"Testbed_Online_Boutique";batch_name=Path(args.batch).name
    incoming=staging/"runs"/batch_name
    exported=json.loads((incoming/"batch.json").read_text())
    protocol_name=json.loads((incoming/"protocol.json").read_text(encoding="utf-8")).get("repository_protocol","repeat-protocol.json")
    if not re.fullmatch(r"repeat-protocol(?:-v[0-9]+)?\.json",protocol_name):raise ValueError("Invalid repository protocol name")
    if hashlib.sha256((lab/"experiments"/protocol_name).read_bytes()).hexdigest()!=exported["protocol_sha256"]:
        raise RuntimeError("Current repository protocol differs; export retained at "+str(staging))
    for source in (staging/"runs").iterdir():
        destination=lab/"runs"/source.name
        if destination.exists():raise FileExistsError("Never overwrite an existing run: "+str(destination))
    for source in (staging/"runs").iterdir():shutil.copytree(source,lab/"runs"/source.name)
    review_path=lab/"runs"/batch_name/"cohort-review.json"
    review=json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else None
    exported["batch_name"]=batch_name
    (lab/"experiments/REPEATS-RESULTS.md").write_text(render(exported,review),encoding="utf-8",newline="\n")
    paths=git(repo,"ls-files","-z","--cached","--others","--exclude-standard","--","Testbed_Online_Boutique").split(b"\0")
    checksum=lab/"SHA256SUMS.txt";lines=[]
    for name in sorted(set(p for p in paths if p)):
        path=repo/name.decode()
        if path==checksum or not path.is_file():continue
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+"  "+path.relative_to(lab).as_posix())
    checksum.write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")
    subprocess.run([sys.executable,"build.py"],cwd=repo,check=True)
    html=[p.relative_to(repo).as_posix() for p in repo.glob("*.html")]
    owned=["Testbed_Online_Boutique/runs/"+p.name for p in (staging/"runs").iterdir()]
    owned.extend(["Testbed_Online_Boutique/experiments/REPEATS-RESULTS.md","Testbed_Online_Boutique/SHA256SUMS.txt"])
    subprocess.run(["git","add","--",*owned,*html],cwd=repo,check=True)
    subprocess.run(["git","commit","-m","Publish repeated S0-S5 batch evidence and final review"],cwd=repo,check=True)
    subprocess.run(["git","push","origin","main"],cwd=repo,check=True)
    commit=git(repo,"rev-parse","HEAD").decode().strip()
    print("Pushed finite batch result:",commit,flush=True)
    expected=git(repo,"show","HEAD:25-do-lap-s0-s5.html").replace(b"\r\n",b"\n")
    for attempt in range(20):
        try:
            with urllib.request.urlopen("https://sonprocode.github.io/kernel-notes/25-do-lap-s0-s5.html?revision="+commit,timeout=20) as response:
                if response.read().replace(b"\r\n",b"\n")==expected:
                    print("GitHub Pages verified:",commit,flush=True)
                    return
        except OSError:pass
        time.sleep(30)
    raise RuntimeError("Git push succeeded; Pages content verification still pending")


if __name__=="__main__":main()
