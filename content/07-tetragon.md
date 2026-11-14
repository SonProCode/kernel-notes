# Tetragon và TracingPolicy

## Process event và policy chọn sự kiện

Tetragon dùng eBPF để quan sát runtime. Process event cho biết việc thực thi hoặc kết thúc tiến trình, kèm ngữ cảnh có sẵn về Pod và tiến trình cha. Tetragon dùng **TracingPolicy** để cấu hình điểm móc và cách chọn sự kiện. CRD mở rộng API Kubernetes để nhận loại đối tượng này. Policy có thể chỉ quan sát hoặc yêu cầu hành động ở các hook được hỗ trợ. Thí nghiệm baseline trong bài này dùng chế độ quan sát. [R16 TracingPolicy](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-Tracing-Policy.pdf)

Đọc policy theo bốn câu hỏi. Hook chạy khi nào? Thu được đối số gì? Selector giữ sự kiện nào? Khi khớp thì chỉ xuất event hay có hành động? Ví dụ, một policy file có thể giữ sự kiện mở file trong một vùng đường dẫn. Độ chính xác của kết luận phụ thuộc hook và trường thu được.

## Cài agent và thử process event

Ví dụ Bash cho cluster một node Linux. K3s chạy trực tiếp trên VM là một bố trí có thể thử. Nếu dùng kind, đọc cấu hình mount host `/proc` và giá trị `tetragon.hostProcPath` theo hướng dẫn trước khi cài. Với nhiều node, tìm agent cùng node với workload để kiểm tra hoặc thu từ tất cả agent để làm dữ liệu. [R16 Quick Kubernetes Install](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-Kubernetes-Install.pdf)

```bash
helm repo add cilium https://helm.cilium.io
helm repo update
helm search repo cilium/tetragon --versions
TETRAGON_CHART_VERSION='THAY_BANG_PHIEN_BAN'
helm upgrade --install tetragon cilium/tetragon -n kube-system \
  --version "$TETRAGON_CHART_VERSION"
kubectl -n kube-system rollout status daemonset/tetragon --timeout=180s
kubectl -n kube-system get pods -o wide
```

Tạo Pod `runtime-probe` bằng các lệnh ở [bài Falco](06-falco.md#tạo-sự-kiện-đã-biết-và-đọc-json) nếu chưa có. Terminal A mở luồng trước khi tạo sự kiện.

```bash
kubectl -n kube-system exec daemonset/tetragon -c tetragon -- \
  tetra getevents --pods runtime-probe > tetragon-probe.jsonl
```

Terminal B tạo sự kiện.

```bash
date -u +%FT%TZ
kubectl -n boutique exec runtime-probe -- /bin/sh -c 'echo tetragon-smoke'
```

Dừng terminal A sau khi nhận event. Khi học cách đọc log, thêm `-o compact` để xem dòng ngắn. Khi lưu cho parser, dùng JSON. Tìm `process_exec`, binary của shell, thời gian, thuộc tính Pod, parent và định danh tiến trình nếu có. Dùng định danh của công cụ cùng node và thời gian để nối dữ liệu; PID có thể tái sử dụng. [R16 Execution Monitoring](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-Execution-Monitoring.pdf)

## Từ process sang file và network

| Mục tiêu | Ví dụ kiểm thử | Diễn giải |
|---|---|---|
| Theo dõi file | Tạo file vô hại `/tmp/lab-marker`, mở hoặc đọc theo một bước đã ghi thời gian | Cần sửa selector của policy mẫu cho đúng đường dẫn và scope. Xem hook thực sự biểu diễn open hay read. |
| Theo dõi nội bộ | Từ probe tạo kết nối mới tới một listener lab | Giữ destination IP/port, đối chiếu DNS, endpoint và phía đích. Kiểm tra riêng đường Service IP và Pod IP khi cần. |
| Theo dõi ra ngoài | Đi tới một endpoint test được kiểm soát | Policy egress mẫu trong tài liệu có thể loại CIDR nội bộ, nên phù hợp với mục tiêu egress riêng. |

Các sự kiện network và file cần policy phù hợp. Bắt đầu bằng policy mẫu cùng phiên bản tool, đọc hook/selector, bỏ các hành động chặn cho pha quan sát, rồi thử bằng hai trường hợp khớp và không khớp. Lưu YAML thực tế và kết quả kiểm tra. [R16 File Access Monitoring](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-File-Access.pdf), [R16 Network Monitoring](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-Network-Monitoring.pdf), [Network observability](https://tetragon.io/docs/use-cases/network-observability/).

Với pipeline nhiều node, cấu hình xuất tập trung hoặc thu theo từng agent. Mỗi tệp nên có node và khoảng thời gian đi kèm. Dùng thử nghiệm đã biết để kiểm tra selector, throttle và khả năng nhận đủ event ở tải mong muốn.

## Tự kiểm tra

1. **Thấy sự kiện từ node A có thể kết luận đã phủ node B chưa?** Kiểm tra agent và đường thu ở từng node chứa workload.
2. **Policy ví dụ tập trung egress ngoài cluster có phù hợp để dựng đồ thị nội bộ không?** Đọc selector, điều chỉnh theo mục tiêu và kiểm chứng từng cạnh nội bộ mẫu.
3. **Policy chạy rồi nhưng file event trống, kiểm tra gì?** Xác định đúng hook, đường dẫn thực tế, namespace, metadata và tiến trình thử.

Tiếp theo [bài 8](08-du-lieu-va-thuc-nghiem.md).

