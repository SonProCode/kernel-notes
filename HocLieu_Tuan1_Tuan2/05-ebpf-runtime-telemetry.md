# eBPF và cách đọc sự kiện runtime

## Runtime là lúc chương trình đang hoạt động

Kiểm tra image cho biết ứng dụng được đóng gói với thành phần nào. Quan sát runtime trả lời tiến trình thực sự đã chạy, mở file hoặc kết nối đi đâu. Ví dụ, một image có shell để phục vụ gỡ lỗi. Khi một tiến trình web sinh shell vào lúc không có phiên bảo trì, sự kiện đó cung cấp thêm ngữ cảnh để điều tra.

**Telemetry** là dữ liệu được thu từ hệ thống đang chạy. Event là bản ghi một việc đã quan sát; metric là số đo được tổng hợp hoặc lấy theo thời gian; trace theo dấu một yêu cầu qua nhiều bước. Cùng một tình huống checkout có thể xuất hiện ở cả ba nguồn.

## Chương trình eBPF được chạy như thế nào

Trên Linux, chương trình eBPF có thể được gắn vào điểm trong kernel hoặc các điểm quan sát được hỗ trợ. Cảm biến như Falco và Tetragon dùng chương trình đã được thiết kế cho các sự kiện chúng quan tâm. Người triển khai lab chủ yếu cấu hình driver, rule và policy, rồi kiểm tra các sự kiện thực thu.

1. **Loader** ở user space yêu cầu kernel nạp chương trình.
2. **Verifier** kiểm tra chương trình tuân thủ giới hạn an toàn của loại chương trình, ví dụ cách truy cập bộ nhớ và các đường thực thi có thể có. Kiểm tra này khác với kiểm tra tính đúng đắn của giả thuyết phát hiện.
3. Chương trình có thể được **JIT** biên dịch thành mã máy nếu được hỗ trợ.
4. Khi **hook** được kích hoạt, chương trình dùng ngữ cảnh được cung cấp, có thể gọi **helper**, lưu trạng thái vào **map** hoặc gửi dữ liệu qua ring buffer.
5. Agent đọc dữ liệu và có thể bổ sung thông tin container, Pod và chính sách trước khi xuất.

| Điểm móc | Giải thích dễ hiểu | Ví dụ |
|---|---|---|
| Tracepoint | Điểm tracing được mã nguồn kernel cung cấp | Quan sát sự kiện liên quan syscall |
| Kprobe | Gắn vào vị trí hoặc hàm kernel phù hợp | Lấy ngữ cảnh tại một hàm kết nối |
| Uprobe | Gắn vào mã chương trình user space | Quan sát hàm của một thư viện |
| Hook mạng hoặc LSM | Điểm quan sát/xử lý mạng hoặc bảo mật, tùy loại chương trình | Thu dữ liệu mạng hoặc áp hành động được hỗ trợ |

BTF mô tả kiểu dữ liệu của kernel. CO-RE dùng thông tin kiểu và cơ chế relocation để thích nghi với khác biệt layout giữa kernel phù hợp. Hỗ trợ thực tế còn phụ thuộc tính năng kernel, quyền agent và cấu hình môi trường. [R11 What is eBPF?](../TaiLieu_Tuan1_Tuan2/PDF/R11-What-is-eBPF.pdf), [Linux kernel BPF documentation](https://docs.kernel.org/bpf/).

## Một kết nối từ kernel đến đồ thị

Giả sử tiến trình checkout gọi `connect()` tới payment:

```text
checkout process → socket/connect → hook trên node
  → bản ghi có tiến trình, địa chỉ và cổng
  → tra Pod/container theo ngữ cảnh runtime
  → tra Service/endpoint theo snapshot tại thời điểm xảy ra
  → cạnh checkoutservice → paymentservice
```

Địa chỉ có thể là Service IP hoặc Pod IP tùy vị trí quan sát và biến đổi mạng. Một socket non-blocking có thể trả `EINPROGRESS` ở lần gọi đầu; muốn biết cuối cùng TCP thiết lập hay thất bại cần quan sát tiếp hoặc đối chiếu phía ứng dụng. Một kết nối tồn tại lâu có thể phục vụ nhiều request gRPC. Dùng log/trace lớp ứng dụng để đếm lời gọi và biết status.

| Tín hiệu | Kết luận có thể rút ra | Bằng chứng cần thêm |
|---|---|---|
| Exec event | Binary đã được thực thi nếu sự kiện thể hiện exec thành công | Dòng lệnh, parent, actor, mục đích |
| Open file thành công | Có thể mở file với quyền tương ứng | Sự kiện read nếu cần chứng minh đã đọc |
| Connect attempt | Tiến trình thử mở kết nối tới địa chỉ/cổng | Kết quả TCP, log ứng dụng hoặc flow tương ứng |
| Audit event API | API server ghi nhận yêu cầu theo chính sách audit | Danh tính tiến trình và ngữ cảnh mạng nếu cần nối chuỗi |
| Không có event | Nguồn thu chưa ghi nhận sự kiện | Kiểm tra coverage, selector, event drop và thời gian thu |

## Chi phí và chất lượng dữ liệu

Thu càng nhiều sự kiện thì càng cần xem CPU, bộ nhớ, băng thông và kho lưu trữ. Lọc tại kernel có thể giảm dữ liệu đi lên agent, đổi lại bằng chứng bị loại không xuất hiện trong log. Cần ghi loại hook đã bật, số event theo node, cảnh báo mất sự kiện hoặc export lỗi nếu tool có số liệu, và tỷ lệ event thiếu metadata. Khởi động lại và backlog có thể làm sự kiện đến trễ; giữ cả thời gian xảy ra và thời gian ingest.

## Tự kiểm tra

1. **Biết binary `sh` đã chạy có biết người khởi tạo không?** Dùng process parent, UID, thông tin container và log điều khiển để đối chiếu.
2. **Có thể dùng số connect để báo throughput gRPC không?** Đếm request ở lớp ứng dụng hoặc proxy được cấu hình tương ứng.
3. **Vì sao cần kiểm thử bằng sự kiện chủ động?** Một thao tác có thời gian và nguồn đã biết cho phép kiểm tra toàn bộ đường từ hook tới log.

Chọn [Falco](06-falco.md) hoặc [Tetragon](07-tetragon.md), sau đó thiết kế dữ liệu ở [bài 8](08-du-lieu-va-thuc-nghiem.md).

