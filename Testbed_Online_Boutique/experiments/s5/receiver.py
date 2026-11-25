"""Temporary bounded receiver: acknowledge synthetic payloads, persist metadata only."""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
import signal
import threading
import time

from fixture import FIXTURE_ID, PAYLOAD_BYTES, RECEIVER_IP, RECEIVER_PORT, operation_id, payload


def now():
    return datetime.now(timezone.utc).isoformat()


class Receiver(HTTPServer):
    allow_reuse_address = False

    def __init__(self, address, run_id, calls, sink=None):
        if type(calls) is not int or not 1 <= calls <= 60:
            raise ValueError("Receiver accepts at most 60 operations")
        self.run_id, self.calls, self.seen = run_id, calls, set()
        self.sink = sink or (lambda r: print(json.dumps(r), flush=True))
        self.deadline = time.monotonic() + 1800
        self.stop_requested = threading.Event()
        super().__init__(address, Handler)
        self.timeout = .5

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(3)
        return connection, address


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(200 if self.path == "/healthz" else 404,
                   {"run_id": self.server.run_id, "fixture_id": FIXTURE_ID})

    def do_POST(self):
        started = now()
        operation = self.headers.get("X-Operation-ID")
        try:
            address = ipaddress.ip_address(self.client_address[0])
            allowed = address in ipaddress.ip_network("10.42.0.0/16") or str(address) in (
                "127.0.0.1", RECEIVER_IP, "192.168.141.143", "192.168.141.144")
            expected_ids = {operation_id(i) for i in range(self.server.calls)}
            if not allowed or self.path != "/upload" or self.headers.get("X-Run-ID") != self.server.run_id:
                raise ValueError("wrong_source_path_or_run")
            if time.monotonic() >= self.server.deadline:
                raise ValueError("receiver_expired")
            if operation not in expected_ids or operation in self.server.seen:
                raise ValueError("invalid_or_duplicate_operation")
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise ValueError("ambiguous_body_length")
            if self.headers.get("Content-Type") != "application/octet-stream" or int(self.headers.get("Content-Length", "0")) != PAYLOAD_BYTES:
                raise ValueError("wrong_payload_length_or_type")
            data = self.rfile.read(PAYLOAD_BYTES)
            digest = hashlib.sha256(data).hexdigest()
            expected = hashlib.sha256(payload(self.server.run_id, operation)).hexdigest()
            if len(data) != PAYLOAD_BYTES or digest != expected or self.headers.get("X-Payload-SHA256") != digest:
                raise ValueError("payload_checksum_mismatch")
            receipt = {"kind": "received", "run_id": self.server.run_id, "operation_id": operation,
                       "started": started, "ended": now(), "payload_bytes": len(data), "payload_sha256": digest,
                       "peer_ip": self.client_address[0], "peer_port": self.client_address[1],
                       "receiver_ip": RECEIVER_IP, "receiver_port": RECEIVER_PORT, "fixture_id": FIXTURE_ID}
            self.server.seen.add(operation)
            self.server.sink(receipt)
            self.reply(200, receipt)
        except (ValueError, OSError) as error:
            self.server.sink({"kind": "rejected", "timestamp": now(), "reason": str(error)[:100]})
            try:
                self.reply(400, {"error": "rejected"})
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--calls", type=int, required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--gid", type=int, required=True)
    args = parser.parse_args()
    payload(args.run_id, operation_id(0))
    if args.uid <= 0 or args.gid <= 0:
        parser.error("Receiver must run as a non-root user")
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(args.gid)
        os.setuid(args.uid)
    if os.geteuid() != args.uid:
        raise RuntimeError("Receiver identity mismatch")
    server = Receiver((RECEIVER_IP, RECEIVER_PORT), args.run_id, args.calls)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: server.stop_requested.set())
    server.sink({"kind": "receiver_ready", "timestamp": now(), "pid": os.getpid(),
                 "uid": os.geteuid(), "bind_ip": RECEIVER_IP, "port": RECEIVER_PORT,
                 "run_id": args.run_id, "max_calls": args.calls, "ttl_seconds": 1800})
    try:
        while not server.stop_requested.is_set() and time.monotonic() < server.deadline:
            server.handle_request()
    finally:
        server.server_close()
        server.sink({"kind": "receiver_stopped", "timestamp": now(), "received": len(server.seen)})


if __name__ == "__main__":
    main()
