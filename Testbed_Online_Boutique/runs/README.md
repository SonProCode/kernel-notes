# Các lượt đo Online Boutique

Các kết quả được sao chép từ thư mục runs trên lab-cp. Lượt baseline sơ bộ gần nhất dùng Tetragon với hai hook tcp_connect và tcp_sendmsg, 10 user ảo, warm-up 400 giây và đo 900 giây.

[Tải bộ log 15 phút · khoảng 17 MB](https://github.com/SonProCode/kernel-notes/raw/refs/heads/main/Testbed_Online_Boutique/runs/s0-tetragon-20261117T162618Z-3967383/dataset.tar.gz) · [Xem summary.json](s0-tetragon-20261117T162618Z-3967383/summary.json) · [Xem tất cả file của lượt đo](https://github.com/SonProCode/kernel-notes/tree/main/Testbed_Online_Boutique/runs/s0-tetragon-20261117T162618Z-3967383)

| Thư mục | Kết quả |
| --- | --- |
| s0-tetragon-20261116T172527Z-2155454 | Đo 15 phút với hook mở kết nối. File chuẩn hóa có 3 sự kiện Redis. Các kết nối mới xuất hiện trước cửa sổ đo. Kiểm tra thu TCP không đạt. |
| s0-tetragon-20261117T162316Z-3962421 | Thử 60 giây sau khi thêm tcp_sendmsg. Có 9.318 sự kiện gửi TCP. Kiểm tra thu log đạt. |
| s0-tetragon-20261117T162618Z-3967383 | Đo 15 phút. Có 141.642 sự kiện, gồm 141.639 sự kiện gửi TCP và 3 sự kiện process_exit. Kiểm tra thu log đạt. |
| smoke-tetragon-* | Kiểm tra từng agent bằng Pod tạm trên hai worker. |
| s0-20261115* | Các lượt chạy tải và kiểm tra giám sát trước khi bổ sung telemetry Tetragon. Một số lượt chỉ có các file bắt đầu. |

Lượt 15 phút gần nhất đo từ 23:33:17 đến 23:48:17 ngày 17/11/2026, giờ Việt Nam. Hai worker ghi 76.189 và 65.453 sự kiện. Agent giữ nguyên UID và số lần restart trong khoảng đo. Hai luồng thu không ghi lỗi stderr.

Mỗi thư mục có summary.json nếu lượt đó đã đi tới bước chuẩn hóa. Giá trị basic_capture_checks_passed xác nhận các kiểm tra trong script. Khi đánh giá mất sự kiện ở kernel và hiệu năng ứng dụng, cần đối chiếu thêm Prometheus/Grafana và Locust. Log Locust là thống kê tích lũy, bao gồm warm-up. Số dòng Tetragon đo hoạt động kernel theo hook được chọn.

## Mở dữ liệu nén

Trong các lượt Tetragon, file dataset.tar.gz chứa thư mục raw với log hai worker và file telemetry.ndjson. Các mốc UTC, log Locust và snapshot cụm được lưu riêng để đọc ngay trên GitHub.

Ví dụ, trên Linux hoặc terminal có tar, từ thư mục repo:

```bash
cd Testbed_Online_Boutique/runs/s0-tetragon-20261117T162618Z-3967383
tar -xzf dataset.tar.gz
cat summary.json
wc -l telemetry.ndjson
```

Kết quả mong đợi là 141642 dòng. Các file archive-notes.txt ghi thông tin đóng gói. Những lượt chỉ có file rời được giữ nguyên các file đã có.

## Kiểm tra file tải về

Trên bản clone GitHub đã tải đủ file, từ thư mục Testbed_Online_Boutique:

```bash
sha256sum -c SHA256SUMS.txt
```


## Pilot S3 runtime ngày 22/11/2026

Hai lượt `s3-20261122T102500Z-378143` (w1) và `s3-20261122T102750Z-382892` (w2) đạt 18/18 thao tác mỗi lượt. Xem [hướng dẫn S3 và danh mục đầy đủ](../experiments/S3.md). Các archive mới giữ thêm `source/` để đối chiếu hash mã với manifest. Các lượt smoke lỗi và interrupted được giữ riêng và không tính là attack hoàn tất.


## Rà soát S1–S3 và cách dùng cho người mới

[Hướng dẫn bắt đầu](../experiments/USAGE.md) giải thích cách chạy và đọc kết quả. [Báo cáo rà soát 22/11](../experiments/REVIEW-S1-S2-S3.md) kiểm tra lại 10 pilot, gồm hai S1 mới đủ 22/22 trên mỗi worker, cùng smoke S2/S3 hồi quy. Các report giữ riêng trong experiments/audits; dữ liệu lịch sử không bị ghi lại bằng source hoặc nhãn mới.

SHA256SUMS.txt trong repo mô tả bản xuất đã đóng gói. Thư mục làm việc trực tiếp trên VM có thể chứa raw thay cho archive và đã có lượt mới, nên cần đối chiếu manifest/source hash của từng run; không áp danh mục checksum của bản xuất lên mọi file sống trên VM.


## S4 và S0 control ngày 23/11/2026

Các run s0-s4-control-* và s4-* lưu cohort đo có request-level Locust, guard và CPU/RAM. [S4.md](../experiments/S4.md) hướng dẫn mở; [S4-RESULTS.md](../experiments/S4-RESULTS.md) so sánh control và 3/6/10 RPS. Bốn S4 pilot có 861 HTTP request được gửi, tất cả có native event khớp. Lượt s4-s4-20261123T045120Z-1837437 là smoke phát triển lỗi normalize, được giữ cùng postmortem; lượt interrupted kiểm tra cleanup giữ riêng.


Các smoke hồi quy contract v2 và lượt failed_validation/interrupted được giữ để kiểm toán, không cộng vào cohort 861 request. Đọc [báo cáo rà soát S4](../experiments/S4-REVIEW.md) để biết từng lỗi, cách sửa và lần chạy nào được dùng xác nhận.


## Nghiệm thu S4 ngày 25/11/2026

[Report chi tiết](../experiments/S4-ACCEPTANCE.md) kiểm tra lại bằng chứng bằng verifier đã sửa, replay nhãn từng cửa sổ và bổ sung throughput/p99 theo pha. Các run hồi quy mới được giữ riêng theo source hash, không cộng vào cohort pilot ngày 23/11. Ngày UTC trong tên thư mục có thể là 24/11, tương ứng sáng 25/11 giờ Việt Nam.


## Pilot S5 ngày 25/11/2026

Các run s5-* có actor/receiver receipt, raw và source snapshot. [Hướng dẫn S5](../experiments/S5.md) giải thích topology receiver ngoài mạng Pod, SNAT và số byte; [bảng kết quả](../experiments/S5-RESULTS.md) chỉ cộng payload của các pilot hoàn tất. Lượt interrupted giữ riêng để chứng minh cleanup và không cộng vào cohort.
