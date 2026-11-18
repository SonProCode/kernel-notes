#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source ./common.sh
umask 077
stamp=$(date -u +%Y%m%d%H%M%S)-$$
result="../runs/smoke-tetragon-$stamp"
mkdir -p "$result"
created=()
cleanup() {
  if (( ${#created[@]} )); then
    k -n boutique delete pod "${created[@]}" --ignore-not-found --wait=false
  fi
}
trap cleanup EXIT
started=$(utc_now)

for node in lab-w1 lab-w2; do
  name="smoke-$node-$stamp"
  k -n boutique create -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $name
spec:
  automountServiceAccountToken: false
  restartPolicy: Never
  activeDeadlineSeconds: 300
  nodeSelector:
    lab.slot: ${node#lab-}
  containers:
    - name: probe
      image: busybox:1.37.0
      command: ["sleep", "300"]
      resources:
        requests:
          cpu: 10m
          memory: 8Mi
EOF
  created+=("$name")
done
for node in lab-w1 lab-w2; do
  name="smoke-$node-$stamp"
  k -n boutique wait --for=condition=Ready "pod/$name" --timeout=90s
  k -n boutique exec "$name" -- wget -T 8 -qO /dev/null http://frontend:80/
  pod=$(agent_pod "$node")
  verified=0
  for attempt in {1..12}; do
    k -n telemetry logs "$pod" -c export-stdout --since-time="$started" > "$result/$node.ndjson"
    if python3 normalize.py --smoke "$result/$node.ndjson" "$name"; then
      echo "$node: thấy process_exec, tcp_connect và tcp_sendmsg từ $name"
      verified=1
      break
    fi
    sleep 3
  done
  if (( !verified )); then
    echo "$node: chưa thấy đủ 3 loại sự kiện. Xem $result/$node.ndjson" >&2
    exit 1
  fi
done
