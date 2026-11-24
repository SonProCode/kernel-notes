# Nghiệm thu lại S4 ngày 25/11/2026

**Kết luận: đường triển khai và dữ liệu pilot S4 đạt các tiêu chí đã kiểm tra. Chưa đủ điều kiện gọi là bộ dữ liệu chính thức hoặc bằng chứng đã gây DoS.** Lần kiểm tra này phát hiện và sửa thêm một khe hở trong verifier; không phát hiện log thật đã bị sai theo khe hở đó.

## 1. Đối chiếu đúng yêu cầu đề cương

Đề cương gốc mô tả S4: “Internal DoS nhẹ”, Pod gửi request tần suất cao tới một service đích; quan sát request rate, latency, CPU. GĐ4 tạo script tái lập và dữ liệu attack/normal có nhãn. Detector thuộc GĐ5, rate limit/deny thuộc GĐ6; hai phần đó chưa phải điều kiện chốt pilot GĐ4.

| Điều kiện | Bằng chứng hiện có | Kết luận |
| --- | --- | --- |
| Actor là Pod trong cluster, gọi đúng service | GET `/` tới frontend ClusterIP; topology, UID, source port và thời gian được lưu | Đạt pilot |
| Tải có thể tái lập và có giới hạn | 3/6/10 RPS, pacing, concurrency, timeout socket và deadline controller; ghi slot bỏ qua | Đạt pilot |
| Có traffic normal chạy cùng | Locust tạm 10 users, dùng hành trình gốc trong image; loadgenerator gốc=0 | Đạt pilot |
| Ghi mức tải thực và lỗi | Receipt từng request; phân biệt số gửi, bỏ qua và lỗi HTTP | Đạt pilot |
| Có latency của người mua | Log từng request Locust; p50/p95 và phân tích bổ sung p99 | Đạt mô tả pilot, chưa đủ mẫu ước lượng tail ổn định |
| Có CPU/RAM frontend | Bốn query CPU/RAM frontend và namespace boutique có mẫu hợp lệ | Đạt thu dữ liệu; cửa sổ CPU 60 giây làm trộn các pha pilot 30 giây |
| Có dữ liệu attack/normal có nhãn | Actor đối chiếu receipt độc lập; S0/pre/recovery có nhãn normal; sự kiện mơ hồ giữ unknown | Đạt pilot; smoke chủ động giữ actor ở unknown |
| Không suy diễn TCP thành HTTP | Native hook chứng minh hoạt động socket; HTTP status/path lấy từ receipt | Đạt phương pháp |
| Có kiểm tra dừng và dọn tài nguyên | Guard, heartbeat, kiểm thử SIGTERM; cleanup và snapshot sau chạy | Đạt đường kiểm thử đã thực hiện |
| Có nguồn mã và dữ liệu để double check | Source hash trong archive, replay normalized và nhãn cửa sổ, checksum bản xuất | Đạt |
| Có bộ chính thức 90 giây, lặp và đối chứng | Chưa có các lượt official S4 theo kế hoạch | **Chưa đủ** |
| Chứng minh suy giảm do tải hoặc hiệu quả chặn | Chưa đủ thiết kế thống kê; detector/mitigation chưa thuộc phần này | **Chưa kết luận** |

Cohort lịch sử v1 chưa có tuổi scrape và cleanup.json riêng từng run; chỉ có checkpoint của cả cohort. Giữ đúng giới hạn này, không bổ sung ngược bằng chứng bằng file của lượt mới. Các lượt mới contract v2 bắt buộc có đủ bằng chứng freshness và cleanup riêng.

## 2. Lỗi mới đã tìm được và sửa

Trên bản sao run `s4-20261123T050441Z-1864262`, chỉ sửa `socket.dport` của một event actor trong normalized thành 12345. Log raw và receipt vẫn giữ nguyên. Verifier ở commit `2bc783e` vẫn trả passed=true: nó kiểm raw có đúng receipt nhưng chưa so toàn bộ trường đặc trưng ở normalized với raw.

Bản sửa so thêm socket, node, namespace, Pod/workload, container ID/PID, binary, PID/exec ID, arguments, parent exec ID, kernel return và đường dẫn file của các event actor có operation_id. Trường HTTP method/status ghép từ receipt cũng phải khớp. Bản sao sai bị từ chối. Các event background và toàn bộ nhãn cửa sổ được đối chiếu thêm bằng cách dựng lại từ raw trong audit.

[Bằng chứng trước/sau](audits/s4-normalized-fields-reproduction-20261125.json) lưu hash verifier và kết quả. [49 kiểm thử](audits/s4-review-tests-20261125.json), gồm 5 subcase sửa socket/binary/container PID/namespace/HTTP status, kiểm tra bản sửa. Không ghi đè log lịch sử để làm cho chúng đạt.

## 3. Phân tích thêm request rate và p99

[Báo cáo nghiệm thu máy đọc được](audits/s4-acceptance-20261125.json) mở archive vào thư mục tạm, kiểm source, verifier, dựng lại từng bản ghi normalized và nhãn cửa sổ. Report kiểm checksum toàn bộ runs/ trước/sau để xác nhận không sửa bằng chứng. **12/12 lượt completed/validated được đọc lại đều đạt**, gồm 5 pilot/control và 7 smoke; 11 lượt nằm trong gate nghiệm thu chính, một smoke v1 ngắn được kiểm tra bổ sung riêng. Các lượt lỗi/interrupted được liệt kê với lý do loại trừ, không tính là dữ liệu attack hoàn tất.

Phân tích mới tách rõ:

- `started_rps`: số request bắt đầu trong pha chia thời lượng pha.
- `completed_rps`: số request hoàn tất trong pha chia thời lượng pha.
- Latency: chỉ các request HTTP 200 không có exception, bắt đầu và kết thúc trong cùng pha; lỗi và request vắt qua biên được đếm riêng.
- `p99_ms`: nearest-rank trên cùng tập latency. Nếu dưới 100 mẫu thành công, p99 chính là giá trị lớn nhất trong mẫu này; không coi đó là ước lượng tail ổn định của hệ thống.

Ví dụ cohort đã công bố:

| Profile | Mẫu Locust trong pha đo | Locust completed RPS | p99 mẫu (ms) |
| --- | --- | --- | --- |
| S0 control | 64 | 2,13 | 250,72 |
| S4 3 RPS / w1 | 62 | 1,97 | 181,18 |
| S4 6 RPS / w1 | 66 | 2,11 | 289,77 |
| S4 10 RPS / w1 | 66 | 2,06 | 780,84 |
| S4 10 RPS / w2 | 63 | 2,00 | 397,11 |

Đây là RPS của người mua Locust, tách khỏi RPS tải phụ. Thời lượng pha dùng timeline thực, có thể dài hơn cửa sổ gửi của client vì khởi động exec và đợi request cuối. Không dùng p99 của các pha ít mẫu này làm ngưỡng cảnh báo chính thức. Bảng p95 và 861 request tải phụ ở [kết quả pilot](S4-RESULTS.md) vẫn giữ nguyên.

CPU frontend và CPU namespace cũng có ý nghĩa khác nhau: namespace boutique gồm cả actor và Locust tạm. Muốn đánh giá chi phí xử lý của service, ưu tiên series frontend. Query `rate(...[1m])` làm mượt theo một phút; `step=5` chỉ là bước đánh giá query, không biến nó thành CPU đo độc lập mỗi 5 giây. Xem [Prometheus querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/).

## 4. Còn thiếu gì trước khi nghiệm thu chính thức?

1. Chốt một profile cuối, giữ source/image/topology và cấu hình telemetry nhất quán. Theo kế hoạch repo, chạy **ít nhất 3 lượt official S4, pha tải 90 giây**, placement w1, w2, w1; thêm lượt nếu cần cân bằng so sánh hai worker.
2. Thu S0 đối chứng bằng cùng instrumentation cuối, xen kẽ với S4. Ghi thứ tự chạy hoặc seed; seed nếu có cũng không tự loại bỏ mọi biến động của mạng và lịch CPU.
3. Giữ warm-up đủ ổn định, pre/recovery đủ dài; tách ít nhất phần đầu 60 giây của pha tải khi diễn giải CPU cửa sổ 1 phút. Lưu cả mẫu chuyển tiếp; không xóa dữ liệu bất lợi. Chốt trước cách tính steady state, RPS, latency, lỗi và điều kiện hồi phục.
4. Báo số mẫu, lỗi, p50/p95/p99 và độ biến động giữa các lượt. Chỉ kết luận có suy giảm nếu bằng chứng lặp lại hỗ trợ; tải nhẹ vẫn ổn định là kết quả hợp lệ.
5. Kiểm đủ receipt ↔ raw ↔ normalized, freshness, loss counter, guard và cleanup cho từng lượt mới. Tách failed/interrupted/smoke khỏi tập official; không trộn source v1/v2 để tính như cùng một cohort.

Phần này là điều kiện cho tập chính thức và đánh giá định lượng. Có thể tiếp tục pilot S5 trước, rồi khóa cấu hình để thu bộ official S0–S5. Không cần ép lab sập để gọi pilot S4 là hoàn thành.

## 5. Tự kiểm tra lại từ đâu?

Trên lab-cp, hoặc máy có Python và bản clone đầy đủ, vào thư mục có `experiments/`:

```bash
cd ~/Testbed_Online_Boutique
python3 -m unittest discover -s experiments -p 'test_s4*.py' -v
python3 experiments/s4/review.py --output experiments/audits/my-s4-acceptance.json
```

Lệnh review không chạy tải và không thay dữ liệu trong runs/. Đọc `passed` cùng từng run và `official_dataset_ready`; một bộ pilot đạt không tự trở thành bộ dữ liệu chính thức.

## 6. Hồi quy và trạng thái lab

Đã chạy và tải về hai lượt mới, không dùng lại số liệu cũ để gọi là hồi quy mới:

| Run | Kết quả |
| --- | --- |
| [s0-s4-control-20261124T180521Z-596177](../runs/s0-s4-control-20261124T180521Z-596177/manifest.json) | Control smoke hoàn tất, validated |
| [s4-20261124T180653Z-599521](../runs/s4-20261124T180653Z-599521/manifest.json) | S4 smoke trên w2, 3 RPS × 12 giây, 36/36 request khớp raw; validated |

[Snapshot sau hồi quy](audits/s4-final-state-20261125.json) xác nhận source vận hành trên lab khớp cả hai manifest, ba node Ready, không MemoryPressure, ứng dụng available, loadgenerator gốc=0 và không còn Pod/Deployment/ConfigMap/ServiceAccount thí nghiệm. Các run mới vẫn là smoke, không đổi thành official hoặc cộng vào 861 request pilot cũ.

 Snapshot trước thử: [trạng thái trực tiếp ngày 25/11](audits/s4-live-state-20261125.json), ba node Ready, không MemoryPressure, các deployment đạt số replica mong đợi và không có tài nguyên thí nghiệm thừa. Timestamp trong file là UTC; ngày 24/11 lúc 18 giờ UTC tương ứng ngày 25/11 lúc 01 giờ Việt Nam.
