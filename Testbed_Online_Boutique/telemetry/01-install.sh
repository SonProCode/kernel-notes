#!/usr/bin/env bash
# Chạy từ lab-cp bằng: sudo bash telemetry/01-install.sh
# Dừng khi lệnh lỗi (-e), khi dùng biến chưa gán (-u) hoặc khi một lệnh
# trong chuỗi có dấu | thất bại (pipefail).
set -euo pipefail
# Vào thư mục của script để tìm được các file YAML và JSON dù terminal
# đang mở ở thư mục khác. common.sh định nghĩa k = k3s kubectl.
cd "$(dirname "$0")"
source ./common.sh

# 1. Kiểm tra cụm trước khi cài.
# Hai worker phải Ready và có đúng label lab.slot=w1/w2. Chart dùng
# các label này để chọn máy chạy agent. boutique chứa ứng dụng,
# monitoring chứa bộ Prometheus/Grafana đang dùng.
# CRD ServiceMonitor là định nghĩa kiểu tài nguyên ServiceMonitor do
# Prometheus Operator cung cấp. Có kiểu này thì Helm mới tạo được monitor.
command -v helm >/dev/null
command -v python3 >/dev/null
k wait --for=condition=Ready node/lab-w1 node/lab-w2 --timeout=45s
for slot in w1 w2; do
  [[ "$(k get nodes -l "lab.slot=$slot" -o jsonpath='{.items[*].metadata.name}')" == "lab-$slot" ]]
done
k get namespace boutique monitoring
k get crd servicemonitors.monitoring.coreos.com

# 2. Cài Tetragon và khai báo nơi Prometheus lấy số liệu.
# Helm đọc kubeconfig của K3s để kết nối đúng cụm. Lệnh upgrade --install
# cài release tetragon nếu chạy lần đầu và cập nhật release khi chạy lại.
# -n telemetry --create-namespace tạo namespace telemetry nếu chưa có.
# Đây là nơi đặt các thành phần Tetragon. File values-tetragon.yaml chọn
# hai worker và cấu hình những loại sự kiện được xuất log từ boutique.
#
# Chart tạo DaemonSet tetragon. Hãy hình dung có một agent gần từng worker:
# agent trên lab-w1 quan sát kernel lab-w1, agent trên lab-w2 quan sát kernel lab-w2.
# Pod ứng dụng ở worker nào thì agent trên worker đó quan sát sự kiện của nó.
#
# Chart cũng tạo Service và ServiceMonitor trong telemetry. Service cung cấp
# đầu mối để tìm các endpoint /metrics của agent. ServiceMonitor khai báo
# cách scrape (đọc định kỳ), mỗi 15 giây. Nhãn release=monitoring khớp bộ lọc
# của Prometheus hiện có. Ví dụ, Prometheus scrape endpoint của lab-w1 và
# lab-w2 để lưu các bộ đếm sự kiện theo thời gian.
helm --kubeconfig /etc/rancher/k3s/k3s.yaml upgrade --install tetragon tetragon \
  --repo https://helm.cilium.io --version 1.8.0 -n telemetry --create-namespace \
  -f values-tetragon.yaml --wait --timeout 8m
# Chờ DaemonSet triển khai, rồi kiểm tra riêng Pod agent trên từng worker.
# desiredNumberScheduled là số node mà DaemonSet dự kiến đặt Pod, ở lab này là 2.
k -n telemetry rollout status daemonset/tetragon --timeout=3m
for node in lab-w1 lab-w2; do
  k -n telemetry wait --for=condition=Ready "pod/$(agent_pod "$node")" --timeout=60s
done
[[ "$(k -n telemetry get ds tetragon -o jsonpath='{.status.desiredNumberScheduled}')" == 2 ]]
# 3. Đăng ký quy tắc quan sát TCP cho ứng dụng.
# Chờ Kubernetes API hỗ trợ kiểu TracingPolicyNamespaced. Dry-run phía server
# để kiểm tra manifest; lệnh apply kế tiếp mới lưu policy vào cụm.
# policy.yaml đặt policy trong boutique và yêu cầu Tetragon gắn hook vào
# tcp_connect ghi lần thử mở kết nối. tcp_sendmsg ghi lần gửi dữ liệu
# qua kết nối TCP, kể cả kết nối đã mở trước khi bắt đầu đo.
# Policy chỉ ghi nhận sự kiện, nên luồng TCP vẫn tiếp tục bình thường.
# Việc apply thành công xác nhận API đã nhận policy. 02-smoke.sh kiểm tra
# agent trên cả hai worker thực sự ghi được sự kiện.
k wait --for=condition=Established crd/tracingpoliciesnamespaced.cilium.io --timeout=60s
k apply --dry-run=server -f policy.yaml
k apply -f policy.yaml

# 4. Đưa định nghĩa dashboard vào Grafana.
# Ba lệnh nối bằng |: tạo YAML ConfigMap từ dashboard.json trong bộ nhớ,
# gắn nhãn grafana_dashboard=1, rồi áp dụng YAML vào namespace monitoring.
# Sidecar của Grafana thấy ConfigMap có nhãn này và nạp dashboard.
# Luồng hiển thị: Tetragon cung cấp metrics, Prometheus scrape và lưu,
# Grafana truy vấn Prometheus để vẽ biểu đồ. Log gốc đi theo đường riêng:
# 03-baseline.sh lấy từng sự kiện từ container export-stdout trên mỗi worker.
k -n monitoring create configmap boutique-runtime-s0 --from-file=dashboard.json \
  --dry-run=client -o yaml | k label --local -f - grafana_dashboard=1 -o yaml | k apply -f -
# In danh sách Pod, ServiceMonitor và policy để kiểm tra tài nguyên đã tạo.
# Trong Grafana, panel "Số agent scrape thành công" cần lên 2 sau khi Prometheus
# đã khám phá và scrape được endpoint của cả hai agent.
k -n telemetry get pods,servicemonitors -o wide
k -n boutique get tracingpoliciesnamespaced
