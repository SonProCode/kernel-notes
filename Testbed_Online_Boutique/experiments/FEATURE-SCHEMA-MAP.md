# Bản đồ schema trước khi phân tích S0–S5

Ngày 25/11/2026. Schema là quy ước tên và ý nghĩa từng trường. Hai file cùng NDJSON không có nghĩa là có thể nối vào nhau rồi huấn luyện ngay.

## Các phiên bản đang có

| Dữ liệu | Bản ghi sự kiện | Nhãn | Cách sử dụng |
| --- | --- | --- | --- |
| S0 GĐ3 | schema 2, baseline thất bại cũ schema 1 | Chưa có hợp đồng nhãn GĐ4 | Tham chiếu lịch sử; loại baseline chỉ 3 event |
| S1 cũ | Có label_version v2 | Nhãn lịch sử | Hai lượt đầu thiếu snapshot source; đánh dấu hạn chế |
| S0 nghiệp vụ mới và S1–S3 hiện hành | schema 4 | label_version v4 | Đối chiếu raw và source theo từng run |
| S4 và S0–S4 | schema 5 | label_version v5 | Có request-level Locust và cửa sổ pha |
| S5 và S0–S5 | schema 6 | label_version v6 | Có receipt upload, socket/native identity và receiver |

`manifest.schema_version` có thể là 3/4/5; đó là phiên bản của **manifest**, không phải schema sự kiện trong normalized.ndjson. Phải đọc từng loại file riêng. Khi kiểm kê tự động, đếm phiên bản thực trong archive; không đoán từ tên thư mục.

## Hợp đồng feature đề xuất

Feature là con số hoặc thuộc tính detector được phép quan sát. Ví dụ “số đích TCP khác nhau trong 5 giây” hữu ích hơn tên Pod ngẫu nhiên. Bảng này là thiết kế cho bước sau; chưa có bộ dữ liệu hợp nhất được chứng nhận.

| Trường chung | Ý nghĩa và quy tắc |
| --- | --- |
| timestamp_utc | Giữ thời gian sự kiện gốc; chuyển UTC, giữ độ chính xác khi có thể |
| event_type | Phân biệt process_exec, process_exit, tcp_connect_attempt, tcp_send và file event; không gộp send với connect |
| workload, namespace, node | Ngữ cảnh từ Pod metadata; lưu provenance ánh xạ |
| process/parent identity | Dùng exec_id, parent_exec_id, PID khi raw có; không tự gán từ tên binary |
| binary | Tên tiến trình thực tế; shell hợp lệ cũng có thể xuất hiện trong normal |
| source/destination IP, port | S0 cũ có socket.dst_ip/dst_port; bản mới dùng daddr/dport. Chuẩn hóa IPv4-mapped IPv6 trước khi ánh xạ |
| destination service | Tra Service/EndpointSlice snapshot theo **IP và cổng**, phân biệt chiều trả lời; lưu unresolved thay vì đoán |
| bytes_requested | Đối số số byte yêu cầu gửi ở hook kernel, không phải payload hay byte đã truyền thành công. Nếu bản chuẩn hóa cũ thiếu, chỉ bổ sung từ raw có đối số tương ứng; thiếu thì null kèm cờ missing |
| file access | Path, thao tác và kết quả từ raw/policy file; không coi process_exec là bằng chứng đã đọc file |
| label và evidence | Tách khỏi feature; suy từ nhật ký thao tác/receipt và native evidence theo hợp đồng phiên bản |

Ví dụ S5 mới có payload receiver 1.966.080 byte nhưng kernel_send_bytes_requested là 1.975.560: có header HTTP và cách chia lần send. Không dùng hiệu số này làm bằng chứng mất dữ liệu. Tetragon cũng không đồng nghĩa HTTP access log.

## Tránh rò rỉ nhãn và báo cáo nhầm

- Không dùng run_id, scenario_id, operation_id, tên actor có tiền tố s5, fixture hash, label/evidence làm đầu vào detector. Chúng có thể tiết lộ đáp án do cách dựng lab.
- Tách train/validation/test **theo toàn bộ run**, trước khi tạo cửa sổ. Chia ngẫu nhiên các dòng cùng một lượt dễ đưa những mẫu gần như giống nhau sang cả train và test.
- Nếu đánh giá khả năng tổng quát giữa node, chốt riêng cách chia w1/w2 và kiểm tra phân bố workload; không mặc nhiên coi hai node độc lập hoàn toàn.
- Không đổi toàn bộ pha attack thành nhãn attack: nghiệp vụ Locust vẫn chạy trong pha đó. Các bản ghi không đủ bằng chứng giữ unknown.
- Không dùng smoke S4/S5 có hành vi unknown như normal để tăng số mẫu normal. Case s0-admin chỉ có phần measurement được xác nhận là tác vụ hợp lệ; setup vẫn theo hợp đồng nhãn của runner.
- Không lấy số thao tác khớp native event làm recall detector. Đó là kiểm tra coverage bằng chứng thực hiện; detector chưa được chạy và chấm điểm ở đây.

Khi triển khai bộ hợp nhất, tạo thư mục derived mới, lưu converter version/hash, nguồn raw, hợp đồng ánh xạ và thống kê missing. Giữ nguyên dữ liệu lịch sử. Chạy lại raw replay và kiểm tra mẫu từng họ trước khi sử dụng feature cho GĐ5.

[Trở lại báo cáo S0–S5](S0-S5-REVIEW.md).
