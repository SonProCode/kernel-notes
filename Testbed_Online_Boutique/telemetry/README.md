# GĐ3 · Thu telemetry cho Online Boutique

Mục tiêu của tuần 7–10 là lấy một bộ log đại diện cho traffic bình thường trong namespace `boutique` và có dashboard kiểm tra được đường thu dữ liệu. Bộ script dùng Tetragon **1.8.0** trên `lab-w1` và `lab-w2`, hai worker của cụm K3s. Tôi chọn Tetragon trước vì giai đoạn này cần nhìn thấy tiến trình và kết nối TCP theo workload. Nếu đề cương yêu cầu so sánh Falco, chạy Falco ở một lượt riêng với cùng tải để đo được ảnh hưởng của mỗi công cụ.

| Tuần | Công việc | Kết quả cần thấy |
| --- | --- | --- |
| 7 | Cài Tetragon trên hai worker và chạy hai Pod kiểm tra. | Mỗi worker ghi được `process_exec`, `tcp_connect` và `tcp_sendmsg` từ Pod kiểm tra. |
| 8 | Chạy thử ngắn, sau đó đo một lượt S0 15 phút với Locust 10 user. | Có log riêng của hai worker, mốc UTC, log Locust và snapshot cụm trước/sau. |
| 9 | Chuẩn hóa log thành NDJSON và kiểm tra dữ liệu thiếu. | Có schema v2, số sự kiện theo node/workload và số kết nối thiếu đích. |
| 10 | Đọc dashboard, so lại với lượt S0 đã đo và lặp thêm các lượt cùng cấu hình. | Có bộ log baseline, ảnh dashboard và ghi chú sự cố hoặc chênh lệch qua từng lượt. |

## Chạy trên lab-cp

Từ Windows, mở SSH vào control-plane. Chạy các lệnh sau trong terminal của VM. Helm và Prometheus/Grafana dùng theo cụm hiện tại.

```bash
ssh sonth32@192.168.141.142
cd ~/Testbed_Online_Boutique

sudo bash telemetry/01-install.sh
sudo bash telemetry/02-smoke.sh
```

### Bước 1 · `01-install.sh` làm gì?

#### 1. Kiểm tra cụm và tạo namespace `telemetry`

Script kiểm tra Helm, Python 3, trạng thái `Ready` của hai worker, nhãn `lab.slot` và hai namespace hiện có. `boutique` chứa ứng dụng Online Boutique, còn `monitoring` chứa Prometheus và Grafana. Script cũng kiểm tra cụm đã có CRD `ServiceMonitor`. CRD là định nghĩa giúp Kubernetes hiểu thêm một kiểu tài nguyên.

Helm đọc kubeconfig của K3s để kết nối tới cụm. Cờ `--create-namespace` tạo `telemetry` nếu chưa có. Namespace là cách nhóm tài nguyên Kubernetes theo tên. Trong lab, `telemetry` là nơi đặt các thành phần quan sát của Tetragon. Helm dùng `upgrade --install` để cài release ở lần đầu và cập nhật release đó khi chạy lại. File `values-tetragon.yaml` chứa cấu hình riêng của lab. [Cài Tetragon bằng Helm](https://tetragon.io/docs/installation/kubernetes/)

#### 2. Đặt một agent Tetragon trên mỗi worker

Helm tạo một **DaemonSet**. DaemonSet đặt một Pod agent lên mỗi node phù hợp với bộ lọc `lab.slot`, ở đây là `lab-w1` và `lab-w2`. Agent chạy với quyền cần thiết để quan sát hoạt động trong kernel của chính worker đó. Ví dụ, nếu Pod `checkoutservice` nằm trên `lab-w1`, agent trên `lab-w1` ghi nhận sự kiện của tiến trình trong Pod đó.

Sau khi Helm cài xong, script đợi DaemonSet triển khai rồi kiểm tra có một Pod agent `Ready` trên từng worker. Kết quả mong đợi là hai agent.

#### 3. Cho Prometheus biết chỗ lấy số liệu

- **Service** cung cấp đầu mối để Prometheus tìm các endpoint của hai agent. Mỗi agent cung cấp các bộ đếm ở đường dẫn `/metrics`.
- **ServiceMonitor** chỉ cho Prometheus Operator biết Service nào cần theo dõi, đọc đường dẫn nào và đọc bao lâu một lần. Chart tạo ServiceMonitor với nhãn `release=monitoring` để bộ Prometheus của lab chọn đúng tài nguyên này.
- **Prometheus** đọc từng endpoint mỗi 15 giây. Thao tác đọc định kỳ này gọi là *scrape*. Ví dụ, nếu bộ đếm tăng từ 100 lên 130 giữa hai lần đọc, Prometheus có thể tính tốc độ sự kiện từ mức tăng đó. [Cấu hình metrics của Tetragon](https://tetragon.io/docs/installation/metrics/)

#### 4. Áp dụng policy để ghi sự kiện TCP trong `boutique`

`policy.yaml` tạo một `TracingPolicyNamespaced` tên `boutique-tcp-connect` trong namespace `boutique`. Policy gắn hai điểm quan sát (*hook*) trong kernel. `tcp_connect` ghi lần thử mở kết nối mới. `tcp_sendmsg` ghi lúc tiến trình gửi dữ liệu qua TCP, kể cả khi kết nối đã được mở trong warm-up. Agent có thể ghi lại tiến trình, IP và cổng đích. Policy chạy ở chế độ quan sát. Một kết nối có thể được tái sử dụng cho nhiều request HTTP hoặc gRPC, vì vậy hãy dùng Locust khi cần đếm request.

Script chạy `kubectl apply --dry-run=server` để nhờ Kubernetes kiểm tra manifest, sau đó mới lưu policy bằng `kubectl apply`. Bước 2 bên dưới kiểm tra agent thật sự ghi được sự kiện trên cả hai worker. [Policy theo namespace](https://tetragon.io/docs/concepts/tracing-policy/k8s-filtering/), [Quan sát kết nối TCP](https://tetragon.io/docs/use-cases/network-observability/)

#### 5. Nạp dashboard vào Grafana

Script đóng gói `dashboard.json` vào một **ConfigMap**, tài nguyên lưu cấu hình trong Kubernetes. ConfigMap nằm trong namespace `monitoring` và mang nhãn `grafana_dashboard=1`. Thành phần đi kèm Grafana theo dõi nhãn này và nạp dashboard **Online Boutique · Runtime telemetry S0**.

```text
Mỗi worker → Tetragon → /metrics → Prometheus → Grafana
                     └→ export-stdout → 03-baseline.sh → file log theo worker
```

Trong Grafana, bạn xem tốc độ sự kiện theo loại hoặc workload. Khi cần xem một sự kiện cụ thể, chẳng hạn Pod nào đã thử kết nối tới IP và cổng nào, mở log mà `03-baseline.sh` thu từ từng agent.

### Bước 2 · Kiểm tra agent thực sự ghi log

`02-smoke.sh` tạo một Pod tạm trên mỗi worker và dùng `wget` gọi `http://frontend:80/` từ trong cụm. Script xác nhận log agent tương ứng có sự kiện chạy tiến trình, mở kết nối và gửi TCP từ đúng Pod kiểm tra. Pod tạm được dọn khi script kết thúc. Log kiểm tra nằm trong `runs/smoke-tetragon-*`.

Tiếp theo, mở Grafana bằng tunnel hiện có tại [localhost:3000](http://localhost:3000) và tìm dashboard **Online Boutique · Runtime telemetry S0**. Chờ panel **Số agent scrape thành công** lên **2**. Nếu hiện 0 hoặc 1, kiểm tra Prometheus Targets và đầu ra sau trước khi bắt đầu lần đo chính.

```bash
sudo k3s kubectl -n telemetry get pods,svc,endpointslice,servicemonitors -o wide
sudo k3s kubectl -n telemetry describe servicemonitor tetragon
sudo k3s kubectl -n monitoring get cm boutique-runtime-s0 --show-labels
```

## Chạy tải và lấy log

Lượt S0 ngày 17/11/2026 đã phục vụ khoảng 1.983 request trong 15 phút. File chuẩn hóa có 3 sự kiện Redis. Cả 19 lần mở kết nối TCP ghi được trên `lab-w1` đều nằm trước cửa sổ đo. Từ schema v2, `tcp_send` cho biết workload vẫn trao đổi dữ liệu trong khoảng đo dù tái sử dụng kết nối. Xem hai hook trong panel **Hoạt động TCP theo workload và hook**. [Ví dụ policy upstream](https://raw.githubusercontent.com/cilium/tetragon/v1.8.0/examples/tracingpolicy/tcp-connect.yaml)

Lượt thử schema v2 lúc 23:24–23:25 ngày 17/11/2026, giờ Việt Nam, thu được 9.318 sự kiện gửi TCP trong 60 giây (5.019 từ lab-w1 và 4.299 từ lab-w2). Các kiểm tra thu log đạt và loadgenerator đã về 0 replica. Thư mục trên lab-cp là `runs/s0-tetragon-20261117T162316Z-3962421`.

Có thể chạy lượt ngắn để thử cả đường thu. Dùng lượt đủ 15 phút khi lập bộ log baseline.

```bash
# Chạy thử 1 phút sau 30 giây warm-up
sudo env WARMUP_SECONDS=30 MEASURE_SECONDS=60 bash telemetry/03-baseline.sh

# Chạy S0 chính thức với warm-up 400 giây và đo 900 giây
sudo bash telemetry/03-baseline.sh
```

Chạy từng lượt tuần tự. Bắt đầu với `loadgenerator` ở 0 replica. Script bật nó lên 1 replica, đợi Locust báo đủ 10 user, chờ warm-up rồi mới ghi mốc bắt đầu đo. `RATE=1` là tốc độ tạo user ảo, tính theo user/giây. Tốc độ HTTP thực tế lấy từ Locust. Script đưa loadgenerator về 0 khi kết thúc hoặc khi nhận Ctrl+C. Giữ nguyên số user, phiên bản workload và đường sinh tải giữa các lượt. 400 giây warm-up được chọn gần với lượt S0 đã ghi trước đó. Mở Grafana ở chế độ UTC và chọn đúng khoảng trong `measure-start.txt` / `measure-end.txt`.

| File trong `runs/s0-tetragon-*` | Nội dung |
| --- | --- |
| `raw/lab-w1.ndjson`, `raw/lab-w2.ndjson` | Log gốc theo worker, gồm cả giai đoạn warm-up, và các file `.stderr` tương ứng. |
| `telemetry.ndjson` | Một sự kiện trên mỗi dòng JSON, chỉ trong khoảng đo `[start, end)`. |
| `summary.json` | Số sự kiện theo loại, workload và node. Có số dòng lỗi, số kết nối thiếu đích và kiểm tra agent có restart hay đổi Pod trong khi đo. |
| `scenario.txt`, `measure-*.txt`, `locust.log` | Tham số tải, giờ UTC và log Locust có timestamp. Các bảng Locust là thống kê tích lũy và có thể gồm warm-up. Đọc p95 cho đúng khoảng đo cần nguồn độ trễ có thể tách riêng khoảng này. |
| `boutique-*.json`, `agents-*.json`, `nodes-*.txt` | Snapshot Deployment, Pod, Service, EndpointSlice, agent và CPU/RAM tại hai mốc. Xem đồ thị CPU/RAM trong Grafana để đánh giá cả khoảng đo. |

Script chạy bằng root trên VM, nên dùng `sudo cat` hoặc `sudo less` để đọc thư mục kết quả. Log thô có thể chứa tham số lệnh và địa chỉ nội bộ. Giữ thư mục `runs/` trên lab hoặc trong nơi lưu dữ liệu nghiên cứu riêng.

## Đọc một sự kiện

Ví dụ minh họa theo schema v2 với địa chỉ IP giả định.

```json
{"schema_version":2,"timestamp":"2026-11-16T09:00:00Z","source":"tetragon","scenario":"S0","run_id":"s0-tetragon-example","event_type":"tcp_connect_attempt","node":"lab-w1","namespace":"boutique","workload":"checkoutservice","pod":"checkoutservice-abc","pod_uid":"example-uid","container":"server","binary":"/src/checkoutservice","exec_id":"example-exec","policy":"boutique-tcp-connect","socket":{"src_ip":"10.42.1.10","src_port":null,"dst_ip":"10.42.2.15","dst_port":50051},"bytes_requested":null}
```

Sự kiện này cho biết tiến trình của `checkoutservice` trên `lab-w1` đã thử mở một kết nối TCP đến IP và cổng quan sát được ở kernel. Có thể tra IP với Service ClusterIP hoặc Pod IP trong snapshot của lượt đo. Nếu địa chỉ đã bị NAT, hãy ghi chú IP quan sát được và đối chiếu với EndpointSlice trước khi gán tên đích. Cổng nguồn có thể chưa được gán lúc hook chạy. Một kết nối HTTP/2 hoặc gRPC có thể phục vụ nhiều request, nên dùng Locust để đánh giá request/s và tỷ lệ lỗi HTTP. Sự kiện `tcp_send` có thêm `bytes_requested`, số byte tiến trình yêu cầu gửi tại thời điểm hook. Số này có thể khác số byte thực sự gửi thành công. Một lần gửi TCP có thể mang một phần request hoặc dữ liệu của nhiều request. Với `process_exec` hoặc `process_exit`, `socket` là `null`. Các trường vắng mặt trong dữ liệu gốc cũng ghi `null`. [Sự kiện Tetragon](https://tetragon.io/docs/concepts/events/), [Metric Tetragon](https://tetragon.io/docs/reference/metrics/)

Đọc `summary.json` trước. Cần có ít nhất một sự kiện `tcp_send` trong cửa sổ đo từ mỗi worker, JSON và timestamp hợp lệ, agent không đổi Pod hoặc tăng restart, và không có lỗi từ các luồng thu. Xem thêm panel mất sự kiện và lỗi export trong cả khoảng đo. Nếu panel hiện `No data`, kiểm tra target và tên metric trong Prometheus trước khi diễn giải. Khi so với lượt S0 cũ, dùng số liệu của từng lượt, kiểm tra lỗi checkout và ghi chú lượt nào thiếu p95. Lưu ảnh dashboard cùng khoảng UTC để dễ đối chiếu.

## Dừng thu khi cần

Để gỡ các hook TCP và tiếp tục giữ agent, chạy từ thư mục testbed:

```bash
sudo k3s kubectl delete -f telemetry/policy.yaml
```

Để gỡ cả agent và dashboard:

```bash
sudo helm --kubeconfig /etc/rancher/k3s/k3s.yaml -n telemetry uninstall tetragon
sudo k3s kubectl -n monitoring delete configmap boutique-runtime-s0 --ignore-not-found
```
