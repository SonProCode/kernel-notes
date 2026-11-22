"""S3 shell -> helper -> bounded tools and projected-token read."""
import argparse
import base64
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from xml.etree import ElementTree as ET

ROOT = Path("/tmp/gd4-s3")
TOKEN = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(data):
    print(json.dumps(data), flush=True)


def aliases(path):
    result = {str(path), str(path).removesuffix(" (deleted)")}
    for value in list(result):
        if value.startswith("/var/run/"):
            result.add("/run/" + value[len("/var/run/"):])
        if value.startswith("/run/"):
            result.add("/var/run/" + value[len("/run/"):])
    return sorted(result)


def steps(target, round_index):
    address = str(ipaddress.ip_address(target["ip"]))
    if ipaddress.ip_address(address) not in ipaddress.ip_network("10.43.0.0/16"):
        raise ValueError("Expected an explicitly supplied lab Service IP")
    url = f"http://{address}:80/_healthz"
    tools = [
        ("curl", ["--noproxy", "*", "-fsS", "--max-time", "3", "-o", "/dev/null", "-w", "%{http_code}", url]),
        ("wget", ["--no-proxy", "--server-response", "--timeout=3", "--tries=1", "-O", "/dev/null", url]),
        ("nc", ["-n", "-z", "-w", "2", address, "80"]),
        ("nmap", ["--unprivileged", "--datadir", str(ROOT/"share/nmap"), "-sT", "-Pn", "-n",
                  "--disable-arp-ping", "--max-retries", "0", "--host-timeout", "5s", "-p", "80",
                  "-oX", "-", address]),
    ]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(ROOT/"lib")
    env["NMAPDIR"] = str(ROOT/"share/nmap")
    env["HOME"] = str(ROOT)
    for name, arguments in tools:
        binary = str(ROOT/"bin"/name)
        started = now()
        process = subprocess.Popen([binary, *arguments], env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=8)
            code = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            code = -1
        observed = {}
        if name == "curl":
            observed["http_code"] = stdout.strip()
            valid = observed["http_code"] == "200"
        elif name == "wget":
            statuses = re.findall(r"HTTP/\S+\s+(\d+)", stderr)
            observed["http_code"] = statuses[-1] if statuses else None
            valid = observed["http_code"] == "200"
        elif name == "nmap":
            try:
                xml = ET.fromstring(stdout)
                port = xml.find(".//port[@portid='80']/state")
                observed["port_state"] = port.get("state") if port is not None else None
            except ET.ParseError:
                observed["port_state"] = None
            valid = observed["port_state"] == "open"
        else:
            observed["connected"] = code == 0
            valid = code == 0
        emit({"operation_id": f"r{round_index}-{name}", "kind": "runtime_tool", "tool": name,
              "round_index": round_index, "binary": binary, "argv": [binary, *arguments],
              "container_pid": process.pid, "parent_container_pid": os.getpid(),
              "shell_container_pid": os.getppid(), "started": started, "ended": now(),
              "ip": address, "port": 80, "target_ips": target["target_ips"],
              "target_ports": target["target_ports"],
              "return_code": code, "observed": observed,
              "outcome": "completed" if code == 0 and valid else "failed"})
        if code != 0 or not valid:
            raise SystemExit("Bounded S3 tool step failed")
        time.sleep(0.5)

    started = now()
    with TOKEN.open("rb") as source:
        resolved = os.readlink(f"/proc/self/fd/{source.fileno()}")
        content = source.read()
    flags = {"jwt_shape": False, "audience_matches": False,
             "subject_matches": False, "not_expired": False}
    try:
        parts = content.split(b".")
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + b"=" * (-len(parts[1]) % 4)))
        audience = claims.get("aud", [])
        if isinstance(audience, str):
            audience = [audience]
        flags = {"jwt_shape": len(parts) == 3, "audience_matches": audience == ["gd4-s3-lab"],
                 "subject_matches": claims.get("sub") == target["expected_subject"],
                 "not_expired": int(claims.get("exp", 0)) > int(time.time())}
    except (ValueError, IndexError, TypeError):
        pass
    token_size = len(content)
    content = b""
    emit({"operation_id": f"r{round_index}-token", "kind": "file_read",
          "round_index": round_index, "path": str(TOKEN),
          "file_aliases": sorted(set(aliases(TOKEN) + aliases(resolved))),
          "container_pid": os.getpid(), "parent_container_pid": os.getppid(),
          "started": started, "ended": now(), "byte_count": token_size,
          "token_metadata": flags, "token_validation": "shape_and_expected_claims_only",
          "outcome": "read_completed" if all(flags.values()) else "failed"})
    if not all(flags.values()):
        raise SystemExit("Projected-token metadata did not match the expected lab claims")


def perform(target, rounds):
    if not 1 <= rounds <= 3:
        raise ValueError("S3 supports 1..3 rounds")
    for index in range(rounds):
        started, tick = now(), time.monotonic()
        command = shlex.join([sys.executable, str(ROOT/"client.py"), "--steps",
                              "--target", json.dumps(target), "--round", str(index)])
        command += '; result=$?; sleep 0.25; exit "$result"'
        process = subprocess.Popen(["/bin/sh", "-c", command], text=True, stdout=subprocess.PIPE)
        for line in process.stdout:
            print(line.rstrip("\n"), flush=True)
        code = process.wait()
        emit({"operation_id": f"r{index}-shell", "kind": "process_exec", "tool": "shell",
              "round_index": index, "binary": "/bin/sh",
              "binary_aliases": ["/bin/sh", str(Path("/bin/sh").resolve())],
              "container_pid": process.pid, "parent_container_pid": os.getpid(),
              "started": started, "ended": now(), "return_code": code,
              "outcome": "completed" if code == 0 else "failed"})
        if code:
            raise SystemExit("S3 shell round failed")
        time.sleep(max(0, 30 - (time.monotonic() - tick)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", action="store_true", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--round", type=int, required=True)
    args = parser.parse_args()
    steps(json.loads(args.target), args.round)
