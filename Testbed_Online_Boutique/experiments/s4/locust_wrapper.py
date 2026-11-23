"""Attach metadata-only request instrumentation to the original image workload."""
import datetime as _s4_datetime
import hashlib as _s4_hashlib
import json as _s4_json
from pathlib import Path as _s4_Path
import time as _s4_time

import locust
from locust import events
_s4_count = 0


@events.request.add_listener
def record_request(request_type, name, response_time, response_length, response=None,
                   exception=None, start_time=None, **kwargs):
    global _s4_count
    _s4_count += 1
    end = _s4_time.time()
    start = start_time if start_time is not None else end - response_time / 1000
    record = {"sequence": _s4_count, "started": _s4_datetime.datetime.fromtimestamp(start, _s4_datetime.timezone.utc).isoformat(),
              "ended": _s4_datetime.datetime.fromtimestamp(end, _s4_datetime.timezone.utc).isoformat(),
              "method": request_type, "path": name.split("?", 1)[0],
              "duration_ms": response_time, "status_code": getattr(response, "status_code", None),
              "response_bytes": response_length, "error": type(exception).__name__ if exception else None,
              "workload_class": "normal_shopping"}
    print("S4REQ " + _s4_json.dumps(record), flush=True)


@events.quitting.add_listener
def record_final(environment, **kwargs):
    print("S4FINAL " + _s4_json.dumps({"recorded_requests": _s4_count,
          "locust_num_requests": environment.stats.total.num_requests,
          "locust_num_failures": environment.stats.total.num_failures}), flush=True)


original = _s4_Path("/loadgen/locustfile.py").read_bytes()
print("S4META " + _s4_json.dumps({"locust_version": locust.__version__,
      "original_locustfile_sha256": _s4_hashlib.sha256(original).hexdigest()}), flush=True)
# Keep the actual image's original task weights, URLs, user type and think time.
exec(compile(original, "/loadgen/locustfile.py", "exec"), globals())
