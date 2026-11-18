# Bước 5 Giám sát và chạy baseline S0

Chạy các lệnh trên **192.168.141.142**, trong `~/Testbed_Online_Boutique`. Cụm đã có metrics-server để chạy `kubectl top`. Bước này thêm **Prometheus** để giữ số liệu theo thời gian và **Grafana** để hiển thị chúng. Sau đó chạy tải người dùng bình thường bằng loadgenerator của Online Boutique.

## 1 Xác nhận luồng mua hàng trước khi bật tải

Mở frontend bằng port-forward và SSH tunnel như ở bước 4. Thử **xem sản phẩm → thêm vào giỏ → checkout giả lập**. Ghi thành công hay thất bại và thời gian vào nhật ký. HTTP 200 ở trang chủ mới xác nhận đường truy cập tới frontend, còn checkout kiểm tra thêm các backend như payment và shipping.

```bash
sudo k3s kubectl -n boutique get pods -o wide
sudo k3s kubectl -n boutique rollout status deployment/emailservice --timeout=60s
```

Một restart cũ của emailservice đã được ghi nhận trong lần khởi động. So sánh cột RESTARTS trước và sau pha đo. Tiếp tục khi các Pod đều Ready, checkout thành công và restart không tăng.

## 2 Cài Prometheus và Grafana

File `monitoring/values-s0.yaml` chọn một Prometheus trên worker 2, Grafana trên worker 1 và node exporter trên các node. Alertmanager cùng các scrape job của endpoint control-plane không dùng trong lab đã được tắt. Prometheus đặt retention tối đa theo thời gian 1 ngày và theo kích thước 1 GB. Bộ cấu hình này dùng dữ liệu tạm trong Pod, phù hợp lần thử S0 vì lab đang tắt provisioner local-storage. Xuất kết quả cần giữ trước khi xoá hoặc tạo lại Pod. [Prometheus Community Helm Charts](https://prometheus-community.github.io/helm-charts/), [Prometheus Operator Storage](https://prometheus-operator.dev/docs/platform/storage/).

```bash
cd ~/Testbed_Online_Boutique
ls monitoring/values-s0.yaml
sudo helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
sudo helm repo update
sudo helm --kubeconfig /etc/rancher/k3s/k3s.yaml upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  --version 93.3.0 --namespace monitoring --create-namespace \
  -f monitoring/values-s0.yaml --wait --timeout 10m
sudo k3s kubectl -n monitoring get pods,svc -o wide
```

Nếu helm hết thời gian chờ, dùng `sudo k3s kubectl -n monitoring get events --sort-by=.metadata.creationTimestamp` và xem Pod nào Pending hoặc không kéo được image. Chỉ bắt đầu đo sau khi cả Prometheus và Grafana Ready.

## 3 Kiểm tra có dữ liệu thật

Chạy hai port-forward trong hai phiên SSH riêng. Dùng tên Service từ `get svc` nếu bạn đổi tên release.

```bash
sudo k3s kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090
```

```bash
sudo k3s kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
```

Từ PowerShell trên Windows, mở một tunnel cho cả hai cổng.

```powershell
ssh -N -L 9090:127.0.0.1:9090 -L 3000:127.0.0.1:3000 sonth32@192.168.141.142
```

- Ở **http://localhost:9090/targets**, kiểm tra target kubelet/cAdvisor và node-exporter từ hai worker. Trong Prometheus, chạy `up`, rồi truy vấn `container_memory_working_set_bytes{namespace="boutique"}` để kiểm tra có dữ liệu ứng dụng.
- Ở **http://localhost:3000**, đăng nhập Grafana bằng user `admin` và đọc mật khẩu trong terminal riêng bằng lệnh dưới đây. Chọn dashboard Kubernetes hoặc Explore với datasource Prometheus. Xác minh đồ thị có dữ liệu cho namespace `boutique`. Không đưa mật khẩu vào biên bản. [Grafana Helm](https://grafana.com/docs/grafana/latest/setup-grafana/installation/helm/).

```bash
sudo k3s kubectl -n monitoring get secret monitoring-grafana \
  -o jsonpath='{.data.admin-password}' | base64 --decode
echo
```

## 4 Bật traffic bình thường và lưu kết quả

Bộ sinh tải v0.10.7 dùng Locust và gọi `frontend:80` **từ trong cluster**. Manifest đặt `USERS=10`, `RATE=1` và mỗi người dùng gửi yêu cầu theo hành trình của mẫu. Một replica loadgenerator chạy 10 người dùng ảo theo cấu hình này. Tunnel của trình duyệt có thể đóng khi thử tải.

```bash
RUNDIR="runs/s0-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUNDIR"
date -u | tee "$RUNDIR/start.txt"
sudo k3s kubectl -n boutique get pods -o wide > "$RUNDIR/pods-before.txt"
sudo k3s kubectl top nodes > "$RUNDIR/nodes-before.txt"
sudo k3s kubectl -n boutique scale deployment/loadgenerator --replicas=1
sudo k3s kubectl -n boutique rollout status deployment/loadgenerator --timeout=180s
sudo k3s kubectl -n boutique logs deployment/loadgenerator --tail=30
```

Chờ khoảng **2 phút warm-up**, rồi quan sát **15 phút** cho lần thử đầu. Ghi thời gian UTC, thời lượng, 10 người dùng ảo, request rate, tỷ lệ lỗi và độ trễ từ Locust nếu log có các cột đó. Lưu CPU/RAM theo namespace từ Grafana, cùng số Pod restart và kết quả checkout thử. Prometheus mặc định đo node/container và trạng thái tài nguyên; để báo p95 **request** cần số liệu từ Locust hoặc nguồn đo ứng dụng tương ứng.

```bash
date -u | tee "$RUNDIR/end.txt"
sudo k3s kubectl -n boutique logs deployment/loadgenerator > "$RUNDIR/locust.log"
sudo k3s kubectl -n boutique get pods -o wide > "$RUNDIR/pods-after.txt"
sudo k3s kubectl top nodes > "$RUNDIR/nodes-after.txt"
sudo k3s kubectl -n boutique scale deployment/loadgenerator --replicas=0
```

Nếu mở phiên SSH mới, đặt lại biến `RUNDIR` bằng đúng thư mục lần chạy trước khi lưu. Chụp màn hình hoặc xuất dữ liệu Grafana trước khi xóa stack hoặc thay Pod. Apply lại overlay Online Boutique cũng sẽ đưa loadgenerator về 0.

**Tiêu chí hoàn thành S0.** Checkout giả lập hoạt động, loadgenerator tạo được request bình thường có số liệu, Prometheus và Grafana quan sát được hai worker và Pod của `boutique`, và restart không tăng trong cửa sổ đo. Giữ các kết quả của lần này để so sánh khi thêm eBPF hoặc policy.


## Xem lại một lần chạy khi Grafana chưa hiện số liệu

Vào **Dashboards → Kubernetes / Compute Resources / Namespace (Pods)**, chọn **Prometheus** và namespace `boutique`, rồi đặt khoảng thời gian trùng với lần chạy trong `start.txt` và `end.txt`. Nếu dashboard có ô Cluster để trống trong lab một cụm, giữ mặc định. CPU Usage và Memory Usage (w/o cache) là hai biểu đồ cần xem trước.

Nếu dashboard trống, vào **Explore → Prometheus → Code**, chọn khoảng thời gian, chạy từng truy vấn:

```promql
sum by (pod) (container_memory_working_set_bytes{job="kubelet",metrics_path="/metrics/cadvisor",namespace="boutique",container!="",image!=""}) / 1024 / 1024
```

```promql
kube_deployment_status_replicas_available{namespace="boutique",deployment="loadgenerator"}
```

Truy vấn đầu hiển thị RAM mỗi Pod theo MiB. Truy vấn thứ hai xác nhận thời điểm bộ sinh tải có một replica. Số request và độ trễ xem trong `locust.log`, vì cấu hình hiện tại chưa đưa metrics Locust vào Prometheus.

