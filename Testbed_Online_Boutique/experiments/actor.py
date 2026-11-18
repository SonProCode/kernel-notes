"""Bounded lab actions. Receipts contain metadata, never fixture contents."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import socket
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def perform(scenario, targets):
    if scenario == "S3":
        path = Path("/tmp/gd4-fixture/token")
        for index in range(3):
            start = now()
            with path.open("rb") as source:
                size = len(source.read())
            print(json.dumps({"operation_id": f"file-{index:04d}", "kind": "file_read",
                              "path": str(path), "started": start, "ended": now(),
                              "outcome": "read_completed", "byte_count": size}), flush=True)
            time.sleep(1)
        return
    if scenario != "S1":
        raise ValueError("Unsupported action")
    if len(targets) > 40:
        raise ValueError("At most 40 explicitly supplied targets")
    for index, target in enumerate(targets):
        ip = ipaddress.ip_address(target["ip"])
        if ip not in ipaddress.ip_network("10.43.0.0/16"):
            raise ValueError("Targets must be explicit lab Service IPs")
        port = int(target["port"])
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        start = now()
        tick = time.monotonic()
        with socket.socket() as connection:
            connection.settimeout(1)
            try:
                connection.connect((str(ip), port))
                outcome = "connected"
            except socket.timeout:
                outcome = "timeout"
            except OSError as error:
                outcome = f"os_error_{error.errno}"
        print(json.dumps({"operation_id": f"connect-{index:04d}", "kind": "tcp_connect",
                          "service": target["service"], "ip": str(ip), "port": port,
                          "started": start, "ended": now(), "outcome": outcome}), flush=True)
        time.sleep(max(0, 0.2 - (time.monotonic() - tick)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["S1", "S3"])
    parser.add_argument("--targets", default="[]")
    args = parser.parse_args()
    perform(args.scenario, json.loads(args.targets))
