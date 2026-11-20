"""S2 client for the mock PaymentService in Online Boutique v0.10.7."""
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
import time
import uuid

BASE = Path("/tmp/gd4-s2")
sys.path[:0] = [str(BASE / "deps"), str(BASE / "api")]
import grpc
import demo_pb2
import demo_pb2_grpc


def now():
    return datetime.now(timezone.utc).isoformat()


def perform(targets, calls):
    if len(targets) != 1 or targets[0]["service"] != "paymentservice":
        raise ValueError("S2 requires exactly one paymentservice target")
    target = targets[0]
    address = ipaddress.ip_address(target["ip"])
    if address not in ipaddress.ip_network("10.43.0.0/16") or target["port"] != 50051:
        raise ValueError("S2 target must be the lab PaymentService at port 50051")
    if not 1 <= calls <= 30:
        raise ValueError("S2 permits 1..30 calls")
    fixture = json.loads((BASE / "fixture.json").read_text())
    endpoint = f"{address}:{target['port']}"
    with grpc.insecure_channel(endpoint, options=[("grpc.enable_retries", 0)]) as channel:
        grpc.channel_ready_future(channel).result(timeout=5)
        client = demo_pb2_grpc.PaymentServiceStub(channel)
        for index in range(calls):
            operation_id = f"charge-{index:04d}"
            nanos = (index + 1) * fixture["amount"]["nanos_step"]
            request = demo_pb2.ChargeRequest(
                amount=demo_pb2.Money(currency_code="USD", units=1, nanos=nanos),
                credit_card=demo_pb2.CreditCardInfo(**fixture["credit_card"]))
            digest = hashlib.sha256(request.SerializeToString(deterministic=True)).hexdigest()
            started = now()
            tick = time.monotonic()
            code, outcome, transaction_id, error = "UNKNOWN", "rpc_error", None, None
            try:
                response = client.Charge(request, timeout=3,
                                         metadata=[("x-gd4-operation-id", operation_id)])
                # A valid response is application-level evidence.
                transaction_id = str(uuid.UUID(response.transaction_id))
                code, outcome = "OK", "api_success"
            except grpc.RpcError as exc:
                code, error = exc.code().name, exc.details()
            except ValueError:
                code, error = "INVALID_RESPONSE", "Response lacks a valid transaction UUID"
            ended = now()
            print(json.dumps({
                "operation_id": operation_id, "kind": "grpc_call",
                "service": "paymentservice", "ip": str(address), "port": 50051,
                "target_ips": target["target_ips"],
                "method": "/hipstershop.PaymentService/Charge",
                "started": started, "ended": ended,
                "elapsed_ms": round((time.monotonic() - tick) * 1000, 3),
                "grpc_code": code, "outcome": outcome, "transaction_id": transaction_id,
                "payload_sha256": digest, "fixture_id": fixture["fixture_id"],
                "amount": {"currency_code": "USD", "units": 1, "nanos": nanos},
                "expected_access": "outside_allowed_checkout_role", "error": error,
            }), flush=True)
            # A persistent channel illustrates repeated RPCs over an existing connection.
            time.sleep(max(0, 2 - (time.monotonic() - tick)))
