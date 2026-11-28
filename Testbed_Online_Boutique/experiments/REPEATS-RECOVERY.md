# Hậu kiểm batch lỗi và cách tái hiện đo lặp

Cập nhật 28/11/2026 theo ngày của phiên làm việc. Tên run và thời gian sự kiện bên dưới giữ nguyên UTC do VM ghi, không đổi thành ngày cập nhật tài liệu.

## 1. Batch vừa rồi có thành công không?

**Chưa hoàn thành toàn bộ kế hoạch.** Batch `batch-repeats-20261125T181112Z-2519845` dừng với trạng thái failed: 5 case completed, 1 case failed và 18 case chưa chạy. Nó không phải bộ dữ liệu đủ ba lần lặp S0–S5.

| Case theo lịch | Điều thực sự xảy ra |
| --- | --- |
| r1-s1-action | Hoàn tất và được runner xác nhận validated |
| r1-s4-control | Hoàn tất đối chứng không bật tải phụ |
| r1-s4-action | Hoàn tất S4 10 RPS, cửa sổ mục tiêu 90 giây |
| r1-s2-action | Hoàn tất 30 lời gọi payment |
| r1-s0-action | Hoàn tất S0 đo 900 giây |
| r1-s5-control | Đã đi hết setup/warm-up/pre/measurement/recovery/finalize và cleanup, nhưng bị dừng khi đang kiểm chứng dữ liệu |
| Các case còn lại | Chưa thực hiện, không có run để tính là kết quả |

`status=completed` trong manifest của lượt S5 control chỉ nói runner đã đi hết phần thu. Nó chưa có `dataset_status=validated`, nên batch không được cộng lượt đó là thành công. Đây là lý do cần đọc cả trạng thái lượt, trạng thái kiểm chứng và trạng thái batch.

[Hậu kiểm độc lập ngày 28/11](audits/repeats-partial-review-20261128.json) xác nhận 5/5 case completed đạt replay/checksum/bằng chứng và `original_evidence_unchanged=true`. Hậu kiểm S5 control bằng verifier mới cũng đạt, nhưng case lịch sử vẫn giữ trạng thái không được batch chấp nhận; không cộng nó thành lượt thứ sáu.

[Batch gốc](../runs/batch-repeats-20261125T181112Z-2519845/batch.json) và [log S5 control](../runs/batch-repeats-20261125T181112Z-2519845/r1-s5-control.log) được giữ nguyên. Các archive và manifest đã xuất bản không bị ghi đè.

## 2. Vì sao dừng?

Bộ theo dõi gọi `k3s kubectl get nodes -o json`, chờ tối đa 12 giây. Một lần đọc quá thời hạn làm bộ điều phối dừng case và gửi SIGTERM tới runner. Traceback cho thấy lúc nhận SIGTERM, verifier S5 đang giải mã toàn bộ raw vào các đối tượng Python trong RAM.

Raw của case này khoảng 280 MiB, bản normalized khoảng 124 MiB. Một file JSON 280 MiB có thể dùng nhiều RAM hơn khi biến thành hàng trăm nghìn dict/list/string Python. Control-plane chỉ có 4 GB RAM, còn phải chạy K3s và các tiến trình khác.

Đây là **yếu tố có khả năng góp phần**, chưa phải chứng minh nguyên nhân duy nhất. Journal K3s cùng khoảng thời gian có heartbeat miss và HTTP handler timeout. Truy vấn kernel journal không trả về bản ghi trong khoảng được tìm; không được suy ra rằng chắc chắn có OOM hoặc chắc chắn không có OOM. Snapshot cuối vẫn ghi 3 node Ready, không MemoryPressure, loadgenerator=0 và không còn tài nguyên thí nghiệm.

[Chẩn đoán và journal](audits/repeats-diagnostic-20261128.json) giữ bằng chứng này. [Kiểm lại trên VM với verifier đọc theo dòng](audits/repeats-stream-check-20261128.json) đạt, mất khoảng 191 giây gồm sao chép và kiểm chứng, RSS cực đại khoảng 1,42 GiB. Đây là footprint đo được của lần hậu kiểm mới; không phải số RAM tiết kiệm so với bản cũ vì chưa có phép đo RSS tương ứng của bản cũ.

## 3. Sửa những gì ở bản tiếp nối?

1. Verifier S5 giữ chỉ mục vị trí byte của từng dòng raw, chỉ giải mã dòng cần đối chiếu và duyệt tuần tự khi phải kiểm tra toàn bộ. Không giữ tất cả raw JSON trong RAM. Không bỏ dòng lỗi, không giảm yêu cầu đối chiếu socket/PID/time/receipt hay replay nhãn.
2. Bộ theo dõi cho phép đọc lại **một lần** nếu một lệnh snapshot bị timeout. Lần timeout được ghi vào `read_timeouts`; nếu cả hai lần đều không đọc được thì dừng. Một phản hồi thực sự báo node/Pod không khỏe vẫn dừng như trước, không được dùng dữ liệu cache thay thế.
3. Việc tiếp nối dùng protocol mới. Chỉ kế thừa case completed/validated đã qua hậu kiểm độc lập, có checksum nguyên vẹn và source runtime khớp. Đồng thời trạng thái ứng dụng, agent, policy và cấu hình tải nền phải khớp checkpoint trước.
4. Case S5 control bị dừng không được kế thừa. Nó được chạy lại với run ID mới; bản lỗi cũ vẫn tồn tại. Không sửa lịch v1 hoặc đổi trạng thái lịch sử thành thành công.

Đây là tiếp nối của mục tiêu 24 case: **5 case đã xác nhận + 19 case cần thực hiện**, không phải tuyên bố đã chạy thêm 24 case. Có khoảng gián đoạn và thay đổi bộ quan sát/verifier; báo cáo phải giữ nguồn batch để người phân tích biết điều đó.

[Protocol v2](repeat-protocol-v2.json) giữ nguyên danh sách/tham số các case và ghi checksum của audit làm điều kiện kế thừa. Protocol v1 vẫn giữ nguyên để kiểm toán.

[132/132 test đạt, không skip](audits/repeats-recovery-tests-20261128.json), với [log đầy đủ](audits/repeats-recovery-tests-20261128.log). Có kiểm tra đọc Unicode đúng byte offset, không bỏ JSON lỗi, mức RAM của chỉ mục, timeout lần hai phải dừng, checksum audit/source thay đổi phải bị từ chối và so sánh đúng trạng thái sau vòng lưu/đọc JSON. 11 test mới cũng đã chạy đạt trên VM.

Fixture regression S0 được cố định vào mẫu 120 giây đã công bố, thay vì tự chọn run mới nhất trong thư mục. Dữ liệu S0 chính thức 900 giây vẫn được hậu kiểm riêng và giữ nguyên lỗi checkout, không bị thay bằng fixture ngắn.

Bản v2 đã bắt đầu lúc 03:52:24 UTC ngày 28/11, tức 10:52:24 giờ Việt Nam. [Checkpoint khởi chạy](audits/repeats-recovery-launch-20261128.json) ghi service active, 5 case kế thừa và 19 case dự kiến chạy. Ở checkpoint đầu chưa có case mới hoàn tất.

Một ví dụ từ phần đã đo: S1 đủ 22 receipt, S2 đủ 30 receipt; S4 thực gửi 893 request tải phụ. Cặp S4–control khớp cấu hình theo [report so sánh](audits/repeats-s4-pair-20261128.json); p95 Locust ở pha tương ứng khoảng 92,42 ms với control và 377,69 ms với S4. Đây chỉ là một cặp, chưa phải tác động trung bình qua ba lần lặp.

S0 mới đo 900,001 giây. Bảng Locust tích lũy cuối gồm 142 checkout và 1 lỗi, có cả warm-up. Lỗi được giữ trong bằng chứng; không ghi rằng normal phải có 0 lỗi hoặc đã có 142 checkout riêng của cửa sổ đo.

## 4. Một lượt thực nghiệm diễn ra thế nào?

Hãy xem một lượt S4 như một buổi đo riêng:

1. **Setup:** tạo actor và Locust tạm, chụp cấu hình, bắt đầu thu log hai worker.
2. **Warm-up 400 giây:** cho 10 người mua ảo hoạt động để ứng dụng qua giai đoạn khởi động.
3. **Pre 120 giây:** chỉ giữ traffic nền để có khoảng trước hành vi mô phỏng.
4. **Action 90 giây:** thêm tải S4 mục tiêu 10 request/giây; ghi cả request tải phụ và request mua hàng.
5. **Recovery 120 giây:** tắt tải phụ nhưng tiếp tục quan sát người mua và ứng dụng.
6. **Finalize và kiểm chứng:** dừng collector, lưu metric/receipt, đối chiếu raw với nhãn và dọn tài nguyên.
7. **Đóng gói:** nén raw/source/normalized, kiểm SHA256 từng thành viên rồi mới giải phóng bản plain trùng nội dung.

Lượt đối chứng S4 giữ actor/Locust/cấu hình nền và cửa sổ 90 giây nhưng không bật client tải phụ. S5 tương tự, chỉ khác là 60 lần upload payload giả 64 KiB; đối chứng S5 vẫn có receiver nhưng gửi 0 upload. S0 nghiệp vụ đo normal 900 giây sau warm-up.

Ba vòng đặt actor lần lượt w1, w2, w1; lịch và seed lưu trước. Không phải mở ba terminal cho ba vòng cùng lúc: batch chạy **tuần tự** để các kịch bản không làm nhiễu nhau. Phân bố node còn lệch và ba lượt chưa bảo đảm đủ lực thống kê.

## 5. Tự kiểm tra kết quả mà không sinh tải mới

Trên Windows mở SSH, sau đó chuyển tới thư mục lab trên control-plane:

```bash
ssh sonth32@192.168.141.142
cd ~/Testbed_Online_Boutique
pwd
```

Trong phiên SSH, chạy hậu kiểm phần đã hoàn tất:

```bash
sudo python3 experiments/review_partial_repeats.py \
  runs/batch-repeats-20261125T181112Z-2519845 \
  --output experiments/audits/my-partial-review.json
```

Lệnh này kiểm checksum, giải nén vào thư mục tạm và replay bằng chứng. Nó không chạy attack hoặc sửa các run lịch sử. Tuy vậy, phân tích file lớn vẫn tốn CPU/RAM: chạy ngoài thời gian đo hoặc trên máy phân tích đủ RAM để tránh tự gây nhiễu control-plane.

Trong report đọc `completed_cases_reviewed`, `completed_cases_passed`, `original_evidence_unchanged` và từng `cases`. Một case lỗi có thể có `posthoc_verification.passed=true` sau này; điều đó chỉ chứng minh bằng chứng được kiểm lại, không tự đổi lịch sử batch thành completed.

## 6. Theo dõi bản tiếp nối trên chính lab này

```bash
sudo systemctl status boutique-repeats-20261128-v2 --no-pager
sudo journalctl -u boutique-repeats-20261128-v2 -n 30 --no-pager
```

Nếu service đang active, chỉ theo dõi, không khởi chạy thêm runner/loadgenerator. Đọc `batch.json` của batch mới để phân biệt `carried_forward_cases=5` với số lượt mới thực sự hoàn tất. `source_batch` ở mỗi case kế thừa trỏ về batch cũ.

Bản v1 thất bại vẫn có thể hiện `systemctl ... failed`; đó là lịch sử đúng. Bản v2 dùng unit khác để không che mất lần thất bại trước.

## 7. Tái hiện một batch mới từ đầu

Phần này dành cho lần thực nghiệm khác, khi không có batch đang chạy. Không dùng nó để khởi chạy trùng bản tiếp nối hiện tại.

Trước hết kiểm tra cụm đang có Boutique và Tetragon đúng cấu hình:

```bash
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl -n boutique get deployments
sudo k3s kubectl -n telemetry get pods -o wide
sudo k3s kubectl -n boutique get pods -l experiment-run
df -h .
```

Cần 3 node Ready, ứng dụng đủ replica, hai agent khỏe, loadgenerator=0, không còn Pod thí nghiệm và đủ dung lượng theo protocol. Bộ điều phối còn tự kiểm lại các điều kiện này.

Từ source đã cập nhật của bản v2, tạo protocol mới **không kế thừa** các run cũ:

```bash
python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import json
source = Path('experiments/repeat-protocol-v2.json')
target = Path('experiments/repeat-protocol-v3.json')
if target.exists():
    raise SystemExit('Tên protocol đã tồn tại; chọn phiên bản mới, không ghi đè')
plan = json.loads(source.read_text())
plan.pop('carry_forward', None)
plan['protocol_id'] = 'gd4-fresh-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
plan['repository_protocol'] = target.name
plan['scope'] = 'Fresh 24-case acquisition; no inherited runs'
target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
print(target)
PY
```

Xóa `carry_forward` nghĩa là cả 24 case đều chạy mới. Source hash được giữ từ bản đã chốt; nếu code khác hash, dừng để rà soát/version lại, không tắt kiểm tra.

Khởi chạy bằng systemd để đóng SSH vẫn tiếp tục:

```bash
sudo systemd-run --unit=boutique-repeats-v3 \
  --property=WorkingDirectory="$PWD" \
  --property=Restart=no --property=KillMode=mixed \
  --property=TimeoutStopSec=180 --property=RuntimeMaxSec=8h \
  --setenv=PYTHONUNBUFFERED=1 \
  /usr/bin/python3 experiments/repeat_batch.py \
  --protocol experiments/repeat-protocol-v3.json
```

Nếu unit hoặc protocol v3 đã tồn tại, dùng tên phiên bản mới cho cả hai; không khởi động lại một unit cũ để che lần lỗi. Bộ điều phối cũng dùng khóa để ngăn hai batch chạy đồng thời.

Theo dõi và dừng có cleanup:

```bash
sudo journalctl -u boutique-repeats-v3 -f
sudo systemctl stop boutique-repeats-v3
```

`Ctrl+C` khi xem journal chỉ thoát màn hình xem log; lệnh `systemctl stop` mới yêu cầu dừng batch. Không dùng kill -9 như thao tác dừng thông thường.

## 8. Khi nào được kết luận tái hiện thành công?

Cần đủ case theo protocol, verifier đạt, các cặp đối chứng khớp, archive nguyên vẹn và cleanup cuối đạt. Xem `cohort-review.json`, không chỉ đếm thư mục hoặc nhìn 1 request HTTP thành công. Giữ và giải thích lỗi ứng dụng, các khoảng observer không đọc được trạng thái, nhãn unknown và mọi lần gián đoạn.

Ngay cả khi đủ ba lượt mỗi S, đây vẫn là xác nhận đường mô phỏng và dữ liệu; precision/recall của detector, hiệu quả policy và khoảng tin cậy hiệu năng cần đánh giá riêng ở các bước sau.
