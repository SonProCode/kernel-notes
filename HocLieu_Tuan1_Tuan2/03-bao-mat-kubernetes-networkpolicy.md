# Bảo mật Kubernetes theo từng lớp

## Danh tính, quyền và cấu hình Pod

**ServiceAccount** là danh tính Kubernetes mà workload có thể dùng để xác thực. Pod khai báo `serviceAccountName`; khi được mount, token đại diện cho tài khoản trong phạm vi, thời hạn và audience tương ứng. Ví dụ, khi checkout gọi API server để đọc ConfigMap, API server xác thực token trước khi kiểm tra quyền đọc. Workload không cần token tự động có thể đặt `automountServiceAccountToken: false` sau khi xác nhận các chức năng phụ thuộc. [R6 Service Accounts](../TaiLieu_Tuan1_Tuan2/PDF/R6-Service-Accounts.pdf)

**RBAC** phân quyền theo thao tác và tài nguyên. `Role` mô tả quyền trong namespace. `ClusterRole` mô tả một bộ quyền để tái sử dụng hoặc dùng cấp cluster. `RoleBinding` cấp quyền trong namespace, ngay cả khi tham chiếu ClusterRole. `ClusterRoleBinding` cấp quyền ở phạm vi cluster. Ví dụ một Role chỉ cho `get` ConfigMap tên `checkout-config` hẹp hơn quyền `list` mọi ConfigMap. Có thể dùng `kubectl auth can-i get configmap/checkout-config -n boutique --as=system:serviceaccount:boutique:checkoutservice` với tài khoản được phép impersonate để hỏi hệ thống về quyền đó. [R6 RBAC Good Practices](../TaiLieu_Tuan1_Tuan2/PDF/R6-RBAC-Good-Practices.pdf)

**Security context** cấu hình quyền tiến trình trong Pod. `runAsNonRoot` yêu cầu container chạy bằng UID khác 0. `allowPrivilegeEscalation: false` giảm khả năng tiến trình con có đặc quyền mới. Capabilities chia quyền đặc biệt của Linux thành từng nhóm nhỏ. Seccomp hạn chế syscall. Pod Security Standards mô tả ba mức Privileged, Baseline và Restricted; Pod Security Admission có thể áp dụng chuẩn tại lúc nhận yêu cầu tạo workload. [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)

**Secret** là đối tượng chứa dữ liệu nhạy cảm. Base64 là mã hóa biểu diễn, có thể giải mã trực tiếp. Cần xét cả quyền đọc API, quyền qua Pod/mount, cách bảo vệ dữ liệu lưu trữ và độ nhạy của log. [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)

## Đọc OWASP Kubernetes Top Ten bản 2025

| Mã | Rủi ro | Ví dụ áp dụng khi đọc cấu hình lab |
|---|---|---|
| K01 | Cấu hình workload thiếu an toàn | Pod chạy privileged hoặc có mount host không cần thiết. |
| K02 | Phân quyền quá rộng | Một token ứng dụng được cấp quyền đọc secrets toàn cluster. |
| K03 | Quản lý secrets kém | Credential được ghi vào log hoặc đặt trực tiếp trong manifest chia sẻ. |
| K04 | Thiếu thực thi policy cấp cluster | Tiêu chuẩn Pod chỉ nằm trong tài liệu, không có cơ chế kiểm tra khi tạo. |
| K05 | Thiếu phân đoạn mạng | Pod nguồn ngoài luồng có đường TCP tới dịch vụ nhạy cảm. |
| K06 | Phơi lộ thành phần Kubernetes | API điều khiển hoặc endpoint quản trị mở rộng hơn nhu cầu. |
| K07 | Thành phần cluster cấu hình sai hoặc dễ tổn thương | Thành phần vận hành có cấu hình hoặc phiên bản tạo lỗ hổng. |
| K08 | Di chuyển từ cluster sang cloud | Quyền cloud của workload cho phép tiếp cận thêm tài nguyên bên ngoài cluster. |
| K09 | Cơ chế xác thực yếu | Xử lý sai danh tính hoặc chấp nhận credential không phù hợp. |
| K10 | Thiếu log và giám sát | Nhìn thấy đích IP nhưng thiếu nguồn Pod và thời gian đối chiếu. |

Các mã gắn với bản 2025. [R3 OWASP Kubernetes Top Ten](../TaiLieu_Tuan1_Tuan2/PDF/R3-OWASP-Kubernetes-Top-Ten.pdf)

## NetworkPolicy từ một ví dụ cụ thể

NetworkPolicy chọn Pod bằng label và kiểm soát luồng L3/L4. **Ingress** là chiều đi vào Pod. **Egress** là chiều đi ra. `policyTypes` xác định chiều được áp dụng; khi Pod bị cô lập ở một chiều, các policy phù hợp hợp lại thành tập luồng được phép. Với hai đầu đều bị cô lập ở chiều liên quan, egress nguồn và ingress đích đều phải cho phép. Lưu lượng trả lời của kết nối được phép được cho qua theo mô hình policy. Cần lớp mạng hỗ trợ thực thi. CNI (Container Network Interface) là quy ước tích hợp plugin mạng với môi trường container. Plugin hoặc controller mạng của cluster chịu trách nhiệm biến cấu hình thành quy tắc có tác dụng trên đường truyền. [R7 Network Policies](../TaiLieu_Tuan1_Tuan2/PDF/R7-Kubernetes-Network-Policies.pdf)

Xét cấu hình minh họa dành cho một lab riêng. Backend giả lập tên `payment` lắng nghe TCP/7070, cả hai Pod đều ở namespace `policy-lab`.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-from-checkout
  namespace: policy-lab
spec:
  podSelector:
    matchLabels:
      app: payment
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: checkout
      ports:
        - protocol: TCP
          port: 7070
```

Policy này chọn Pod **đích** bằng `spec.podSelector` và chọn Pod **nguồn** trong `from`. Với cấu hình trên, selector nguồn chọn checkout trong cùng namespace. Để yêu cầu đồng thời đúng namespace và đúng label, đặt `namespaceSelector` và `podSelector` trong **cùng** phần tử `from`. Hai phần tử riêng là các lựa chọn khác nhau. `ipBlock` dùng CIDR; lưu ý NAT và cách CNI triển khai có thể ảnh hưởng IP được so khớp. [R7 hành vi selector và NAT](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

### Cách kiểm chứng

1. Dựng hai Pod nguồn với label `app=checkout` và `app=probe`, một Pod đích `app=payment` và Service cho đích. Ghi nhãn thực tế bằng `kubectl -n policy-lab get pod --show-labels`.
2. Kiểm tra kết nối mới tới cùng đích từ hai nguồn trước khi áp policy. Xác nhận listener đang chạy để có đối chứng.
3. Áp policy và thử lại kết nối **mới**. Dự kiến checkout kết nối được còn probe bị chặn nếu các chính sách còn lại phù hợp.
4. Kiểm tra DNS riêng. Khi khóa egress, cần xem cấu hình DNS của cluster và cho phép đường DNS cần thiết qua UDP/TCP 53, nếu workload dùng đường đó.
5. Ghi thời điểm gửi policy và thời điểm probe lần đầu không kết nối được. Thử riêng kết nối đã mở, vì hành vi với kết nối đang tồn tại tùy triển khai. [Ví dụ kiểm chứng của Kubernetes](https://kubernetes.io/docs/tasks/administer-cluster/declare-network-policy/)

**Ví dụ cộng dồn.** Policy A cho checkout vào payment. Policy B chọn payment và có `policyTypes: [Ingress]` với `ingress: []`. Checkout vẫn có thể vào nhờ A. Muốn cách ly, cần thay đổi hoặc loại trừ Pod khỏi mọi allow áp dụng, hoặc dùng cơ chế có ngữ nghĩa deny thích hợp.

## Thực hành kiểm chứng bằng ba Pod

Lệnh Bash dưới đây tạo hai nguồn và một đích riêng cho ví dụ TCP/7070. Chạy trong context lab. Lưu YAML ở mục trên thành `payment-from-checkout.yaml` để áp dụng ở bước thứ hai.

```bash
kubectl create namespace policy-lab --dry-run=client -o yaml | kubectl apply -f -
kubectl -n policy-lab run payment --image=busybox:1.36.1 --restart=Never \
  --labels=app=payment --command -- /bin/sh -c \
  'mkdir -p /www && echo payment-lab > /www/index.html && exec httpd -f -p 7070 -h /www'
kubectl -n policy-lab expose pod payment --name=payment --port=7070 --target-port=7070
kubectl -n policy-lab run checkout --image=busybox:1.36.1 --restart=Never \
  --labels=app=checkout --command -- sleep 3600
kubectl -n policy-lab run probe --image=busybox:1.36.1 --restart=Never \
  --labels=app=probe --command -- sleep 3600
kubectl -n policy-lab wait --for=condition=Ready pod/payment pod/checkout pod/probe --timeout=120s

# Trước policy, cả hai lệnh dự kiến in payment-lab.
kubectl -n policy-lab exec checkout -- wget -T 3 -qO- http://payment:7070/
kubectl -n policy-lab exec probe -- wget -T 3 -qO- http://payment:7070/

kubectl apply -f payment-from-checkout.yaml
# Sau khi policy có hiệu lực, checkout vẫn in payment-lab, probe dự kiến hết thời gian.
kubectl -n policy-lab exec checkout -- wget -T 3 -qO- http://payment:7070/
kubectl -n policy-lab exec probe -- wget -T 3 -qO- http://payment:7070/
```

Ghi mã thoát và thời điểm của lần thử. Nếu cả hai vẫn truy cập được, kiểm tra lớp thực thi, nhãn và các policy đang áp dụng. Nếu cả hai đều lỗi, kiểm tra backend và DNS từ nguồn được phép. Listener HTTP nhỏ ở đây giúp kiểm chứng đường TCP. Payment của Online Boutique v0.10.7 dùng Service gRPC cổng 50051 theo manifest đã lưu.



## Tự kiểm tra

1. **RBAC cho đọc ConfigMap có cho kết nối TCP tới payment không?** RBAC áp cho thao tác API Kubernetes; kết nối phụ thuộc chính sách mạng và server.
2. **Timeout có chứng minh policy hoạt động không?** Phải đối chiếu listener, DNS, trạng thái workload và một nguồn đối chứng được phép.
3. **Cho phép đúng cổng đã giới hạn được method gRPC chưa?** Muốn giới hạn method cần cơ chế nhận biết giao thức ứng dụng và danh tính phù hợp.

Tiếp theo [bài 4](04-testbed-online-boutique.md).



