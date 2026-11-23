"""Bounded, paced HTTP GET workload for the private Online Boutique lab."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import os
from pathlib import Path
import signal
import threading
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def run(target, rate, duration, concurrency):
    if ipaddress.ip_address(target["ip"]) not in ipaddress.ip_network("10.43.0.0/16"):
        raise ValueError("Only the explicitly supplied lab Service IP is allowed")
    if rate not in (3, 6, 10) or not 1 <= duration <= 90 or not 1 <= concurrency <= 4:
        raise ValueError("Unsupported bounded profile")
    Path("/tmp/s4-action.pid").write_text(str(os.getpid()))
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    slots = threading.BoundedSemaphore(concurrency)
    output_lock = threading.Lock()
    stats = {"scheduled": rate * duration, "submitted": 0, "skipped_busy": 0, "skipped_late": 0}

    def request(index):
        begin, tick = now(), time.perf_counter()
        connection = http.client.HTTPConnection(target["ip"], 80, timeout=3)
        source_port, status, error, size = None, None, None, 0
        try:
            connection.connect()
            source_port = connection.sock.getsockname()[1]
            connection.request("GET", "/", headers={"Connection": "close", "User-Agent": "gd4-s4-lab/1"})
            response = connection.getresponse()
            status = response.status
            body = response.read(1048577)
            size = len(body)
            if size > 1048576:
                error = "response_limit_exceeded"
        except (OSError, http.client.HTTPException) as exception:
            error = type(exception).__name__
        finally:
            connection.close()
            record = {"operation_id": f"http-{index:05d}", "kind": "http_request", "method": "GET", "path": "/",
                      "started": begin, "ended": now(), "duration_ms": (time.perf_counter() - tick) * 1000,
                      "ip": target["ip"], "port": 80, "target_ips": target["target_ips"],
                      "target_ports": target["target_ports"], "source_port": source_port,
                      "container_pid": os.getpid(), "status_code": status, "response_bytes": size,
                      "error": error, "outcome": "http_success" if status == 200 and error is None else "http_error"}
            with output_lock:
                print(json.dumps(record), flush=True)
            slots.release()

    begin, tick = now(), time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for index in range(stats["scheduled"]):
                due = tick + index / rate
                if stopped.wait(max(0, due - time.monotonic())):
                    break
                if time.monotonic() - due > 1 / rate:
                    stats["skipped_late"] += 1
                    continue
                if not slots.acquire(blocking=False):
                    stats["skipped_busy"] += 1
                    continue
                pool.submit(request, index)
                stats["submitted"] += 1
            stopped.wait(max(0, tick + duration - time.monotonic()))
    finally:
        summary = {**stats, "started": begin, "ended": now(), "elapsed_seconds": time.monotonic() - tick,
                   "configured_rate": rate, "duration_seconds": duration, "concurrency": concurrency,
                   "interrupted": stopped.is_set(), "connection_mode": "one_new_tcp_connection_per_request"}
        Path("/tmp/s4-client-summary.json").write_text(json.dumps(summary))
        Path("/tmp/s4-action.pid").unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--rate", type=int, required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    args = parser.parse_args()
    run(json.loads(args.target), args.rate, args.duration, args.concurrency)
