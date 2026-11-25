"""Linux loopback-only check: previous TIME_WAIT behavior, fix and active bind ownership."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading

from fixture import operation_id, payload
from receiver import Receiver


def check_rebind():
    run="s5-20261125T120000Z-123"
    old_flag=Receiver.allow_reuse_address
    cases=[]
    active_blocked=False
    try:
        for reuse in (False,True):
            Receiver.allow_reuse_address=reuse
            server=Receiver(("127.0.0.1",0),run,1,lambda record:None)
            port=server.server_port
            if reuse:
                try:
                    other=Receiver(("127.0.0.1",port),run,1,lambda record:None)
                except OSError as error:
                    active_blocked=error.errno==98
                else:
                    other.server_close()
            thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01},daemon=True)
            thread.start()
            try:
                body=payload(run,operation_id(0));digest=hashlib.sha256(body).hexdigest()
                headers=(f"POST /upload HTTP/1.0\r\nHost: 127.0.0.1\r\nContent-Type: application/octet-stream\r\nContent-Length: {len(body)}\r\nX-Run-ID: {run}\r\nX-Operation-ID: {operation_id(0)}\r\nX-Payload-SHA256: {digest}\r\n\r\n").encode()
                with socket.create_connection(("127.0.0.1",port),timeout=3) as client:
                    client.sendall(headers+body)
                    response=bytearray()
                    while data:=client.recv(8192):response.extend(data)
                if not response.startswith(b"HTTP/1.0 200"):
                    raise RuntimeError("Loopback fixture upload failed")
            finally:
                server.shutdown();server.server_close();thread.join(timeout=2)
            try:
                again=Receiver(("127.0.0.1",port),run,1,lambda record:None)
            except OSError as error:
                cases.append({"reuse_address":reuse,"rebound":False,"errno":error.errno})
            else:
                again.server_close();cases.append({"reuse_address":reuse,"rebound":True})
    finally:
        Receiver.allow_reuse_address=old_flag
    return {"scope":"Ephemeral loopback ports and synthetic bytes only; lab receiver port 18080 untouched",
            "previous_default_reuse_address":False,"cases":cases,"active_listener_still_blocks_bind":active_blocked,
            "receiver_source_sha256":hashlib.sha256((Path(__file__).parent/"receiver.py").read_bytes()).hexdigest(),
            "check_source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "passed":len(cases)==2 and cases[0].get("errno")==98 and cases[1]["rebound"] and active_blocked}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!="linux":parser.error("Run this Linux socket test on lab-cp")
    if args.output.resolve().is_relative_to((Path(__file__).resolve().parents[2]/"runs").resolve()):
        parser.error("Write the report outside captured runs/")
    result=check_rebind();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2));raise SystemExit(not result["passed"])
