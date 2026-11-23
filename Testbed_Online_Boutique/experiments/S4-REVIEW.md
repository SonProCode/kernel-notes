# Rà soát sâu S4 ngày 23/11/2026

Kết luận: số liệu của cohort pilot đã công bố vẫn qua hậu kiểm chặt hơn. Lần rà soát này tìm được các trường hợp verifier hoặc công cụ kiểm thử có thể xử lý sai; đã sửa và bổ sung kiểm thử âm tính. Phạm vi kết luận là chất lượng đường thực hiện và bằng chứng pilot GĐ4.

## 1. Ba trường hợp báo đạt sai đã tái hiện

Trên bản sao của run `s4-20261123T050441Z-1864262`, dùng đúng verifier tại commit d6e5684 rồi thử lại bằng verifier mới:

| Dữ liệu cố ý làm hỏng | Verifier cũ | Verifier mới |
| --- | --- | --- |
| Tất cả mẫu CPU/RAM thành NaN | passed=true | Từ chối giá trị không hữu hạn và thiếu mẫu hợp lệ theo pha |
| Guard chỉ còn một dòng | passed=true | Từ chối thiếu coverage các pha và heartbeat |
| Latency âm, cả raw/derived cùng ghi sai | passed=true | Từ chối latency âm |

[Report tái hiện trước/sau](audits/s4-false-pass-reproduction-20261123.json) lưu commit/hash và lỗi xác minh. Đây là dữ liệu giả lỗi trong thư mục tạm; không phải số liệu pilot thật bị phát hiện có NaN hay latency âm. Raw, receipt và manifest của các run lịch sử được giữ nguyên.

## 2. Các điều kiện kiểm tra đã bổ sung

- Locust derived phải bằng các dòng S4REQ/S4META/S4FINAL trong log nguyên gốc; sequence và cả counter request/failure phải nhất quán.
- Latency phải hữu hạn, không âm, phù hợp khoảng thời gian; HTTP status, số byte và các bộ đếm phải có giá trị hợp lệ.
- Từng request actor phải đúng GET `/`, frontend trong topology snapshot, source port, khoảng attack và operation_id trong lịch gửi.
- Counter submitted/skipped không âm; cấu hình client phải khớp manifest, concurrency và thời lượng nằm trong profile.
- Timeline có đủ pha, đúng thứ tự và mốc measurement_end.
- Guard có mẫu trong warm-up, pre, attack/measurement và recovery; heartbeat không gián đoạn quá 35 giây, timestamp và trạng thái Pod nhất quán.
- Bốn resource series phải có mẫu hữu hạn, không âm, có dữ liệu ở các pha chính; không chỉ kiểm tra response chứa một mảng values.
- Agent up phải đúng hai worker; loss/export phải đúng bốn loại counter trên từng worker, giá trị hợp lệ và delta bằng 0.
- Native reference không trùng/mất, mở lại đúng dòng raw; kiểm UID, namespace PID, loại hook, socket, thời gian, phase và nhãn.
- Kiểm lại các số đếm quality; audit dựng lại normalized từ raw trong thư mục tạm và so toàn bộ bản ghi với bản đã công bố.

Prometheus có quy tắc lookback/staleness; một instant query trả up=1 chưa tự chứng minh sample mới vừa được scrape. Bản thu mới bổ sung query tuổi sample ở hai snapshot và yêu cầu không quá 60 giây. [Prometheus querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/).

## 3. Guard và cleanup của bản chạy mới

Controller kiểm tra cả trạng thái luồng guard và heartbeat. Nếu guard chết luồng, lỗi ghi file hoặc heartbeat quá hạn, controller dừng lượt thay vì tiếp tục tải không có giám sát. Unit tests mô phỏng các lỗi này; không gây OOM thật trên VM để thử.

Trong cleanup, yêu cầu dừng guard được đặt ngay, rồi xóa actor và Locust tạm trước khi chờ guard kết thúc. Các run mới lưu cleanup.json, kiểm lại tài nguyên theo experiment-run và spec loadgenerator gốc. Nếu cleanup không xác nhận được, dataset không được đánh dấu validated.

Thêm một lỗi đã phát hiện ở check_cleanup.py: glob s4-* có thể chọn file transcript s4-strict-regression-*.log thay cho thư mục run. Bộ chọn mới yêu cầu thư mục có manifest và đúng PID của child runner. Có test cho logfile giả và runner khác PID; phép thử dừng còn đợi thấy receipt thực trước khi gửi SIGTERM.

## 4. Lỗi chốt log Locust và lượt kiểm thử thất bại

Lượt `s4-20261123T094419Z-2238057` được giữ ở `dataset_status=failed_validation`. Ngoài lỗi selector, recovery 5 giây không có mẫu guard. Log còn cho thấy S4FINAL chốt ở 279 request nhưng một callback request thứ 280 tới sau đó; có một lỗi checkout HTTP 500 thật, vẫn được giữ trong dữ liệu. Không cộng lượt này vào cohort hiệu năng. [Postmortem](../runs/s4-20261123T094419Z-2238057/postmortem.json) ghi rõ các nguyên nhân.

Theo [mã nguồn Locust 2.43.0](https://github.com/locustio/locust/blob/2.43.0/locust/main.py#L566-L603), `quitting` xảy ra trước `runner.quit()`, còn `quit` xảy ra sau khi dừng runner. Wrapper mới chỉ giữ environment ở quitting và chốt S4FINAL ở quit. Verifier từ chối request xuất hiện sau S4FINAL kể cả counter bị sửa cho khớp; test mô phỏng callback đến muộn xác nhận thứ tự này.

## 5. Bằng chứng và phiên bản

- [Bộ test mở rộng](audits/s4-review-tests-20261123.json) và [log test](audits/s4-review-tests-20261123.log).
- [Hậu kiểm cohort cũ](audits/s4-strict-review-20261123.json): năm pilot/control vẫn đạt; tái dựng normalized từ raw và kiểm source snapshot trong archive.
- Kết quả 861 request tải phụ và biểu đồ của cohort cũ không bị thay bằng các lượt regression mới.
- Các run cũ dùng verification contract v1. Chúng chưa ghi tuổi scrape và cleanup.json theo từng run; report giữ giới hạn đó và dùng checkpoint cleanup đã công bố cho cohort cũ.
- Bản chạy mới ghi verification_contract=2. Hai loại dữ liệu được phân biệt bằng manifest và source hash; không trộn smoke 12 giây với pilot 30 giây để tính hiệu năng.

### Hồi quy trực tiếp trên lab bằng source cuối cùng

| Lượt | Kết quả | Vai trò |
| --- | --- | --- |
| s0-s4-control-20261123T095509Z-2255902 | completed, validated | S0 control cùng instrumentation mới |
| s4-20261123T095629Z-2258990 | completed, validated; 36/36 request tải phụ khớp native | S4 3 RPS, 12 giây, worker w2 |
| s4-20261123T095751Z-2262231 | interrupted; cleanup đạt sau 10 request thực | Gửi SIGTERM khi đang có tải |

Hai lượt hoàn tất có cùng bundle mã cuối và đều qua kiểm tra input/native, freshness và cleanup. [Snapshot sau kiểm thử](audits/s4-final-review-state-20261123.json) xác nhận source trên lab khớp hai lượt này, 3 node Ready, frontend/checkout/payment available, loadgenerator gốc=0 và không còn tài nguyên thí nghiệm. Các run, timeline, raw Locust, receipt, cleanup.json và archive được lưu dưới runs/ theo tên trong bảng.

[Bộ test cuối](audits/s4-review-tests-20261123.json): **45/45 đạt, 0 lỗi, 0 bỏ qua**. Hậu kiểm cohort cũ đạt 5/5 và replay normalized từ raw trùng toàn bộ bản ghi. Các lượt hồi quy trước khi sửa thứ tự callback cũng được giữ, nhưng không dùng làm bằng chứng source cuối hoặc cộng vào kết quả hiệu năng.

## 6. Chạy lại kiểm tra

Từ thư mục Testbed_Online_Boutique, nơi có experiments/:

```bash
python3 -m unittest discover -s experiments -p 'test_s4*.py' -v
python3 experiments/s4/audit.py --output experiments/audits/my-s4-strict-review.json
```

Các test integrity dùng archive pilot đã đi kèm repo, giải nén vào thư mục tạm và cố ý sửa bản sao. Đọc số test skipped nếu bạn chỉ sao chép script mà chưa tải dataset. Audit cũng dùng thư mục tạm, không ghi lại nhãn lịch sử.

Smoke của bản kiểm tra mới cần các pha đủ dài để có mẫu guard/resource. Lệnh mẫu:

```bash
sudo python3 experiments/runner.py --scenario S4 --mode smoke --node w2 --s4-rate 3 --s4-duration 12 --s4-concurrency 2 --warmup 12 --pre 12 --recovery 12
```

## 7. Đối chiếu đề cương và giới hạn kết luận

Đã đọc lại đề cương gốc: S4 là Pod gửi request tần suất cao tới service, quan sát request rate, latency và CPU. Đường chạy hiện có actor nội bộ, log từng request, Locust normal, metric CPU/RAM và telemetry có nhãn theo receipt độc lập. GĐ4 yêu cầu cả S1–S5 và dữ liệu attack/normal; hoàn tất pilot S4 chưa đồng nghĩa hoàn tất GĐ4. Rate limit/deny và detector được để đúng các giai đoạn GĐ6/GĐ5 trong đề cương.

Passed xác nhận tính nhất quán và điều kiện thu dữ liệu đã định nghĩa; dataset vẫn có thể chứa lỗi HTTP thật do tải, và lỗi đó phải được giữ để phân tích. Passed không có nghĩa ứng dụng chịu được mọi mức tải hay detector đã đạt recall/precision cao.

Cohort hiện chưa khóa seed Locust và chưa có đủ lượt lặp độc lập để suy luận thống kê. CPU rate dùng cửa sổ một phút, còn pha pilot là 30 giây. Bộ official, detector và mitigation vẫn nghiệm thu theo kế hoạch GĐ4/GĐ5/GĐ6.
