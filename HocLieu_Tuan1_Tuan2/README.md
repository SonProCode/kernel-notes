# Học liệu bảo mật Kubernetes và eBPF

Bộ học liệu tiếng Việt cho hai tuần đầu của đề tài phát hiện và giảm thiểu di chuyển ngang trong microservices. Bạn có thể đọc từ đầu nếu chưa từng dùng Linux, Kubernetes hay công cụ bảo mật runtime. Ví dụ xuyên suốt dùng cửa hàng giả lập Online Boutique. Các cấu hình, dòng log và số đo minh họa được ghi rõ để dễ phân biệt với dữ liệu thực nghiệm.

| Thứ tự | Bài học | Kết quả sau khi đọc |
|---|---|---|
| 1 | [Nền tảng hệ thống và Kubernetes](01-nen-tang-kubernetes.md) · R6 | Lần được đường đi từ người dùng tới tiến trình trong pod và đọc được manifest cơ bản. |
| 2 | [Zero Trust, di chuyển ngang và mô hình đe dọa](02-zero-trust-threat-model.md) · R1, R2 | Mô tả đối thủ, ranh giới tin cậy, hành vi và tiêu chí thành công. |
| 3 | [Bảo mật Kubernetes và NetworkPolicy](03-bao-mat-kubernetes-networkpolicy.md) · R3, R6, R7 | Phân biệt danh tính, quyền API và quyền kết nối. Viết chính sách và kiểm chứng cả chiều cho phép lẫn chiều chặn. |
| 4 | [Dựng testbed Online Boutique](04-testbed-online-boutique.md) · R8 | Triển khai workload cố định phiên bản, xác nhận luồng nghiệp vụ và lưu cấu hình mỗi lần chạy. |
| 5 | [eBPF và telemetry runtime](05-ebpf-runtime-telemetry.md) · R11 | Giải thích sự kiện đi từ kernel đến log và giới hạn của từng loại bằng chứng. |
| 6 | [Falco và phát hiện theo rule](06-falco.md) · R14 | Đọc, viết và thử một rule, xuất cảnh báo JSON theo ngữ cảnh Kubernetes. |
| 7 | [Tetragon và TracingPolicy](07-tetragon.md) · R16 | Thu process event, hiểu cách mở rộng sang file và network. |
| 8 | [Từ telemetry đến thực nghiệm luận văn](08-du-lieu-va-thuc-nghiem.md) | Thiết kế nhãn, baseline, đặc trưng và phép đánh giá lặp lại được. |
| Tra cứu | [Thuật ngữ và danh mục nguồn](09-tra-cuu.md) | Tìm PDF theo mã R và dùng mẫu bàn giao cho phiên phân tích tiếp theo. |

Tuần 1 đọc bài 1–3. Tuần 2 đọc bài 4–5, chọn bài 6 hoặc 7 để làm lab, sau đó dùng bài 8 để chuẩn bị dữ liệu. Nếu chọn Falco và cần đồ thị kết nối bình thường, hãy xác định thêm nguồn thu kết nối. Nếu chọn Tetragon, hãy xác nhận độ phủ của hook trước khi xây baseline.

Các bài dùng Bash trên Linux cho lệnh lab, trừ bước giải nén trên Windows. Những đoạn lệnh là hướng dẫn thực hành và chưa được chạy trên một cluster trong đợt soạn tài liệu này. Khi phân tích kết quả, lấy manifest đã triển khai, log thô và lịch chạy làm bằng chứng.

[Mục lục PDF hai tuần](../TaiLieu_Tuan1_Tuan2/Muc_luc.html)


Đọc tiếp [học liệu Tuần 3](../HocLieu_Tuan3/README.md).
