# Trạng thái batch đo lặp ngày 26/11/2026

**Đã khởi chạy lúc 01:11 ngày 26/11/2026, giờ Việt Nam.** Batch `batch-repeats-20261125T181112Z-2519845` chạy theo [protocol 24 lượt](repeat-protocol.json).

Ở snapshot đầu lúc 18:11:35 UTC ngày 25/11 (01:11:35 giờ Việt Nam), lượt `r1-s1-action` đang setup, **0/24 lượt hoàn tất**. Hai file raw của worker đã có dữ liệu, stderr rỗng và guard chưa có lý do dừng. Đây là bằng chứng đã bắt đầu thu log, chưa phải kết quả cohort.

- [Checkpoint khởi chạy và trạng thái systemd](audits/repeats-launch-20261126.json).
- [Checkpoint thu log đầu tiên](audits/repeats-first-capture-20261126.json).
- [121 test đạt, không skip](audits/repeats-tests-20261126.json) và [log](audits/repeats-tests-20261126.log).

Trang này giữ snapshot khởi chạy cho đến khi tiến trình đồng bộ cuối batch xuất bản kết quả mới. Không dùng snapshot này để suy ra tiến độ trực tiếp nhiều giờ sau.

Trạng thái trực tiếp được ghi trên VM trong runs/batch-repeats-*/batch.json và service boutique-repeats-20261126-v1. [Hướng dẫn theo dõi và dừng an toàn](REPEATS.md).
