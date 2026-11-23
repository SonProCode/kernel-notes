"""S4 isolated workload, metric collection and resource guard helpers."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
PROM = "/api/v1/namespaces/monitoring/services/monitoring-kube-prometheus-prometheus:http-web/proxy/api/v1/"
LOSS_QUERY = 'sum by (__name__,node) ({__name__=~"tetragon_observer_ringbuf_events_lost_total|tetragon_observer_ringbuf_queue_events_lost_total|tetragon_events_export_failed_total|tetragon_export_ratelimit_events_dropped_total",service="tetragon"})'
RESOURCE_QUERIES = {
    "frontend_cpu_cores": 'sum(rate(container_cpu_usage_seconds_total{namespace="boutique",pod=~"frontend-.*",container="server"}[1m]))',
    "frontend_memory_bytes": 'sum(container_memory_working_set_bytes{namespace="boutique",pod=~"frontend-.*",container="server"})',
    "boutique_cpu_cores": 'sum(rate(container_cpu_usage_seconds_total{namespace="boutique",container!="",container!="POD"}[1m]))',
    "boutique_memory_bytes": 'sum(container_memory_working_set_bytes{namespace="boutique",container!="",container!="POD"})',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def command(*args, timeout=20, **kwargs):
    return subprocess.run(["k3s", "kubectl", *args], check=True, text=True, capture_output=True,
                          timeout=timeout, **kwargs).stdout


def get(*args):
    return json.loads(command(*args, "-o", "json"))


def query(name, **parameters):
    return json.loads(command("get", "--raw", PROM + name + "?" + urlencode(parameters)))


def pod_state(pods):
    return {p["metadata"]["uid"]: {"name": p["metadata"]["name"],
            "restarts": sum(c.get("restartCount", 0) for c in p.get("status", {}).get("containerStatuses", []))}
            for p in pods}


class Guard:
    def __init__(self, output, actor, target, phase):
        self.output, self.actor, self.target, self.phase = output, actor, target, phase
        self.baseline = pod_state(get("-n", "boutique", "get", "pods")["items"])
        self.stop, self.triggered = threading.Event(), threading.Event()
        self.reason, self.failed_probes = None, 0
        self.started_monotonic, self.last_sample_monotonic = None, None
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def sample(self):
        nodes = json.loads(command("get", "nodes", "-o", "json", timeout=8))["items"]
        pods = json.loads(command("-n", "boutique", "get", "pods", "-o", "json", timeout=8))["items"]
        state = pod_state(pods)
        reasons = []
        for node in nodes:
            if not any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"]["conditions"]):
                reasons.append("node_not_ready:" + node["metadata"]["name"])
            if any(c["type"] == "MemoryPressure" and c["status"] == "True" for c in node["status"]["conditions"]):
                reasons.append("MemoryPressure:" + node["metadata"]["name"])
        for uid, old in self.baseline.items():
            if uid not in state:
                reasons.append("pod_replaced_or_missing:" + old["name"])
            elif state[uid]["restarts"] > old["restarts"]:
                reasons.append("container_restart:" + old["name"])
        for pod in pods:
            for container in pod.get("status", {}).get("containerStatuses", []):
                if container.get("state", {}).get("terminated", {}).get("reason") == "OOMKilled":
                    reasons.append("OOMKilled:" + pod["metadata"]["name"])
        probe = "import urllib.request; r=urllib.request.urlopen('http://" + self.target["ip"] + ":80/_healthz',timeout=3); print(r.status)"
        try:
            healthy = command("-n", "boutique", "exec", self.actor, "-c", "actor", "--", "python3", "-c", probe, timeout=7).strip() == "200"
        except (subprocess.SubprocessError, OSError):
            healthy = False
        self.failed_probes = 0 if healthy else self.failed_probes + 1
        if self.failed_probes >= 3:
            reasons.append("three_consecutive_frontend_probe_failures")
        return {"timestamp": now(), "phase": self.phase(), "probe_ok": healthy,
                "consecutive_probe_failures": self.failed_probes, "pods": state, "reasons": reasons}

    def loop(self):
        try:
            with (self.output / "guard.ndjson").open("w") as stream:
                while not self.stop.is_set():
                    try:
                        record = self.sample()
                    except Exception as error:
                        record = {"timestamp": now(), "phase": self.phase(), "reasons": ["guard_error:" + type(error).__name__]}
                    if self.stop.is_set(): return
                    stream.write(json.dumps(record) + "\n"); stream.flush()
                    self.last_sample_monotonic = time.monotonic()
                    if record["reasons"]:
                        self.reason = record["reasons"]
                        self.triggered.set()
                        return
                    self.stop.wait(5)
        except BaseException as error:
            self.reason = ["guard_thread_error:" + type(error).__name__]
            self.triggered.set()

    def start(self):
        self.started_monotonic = time.monotonic()
        self.thread.start()

    def failure_reason(self):
        if self.triggered.is_set(): return self.reason or ["guard_triggered"]
        if self.stop.is_set(): return None
        if not self.thread.is_alive(): return ["guard_thread_not_alive"]
        heartbeat = self.last_sample_monotonic if self.last_sample_monotonic is not None else self.started_monotonic
        if heartbeat is None or time.monotonic()-heartbeat>35: return ["guard_heartbeat_stale"]
        return None

    def close(self):
        self.stop.set()
        self.thread.join(timeout=35)
        if self.thread.is_alive():
            raise RuntimeError("Guard did not stop")
