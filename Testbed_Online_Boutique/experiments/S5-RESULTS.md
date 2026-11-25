# Kết quả pilot S5 ngày 25/11/2026

Đã chạy smoke, hai pilot trên w1/w2 và một lượt dừng có chủ đích. Các số dưới đây chỉ cộng hai pilot hoàn tất. Mỗi pilot dùng 60 payload giả × 64 KiB, mục tiêu 1 lần/giây, Locust normal 10 users chạy cùng.

| Worker / run | Payload nhận / gửi | Body thực nhận (byte) | Native connect / send | Nhãn attack | Peer IP receiver thấy |
| --- | --- | --- | --- | --- | --- |
| w1 / [s5-20261125T055108Z-1526279](../runs/s5-20261125T055108Z-1526279/s5-verification.json) | 60/60 | 3,932,160 | 60 / 120 | 180 | 192.168.141.143 |
| w2 / [s5-20261125T055455Z-1533348](../runs/s5-20261125T055455Z-1533348/s5-verification.json) | 60/60 | 3,932,160 | 60 / 120 | 180 | 192.168.141.144 |

Tổng: **120/120 payload, 7.864.320 byte = 7,5 MiB body**, tất cả có checksum/ACK khớp và đủ connect/send. Hai lượt có 360 event actor mang nhãn attack; số event kernel không bằng số HTTP request. Kernel ghi tổng 7.902.240 bytes_requested, gồm header HTTP; không dùng số đó thay body nhận hoặc tổng byte trên dây.

## Traffic người mua trong thời gian gửi

| Worker | Mẫu Locust / lỗi trong attack | p95 trước / attack / recovery (ms) |
| --- | --- | --- |
| w1 | 129 / 0 | 91.51 / 98.78 / 58.36 |
| w2 | 141 / 0 | 84.49 / 120.29 / 98.26 |

Hai pilot ghi 750 request Locust trên toàn lượt, gồm setup/warm-up/finalize; số lỗi HTTP/client trong dữ liệu này: 0. Các mẫu vắt qua biên pha không đưa vào p95 theo pha. Đây là quan sát chức năng và hồi phục của pilot, chưa phải phép đo tác động nhân quả hoặc overhead có đối chứng.

## Smoke và thử dừng

- [s5-20261125T054746Z-1520142](../runs/s5-20261125T054746Z-1520142/manifest.json): smoke 12/12 payload, 786.432 byte; actor giữ nhãn unknown. Verifier được bổ sung thêm kiểm tra provenance, guard timestamp và Locust sau smoke; audit hiện tại vẫn kiểm lại smoke từ raw. Source snapshot gốc được giữ riêng. Hai pilot chạy cùng bản mã đã khóa sau bổ sung này.
- [s5-20261125T055833Z-1540255](../runs/s5-20261125T055833Z-1540255/manifest.json): helper đợi có receipt rồi gửi SIGTERM. Receiver đã nhận 3 payload trước khi dừng; status interrupted, cleanup đạt. Không cộng các payload này vào 120 payload pilot.
- Traceback KeyboardInterrupt: Signal 15 trong log cleanup là tín hiệu thử dừng có chủ đích. Kết luận dựa trên manifest, cleanup.json, log receiver và thông báo SIGTERM cleanup verified.

## Hậu kiểm và trạng thái cuối

- [Audit S5](audits/s5-pilots-audit-20261125.json): mở archive trong thư mục tạm, kiểm lại ba nguồn bằng chứng, replay normalized và nhãn cửa sổ, source/image, chỉ tính cohort pilot hoàn tất.
- [Policy snapshots](audits/s5-policy-check-20261125.json): spec của toàn bộ TracingPolicyNamespaced giống nhau trước/sau cả hai pilot. Không thêm policy hay tắt enforcement để chạy S5.
- [28 kiểm thử S5](audits/s5-tests-20261125.json): fixture, giao thức receiver/client, từ chối dữ liệu sai và các bản sao evidence bị làm hỏng.
- [77 kiểm thử kết hợp S4/S5](audits/s4-s5-regression-20261125.json): 0 failure/error/skipped; kiểm tra thêm việc dùng chung helper và import.
- [Hậu kiểm S1–S3](audits/s1-s2-s3-after-s5-20261125.json): 10/10 pilot lịch sử tiếp tục đạt; không ghi lại dữ liệu cũ.
- [Trạng thái lab cuối](audits/s5-final-state-20261125.json): ba node Ready, không MemoryPressure; các deployment đạt replica mong đợi; loadgenerator gốc=0; không còn tài nguyên experiment-run; port 18080 đã đóng. Source đang triển khai khớp cả hai pilot. Receiver host dùng Python 3.10.12; actor/Locust image ID có trong từng manifest.

## Nhật ký triển khai để double check

1. Đối chiếu đề cương và kế hoạch S5; chọn receiver trên IP riêng lab-cp, ngoài mạng Pod. Kiểm tra port trống, route, worker Ready, policy TCP và firewall trước khi chạy.
2. Thêm fixture sinh dữ liệu giả, receiver tạm chạy không root, client POST có pacing/timeout, run_id/operation_id/bytes/SHA-256 và ACK.
3. Thêm runner riêng cho S5, dùng Locust/guard/Prometheus đã có; snapshot 12 source files và image IDs. Không đổi pipeline chuẩn hóa S1–S4.
4. Thêm normalized/label v6 cho S5 và verifier đối chiếu client ↔ receiver ↔ raw; kiểm lại toàn bộ feature background và cửa sổ bằng replay.
5. Smoke 12 payload, bổ sung kiểm tra biên dữ liệu rồi khóa mã cho hai pilot 60 payload. Chạy tuần tự w1 rồi w2; sau đó kiểm thử SIGTERM khi đang upload.
6. Xuất metadata và dataset.tar.gz, kiểm SHA-256, audit bản xuất, cập nhật hướng dẫn và website. Giữ smoke/interrupted riêng, không đổi thành pilot hoàn tất.

## Điều chưa được kết luận

Đã kiểm chứng gửi payload giả tới endpoint lab ngoài mạng Pod và có dữ liệu có nhãn để phân tích. Chưa thử exfiltration Internet, DNS/TLS/covert channel; chưa đo recall/precision hay hiệu quả egress deny. Những phạm vi đó không được suy ra từ pilot này.

Tập official vẫn cần các lượt lặp và S0 đối chứng theo kế hoạch. Cần chốt tập đặc trưng/schema thống nhất cho S0–S5; các schema v4/v5/v6 đang được giữ theo phiên bản, không ghép mù làm cùng một bảng huấn luyện. Dữ liệu raw còn nguyên để phân tích lại theo phiên bản mới khi cần.
