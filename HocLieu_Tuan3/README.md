# Tuần 3 Thực thi chính sách và phát hiện bất thường

## Mục tiêu

Sau tuần này, bạn có thể giải thích vì sao một Pod có đường TCP đến payment nhưng vẫn có thể bị Istio từ chối khi gọi Charge. Bạn cũng có thể thiết kế một detector đơn giản, tách cảnh báo khỏi quyết định chặn và kiểm chứng cả luồng hợp lệ.

| Thứ tự | Bài đọc | Việc cần làm |
|---|---|---|
| 1 | [Thực thi chính sách với Istio](10-istio-policy-enforcement.md) · R19, R20 | Vẽ đường đi của request, xác định danh tính nguồn và chính sách ở đích. |
| 2 | [Phát hiện bất thường](11-phat-hien-bat-thuong.md) · R24 và hướng mở rộng R23 | Chạy ví dụ baseline tiến trình, giải thích trường hợp bỏ sót và cảnh báo nhầm. |
| 3 | [Đánh giá detector và phản ứng](12-danh-gia-va-phan-ung.md) · R18 | Lập ma trận thực nghiệm và đo khả năng chặn probe mà vẫn giữ checkout hoạt động. |

## Ví dụ xuyên suốt

Checkout thực hiện một lần gọi Charge và được phép vì đúng danh tính, phương thức và đích. Pod thử với danh tính khác cũng tạo yêu cầu Charge. Nếu mTLS thành công nhưng AuthorizationPolicy từ chối, đó là bằng chứng ở lớp phân quyền. Một dòng exec shell trước lần gọi chỉ giúp dựng trình tự sự kiện, còn nhận diện nguồn và kết quả gRPC cần thêm log phù hợp.

## Kế hoạch học

1. Đọc R19 và R20. Tự giải thích sự khác nhau giữa ServiceAccount, mTLS, RBAC, NetworkPolicy và AuthorizationPolicy. Dùng manifest ví dụ để lập ma trận caller hợp lệ, caller ngoài quyền và caller ngoài mesh.
2. Đọc R24. Dùng telemetry của một lần chạy sạch để lập baseline executable. Chạy lại với ví dụ hoạt động bình thường, shell mô phỏng và event thiếu metadata.
3. Đọc R23 nếu muốn nghiên cứu quan hệ mạng. Thử dò cạnh mới trên dữ liệu có độ phủ phù hợp trước khi tính tới GNN.
4. Đọc R18 để lập bảng chỉ số. Lưu riêng thời điểm thử, alert, quyết định và kết quả thực thi. Đo lại với luồng checkout đối chứng.

Các ví dụ detector và YAML minh họa phương pháp. Trước khi dùng trong báo cáo, chạy phép thử trên cluster lab và lưu dữ liệu thật. Xem [mẫu bàn giao](../HocLieu_Tuan1_Tuan2/09-tra-cuu.md).

## Nguồn chính

- R19 · [Istio Security](https://istio.io/latest/docs/concepts/security/)
- R20 · [Istio AuthorizationPolicy](https://istio.io/latest/docs/reference/config/security/authorization-policy/)
- R18 · [Syairozi và Arizal, so sánh công cụ eBPF](https://www.scitepress.org/Papers/2025/142727/142727.pdf)
- R23 · [GATAKU và phát hiện bất thường bằng GNN](https://digitalcollection.zhaw.ch/bitstreams/15ae5877-9515-4c65-9712-aa32a2a2cc89/download)
- R24 · [El Khairi, Peter và Continella, PROCATCH](https://conand.me/publications/elkhairi-procatch-2025.pdf)

[Đọc Tuần 3 trên Kernel Notes](https://sonprocode.github.io/kernel-notes/#tuan-3)

