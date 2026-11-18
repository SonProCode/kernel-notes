if [[ $EUID -ne 0 ]]; then
  echo 'Chạy script bằng sudo bash trên lab-cp.' >&2
  exit 1
fi

k() {
  k3s kubectl "$@"
}

utc_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

agent_pod() {
  local node=$1 pod
  pod=$(k -n telemetry get pods -l app.kubernetes.io/name=tetragon \
    --field-selector "spec.nodeName=$node,status.phase=Running" \
    -o jsonpath='{.items[*].metadata.name}')
  if [[ -z "$pod" || "$pod" == *' '* ]]; then
    echo "Cần đúng một Pod Tetragon Running trên $node. Tìm thấy: $pod" >&2
    return 1
  fi
  printf '%s\n' "$pod"
}
