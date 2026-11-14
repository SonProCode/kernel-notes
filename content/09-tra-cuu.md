# Tra cứu thuật ngữ và nguồn

## Từ vựng dùng trong các bài

| Thuật ngữ | Cách hiểu trong bộ tài liệu |
|---|---|
| Workload | Chương trình hoặc nhóm Pod thực hiện một vai trò, chẳng hạn checkout |
| Pod UID | Mã nhận diện một Pod cụ thể trong vòng đời của nó |
| Service / endpoint | Điểm truy cập ổn định / địa chỉ backend phục vụ lưu lượng |
| ServiceAccount / RBAC | Danh tính Kubernetes / cơ chế cấp quyền thao tác API |
| CNI / NetworkPolicy | Lớp tích hợp mạng cho container / đối tượng Kubernetes mô tả quyền kết nối |
| Ingress / egress | Luồng vào / luồng ra của đối tượng đang xét |
| L3, L4, L7 | Tầng mạng, tầng vận chuyển và tầng ứng dụng |
| Zero Trust | Mô hình kiểm soát truy cập tài nguyên theo danh tính, quyền và ngữ cảnh |
| Threat model | Giả định về tài sản, đối thủ, năng lực và phạm vi |
| Lateral movement | Quá trình đối thủ tiến sang hệ thống khác sau chỗ đứng ban đầu |
| Blast radius | Phạm vi ảnh hưởng đo theo tài nguyên và phép thử đã định nghĩa |
| Hook / syscall | Điểm kích hoạt chương trình quan sát / yêu cầu của tiến trình với kernel |
| Collector / detector | Khối thu dữ liệu / khối đánh giá để phát hiện |
| Normalization / enrichment | Đưa dữ liệu về schema chung / bổ sung ngữ cảnh từ nguồn khác |
| Ground truth / baseline | Nhãn thực nghiệm độc lập / mô tả hành vi bình thường trong phạm vi đã lấy mẫu |
| TCP connection / RPC | Kết nối vận chuyển / một lần gọi thủ tục từ xa |
| Smoke test | Phép thử ngắn chứng minh thành phần hoạt động ở một đường đã biết |

## Mục đọc theo mã R

| Mã | Bài liên quan | Mở tài liệu |
|---|---|---|
| R1 | Bài 2, mục nguyên tắc và quyết định | [PDF NIST SP 800-207](../TaiLieu_Tuan1_Tuan2/PDF/R1-NIST-SP-800-207.pdf) · [Nguồn NIST](https://doi.org/10.6028/NIST.SP.800-207) |
| R2 | Bài 2, cách phân loại hành vi | [PDF TA0008](../TaiLieu_Tuan1_Tuan2/PDF/R2-MITRE-ATTACK-TA0008.pdf) · [MITRE ATT&CK](https://attack.mitre.org/tactics/TA0008/) |
| R3 | Bài 3, bản OWASP 2025 | [PDF OWASP](../TaiLieu_Tuan1_Tuan2/PDF/R3-OWASP-Kubernetes-Top-Ten.pdf) · [OWASP Kubernetes Top Ten](https://kubernetes-top10.owasp.org/) |
| R6 | Bài 1 và 3 | [Concepts](../TaiLieu_Tuan1_Tuan2/PDF/R6-Kubernetes-Concepts.pdf) · [Service Accounts](../TaiLieu_Tuan1_Tuan2/PDF/R6-Service-Accounts.pdf) · [RBAC](../TaiLieu_Tuan1_Tuan2/PDF/R6-RBAC-Good-Practices.pdf) |
| R7 | Bài 3, cô lập và selector | [PDF Network Policies](../TaiLieu_Tuan1_Tuan2/PDF/R7-Kubernetes-Network-Policies.pdf) · [Kubernetes](https://kubernetes.io/docs/concepts/services-networking/network-policies/) |
| R8 | Bài 4, kiến trúc và manifest | [README v0.10.7](../TaiLieu_Tuan1_Tuan2/PDF/R8-Online-Boutique-README-v0.10.7.pdf) · [Mã nguồn v0.10.7](https://github.com/GoogleCloudPlatform/microservices-demo/tree/v0.10.7) |
| R11 | Bài 5, hook và pipeline | [PDF What is eBPF?](../TaiLieu_Tuan1_Tuan2/PDF/R11-What-is-eBPF.pdf) · [eBPF.io](https://ebpf.io/what-is-ebpf/) |
| R14 | Bài 6, driver, rule và JSON | [Falco Docs](../TaiLieu_Tuan1_Tuan2/PDF/R14-Falco-Documentation.pdf) · [Falco Rules](../TaiLieu_Tuan1_Tuan2/PDF/R14-Falco-Rules.pdf) |
| R16 | Bài 7, process, file và kết nối | [Tetragon Docs](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-Documentation.pdf) · [Tracing Policy](../TaiLieu_Tuan1_Tuan2/PDF/R16-Tetragon-Tracing-Policy.pdf) |

| R18 | Tuần 3, so sánh collector và thiết kế phép đo | [Syairozi và Arizal — bài gốc](https://www.scitepress.org/Papers/2025/142727/142727.pdf) |
| R19 | Tuần 3, danh tính và mTLS | [Istio Security](https://istio.io/latest/docs/concepts/security/) |
| R20 | Tuần 3, cấu trúc và thứ tự policy | [Istio AuthorizationPolicy](https://istio.io/latest/docs/reference/config/security/authorization-policy/) |
| R23 | Tuần 3, đồ thị giao tiếp và GNN | [GATAKU — bài gốc](https://digitalcollection.zhaw.ch/bitstreams/15ae5877-9515-4c65-9712-aa32a2a2cc89/download) |
| R24 | Tuần 3, baseline tiến trình | [PROCATCH — bài gốc](https://conand.me/publications/elkhairi-procatch-2025.pdf) |

[Mục lục PDF Tuần 1 và Tuần 2](../TaiLieu_Tuan1_Tuan2/Muc_luc.html)

## Mẫu bàn giao cho phiên phân tích tiếp theo

Sao chép phần dưới và điền bằng kết quả thực tế. Chỉ rõ đường dẫn tới bằng chứng và dữ liệu nào là minh họa.

```text
Câu hỏi cần phân tích
Giả thuyết và đơn vị đo
Mã lần chạy và thời gian UTC
Phiên bản workload, cluster, driver, chart và policy
Thông tin node và Pod tham gia
Lệnh hoặc kịch bản đã chạy
Các pha baseline, thử nghiệm và đối chứng
Đường dẫn manifest, log raw, dữ liệu chuẩn hóa, nhãn
Định nghĩa thành công và điều kiện gắn alert với nhãn
Kết quả quan sát được
Giới hạn coverage hoặc trường còn thiếu
Điểm cần kiểm chứng tiếp theo
```

Ví dụ yêu cầu phân tích cho một phiên sau: “Đọc bài 3 và bài 8 để lấy định nghĩa. Từ lần chạy lab-004, đối chiếu ground truth, log đúng node và policy đã lưu. Kiểm tra nguồn hợp lệ còn kết nối được không, xác định đơn vị tính chỉ số và ghi trường dữ liệu còn thiếu.”

Về [mục lục học liệu](README.md).
