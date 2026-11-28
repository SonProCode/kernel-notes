# Kết quả đo lặp S0–S5 ngày 28/11/2026

**Đã hoàn tất lúc 15:27:15 ngày 28/11, giờ Việt Nam** (08:27:15 UTC). Batch `batch-repeats-20261128T035224Z-2912209` có status completed; cả 24 case và 6 cặp đối chứng qua hậu kiểm. Đây là 5 case đã hậu kiểm kế thừa từ batch v1 và 19 case chạy mới, không phải 24 lượt thu mới liên tục.

Nguồn số liệu: [batch.json](../runs/batch-repeats-20261128T035224Z-2912209/batch.json), [cohort-review.json](../runs/batch-repeats-20261128T035224Z-2912209/cohort-review.json) và [kiểm kê cuối](audits/repeats-final-inventory-20261128.json). Checksum của cả 24 archive đã được kiểm lại khi lập bản tổng hợp này.

## 1. Đã chạy được những gì?

| Nhóm | Lượt chính | Kết quả thực đo |
| --- | ---: | --- |
| S0 nghiệp vụ | 3 | Mỗi lượt đo 900 giây, tổng 45 phút measurement, ngoài warm-up |
| S1 thăm dò | 3 | 66 lần thử TCP, mỗi lượt 22; đối chiếu được với native event. Có cả cổng mở và lần thử không kết nối được |
| S2 gọi payment trái luồng | 3 | 90 lời gọi API, mỗi lượt 30; client/server/native evidence đạt |
| S3 runtime abuse | 3 | 54 thao tác, mỗi lượt 18; đủ chuỗi shell, công cụ mạng và đọc token theo verifier |
| S4 tải phụ | 3 | Thực gửi 893 + 849 + 864 = **2.606 request**, đối chiếu được native evidence |
| S5 gửi payload giả | 3 | **180/180 upload** được nhận; tổng **11.796.480 byte = 11,25 MiB** payload giả |
| Đối chứng S4/S5 | 6 | 3 đối chứng S4 và 3 đối chứng S5; **6/6 cặp khớp cấu hình** |

18 lượt chính + 6 đối chứng = 24 case. Không cộng batch pilot, lượt v1 bị dừng hoặc lần hậu kiểm lại vào tổng này. S1 là số lần **thử** kết nối, không phải số lần kết nối thành công. Các con số thao tác/request/upload cũng không phải số dòng log Tetragon.

S4 đặt mục tiêu 900 slot mỗi lượt nhưng giới hạn concurrency và scheduler khiến một số slot không được gửi: tổng 2.700 slot, 2.606 request thực gửi. Slot bỏ qua không phải request đã gửi rồi nhận lỗi HTTP. Không báo rate cấu hình 10 RPS như thể mọi lượt đều đạt đúng 10 RPS.

## 2. Website có chậm khi chạy S4 không?

P95 dưới đây là latency request HTTP của **người mua Locust**, lấy từ từng pha tương ứng, chỉ trên HTTP 200 không có exception. Nó không phải latency của client tạo tải phụ và không phải thời gian kernel event.

| Vòng | P95 đối chứng S4 (ms) | P95 trong S4 (ms) | P95 hồi phục sau S4 (ms) |
| --- | ---: | ---: | ---: |
| 1 | 92,42 | 377,69 | 91,32 |
| 2 | 182,08 | 454,46 | 154,35 |
| 3 | 98,02 | 385,75 | 95,23 |

Trong cả ba cặp, p95 khi có tải S4 cao hơn đối chứng; sau khi dừng tải, p95 giảm xuống. Đây là quan sát lặp lại trong lab này. Ba cặp, phân bố actor w1/w2/w1 và lần tiếp nối sau gián đoạn chưa đủ để suy thành kết luận nhân quả tổng quát hay một mức suy giảm có khoảng tin cậy.

Với S5, p95 đối chứng / khi upload lần lượt khoảng 199,55 / 186,02 ms; 93,63 / 178,66 ms; 127,46 / 94,07 ms. Chưa thấy mức tăng latency nhất quán ở cả ba cặp. Kết quả cốt lõi của S5 là chứng minh đường gửi/nhận dữ liệu giả bằng client, receiver và native event, không bắt buộc phải gây chậm như S4.

## 3. Có bao nhiêu dữ liệu và nhãn?

Tổng kiểm kê từ quality đã qua replay: **3.085.301 bản ghi normalized**, bao gồm setup, warm-up, measurement/action và recovery của 24 case.

| Nhãn | Số bản ghi |
| --- | ---: |
| normal | 1.274.208 |
| attack | 6.038 |
| unknown | 1.805.055 |

Unknown được giữ khi quy tắc hiện hành chưa đủ căn cứ gán normal hoặc attack, đặc biệt ở setup/warm-up và các sự kiện nền trong pha action. Không tự đổi unknown thành normal để tăng số mẫu, cũng không coi mọi sự kiện trong một lượt S4 là attack.

Các bản ghi vẫn thuộc schema v4/v5/v6 theo từng họ. Bảng trên là kiểm kê số dòng theo nhãn, không chứng nhận rằng chúng đã được hợp nhất thành một bộ feature dùng trực tiếp cho mô hình. Khi học/đánh giá cần chuẩn hóa trường, chọn đơn vị mẫu và tách train/test theo run. Tỷ lệ nhãn mất cân bằng cũng khiến accuracy đơn lẻ dễ gây hiểu nhầm.

## 4. Có lỗi hoặc hạn chế gì cần giữ lại?

- Batch v1 từng dừng ở bước kiểm chứng S5 control. Nó vẫn có trạng thái failed, không bị viết lại. [Báo cáo sự cố và cách tái hiện](REPEATS-RECOVERY.md) giải thích bản tiếp nối và verifier đọc tiết kiệm RAM.
- Bảng Locust tích lũy cuối của S0 vòng 1 có 142 checkout, 1 lỗi; vòng 2 có 120/0 và vòng 3 có 135/0. Các bảng này bao gồm warm-up, không phải số checkout riêng của cửa sổ 900 giây. Không tuyên bố mọi request trong toàn bộ thí nghiệm đều thành công.
- Bản tiếp nối có thay đổi observer/verifier và khoảng gián đoạn giữa hai batch; mỗi run giữ source/batch để truy vết.
- Source/ảnh/vị trí và cấu hình từng cặp S4/S5 khớp theo kiểm tra fingerprint; seed không làm hành trình HTTP đồng thời giống hoàn toàn giữa hai lượt.
- Kết quả trên chứng minh đường mô phỏng, nhãn và bằng chứng qua các kiểm tra đã định nghĩa. Chưa có điểm precision/recall của detector hay hiệu quả chặn của policy.

## 5. Lab sau khi kết thúc

Checkpoint cuối ghi 3 node Ready, không có lỗi môi trường cuối; loadgenerator gốc trở về 0 và không còn Pod thí nghiệm. Receiver tạm được cleanup theo kiểm tra từng lượt S5. Đây là trạng thái tại thời điểm kết thúc batch, không phải giám sát liên tục sau đó.

Source, manifest, timeline, receipt, metric, raw và checksum đã được xuất bản cùng kết quả. Raw/source/normalized nằm trong dataset.tar.gz của từng run; metadata và report nằm ngoài để đọc nhanh.

## 6. Bước tiếp theo

Phần **đo lặp và kiểm chứng tái hiện đã xong**. Tiếp theo là chốt danh sách run và hợp đồng feature, xử lý unknown theo căn cứ, chia tập theo run rồi mới xây/đánh giá detector GĐ5. Bài [bản đồ schema](FEATURE-SCHEMA-MAP.md) và [hướng dẫn tái hiện từ đầu](REPEATS-RECOVERY.md) là điểm bắt đầu.
