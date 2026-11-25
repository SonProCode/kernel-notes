# Kết quả khởi động GĐ4

Cập nhật ngày 19/11/2026, giờ Việt Nam.

Đã triển khai phần chuẩn bị tuần 11 và pilot S1 trên lab. Đây là checkpoint đầu của GĐ4. Hướng dẫn chạy hiện tại ở [IMPLEMENTATION.md](IMPLEMENTATION.md), kế hoạch đầy đủ ở [README.md](README.md).

## Kết quả kiểm thử

- Ma trận giao tiếp có 17 cạnh cấu hình, trong đó 16 cạnh tới Service đang triển khai. Các cạnh có đường dẫn chứng minh từ mã nguồn v0.10.7.
- Policy file đã hoạt động trên cả hai worker. Mỗi worker đối chiếu được 3/3 lần đọc fixture token giả. Mỗi lượt thu 12 sự kiện security_file_permission.
- Có 3 lượt S1 pilot, gồm một lượt trên w1 và hai lượt trên w2. Mỗi lượt đối chiếu được 22/22 thao tác với sự kiện TCP, tổng 66 thao tác có bằng chứng.
- Lượt S0 smoke mới đo 15 giây, dùng schema v3. Đây là kiểm thử pipeline; các lượt S0 15 phút theo cấu hình mới sẽ thu ở bước dữ liệu chính thức.
- Đã kiểm tra quy tắc nhãn với các trường hợp đúng actor/đích/thời gian, sai đích, traffic nền trong attack, traffic trước attack và dòng JSON sai kiểu.
- Bản nhãn v2 tách phần đuôi collector sau measurement_end thành finalize/unknown. Mỗi lượt xử lý lại có processing.json ghi phiên bản nhãn, mã SHA-256 bộ xử lý và mã archive trước xử lý.

| Lượt chạy | Kịch bản và chế độ | Placement được yêu cầu | Thao tác khớp / tổng hoặc trạng thái |
| --- | --- | --- | --- |
| [s0-20261118T165608Z-1704557](../runs/s0-20261118T165608Z-1704557/manifest.json) | S0 / smoke | w1 | failed |
| [s0-20261118T165734Z-1707230](../runs/s0-20261118T165734Z-1707230/manifest.json) | S0 / smoke | w1 | interrupted |
| [s0-20261118T165950Z-1711725](../runs/s0-20261118T165950Z-1711725/manifest.json) | S0 / smoke | w1 | 0/0 |
| [s1-20261118T165249Z-1698505](../runs/s1-20261118T165249Z-1698505/manifest.json) | S1 / pilot | w1 | 22/22 |
| [s1-20261118T165440Z-1701809](../runs/s1-20261118T165440Z-1701809/manifest.json) | S1 / pilot | w2 | 22/22 |
| [s1-20261118T165755Z-1708256](../runs/s1-20261118T165755Z-1708256/manifest.json) | S1 / pilot | w2 | 22/22 |
| [s3-20261118T164938Z-1692635](../runs/s3-20261118T164938Z-1692635/manifest.json) | S3 / smoke | w1 | 3/3 |
| [s3-20261118T165143Z-1696393](../runs/s3-20261118T165143Z-1696393/manifest.json) | S3 / smoke | w2 | 3/3 |

Kết quả client của các lượt S1 cộng lại là connected=33, timeout=33. Các cổng timeout vẫn là thao tác scan đã được thực hiện; kết quả kết nối lấy từ receipt.

## Kiểm thử dừng runner

Lượt kiểm thử cleanup đầu dùng bản runner cũ vì bước đồng bộ chọn sai thư mục. SIGTERM khi đó làm runner dừng mà chưa đưa loadgenerator về 0. Đã đưa tải về 0, dừng hai collector còn lại của đúng lượt lỗi và lưu postmortem.json cùng manifest-original.json. Manifest chính của lượt đó được đối soát thành failed/excluded.

Bước đồng bộ đã được sửa để yêu cầu runner.py tồn tại trong thư mục nguồn, thay file bằng rename và kiểm tra SHA-256 sau khi chép. Bản runner có xử lý SIGTERM đã được kiểm thử lại thành công, lưu status=interrupted và đưa loadgenerator về 0. Lượt dừng chủ động này được giữ làm bằng chứng kiểm thử.

Sau các lượt thử, loadgenerator ở 0 replica và các Pod actor của lượt chạy đã được dọn.

## Chất lượng và giới hạn

Các lượt hoàn tất đều có dữ liệu cả hai worker, không có lỗi parse trong quality.json, agent giữ nguyên UID/restart và stderr của collector rỗng. Những lượt mới có snapshot Prometheus trước/sau. Ở các mốc đọc đã kiểm tra, hai agent đều up=1 và các bộ đếm mất ring buffer, mất hàng đợi, lỗi export và giới hạn export đều có giá trị 0. Các snapshot chịu độ phân giải scrape của Prometheus.

Nhãn attack ở S1 được gán cho sự kiện TCP có căn cứ từ actor UID, thời gian và đích của receipt. Sự kiện chưa đủ căn cứ giữ unknown. Smoke file thuộc kiểm thử thiết bị đo và giữ nhãn unknown cho thao tác mô phỏng. Bộ pilot chưa phải toàn bộ dataset S1–S5 của GĐ4.

Bổ sung ngày 20/11/2026, S2 đã được triển khai và có hướng dẫn tại [S2.md](S2.md). Ngày 22/11 đã triển khai S3 runtime; xem [S3.md](S3.md) để kiểm tra từng thao tác, projected token và kết quả hai worker. Các kịch bản tiếp theo gồm S5 receiver nhận payload giả và S4 tải phụ có request-level latency. Sau khi kiểm chứng từng pilot, thực hiện các lượt chính thức và S0 đối chiếu.

## Mở dữ liệu

Trong mỗi thư mục run đã hoàn tất, dataset.tar.gz chứa raw/, normalized.ndjson và labeled-windows.ndjson. Manifest, timeline, receipt, quality và processing được giữ riêng để đọc trên GitHub.

Các lượt interrupted/failed có thể chỉ có raw. Đọc manifest và postmortem trước khi chọn dữ liệu cho phân tích. Liên kết raw_file/raw_line trong bản ghi chuẩn hóa dùng được sau khi giải nén tại thư mục run.


## Rà soát toàn bộ S1–S3 ngày 22/11/2026

Đã kiểm chứng lại 10 pilot từ archive và chạy thêm smoke hồi quy S2/S3. S1 có verifier strict cho đủ từng thao tác, source snapshot và hai pilot mới trên w1/w2. Bắt đầu thực hành từ [USAGE.md](USAGE.md); xem [S1.md](S1.md) và [báo cáo rà soát đầy đủ](REVIEW-S1-S2-S3.md) để biết kết quả, hạn chế và các lỗi hướng dẫn đã sửa.


## S4 ngày 23/11/2026

Đã triển khai và chạy 1 S0 control cùng 4 S4 pilot (3/6/10 RPS trên w1, thử lại 10 RPS trên w2). Có 861/861 HTTP operation tải phụ đối chiếu native, source và image đồng nhất giữa 5 lượt. Có thêm smoke, thử dừng SIGTERM trong attack, unit tests và report CPU/RAM/latency theo request. Xem [hướng dẫn S4](S4.md) và [kết quả S4](S4-RESULTS.md). Đây là checkpoint pilot; S5 và cohort official vẫn thuộc bước tiếp theo.


Xem [rà soát sâu S4 ngày 23/11/2026](S4-REVIEW.md): sửa verifier, guard, thứ tự chốt log Locust và kiểm tra cleanup; kết quả hồi quy và giới hạn của dữ liệu lịch sử được ghi riêng.


Cập nhật 25/11: [nghiệm thu lại S4](S4-ACCEPTANCE.md) đối chiếu đề cương, sửa kiểm tra đặc trưng normalized, bổ sung RPS/p99 và liệt kê điều kiện còn thiếu trước bộ official.


## Pilot S5 ngày 25/11/2026

Đã bổ sung [S5 gửi dữ liệu giả](S5.md): actor POST 64 KiB tới receiver tạm trên lab-cp:18080, đối chiếu client/receiver/raw Tetragon, schema v6 và cleanup cả Pod lẫn tiến trình host. [Kết quả và bằng chứng](S5-RESULTS.md) tách smoke, pilot hai worker và lượt SIGTERM. Tập official S0–S5 có lặp/đối chứng tiếp tục theo kế hoạch sau khi khóa cấu hình.


Xem [rà soát S5 sau pilot](S5-REVIEW.md) để đọc các lỗi đã tái hiện/sửa, 88 kiểm thử, hậu kiểm dữ liệu gốc và smoke bản mới. Số liệu 120 payload pilot gốc được giữ riêng theo source của các lượt đó.
