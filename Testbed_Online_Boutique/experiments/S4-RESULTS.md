# Kết quả pilot S4 ngày 23/11/2026

Các số dưới đây lấy từ verifier từng run. Rate là tải phụ; Locust vẫn có 10 người dùng bình thường.

| Rate / worker | Request tải phụ khớp | Lỗi tải phụ | Locust: số mẫu / lỗi trong pha đo | Locust p95 trước / trong / hồi phục (ms) | CPU frontend trung bình trong pha (core) |
| --- | --- | --- | --- | --- | --- |
| 0 RPS / w1 | 0/0 | 0 | 64 / 0 | 81.26 / 178.65 / 93.72 | 0.027 |
| 3 RPS / w1 | 90/90 | 0 | 62 / 0 | 111.19 / 114.42 / 88.64 | 0.037 |
| 6 RPS / w1 | 179/179 | 0 | 66 / 0 | 90.65 / 175.85 / 74.09 | 0.046 |
| 10 RPS / w1 | 295/295 | 0 | 66 / 0 | 91.10 / 299.89 / 74.76 | 0.058 |
| 10 RPS / w2 | 297/297 | 0 | 63 / 0 | 63.10 / 258.61 / 91.95 | 0.057 |

Control 0/0 nghĩa là không bật client tải phụ; các request mua hàng Locust vẫn được đo. P95 tính trên HTTP 200 không có exception; request vắt qua biên pha giữ riêng. CPU dùng rate cửa sổ một phút, có làm mượt. Các profile chạy tuần tự, route mix và số mẫu có thể khác; chưa dùng những số này làm kết luận nhân quả hoặc ngưỡng DoS.

## Quan sát từ cohort này

Có 861 request tải phụ thực sự được gửi, tất cả có native event đối chiếu. Có 9 slot được bỏ qua do giới hạn concurrency hoặc scheduler; đó không phải request đã gửi rồi thất bại. Lỗi HTTP của tải phụ trong cohort: 0.

Đọc p95 trước/trong/hồi phục và CPU của từng profile cùng control. Cohort ngắn, control tự có dao động p95 và chưa khóa seed; cần lặp thêm cùng profile để ước lượng tác động ổn định.

Cờ verifier passed xác nhận đường chạy, đối chiếu và chất lượng xuất theo các kiểm tra đã nêu. Hãy đọc failure ratio, số mẫu và recovery cùng cờ này. Không dùng passed làm kết luận đã phát hiện/chặn DoS.

## Mở bằng chứng từng lượt

- [s0-s4-control-20261123T045647Z-1848096](../runs/s0-s4-control-20261123T045647Z-1848096/s4-verification.json): [manifest](../runs/s0-s4-control-20261123T045647Z-1848096/manifest.json), [timeline](../runs/s0-s4-control-20261123T045647Z-1848096/timeline.ndjson), [archive](../runs/s0-s4-control-20261123T045647Z-1848096/dataset.tar.gz).
- [s4-20261123T045922Z-1853277](../runs/s4-20261123T045922Z-1853277/s4-verification.json): [manifest](../runs/s4-20261123T045922Z-1853277/manifest.json), [timeline](../runs/s4-20261123T045922Z-1853277/timeline.ndjson), [archive](../runs/s4-20261123T045922Z-1853277/dataset.tar.gz).
- [s4-20261123T050200Z-1858668](../runs/s4-20261123T050200Z-1858668/s4-verification.json): [manifest](../runs/s4-20261123T050200Z-1858668/manifest.json), [timeline](../runs/s4-20261123T050200Z-1858668/timeline.ndjson), [archive](../runs/s4-20261123T050200Z-1858668/dataset.tar.gz).
- [s4-20261123T050441Z-1864262](../runs/s4-20261123T050441Z-1864262/s4-verification.json): [manifest](../runs/s4-20261123T050441Z-1864262/manifest.json), [timeline](../runs/s4-20261123T050441Z-1864262/timeline.ndjson), [archive](../runs/s4-20261123T050441Z-1864262/dataset.tar.gz).
- [s4-20261123T050725Z-1869684](../runs/s4-20261123T050725Z-1869684/s4-verification.json): [manifest](../runs/s4-20261123T050725Z-1869684/manifest.json), [timeline](../runs/s4-20261123T050725Z-1869684/timeline.ndjson), [archive](../runs/s4-20261123T050725Z-1869684/dataset.tar.gz).

[Audit source/native và tính đồng nhất release](audits/s4-pilots-audit-20261123.json).

[Trạng thái lab sau đo và hash source đang triển khai](audits/lab-state-s4-20261123.json): loadgenerator gốc=0, không còn Pod/Deployment/ConfigMap/SA thí nghiệm; ba node Ready và frontend/checkout/payment available.
