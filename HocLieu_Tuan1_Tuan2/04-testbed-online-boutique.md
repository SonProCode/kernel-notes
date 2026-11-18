# Dựng lab Online Boutique có thể tái lập

## Testbed là gì

Testbed là môi trường thí nghiệm có cấu hình được ghi lại để lặp lại phép đo. Một cluster Linux một node đủ để thử pipeline. Khi nghiên cứu khác biệt cùng node và khác node, cần bố trí workload trên nhiều node và lưu thông tin vị trí. Ví dụ dưới đây giả định có cluster lab, `kubectl`, và Helm nếu cài collector qua chart. Trên máy Windows có thể dùng một VM Linux cho node và chạy các lệnh Bash ở VM. Phiên bản kernel cần đọc từ node Linux chạy agent.

Một cài đặt K3s mặc định có controller NetworkPolicy tích hợp. Khả năng thực thi trong cụm cụ thể vẫn cần kiểm chứng bằng kết nối thử theo [bài 3](03-bao-mat-kubernetes-networkpolicy.md). [K3s Quick Start](https://docs.k3s.io/quick-start), [K3s Networking Services](https://docs.k3s.io/networking/networking-services).

## Luồng ứng dụng và dữ liệu mẫu

| Hành trình | Chuỗi đơn giản hóa để bắt đầu quan sát |
|---|---|
| Mở trang và xem sản phẩm | Trình duyệt → frontend → productcatalogservice |
| Thêm giỏ hàng | Frontend → cartservice → redis-cart |
| Đặt hàng | Frontend → checkoutservice → paymentservice, shippingservice và emailservice |
| Gợi ý sản phẩm | Frontend → recommendationservice → productcatalogservice |
| Tải nền | Loadgenerator → frontend |

Đây là các cạnh mẫu, có thể có thêm cạnh phụ thuộc đường chạy. README và sơ đồ mô tả cấu trúc. Quan sát thực tế để xác định cạnh nào xuất hiện ở phiên bản và cấu hình thí nghiệm. Dùng dữ liệu thanh toán giả lập. [R8 README v0.10.7](../TaiLieu_Tuan1_Tuan2/PDF/R8-Online-Boutique-README-v0.10.7.pdf)

## Chạy workload từ manifest đã lưu

Dùng [ZIP mã nguồn v0.10.7](../TaiLieu_Tuan1_Tuan2/R8-Online-Boutique-v0.10.7.zip), giải nén rồi mở shell ở thư mục gốc bản giải nén. Kiểm tra context trỏ vào cluster lab và node đã Ready.

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl create namespace boutique --dry-run=client -o yaml | kubectl apply -f -
kubectl -n boutique apply -f release/kubernetes-manifests.yaml
kubectl -n boutique rollout status deployment/frontend --timeout=180s
kubectl -n boutique get deploy,pods,svc,endpointslice -o wide
kubectl -n boutique port-forward service/frontend 8080:80
```

Mở `http://localhost:8080` từ máy chạy lệnh port-forward. Nếu lệnh chạy trong VM, truy cập qua kết nối tới VM đã cấu hình. Port-forward chạy ở một terminal riêng. Manifest upstream có Service `frontend-external` kiểu LoadBalancer; kiểm tra cách phân phối Kubernetes của bạn xử lý đối tượng đó. Với lab chỉ truy cập bằng port-forward, có thể bỏ đối tượng này trong bản manifest lab và ghi thay đổi. [R8 mã nguồn và manifest](https://github.com/GoogleCloudPlatform/microservices-demo/tree/v0.10.7)

Thử đủ ba hành trình mở trang, thêm giỏ và đặt hàng. Ghi thời điểm, hành trình và kết quả. Nếu muốn điều khiển tải thủ công, ghi số replica hiện tại của loadgenerator trước khi chỉnh, rồi đặt bằng 0 trong pha tay và phục hồi khi đổi pha.

```bash
kubectl -n boutique get deploy/loadgenerator
kubectl -n boutique scale deploy/loadgenerator --replicas=0
```

Một lần chạy hiệu năng cần cố định quy trình tạo tải, mức đồng thời, thời gian warm-up, thời gian đo và dữ liệu đầu vào. Duyệt vài trang bằng tay hữu ích cho kiểm tra chức năng, còn đo hiệu năng cần tải lặp lại được.

## Đọc lỗi theo từng lớp

| Dấu hiệu | Kiểm tra tiếp |
|---|---|
| `ImagePullBackOff` | Pod events, registry, DNS và phiên bản image |
| Pod chạy nhưng chưa Ready | Probe, log container, downstream cần thiết |
| Không có endpoint Ready | Selector Service, label Pod, readiness |
| Trang mở nhưng checkout lỗi | Log frontend và checkout cùng mốc thời gian, luồng checkout tới backend |
| Collector không thấy workload | DaemonSet có pod đúng node, lọc namespace, phiên bản driver hoặc policy |
| Sau khi thêm policy, nhiều dịch vụ lỗi | Kiểm tra DNS, hai chiều ingress/egress và policy có sẵn |

```bash
kubectl -n boutique describe pod TEN_POD
kubectl -n boutique logs deployment/checkoutservice --since=10m
kubectl -n boutique get events --sort-by=.metadata.creationTimestamp
```

## Hồ sơ của mỗi lần chạy

Lưu mã lần chạy, phiên bản Kubernetes, Linux kernel, CNI, collector/chart và rule/policy, cấu hình node, revision ứng dụng, placement, image digest thực tế, thời gian UTC, cách phát tải và thay đổi so với baseline. Có thể xuất `kubectl -n boutique get pods -o json` và `kubectl -n boutique get svc,endpointslice -o json` ở mỗi mốc để ánh xạ IP và ứng dụng.

## Tự kiểm tra

1. **Vì sao dùng phiên bản v0.10.7 cố định?** Người sau có cùng source và manifest để kiểm chứng. Cần ghi thêm digest image thực tế để tăng khả năng tái lập.
2. **Một node cho phép kết luận gì?** Kiểm tra pipeline và hành vi trong bố trí một node; cần thí nghiệm đa node cho kết luận về đường mạng qua các node.
3. **Thấy cạnh checkout → payment trong sơ đồ, có thể dùng làm ground truth số request không?** Cần đo hoặc ghi kết quả ứng dụng trong từng lần chạy.

Tiếp theo [bài 5](05-ebpf-runtime-telemetry.md).

