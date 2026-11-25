"""Synthetic-only fixture and the explicitly owned lab receiver address."""
import hashlib
import re

RECEIVER_IP = "192.168.141.142"
RECEIVER_PORT = 18080
PAYLOAD_BYTES = 64 * 1024
FIXTURE_ID = "gd4-s5-synthetic-v1"


def operation_id(index):
    if type(index) is not int or not 0 <= index < 60:
        raise ValueError("Operation index must be 0..59")
    return f"upload-{index:05d}"


def payload(run_id, operation):
    if not re.fullmatch(r"(?:s5|s0-s5-control)-[0-9]{8}T[0-9]{6}Z-[0-9]+", run_id):
        raise ValueError("Invalid lab run ID")
    if not re.fullmatch(r"upload-[0-9]{5}", operation) or int(operation[7:]) >= 60:
        raise ValueError("Invalid operation ID")
    prefix = b"GD4-S5-SYNTHETIC-NOT-REAL-DATA\n"
    block = hashlib.sha256((FIXTURE_ID + run_id + operation).encode()).hexdigest().encode()
    return (prefix + block * (PAYLOAD_BYTES // len(block) + 1))[:PAYLOAD_BYTES]
