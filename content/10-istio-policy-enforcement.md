# Thực thi chính sách với Istio

Trong lab Online Boutique, checkout cần gọi dịch vụ thanh toán. Giả sử một Pod recommendation bị xâm nhập và cố gửi cùng yêu cầu ấy. Tuần 2 giúp ta thấy một lần thử kết nối. Tuần 3 đặt thêm một điều kiện cụ thể: chỉ tiến trình chạy dưới danh tính workload checkout được gọi phương thức thanh toán ở đích.

## Service mesh, sidecar và mTLS

**Service mesh** bổ sung một lớp xử lý lưu lượng giữa các workload. Trong chế độ sidecar của Istio, một proxy Envoy chạy bên cạnh container ứng dụng. Các proxy là **data plane** vì trực tiếp xử lý dữ liệu. Istiod nằm ở **control plane**, phân phối cấu hình và tham gia quản lý danh tính, chứng chỉ. Khi traffic đi qua đúng đường mesh, proxy phía đích có thể áp chính sách trước khi chuyển yêu cầu vào ứng dụng. Bài lab dưới đây dùng sidecar. Với ambient, cần tìm hiểu điểm thực thi L4 và waypoint L7 trước khi áp dụng ví dụ tương đương. [R19 Istio Security](https://istio.io/latest/docs/concepts/security/)

**mTLS** là TLS xác thực hai phía. Proxy đích có thể lấy danh tính phía gửi từ chứng chỉ mesh. Danh tính này thường gắn với namespace và Kubernetes ServiceAccount, ví dụ `cluster.local/ns/boutique/sa/checkoutservice` nếu trust domain là `cluster.local`. Token ServiceAccount dùng với Kubernetes API và danh tính peer xuất hiện trong kết nối mTLS là hai ngữ cảnh khác nhau. Nếu hai ứng dụng dùng chung ServiceAccount hoặc đối thủ đã chiếm chính Pod checkout, policy chỉ dựa vào ServiceAccount sẽ không phân biệt được hai tác nhân đó. [R19 Istio Security](https://istio.io/latest/docs/concepts/security/)

| Lớp | Điều kiểm tra | Ví dụ |
|---|---|---|
| Kubernetes RBAC | Quyền thao tác với Kubernetes API | Checkout có được đọc Secret qua API server không? |
| NetworkPolicy | Luồng mạng L3/L4 được phép | Nguồn có đường tới Pod đích qua TCP/50051 không? |
| PeerAuthentication | Kiểu xác thực peer được chấp nhận ở đích | Payment chỉ nhận kết nối mTLS trong đường mesh. |
| AuthorizationPolicy | Danh tính và thao tác được phép ở workload đích | Chỉ checkout được gọi phương thức Charge. |
| Kiểm tra nghiệp vụ | Quyền và dữ liệu của yêu cầu tại ứng dụng | Yêu cầu có gắn với đơn hàng hợp lệ không? |

Nguồn tham chiếu. [R7 Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/), [R19 Istio Security](https://istio.io/latest/docs/concepts/security/), [R20 AuthorizationPolicy](https://istio.io/latest/docs/reference/config/security/authorization-policy/)

## Đọc một AuthorizationPolicy

`metadata.namespace` cùng `spec.selector` xác định **workload đích**. Trong một rule, `from` chọn chủ thể nguồn, `to` chọn thao tác, `when` thêm điều kiện. Một rule cần khớp các nhóm điều kiện đã khai báo. Nhiều lựa chọn trong danh sách nguồn hoặc thao tác cho phép khớp một lựa chọn. Khai báo rõ namespace và label giúp kiểm tra phạm vi trước khi áp dụng. [R20 cấu trúc policy](https://istio.io/latest/docs/reference/config/security/authorization-policy/)

Thứ tự xét truy cập là CUSTOM, rồi DENY, rồi ALLOW. Một DENY khớp có thể chặn dù có ALLOW khớp. Sau khi vượt qua CUSTOM/DENY, nếu workload có ít nhất một ALLOW áp dụng thì yêu cầu phải khớp một ALLOW. Nếu không có ALLOW áp dụng, yêu cầu qua bước này. Ví dụ, thêm một ALLOW hẹp cho payment có thể làm các client hợp lệ khác mất quyền. Kiểm tra toàn bộ policy ở namespace workload và root namespace của mesh. AUDIT đánh dấu yêu cầu để audit nếu có tích hợp hỗ trợ. Với TCP thuần, trường HTTP như path hoặc method có thể vắng mặt. Trong DENY, thuộc tính vắng mặt có thể được coi là khớp, vì vậy cần giới hạn cổng và xác minh giao thức. [R20 thứ tự và giới hạn với TCP](https://istio.io/latest/docs/reference/config/security/authorization-policy/)

## Ví dụ checkout gọi payment trong Online Boutique

Manifest upstream v0.10.7 có label Pod `app: paymentservice`, Service gRPC TCP/50051 và ServiceAccount checkout `checkoutservice`. Định nghĩa protobuf dùng package `hipstershop` và RPC `PaymentService.Charge`. Trong gRPC qua HTTP/2, proxy có thể đối chiếu path `/hipstershop.PaymentService/Charge`. Xác minh các giá trị với manifest đang chạy, nhất là khi dùng overlay hoặc đổi namespace. [R8 manifest và protobuf v0.10.7](https://github.com/GoogleCloudPlatform/microservices-demo/tree/v0.10.7)

Hai manifest sau dành cho namespace lab `boutique`. Giả định các caller đã vào mesh, API Istio hỗ trợ `security.istio.io/v1` và proxy nhận diện luồng ở cổng 50051 là gRPC. Kiểm kê health check và các client trước khi bật cấu hình chặn thật. Ví dụ dùng `serviceAccounts` để so khớp peer theo chứng chỉ mTLS. [R19 Istio Security](https://istio.io/latest/docs/concepts/security/), [R20 các trường Source và Operation](https://istio.io/latest/docs/reference/config/security/authorization-policy/)

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: payment-mtls
  namespace: boutique
spec:
  selector:
    matchLabels:
      app: paymentservice
  mtls:
    mode: STRICT
---
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: payment-charge-from-checkout
  namespace: boutique
spec:
  selector:
    matchLabels:
      app: paymentservice
  action: ALLOW
  rules:
    - from:
        - source:
            serviceAccounts: ["boutique/checkoutservice"]
      to:
        - operation:
            ports: ["50051"]
            methods: ["POST"]
            paths: ["/hipstershop.PaymentService/Charge"]
```

## Chạy phép thử có đối chứng

1. Chuẩn bị mesh ở cluster lab và kiểm tra sidecar thực sự có mặt ở cả hai đầu. Chỉ thêm label injection cho namespace sẽ không sửa Pod đang chạy. Cần tạo lại workload theo cơ chế triển khai phù hợp. Kiểm tra controller, selector và proxy bằng các lệnh dưới đây. [Istio sidecar installation](https://istio.io/latest/docs/setup/additional-setup/sidecar-injection/)
2. Chạy đối chứng trước policy với **cùng invocation gRPC**, một lần từ checkout hợp lệ và một lần từ một client lab trong mesh có ServiceAccount khác. Dùng protobuf v0.10.7 và payload thử nghiệm. Đừng dùng một phép `nc` để kiểm tra quyền gọi RPC. Nếu dùng grpcurl, cung cấp protobuf khi server không có reflection. Thử riêng hành trình checkout qua frontend để phát hiện ảnh hưởng nghiệp vụ.
3. Tách mTLS STRICT và AuthorizationPolicy thành hai lần thay đổi. Khi bản Istio hỗ trợ, thử authorization với annotation `istio.io/dry-run: "true"`; quan sát quyết định dự kiến rồi gỡ annotation để enforcement trong lab. Dry-run là tính năng thử nghiệm và cần kiểm tra đường log/metric đã cấu hình. [Istio Dry Run](https://istio.io/latest/docs/tasks/security/authorization/authz-dry-run/)
4. Chạy lại hai client. Kỳ vọng checkout vẫn thực hiện được Charge, client mesh khác bị từ chối ở đích. Thử client ngoài mesh riêng để xem tác động của STRICT. Ghi status, log proxy cùng thời gian và nguồn, cùng kết quả nghiệp vụ.
5. Nếu cả hai client lỗi, lần lượt kiểm tra lớp mạng, sidecar, mTLS, ServiceAccount, protocol/port và path. Khi hoàn tác, phục hồi đúng cấu hình trước lần chạy và xác nhận checkout lại.

```bash
kubectl config current-context
kubectl -n boutique get pod -l app=paymentservice -o wide
kubectl -n boutique get deploy checkoutservice \
  -o jsonpath='{.spec.template.spec.serviceAccountName}'
kubectl -n boutique get svc paymentservice -o yaml
istioctl analyze -n boutique
istioctl proxy-status
# Lưu YAML ví dụ thành payment-policy.yaml và kiểm tra API trước khi áp thật.
kubectl apply --dry-run=server -f payment-policy.yaml
```

| Kết quả | Có thể kết luận gì? |
|---|---|
| TCP mở, gRPC bị từ chối và có log authorization khớp | Kết nối lên được, policy đã từ chối yêu cầu được quan sát. |
| TCP timeout từ cả checkout và probe | Kiểm tra đường mạng hoặc listener trước khi kết luận về L7. |
| Request hợp lệ chạy nhưng nguồn thử cũng qua | Xem lại sidecar, selector, danh tính và mọi ALLOW áp dụng. |
| Apply thành công, proxy chưa nhận cấu hình | API đã nhận manifest. Cần đo thời điểm kết nối thử đổi hành vi. |

## Tự kiểm tra

1. **Vì sao checkout và probe cần ServiceAccount khác nhau?** Policy đọc danh tính peer từ chứng chỉ. Hai nguồn có cùng danh tính có thể được cấp cùng quyền.
2. **Resource đã được API server chấp nhận thì đã có enforcement chưa?** Cần chứng minh cấu hình đã đến lớp thực thi và lặp lại probe với đối chứng hợp lệ.
3. **Tại sao test thêm đường mTLS trước authorization?** Hai lớp có thể từ chối vì hai nguyên nhân khác nhau. Thay đổi từng lớp giúp tìm được nguyên nhân của kết quả.

Tiếp theo [Phát hiện bất thường](11-phat-hien-bat-thuong.md).
