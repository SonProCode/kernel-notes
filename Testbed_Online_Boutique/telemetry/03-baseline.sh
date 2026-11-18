#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source ./common.sh
umask 077
exec 9>/run/lock/boutique-s0-tetragon.lock
flock -n 9 || { echo 'Một lượt S0 Tetragon khác đang chạy.' >&2; exit 1; }

warmup=${WARMUP_SECONDS:-400}
duration=${MEASURE_SECONDS:-900}
[[ "$warmup" =~ ^(0|[1-9][0-9]*)$ && "$duration" =~ ^[1-9][0-9]*$ ]] || {
  echo 'WARMUP_SECONDS phải >= 0 và MEASURE_SECONDS phải > 0, nhập số nguyên.' >&2
  exit 1
}
loadgen() {
  k -n boutique "$@"
}
[[ "$(loadgen get deploy loadgenerator -o jsonpath='{.spec.replicas}')" == 0 ]] || {
  echo 'Cần loadgenerator ở 0 replica trước khi đo.' >&2
  exit 1
}
k -n boutique get tracingpoliciesnamespaced boutique-tcp-connect >/dev/null
users=$(loadgen get deploy loadgenerator -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="USERS")].value}')
rate=$(loadgen get deploy loadgenerator -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="RATE")].value}')
[[ "$users" == 10 && "$rate" == 1 ]] || {
  echo "Cần USERS=10 và RATE=1 theo S0. Hiện tại: USERS=$users RATE=$rate" >&2
  exit 1
}

run="../runs/s0-tetragon-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$run/raw"
echo "Thư mục kết quả: $run"
nodes=(lab-w1 lab-w2)
collectors=()
scaled=0

stop_collectors() {
  local pid
  for pid in "${collectors[@]}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  collectors=()
}
cleanup() {
  local status=$?
  stop_collectors
  if (( scaled )); then
    loadgen scale deployment/loadgenerator --replicas=0 || {
      echo 'Hãy kiểm tra và đưa loadgenerator về 0 replica.' >&2
      status=1
    }
  fi
  if (( status )); then
    echo "Lần đo chưa hoàn tất. Dữ liệu đã thu ở $run" >&2
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

snapshot() {
  local stage=$1
  k -n boutique get deploy,pods,svc,endpointslice -o json > "$run/boutique-$stage.json"
  k -n telemetry get pods -l app.kubernetes.io/name=tetragon -o json > "$run/agents-$stage.json"
  k top nodes > "$run/nodes-$stage.txt" 2>&1 || echo "kubectl top chưa có dữ liệu tại $stage" >&2
}
collectors_alive() {
  local pid
  for pid in "${collectors[@]}"; do
    kill -0 "$pid" 2>/dev/null || {
      echo "Mất luồng log Tetragon. Xem $run/raw/*.stderr" >&2
      return 1
    }
  done
}
pause_with_check() {
  local deadline=$(( SECONDS + $1 )) remaining
  while (( SECONDS < deadline )); do
    collectors_alive
    remaining=$(( deadline - SECONDS ))
    sleep "$(( remaining < 10 ? remaining : 10 ))"
  done
  collectors_alive
}

snapshot before
started=$(utc_now)
for node in "${nodes[@]}"; do
  pod=$(agent_pod "$node")
  k3s kubectl -n telemetry logs "$pod" -c export-stdout --since-time="$started" -f \
    > "$run/raw/$node.ndjson" 2> "$run/raw/$node.stderr" &
  collectors+=("$!")
done

loadgen scale deployment/loadgenerator --current-replicas=0 --replicas=1
scaled=1
loadgen rollout status deployment/loadgenerator --timeout=180s
spawned=0
for attempt in {1..36}; do
  collectors_alive
  loadgen logs deployment/loadgenerator > "$run/locust-startup.log"
  if grep -Fq 'All users spawned' "$run/locust-startup.log"; then
    spawned=1
    break
  fi
  sleep 5
done
[[ "$spawned" == 1 ]] || { echo 'Locust chưa báo đã sinh đủ user.' >&2; exit 1; }

utc_now > "$run/warmup-start.txt"
printf 'users=%s\nspawn_rate=%s\nwarmup_seconds=%s\nmeasurement_seconds=%s\n' \
  "$users" "$rate" "$warmup" "$duration" > "$run/scenario.txt"
echo "Warm-up: $warmup giây"
pause_with_check "$warmup"
utc_now > "$run/measure-start.txt"
echo "Đang đo $duration giây. Có thể mở Grafana trong thời gian này."
pause_with_check "$duration"
utc_now > "$run/measure-end.txt"
loadgen logs deployment/loadgenerator --timestamps > "$run/locust.log"
loadgen scale deployment/loadgenerator --replicas=0
scaled=0
pause_with_check 3
stop_collectors
snapshot after
python3 normalize.py "$run"
echo "Hoàn tất. Xem $run/summary.json và $run/telemetry.ndjson."
