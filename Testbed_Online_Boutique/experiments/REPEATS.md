# Đo lặp S0–S5 theo lịch đã chốt

Ngày 26/11/2026, giờ Việt Nam. Người dùng đã yêu cầu thực hiện đo lặp sau khi hoàn tất pilot. **Lịch gồm 24 lượt dự kiến: 18 lượt chính S0–S5 và 6 đối chứng bổ sung cho S4/S5.** Đây là số lượt lên lịch; chỉ đếm thành công sau khi có dữ liệu, kiểm chứng và trạng thái cuối.

[Kết quả và trạng thái xuất bản](REPEATS-RESULTS.md) được cập nhật riêng. [Protocol đã chốt](repeat-protocol.json) là căn cứ xác định thứ tự, tham số và source hash. Không nhập các lượt pilot cũ vào cohort mới.

## 1. Vì sao phải đo nhiều lượt?

Một lượt có thể chậm do CPU, bộ nhớ đệm, hành trình mua hàng hoặc trạng thái ứng dụng lúc đó. Đo lặp giúp thấy kết quả có lặp lại và dao động bao nhiêu. Ví dụ p95 S4 cao hơn S0 một lần chưa đủ chứng minh tác động ổn định; cần nhìn cả các cặp khác.

Ba vòng là bước khởi đầu theo kế hoạch GĐ4, không phải bảo đảm đủ lực thống kê. 2.000 request trong cùng một lượt không thay thế 3 lượt riêng. Khi xây detector sau này, chia dữ liệu theo run, không chia ngẫu nhiên từng dòng của cùng một run.

## 2. Lịch thực hiện

| Nhóm | Số lượt | Cấu hình |
| --- | ---: | --- |
| S0 nghiệp vụ | 3 | Warm-up 400 giây, đo 900 giây, Locust gốc 10 user |
| S1 | 3 | 22 đích IP/cổng hiện có; timeout và giới hạn trong runner; không ép thời gian thành 120 giây nếu danh sách đã thực hiện xong |
| S2 | 3 | 30 lời gọi payment, khoảng cách 2 giây |
| S3 | 3 | 3 vòng shell/tool/token, tổng 18 thao tác, khoảng 90 giây |
| S4 | 3 | Tải phụ mục tiêu 10 RPS, concurrency 4, 90 giây |
| Đối chứng S4 | 3 | Cùng actor/Locust/cấu hình nền, không bật tải phụ, cửa sổ 90 giây |
| S5 | 3 | 60 upload dữ liệu giả 64 KiB, 1 upload/giây |
| Đối chứng S5 | 3 | Receiver có mặt, không upload, cửa sổ 60 giây |

Với S1–S5 và hai họ đối chứng: warm-up 400 giây, pre 120 giây, recovery 120 giây. Mỗi lượt còn có setup, xác minh và đóng gói nên tổng dự kiến khoảng **5–6 giờ**. Lịch không rút ngắn warm-up để chạy nhanh hơn.

Actor lần lượt ở w1, w2, w1 qua ba vòng; phân bố này chưa cân bằng. Locust gốc đã có nodeSelector w1; Locust tạm của S4/S5 cũng được đặt ở w1. Không có actor trong S0 nghiệp vụ. Các Pod ứng dụng và policy phải giữ cùng trạng thái trong suốt batch.

Seed lịch là 20261126. Thứ tự các nhóm được xáo trước bằng seed, giữ hai phần của một cặp gần nhau. Vòng 1 và 3 chạy control trước; vòng 2 chạy action trước. Thứ tự này được công bố trước khi chạy, không điều chỉnh theo kết quả. Seed Locust là 20261127/20261128/20261129 theo vòng, chỉ áp dụng với Locust có instrument của S4/S5. Seed không cố định hoàn toàn lịch chạy đồng thời của request.

S0/S1–S3 vẫn dùng Locust gốc và không có latency từng request như họ S4/S5. Các S0 dài dùng làm tham chiếu normal; không coi đó là cặp đo overhead hoàn toàn giống bộ instrument S4/S5. Chưa gộp các schema khác phiên bản thành một tập feature.

## 3. Bộ điều phối làm gì?

`repeat_batch.py` chạy từng case bằng runner hiện có, ghi `batch.json` theo cách thay file nguyên tử. File này có toàn bộ 24 case từ đầu: pending, running, completed hoặc failed/interrupted. Mỗi case giữ log riêng, run ID, thời điểm, return code và trạng thái dataset.

Trước và sau mỗi lượt, bộ điều phối kiểm tra source hash. Trong lượt, khoảng mỗi 15 giây kiểm tra node, Pod ứng dụng, Tetragon, policy và dung lượng. Nó dừng nếu node không Ready/có áp lực tài nguyên, Pod đổi UID/image/restart/readiness, policy hay cấu hình tải nền đổi, còn dưới 6 GiB trống, hoặc frontend health check lỗi 3 lần liên tiếp. Guard sẵn có của S4/S5 vẫn hoạt động.

Health check bổ sung được gửi từ control-plane tới frontend `/_healthz`, có nhật ký và áp dụng cho mọi case. Đây là traffic quan sát hợp lệ; phải tính đến nó khi diễn giải log. Một lỗi checkout nghiệp vụ riêng lẻ được lưu trong Locust/log ứng dụng, không tự xóa hoặc chạy thay lượt đó. Lỗi có thể do fixture mua hàng của demo; đọc log trước khi quy nguyên nhân cho attack.

**Không tự retry.** Khi một lượt lỗi, giữ dữ liệu đã thu, dừng các case còn lại, chạy cleanup của runner và ghi lý do. Đổi source hoặc sửa protocol để chạy tiếp phải tạo phiên bản/lịch mới. Không sửa protocol của batch đã bắt đầu.

## 4. Vì sao có file nén thay vì thư mục raw?

Batch dài có thể sinh nhiều GB log. Sau một lượt đã completed/validated, `repeat_support.py` đóng gói raw, source, normalized và labeled-windows vào `dataset.tar.gz`, rồi đọc lại **từng file trong archive để kiểm SHA256**. Chỉ khi khớp toàn bộ mới giải phóng các bản plain trùng nội dung.

`archive-integrity.json` giữ checksum của archive và từng thành viên. Đây là đổi cách lưu giữ bằng chứng, không bỏ log gốc. Nếu nén hoặc đối chiếu lỗi, bản plain được giữ. Không ghi đè archive có sẵn, không đóng gói lại các lượt lịch sử. Manifest, receipt, metric và report vẫn nằm ngoài archive để đọc nhanh.

Cuối batch, `repeat_review.py` giải nén vào thư mục tạm, kiểm hash, replay raw/normalized/nhãn, chạy verifier từng họ và kiểm 6 cặp đối chứng. `cohort-review.json` ghi kết quả. Mean của p95 từng run chỉ là trung bình các p95, không phải p95 gộp hay khoảng tin cậy nhân quả.

Một tiến trình đồng bộ hữu hạn trên máy Windows chờ đúng batch này kết thúc, tải và kiểm checksum, cập nhật Markdown rồi push GitHub/Pages. Mật khẩu SSH chỉ truyền qua stdin và giữ trong bộ nhớ, không ghi vào repo hay tham số tiến trình; host key được ghim theo phiên khởi chạy. Nếu máy Windows dừng hoặc repo đang có thay đổi chưa commit, phần xuất bản có thể chưa hoàn tất; dữ liệu batch vẫn ở VM. Tiến trình này không tự khởi chạy thí nghiệm khác, không lặp theo ngày và không gửi thông báo cho người khác.

## 5. Theo dõi trên lab-cp

Batch chạy bằng service systemd để đóng SSH vẫn tiếp tục. **Không chạy thêm loadgenerator hay runner khác trong lúc batch này đang hoạt động.**

```bash
cd ~/Testbed_Online_Boutique
sudo systemctl status boutique-repeats-20261126-v1 --no-pager
sudo journalctl -u boutique-repeats-20261126-v1 -n 30 --no-pager
```

`Starting:` là bắt đầu một case; `Completed:` là một case đã chạy, được runner xác nhận và nén kiểm hash xong. `Final status: completed` chỉ xuất hiện sau hậu kiểm cohort. `failed`/`interrupted` cần đọc lỗi, không tính các case pending là đã chạy.

Xem tiến độ chi tiết mà không thay đổi thí nghiệm:

```bash
sudo python3 - <<'PY'
from pathlib import Path
import json
batch = max(Path('runs').glob('batch-repeats-*'))
state = json.loads((batch/'batch.json').read_text())
print('Batch:', batch.name)
print('Trạng thái:', state['status'])
print('Case hiện tại:', state.get('current_case'))
print('Heartbeat UTC:', state.get('heartbeat'))
print('Hoàn tất:', sum(c['status']=='completed' for c in state['cases']), '/', len(state['cases']))
for case in state['cases']:
    print(case['case_id'], case['status'], case.get('run_id', ''))
PY
```

Heartbeat cũ không đủ kết luận đang chạy; kiểm thêm trạng thái systemd. VM tắt hoặc mất điện thì batch không tự chạy tiếp để tránh nhập nhầm một lượt bị cắt. Sau sự cố cần giữ dữ liệu và lập phương án tiếp nối có ghi nhận.

Nếu cần dừng có cleanup:

```bash
sudo systemctl stop boutique-repeats-20261126-v1
```

Lệnh stop có thể mất thời gian vì runner phải dừng tải, kết thúc collector và xóa tài nguyên tạm. Không dùng kill -9 như cách dừng thông thường.

## 6. Sau khi chạy xong

Đối chiếu đủ 18 lượt chính, 6 đối chứng, 6 cặp khớp cấu hình, source và checksum, các lượt lỗi và trạng thái lab cuối. Báo cáo giữ số request/lỗi/latency từng pha và từng run. Đọc cả application-diagnostics.json khi có HTTP lỗi.

Sau đó mới chốt danh sách run đủ điều kiện, hợp đồng feature và cách chia train/test cho GĐ5. Dataset chạy đủ lượt vẫn chưa đồng nghĩa detector đã đạt precision/recall hay policy đã chặn được hành vi; những đánh giá đó thuộc bước sau.

[Báo cáo pilot và đối chứng trước đó](S0-S5-REVIEW.md) · [Bản đồ schema](FEATURE-SCHEMA-MAP.md).
