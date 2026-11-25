"""Upload generated synthetic bytes to the one owned lab receiver, at most 1 RPS."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import threading
import time

from fixture import FIXTURE_ID, PAYLOAD_BYTES, RECEIVER_IP, RECEIVER_PORT, operation_id, payload


def now():
    return datetime.now(timezone.utc).isoformat()


def run(run_id, calls):
    if type(calls) is not int or not 1 <= calls <= 60:
        raise ValueError("Calls must be 1..60")
    payload(run_id, operation_id(0))
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    Path("/tmp/s5-action.pid").write_text(str(os.getpid()))
    tick, started = time.monotonic(), now()
    submitted, skipped = 0, 0
    next_allowed = tick
    try:
        for index in range(calls):
            if stop.wait(max(0, max(tick + index, next_allowed) - time.monotonic())):
                break
            if time.monotonic() > tick + index + 1:
                skipped += 1
                continue
            operation = operation_id(index)
            body = payload(run_id, operation)
            digest = hashlib.sha256(body).hexdigest()
            begin, clock = now(), time.monotonic()
            next_allowed = clock + 1
            connection = http.client.HTTPConnection(RECEIVER_IP, RECEIVER_PORT, timeout=3)
            source_port, status, error, acknowledgment = None, None, None, None
            try:
                connection.connect()
                source_port = connection.sock.getsockname()[1]
                connection.request("POST", "/upload", body=body, headers={
                    "Content-Type": "application/octet-stream", "Connection": "close",
                    "X-Run-ID": run_id, "X-Operation-ID": operation, "X-Payload-SHA256": digest})
                response = connection.getresponse()
                status = response.status
                raw = response.read(8193)
                if len(raw) > 8192:
                    raise ValueError("response_too_large")
                acknowledgment = json.loads(raw)
                if not isinstance(acknowledgment, dict):
                    raise ValueError("receiver_acknowledgment_not_object")
                if status != 200 or acknowledgment.get("operation_id") != operation or acknowledgment.get("run_id") != run_id or acknowledgment.get("payload_sha256") != digest or acknowledgment.get("payload_bytes") != PAYLOAD_BYTES:
                    raise ValueError("receiver_acknowledgment_mismatch")
            except (OSError, http.client.HTTPException, ValueError) as exception:
                error = type(exception).__name__
            finally:
                connection.close()
            record = {"kind": "http_upload", "run_id": run_id, "operation_id": operation,
                      "method": "POST", "path": "/upload", "started": begin, "ended": now(),
                      "duration_ms": (time.monotonic()-clock)*1000, "ip": RECEIVER_IP, "port": RECEIVER_PORT,
                      "target_ips": [RECEIVER_IP], "target_ports": [RECEIVER_PORT], "source_port": source_port,
                      "container_pid": os.getpid(), "payload_bytes": len(body), "payload_sha256": digest,
                      "fixture_id": FIXTURE_ID, "status_code": status, "error": error,
                      "outcome": "received" if error is None and status == 200 else "failed",
                      "receiver_acknowledgment": acknowledgment}
            print(json.dumps(record), flush=True)
            submitted += 1
        stop.wait(max(0, tick + calls - time.monotonic()))
    finally:
        Path("/tmp/s5-client-summary.json").write_text(json.dumps({"run_id": run_id,
            "scheduled": calls, "submitted": submitted, "skipped_late": skipped,
            "started": started, "ended": now(), "elapsed_seconds": time.monotonic()-tick,
            "interrupted": stop.is_set(), "rate": 1, "payload_bytes": PAYLOAD_BYTES}))
        Path("/tmp/s5-action.pid").unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--calls", type=int, required=True)
    args = parser.parse_args()
    run(args.run_id, args.calls)
