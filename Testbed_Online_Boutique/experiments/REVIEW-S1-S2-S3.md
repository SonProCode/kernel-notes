# Rà soát S1, S2, S3 và hướng dẫn sử dụng

Ngày rà soát: 22/11/2026. Kết luận trong trang này là **checkpoint chức năng GĐ4 ở mức pilot**. Detector, hiệu quả chặn và bộ dữ liệu official được nghiệm thu ở các bước tương ứng.

## 1. Đã đối soát bằng cách nào?

Đã đọc lại bảng S1–S3 trong đề cương, code thực thi, receipt, normalized, raw Tetragon, log server S2 và snapshot từng lượt. Các verifier chạy lại trong thư mục tạm từ archive; không đổi raw, receipt, manifest hoặc nhãn của run lịch sử.

[Báo cáo máy đọc được](audits/s1-s2-s3-review-20261122.json) liệt kê từng run, kết quả, hash của công cụ rà soát và các giới hạn. [audit_scenarios.py](audit_scenarios.py) giúp kiểm tra lại bằng một lệnh; [USAGE.md](USAGE.md) hướng dẫn từ bước SSH.

## 2. Kết quả tổng hợp

| Kịch bản | Pilot được kiểm tra | Độ phủ thao tác native | Điều đã chứng minh |
| --- | ---: | ---: | --- |
| S1 | 5 lượt, gồm 3 lịch sử và 2 chạy lại | 110/110 | Từng cặp Service IP/cổng được thử; raw tcp_connect đúng actor/đích/thời gian |
| S2 | 3 lượt pilot | 65/65 | Charge trả OK/UUID; mỗi RPC có network event và đúng một handler log tương quan |
| S3 runtime | 2 lượt pilot ba vòng | 36/36 | Đủ shell, bốn công cụ, token read, ancestry và bằng chứng native |

Mười pilot đều đạt kiểm tra chức năng. Smoke, interrupted và failed_validation được liệt kê riêng, không cộng vào bảng pilot. Pilot S3 lỗi shell alias ban đầu vẫn được giữ. Các bản ghi normal/unknown tiếp tục giữ quy tắc của phiên bản nhãn trong từng run.

### Chạy lại bản script sau sửa

| Run mới | Mục đích | Kết quả |
| --- | --- | --- |
| [s1-20261122T131843Z-611505](../runs/s1-20261122T131843Z-611505/s1-verification.json) | Pilot trên w1, gate S1 mới | 22/22; source snapshot bốn file |
| [s1-20261122T131941Z-613505](../runs/s1-20261122T131941Z-613505/s1-verification.json) | Pilot trên w2, cùng code S1 | 22/22; source snapshot bốn file |
| [s2-20261122T132039Z-615550](../runs/s2-20261122T132039Z-615550/s2-verification.json) | Smoke hồi quy sau thay đổi runner | 1/1 RPC, network, server |
| [s3-20261122T132130Z-617543](../runs/s3-20261122T132130Z-617543/s3-verification.json) | Smoke runtime hồi quy | 6/6, gồm một lần đọc token |

Các lượt trên có status completed và dataset_status validated. Hai S1 mới có cùng bốn hash source và cùng image actor. S2/S3 smoke được kiểm tra lại độc lập từ archive, bao gồm hash nguồn, native events, metric và quét credential: [report hồi quy](audits/regression-smokes-20261122.json). [Transcript điều phối](../runs/s123-review-20261122T131842Z.log) giữ các pha và đầu ra chạy thử. Hai S1 mới dùng profile warm-up/pre/recovery 10/5/5; S2/S3 smoke dùng 5/5/5. Chúng được ghi đúng tham số thực tế.

## 3. Lỗi và điểm yếu đã sửa

### S1 có điều kiện đạt quá nhẹ

Runner trước đây chỉ cần có ít nhất một operation khớp là có thể qua gate S1. Ba pilot cũ thực tế đã đủ 22/22, nhưng điều kiện đó chưa ngăn một lượt chỉ thu được một phần bị đánh dấu đạt.

Đã thêm [s1_verify.py](s1_verify.py): kiểm tra danh sách receipt khớp manifest, không thiếu/trùng operation_id và đủ raw tcp_connect cho từng thao tác. Runner mới yêu cầu verifier này passed và ghi s1-verification.json. Các lượt S1 mới cũng lưu source snapshot.

Đã thử âm tính trên bản sao dữ liệu: bỏ receipt, trùng receipt, bỏ sự kiện một operation, đổi actor UID, đổi cổng đích và đổi timestamp. Tất cả trường hợp đều bị từ chối. [Kết quả kiểm thử âm tính](audits/s1-negative-checks-20261122.json) ghi rõ từng trường hợp; dữ liệu gốc không bị sửa.

### Hướng dẫn chưa thuận tiện cho người mới

Đã bổ sung hoặc sửa:

- Một bài dùng chung giải thích máy chạy lệnh, SSH, cd/pwd, sudo, tham số và cách chọn run.
- Bài S1 riêng, có ví dụ TCP/Service/port, kết quả thành công/timeout và bảng điều kiện đạt.
- Giải thích API/gRPC/UUID, danh tính nguồn và mock payment trong bài S2.
- Đưa bước giải nén archive lên trước verifier trong S2/S3.
- Phân biệt label v3 của S2 lịch sử với normalized v4 của code hiện tại; manifest có schema 3 riêng.
- Thay ví dụ placeholder dễ gõ sai bằng biến RUN có tên run thực, thêm cách xem run mới.
- Giải thích smoke/pilot/official, file nào do runner tạo và file nào do bước xuất GitHub đóng gói.
- Bổ sung thao tác đọc log gốc, kiểm tra cleanup và bảng xử lý lỗi thường gặp.
- Đánh dấu README kế hoạch là tài liệu thiết kế; chỉ rõ phần hiện thực đã thay đổi so với đề xuất ban đầu.

## 4. Phần nào còn giới hạn?

| Nội dung | Cách hiểu đúng sau rà soát |
| --- | --- |
| Source S1 cũ và S2 pilot đầu | Chưa có source snapshot trong archive. Kiểm tra được raw hành vi; không tự dựng lại source lịch sử bằng code mới |
| Hai S1 đầu ngày 18/11 | Chưa có snapshot Prometheus before/after, nên không kết luận được bộ đếm loss/export của hai lượt đó |
| Source snapshot mới | Kiểm hash các file được liệt kê trong manifest. Đây không phải bộ môi trường độc lập chứa toàn bộ phụ thuộc hệ thống; chạy lại cần repo, bundle và môi trường lab |
| S2 payment/checkout | Biến thể đã làm là payment.Charge từ actor ngoài vai trò checkout. Chưa kiểm thử trực tiếp API checkout |
| Hai S2 pilot 30 RPC | Hai bản runner trong quá trình phát triển; source từng lượt có lưu. Chưa coi chúng là cohort official cùng release |
| S3 token | Projected token thật của SA tạm, audience lab, yêu cầu TTL 600 giây; chỉ đọc và xuất metadata, không dùng credential gọi API |
| JWT metadata | Kiểm hình dạng và claim kỳ vọng trong bộ nhớ; không phải xác minh chữ ký |
| Metric loss/export | Hai snapshot và các series đã thu chỉ hỗ trợ phát hiện lỗi quan sát được; không chứng minh tuyệt đối không mất event ở mọi tầng |
| Nhãn attack | Ground truth do kịch bản/receipt đối chiếu; không phải cảnh báo tự phát từ detector |
| Độ phủ 22/22, 30/30, 18/18 | Độ phủ bằng chứng thao tác đã tạo; không dùng làm recall/precision của detector |
| Trạng thái official | Cần chốt release/profile, chạy số lượt lặp và S0 cùng policy/schema theo kế hoạch |

Đề cương GĐ4 yêu cầu script tái lập và bộ dữ liệu attack/normal có nhãn. GĐ5 xây detector; GĐ6 thực thi giảm thiểu. S1–S3 đã có checkpoint chức năng để tiếp tục S4/S5. Việc chốt toàn bộ dataset GĐ4 vẫn cần các mục còn lại.

## 5. Tự kiểm tra lại từ bản clone

Từ thư mục có `experiments/` và `runs/`:

```bash
python3 experiments/audit_scenarios.py --output experiments/audits/my-review.json
```

Tool tự mở archive trong thư mục tạm. Đọc `passed`, `pilots_reviewed`, `pilots_passed`, từng verification và limitations trong report. Output được ghi ở thư mục audits riêng; code từ chối output nằm bên trong run lịch sử được kiểm tra.

Trên lab-cp, nếu dữ liệu root sở hữu thì thêm sudo. Lệnh này không bật tải hay tạo actor. Để thực sự chạy lại hành vi trên cluster, dùng các lệnh trong [USAGE](USAGE.md), [S1](S1.md), [S2](S2.md), [S3](S3.md).

## 6. Trạng thái sau kiểm tra

[Snapshot kiểm tra cuối](audits/lab-state-20261122.json) xác nhận ba node Ready, loadgenerator=0, actor Pod=0, ServiceAccount thí nghiệm=0, builder Pod=0. Frontend, checkoutservice và paymentservice đều available 1/1. Các file xuất gồm cả run mới, report kiểm tra và checksum; lịch sử lỗi vẫn được giữ để đối soát.
