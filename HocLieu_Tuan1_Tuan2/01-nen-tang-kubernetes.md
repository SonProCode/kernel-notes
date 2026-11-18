# Từ ứng dụng đến tiến trình trong Kubernetes

## Một lần bấm mua hàng đi qua đâu

Trong Online Boutique, trình duyệt gửi yêu cầu tới frontend. Khi người dùng mua hàng, frontend gọi checkout để điều phối đơn. Checkout có thể gọi payment giả lập và shipping. Các dịch vụ trao đổi qua mạng nên lỗi, quyền và dữ liệu quan sát của mỗi lần gọi có thể khác nhau.

- **Client** là phía phát yêu cầu. Frontend là server đối với trình duyệt và có thể là client đối với checkout.
- **API** quy định thao tác và định dạng dữ liệu. HTTP là giao thức ứng dụng. gRPC là khuôn khổ gọi thủ tục từ xa, thường truyền nhiều lời gọi trên một kết nối HTTP/2.
- **IP** giúp định vị đầu mạng. **Port** giúp chọn điểm nhận trong máy hoặc địa chỉ đó. **DNS** phân giải tên thành địa chỉ.
- **TCP** tạo kết nối có trạng thái. Kết nối TCP tới payment có thể thành công trong khi lời gọi gRPC bị từ chối hoặc trả lỗi.
- **Lưu lượng nội bộ** giữa workload thường gọi là east–west. Lưu lượng ra hoặc vào biên hệ thống thường gọi là north–south.

Ví dụ, một dấu vết có IP và cổng xác nhận được đích quan sát tại một vị trí trên đường đi. Muốn biết lời gọi nào đã chạy, cần thêm log hoặc trace ở lớp ứng dụng. [R8 Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo/tree/v0.10.7)

## Linux, image, container và Pod

**Tiến trình** là một lần chương trình đang chạy. Chương trình có thể gọi **system call** để yêu cầu kernel làm việc như mở file hay tạo socket. **Kernel** là phần hệ điều hành quản lý bộ nhớ, tiến trình và tài nguyên.

**Image** đóng gói chương trình và tệp cần để tạo container. **Container** chạy chương trình với các cơ chế cách ly và giới hạn của hệ điều hành. Các container Linux trên cùng node thường dùng chung kernel; namespace Linux giới hạn những gì tiến trình nhìn thấy, còn cgroup quản lý và hạch toán tài nguyên như CPU và bộ nhớ.

**Pod** là đơn vị chạy workload mà Kubernetes quản lý. Các container trong một Pod dùng chung không gian mạng của Pod, có thể kết nối qua localhost và có thể chia sẻ volume nếu được cấu hình. Ví dụ, backend và sidecar trong cùng pod có thể giao tiếp qua loopback. Khi cần xác định ai tạo kết nối, lưu thêm container và tiến trình thay vì chỉ tên Pod. [R6 Pods](https://kubernetes.io/docs/concepts/workloads/pods/)

## Các đối tượng cần đọc trong manifest

| Đối tượng | Giải thích | Ví dụ |
|---|---|---|
| Node | Máy ảo hoặc máy vật lý chạy workload | Worker chứa pod payment và agent telemetry |
| Deployment | Khai báo trạng thái mong muốn, quản lý rollout thông qua ReplicaSet | Muốn duy trì hai replica frontend |
| ReplicaSet | Duy trì số pod theo mẫu được chỉ định | Khi một pod mất, controller tạo pod khác |
| Service | Điểm truy cập ổn định cho một nhóm endpoint | Checkout gọi tên DNS của payment |
| EndpointSlice | Thông tin các endpoint phía sau một Service | Địa chỉ và trạng thái backend |
| Namespace | Phạm vi tên đối tượng và quản trị trong cluster | Tách boutique và namespace kiểm thử |
| Label và selector | Cặp khóa giá trị và biểu thức chọn đối tượng | Service chọn pod có `app: paymentservice` |
| DaemonSet | Tạo pod trên từng node đủ điều kiện | Đặt cảm biến ở các node chứa workload |
| ConfigMap và Secret | Tách cấu hình và dữ liệu nhạy cảm ra khỏi image | URL backend và credential |

Control plane quản lý trạng thái của cluster. API server tiếp nhận yêu cầu Kubernetes, etcd lưu trạng thái, scheduler chọn node và controller đối chiếu trạng thái mong muốn. Kubelet ở node phối hợp với container runtime để chạy các Pod đã được giao. [R6 Kubernetes Concepts](../TaiLieu_Tuan1_Tuan2/PDF/R6-Kubernetes-Concepts.pdf)

## Ví dụ đọc YAML từ ngoài vào trong

Đây là trích đoạn minh họa, dùng cổng tùy chọn.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: payment
  namespace: boutique
spec:
  selector:
    app: payment
  ports:
    - port: 7000
      targetPort: 7070
```

Client gọi `payment.boutique.svc` qua cổng Service 7000. Service chọn Pod theo label trong cùng namespace và chuyển tới backend cổng 7070. Nếu selector sai hoặc thiếu backend sẵn sàng, Service có thể tồn tại mà yêu cầu vẫn lỗi. Khi Pod được thay thế, IP và UID có thể đổi trong khi tên Service vẫn giữ nguyên. [R6 Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/)

## Đọc tình trạng bằng kubectl

`kubectl` gửi yêu cầu đến API server theo context. Các lệnh sau chỉ xem trạng thái. Chúng có thể thực hiện trong lab ở [bài 4](04-testbed-online-boutique.md).

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl -n boutique get deployment,pod,service,endpointslice -o wide
kubectl -n boutique get pods --show-labels
```

`Running` là pha của Pod; cột `READY` cho biết các container trong Pod đã sẵn sàng theo trạng thái hiện tại. Khi frontend lỗi, lần lượt kiểm tra Deployment, Pod, Service, endpoint và tình trạng nghiệp vụ. Sự cố của một lớp có thể hiện ra như lỗi ở lớp khác.

## Tự kiểm tra

1. **Pod restart hoặc bị thay thế, nên nhóm hành vi theo gì?** Dùng namespace và workload để thống kê; giữ pod UID, container ID và thời gian để truy lại sự kiện.
2. **Hai Pod có cùng namespace thì đã bị tách mạng với phần còn lại chưa?** Namespace tạo phạm vi quản lý. Việc giới hạn luồng còn tùy chính sách và lớp thực thi.
3. **TCP kết nối được đã đủ kết luận đặt hàng thành công chưa?** Cần kiểm tra kết quả API nghiệp vụ hoặc dấu vết ứng dụng tương ứng.

Tiếp theo [bài 2](02-zero-trust-threat-model.md).

