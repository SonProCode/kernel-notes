# Đánh giá detector và thiết kế phản ứng

Mục tiêu tuần 3 là trả lời được hai câu hỏi trên cùng một lab: **tín hiệu nào phát hiện hành vi mục tiêu**, và **policy chặn được gì trong khi vẫn giữ luồng checkout hợp lệ**. Một công cụ có độ trễ thấp trong bài báo có thể khác khi chạy với hook, rule và tải của bạn.

## R18 so sánh Falco, Tetragon và Tracee

Bài của Aldien Asy Syairozi và Arizal so ba công cụ trong ba nhóm kịch bản: container escape, DoS và cloud cryptomining. Các phép đo gồm MTTD, detection rate, FPR, CPU và bộ nhớ. Trong bộ thử của tác giả, Tetragon phát hiện nhanh nhất ở hai nhóm container escape và cryptomining, Falco nhanh nhất ở DoS. Dùng bài làm mẫu cách thiết kế bảng đo theo từng kịch bản. Ba nhóm đó khác bài thử di chuyển ngang của đề tài, nên cần đo lại. Tên bài tại nhà xuất bản là *Comparative Analysis of eBPF-Based Runtime Security Monitoring Tools in Monitoring and Threat Detection on Kubernetes*. [R18 bản gốc và bảng kết quả](https://www.scitepress.org/Papers/2025/142727/142727.pdf)

**MTTD** là trung bình độ trễ phát hiện của các lần đã phát hiện, tính từ mốc bắt đầu hành vi đã quy ước đến alert đầu tiên khớp. Báo kèm tỷ lệ phát hiện và timeout để thấy số lần bị bỏ sót. Ví dụ, detector phát hiện 3/5 lần với các độ trễ 0,8, 1,1 và 1,4 giây thì MTTD của ba lần khớp là 1,1 giây, recall theo lần chạy là 60%. Hai lần còn lại ghi là bỏ sót tại thời hạn đã quy định. Dữ liệu này chỉ là minh họa. Xem thêm [định nghĩa TP/FP và độ trễ](../HocLieu_Tuan1_Tuan2/08-du-lieu-va-thuc-nghiem.md#đánh-giá-bảo-mật-và-hiệu-năng).

## Ma trận thí nghiệm tuần 3

| Lần chạy | Điều thay đổi | Câu hỏi cần trả lời |
|---|---|---|
| A | Ứng dụng và tải chuẩn | Checkout thành công và mất bao lâu? |
| B | Thêm collector và dữ liệu chuẩn hóa | Event nào được thu và tỷ lệ thiếu metadata ra sao? |
| C | Cùng dữ liệu chuẩn hóa, chạy rule cố định và detector bất thường | Mô hình nào bắt được S2 hoặc S3 và cảnh báo nhầm bao nhiêu? |
| D | Bật Istio và mTLS, giữ detector | Chi phí thêm proxy là gì và đường mesh hoạt động ra sao? |
| E | Bật AuthorizationPolicy đã kiểm tra | Probe ngoài quyền bị từ chối không? Checkout còn thành công không? |
| F | Tùy chọn thử controller phản ứng ở chế độ audit rồi canary | Sau alert bao lâu thì chặn thật, rollback có phục hồi luồng không? |

Cố định phiên bản, placement, workload, số replica, tần suất thử và lịch tải. Lặp lại theo run độc lập. So detector trên cùng input khi muốn đo tác động của **thuật toán**. Khi muốn so **cả pipeline** Falco và Tetragon, ghi rõ khác biệt giữa cấu hình, rule và dữ liệu mà từng công cụ nhận. Đo CPU/bộ nhớ collector và proxy theo node hoặc container nhất quán. Đo cả p95 request latency, throughput và số lần checkout lỗi.

## Phản ứng từ cảnh báo đến chặn có kiểm chứng

Phương án đề xuất cho lab:

```text
Telemetry → detector → cảnh báo có run_id và bằng chứng
  → đối chiếu Pod UID, workload và ServiceAccount hiện tại
  → quyết định của controller theo policy đã duyệt
  → proxy hoặc lớp mạng thực thi
  → probe hợp lệ và probe ngoài quyền kiểm chứng kết quả
```

**Ví dụ.** Detector thấy shell trong recommendation rồi thấy nhiều lần thử tới payment. Tín hiệu đầu tiên tạo cảnh báo điều tra. Cảnh báo thứ hai tăng mức ưu tiên khi cùng Pod UID trong khoảng thời gian đã định. Với nguyên mẫu, controller có thể ghi đề xuất và chờ bước xác nhận của thí nghiệm trước khi áp thay đổi. Sau khi đổi cấu hình, thử lại Charge từ checkout và probe lab. Tác động đến quyền của source ServiceAccount có thể ảnh hưởng mọi Pod dùng danh tính đó; phép thử cần giới hạn scope theo mục tiêu đã định.

Các trường nên lưu trong bản ghi quyết định gồm `event_ids`, `run_id`, `target_policy`, scope nguồn và đích, lý do, phiên bản trước/sau, thời điểm alert, thời điểm apply, thời điểm probe thấy từ chối và kết quả kiểm tra checkout. Controller chỉ có quyền sửa nhóm tài nguyên/policy được giao trong namespace lab. Khi nhận cùng alert nhiều lần, cập nhật một quyết định theo khóa cố định hoặc bỏ qua bản trùng để giữ trạng thái nhất quán. Ghi thời hạn và quy trình rollback cho quyết định phản ứng.

Để tách kết quả, lưu cả **cố gọi**, **bị policy từ chối**, **detector phát hiện** và **checkout hợp lệ thành công**. Nếu policy chặn ngay trong lần chạy dùng để đo detector, chuỗi hành vi sau đó có thể không xảy ra. Dùng một pha quan sát và một pha enforcement khi cần so độ phủ phát hiện với hiệu quả chặn.

## Tự kiểm tra

1. **Có 0 cảnh báo sai ở hai lần chạy bình thường, đã chứng minh FPR thấp chưa?** Báo kích thước mẫu và tăng độ đa dạng đối chứng trước khi khái quát.
2. **Nếu Istio chặn request nhưng detector bỏ sót, ghi thế nào?** Ghi riêng policy chặn thành công và detector bỏ sót theo mục tiêu của lần chạy.
3. **Tại sao cần đo luồng checkout sau rollback?** Lần probe xác nhận hệ thống nghiệp vụ đã phục hồi sau thay đổi.

## Đầu ra tuần 3

- Manifest Istio có scope rõ, kèm bảng luồng cho phép và bị chặn.
- Một detector luật cố định và một detector đơn giản lấy cảm hứng từ R24 hoặc cạnh mạng mới theo R23.
- Hồ sơ run có ground truth, log và phép kiểm chứng phía đích. Bảng kết quả báo recall, precision, cảnh báo sai, MTTD, tác động tới checkout và chi phí.
- Tài liệu bàn giao ghi giả định, phần đã thử và việc còn cần kiểm chứng.

Xem [danh mục nguồn](09-tra-cuu.md#mục-đọc-theo-mã-r).
