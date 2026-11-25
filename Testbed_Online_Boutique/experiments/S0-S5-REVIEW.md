# Rà soát S0–S5 và bổ sung đối chứng pilot

Cập nhật ngày 25/11/2026. **Đã kiểm tra lại 16 pilot chức năng S1–S5 và chạy xong batch bổ sung 6 lượt.** Đường mô phỏng, thu log và đối chiếu bằng chứng đã được xác nhận ở mức pilot. Bộ dữ liệu chính thức vẫn cần lịch chạy, các lần lặp độc lập và hợp đồng feature chung.

## 1. Đối chứng nghĩa là gì?

Giả sử lúc chạy S4, p95 của trang web tăng. Chỉ nhìn một lượt S4 chưa biết phần tăng đến từ tải phụ, thay đổi vị trí Pod hay dao động của ứng dụng. Ta cần một lượt tương tự nhưng không bật hành vi mô phỏng, gọi là **đối chứng S0**.

Ví dụ cặp S5: cả hai lượt đều có 10 người mua Locust, actor trên w1 và receiver lắng nghe ở control-plane. Lượt S0 không upload; lượt S5 gửi payload giả. Như vậy, chi phí tạo actor và receiver cùng có ở hai bên. Nếu S0 không có receiver thì so sánh sẽ lẫn thêm khác biệt đó.

Một cặp giống cấu hình vẫn có thể khác thứ tự request, thời gian xử lý và độ trễ. Vì vậy cặp ngắn này kiểm tra được cách tổ chức thí nghiệm; chưa đủ để kết luận định lượng về tác động hay hiệu quả phát hiện.

## 2. Tổng kiểm tra các kịch bản đã có

| Phần | Pilot chức năng đạt | Nội dung kiểm tra | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| S0 GĐ3 | 1 lượt 60 giây, 1 lượt 900 giây đạt kiểm tra capture ban đầu | Replay raw, lượng sự kiện, hai agent | Schema và bộ quan sát cũ; chỉ làm tham chiếu lịch sử |
| S1 | 5/5 | 22 lần thử TCP mỗi lượt, receipt và native event | Hai lượt đầu thiếu source snapshot và metric mất log; không coi là cùng mức provenance với lượt mới |
| S2 | 3/3 | Lời gọi gRPC payment trái luồng, client/server và native TCP | Chứng minh đường gọi trong lab, chưa đánh giá detector hay policy chặn |
| S3 | 2/2 | Shell, curl/wget/nc/nmap, đọc projected token; 18 thao tác mỗi lượt | Actor là Pod tạm; không tuyên bố đã khai thác lỗ hổng ứng dụng |
| S4 | 4/4 | 861 HTTP request tải phụ có bằng chứng kernel, Locust và hồi phục | Cohort cũ không khóa seed; đối chứng w1 không thay cho w2 |
| S5 | 2/2 | 120 upload, 7.864.320 byte payload giả; client–receiver–kernel khớp | Receiver trong lab, ngoài mạng Pod; chưa đại diện mọi hình thức exfiltration |

**16 là tổng pilot S1–S5: 5 + 3 + 2 + 4 + 2.** Không cộng smoke, interrupted, failed_validation hoặc lượt bổ sung ở mục tiếp theo vào cohort này.

Baseline `s0-tetragon-20261116T172527Z-2155454` chỉ có 3 sự kiện và capture không đạt: **loại khỏi tập baseline dùng phân tích**. Baseline 17/11 có 141.642 sự kiện vẫn giữ làm tham chiếu lịch sử, không tự biến thành đối chứng cùng source/policy của mọi S1–S5.

Báo cáo máy đọc được, được chạy lại bằng verifier hiện tại:

- [S1–S3](audits/s0-s5-final-s1-s3-20261125.json).
- [S4, gồm các smoke hồi quy](audits/s0-s5-final-s4-20261125.json).
- [S5, gồm các smoke hồi quy](audits/s0-s5-final-s5-20261125.json).
- [Batch đối chứng và replay S0 lịch sử](audits/s0-s5-controls-20261125.json).
- [Kiểm chứng lại trực tiếp trên VM](audits/s0-s5-live-controls-20261125.json): sáu case và hai cặp cùng đạt như bản xuất về Windows.

## 3. Sáu lượt bổ sung thực sự đã chạy

Batch [batch-controls-20261125T113929Z-1995885](../runs/batch-controls-20261125T113929Z-1995885/batch.json) đã hoàn tất cả sáu case. [Protocol](controls-protocol.json) ghi trước thứ tự, tham số và hash source. Coordinator kiểm tra lại source trước mỗi case và dừng nếu source đổi hoặc một case lỗi; không tự bỏ lượt lỗi để chọn kết quả đẹp.

| Case | Run ID | Mục đích |
| --- | --- | --- |
| S0 nghiệp vụ | `s0-20261125T113929Z-1995886` | 10 user, warm-up 30 giây, đo 120 giây; tham chiếu normal định tính cho S1–S3 |
| S0 đối chứng S4 | `s0-s4-control-20261125T114222Z-2000363` | Actor w2, Locust w1, không gửi tải phụ |
| S4 so sánh | `s4-20261125T114457Z-2005619` | Cùng cấu hình nền, tải phụ 10 RPS, concurrency 4 trong 30 giây |
| S0 đối chứng S5 | `s0-s5-control-20261125T114740Z-2011018` | Actor w1, Locust w1, receiver có mặt nhưng không upload trong 30 giây |
| S5 so sánh | `s5-20261125T115035Z-2016678` | 30 upload, mỗi payload 64 KiB, cùng cấu hình nền |
| Quản trị hợp lệ | `s0-s5-control-20261125T115338Z-2022595` | Shell chạy Python GET frontend `/_healthz`, nhận HTTP 200, không upload |

Lượt S0 nghiệp vụ dùng `mode=pilot`. Năm lượt còn lại dùng `mode=smoke` để kiểm tra đối chứng ở mức chức năng. Trong smoke S4/S5, sự kiện của hành vi mô phỏng vẫn có thể mang nhãn `unknown`; **không tự đổi chúng thành attack rồi nhập vào tập huấn luyện**. Cần dùng run chính thức/pilot theo hợp đồng nhãn tương ứng khi xây bộ attack có nhãn.

Lượt thử chẩn đoán trước batch `s0-s5-control-20261125T113439Z-1988110` được giữ riêng. Nó không phải case thứ bảy và không thay thế case đã khai báo trước.

### S0 nghiệp vụ cho thấy điều gì?

Đo được **19.079 sự kiện normal** trong 120 giây, có cả hai worker. Suy luồng theo IP và cổng Service/EndpointSlice thấy **16/16 cạnh giao tiếp đã triển khai**, gồm checkoutservice → paymentservice. Không thấy cạnh đã ánh xạ nào nằm ngoài danh sách kỳ vọng. Gửi TCP theo chiều trả lời hoặc chưa ánh xạ được được giữ riêng, không coi là cạnh nghiệp vụ mới.

Bảng Locust tích lũy cuối có 17 checkout, 0 lỗi. Bảng này bao gồm cả warm-up, không phải 17 checkout riêng của cửa sổ đo. Cũng không được coi 19.079 sự kiện là 19.079 HTTP request: một request có thể tạo nhiều lần gửi TCP, một kết nối phục vụ nhiều request.

Lượt này không có actor tấn công và không thấy process_exec trong cửa sổ đo. Nó giúp tham chiếu hành vi nghiệp vụ bình thường, nhưng chưa phải cặp đo overhead chính xác với S1–S3: Locust gốc chưa xuất latency từng request và không có continuous guard như bộ S4/S5.

### Hai cặp S4/S5 có thật sự giống cấu hình không?

Report đối chứng kiểm tra source bundle, actor và Locust thực sự chạy ở node nào, image digest, Pod spec đã bỏ tên tài nguyên sinh động, CPU/RAM, biến môi trường, source Locust gốc, phiên bản Locust, số user, spawn rate, seed, thời lượng cấu hình, policy, đích gọi và UID/image/vị trí của các Pod ứng dụng nền. **Cả hai cặp đều khớp.** Đồng thời manifest phải khớp tham số protocol, không chỉ tin dòng lệnh trong batch.json.

Seed=42 được ghi nhận trong Locust. Seed cố định trạng thái PRNG ban đầu; không đảm bảo các greenlet đồng thời tạo cùng chuỗi request và cùng thời điểm. Thứ tự case đã khai báo trước nhưng không được ngẫu nhiên hóa: đây vẫn là giới hạn của pilot.

## 4. Đọc kết quả so sánh mà không kết luận quá mức

Các số dưới đây tính từ request Locust từng pha. P95 chỉ tính request HTTP 200 không có exception; tỷ lệ lỗi tính riêng.

| Lượt | Hành vi phụ thực sự | Mẫu Locust trong pha đo / lỗi | P95 trước / trong / hồi phục (ms) |
| --- | --- | --- | --- |
| S0–S4 w2 | 0 request tải phụ | 68 / 0 | 108,89 / 180,46 / 104,36 |
| S4 w2 | 297 request tải phụ có native evidence | 81 / 0 | 91,91 / 311,72 / 99,34 |
| S0–S5 w1 | 0 upload; receiver nhận 0 | 64 / 0 | 92,92 / 64,10 / 125,21 |
| S5 w1 | 30/30 upload, 1.966.080 byte payload | 74 / 0 | 89,94 / 88,44 / 1.506,85 |

Đây là mô tả **một cặp mỗi họ**, chưa có khoảng tin cậy hay kiểm định. Pha attack S4 thực tế kéo dài khoảng 31,46 giây do khởi động/kết thúc client, trong khi control đo khoảng 30 giây; phải dùng timeline để tính rate thực tế, không chia mọi thứ cố định cho 30.

### Một lỗi checkout ở pha hồi phục S5

Locust ghi một `POST /cart/checkout` HTTP 500, sequence 315, từ 11:52:45.176780Z đến 11:52:57.014750Z, khoảng 11,84 giây. Pha recovery có 70 request, 1 lỗi; 69 request thành công được dùng tính percentile. Vì vậy không được ghi “toàn bộ traffic không lỗi”.

[Log hậu kiểm](audits/s0-s5-recovery-diagnostic-20261125.json) có frontend request ID `c3077351-c3f5-48c0-a457-64212042018a`: payment từ chối loại thẻ `visa_electron`, frontend trả 500. Payment log cùng thời điểm có `UnacceptedCreditCard`. Bằng chứng giải thích lỗi chức năng cụ thể này; **chưa giải thích đầy đủ biến động độ trễ và chưa chứng minh S5 gây ra hoặc không gây ra biến động đó**. Giữ nguyên cả lượt và lỗi, không chạy lại để thay kết quả.

30 payload vẫn được nhận đủ và khớp checksum, receipt cùng native event. Verifier kiểm chứng bằng chứng thí nghiệm, chất lượng thu và điều kiện dừng; không lấy điều kiện “mọi request mua hàng phải thành công” làm định nghĩa dữ liệu hợp lệ.

## 5. Vì sao cần một lượt shell/Python hợp lệ?

Trong S3, kẻ mô phỏng dùng shell và công cụ mạng. Nhưng người quản trị cũng có thể dùng shell để kiểm tra ứng dụng. Ví dụ ở case `s0-admin`: người vận hành được phép mở shell, chạy Python gọi frontend `/_healthz`, nhận HTTP 200. Tetragon ghi được process_exec của shell/Python và TCP tới frontend; receiver không nhận upload.

Đây là **mẫu normal khó phân biệt**, giúp kiểm tra báo nhầm sau này. Không thể viết quy tắc “thấy shell là attack” rồi coi đã đáp ứng mọi yêu cầu. Cần thêm danh tính, nguồn–đích, mục đích được phép, đường dẫn file và ngữ cảnh.

Case này có tác vụ quản trị nên được giữ riêng, không thay cho đối chứng S5 thuần túy không có can thiệp. [Receipt](../runs/s0-s5-control-20261125T115338Z-2022595/normal-admin.json) ghi purpose, Pod UID, PID, URL, thời điểm và status; verifier đối chiếu với raw. Chỉ thêm chữ “normal” vào manifest mà không có bằng chứng không đủ.

## 6. Tự double check như thế nào?

Trên `lab-cp`, từ thư mục `~/Testbed_Online_Boutique` đã cập nhật:

```bash
cd ~/Testbed_Online_Boutique
sudo python3 experiments/review_controls.py --include-legacy \
  --output experiments/audits/controls-recheck.json
sudo python3 experiments/audit_scenarios.py \
  --output experiments/audits/s1-s3-recheck.json
sudo python3 experiments/s4/review.py \
  --output experiments/audits/s4-recheck.json
sudo python3 experiments/s5/audit.py \
  --output experiments/audits/s5-recheck.json
```

Các lệnh trên **đọc và kiểm chứng**, không chạy tấn công mới. Kết quả ghi ngoài `runs/`. Nếu thiếu archive cũ trên VM, dùng bản repo đầy đủ; không tạo file giả để qua kiểm tra. Verifier giải nén vào thư mục tạm để replay, không ghi đè dữ liệu lịch sử.

Mở `experiments/audits/s0-s5-controls-20261125.json`: xem `passed`, từng `cases[].verification`, hai `pairs[].mismatched_fields`, `original_evidence_unchanged` và `official_ready=false`. Khi sai source/node/seed/cấu hình, phải xử lý sai khác trước khi ghép cặp.

Muốn **chạy lại cả batch**, đây là lệnh tạo lượt mới, có traffic trong lab:

| Cờ mới | Ý nghĩa dễ nhớ |
| --- | --- |
| `--scenario S0 --s4-control` | Giữ actor/Locust của S4, tắt client tải phụ |
| `--scenario S0 --s5-control` | Giữ actor/Locust/receiver của S5, tắt client upload |
| `--s5-calls 30` | Với S5: 30 upload; với S0–S5 control: cửa sổ không upload dài 30 giây |
| `--node w1` | Chọn worker chạy actor |
| `--loadgen-node w1` | Chọn worker chạy Locust tạm của họ S4/S5 |
| `--locust-seed 42` | Cố định và ghi nhận seed PRNG ban đầu của Locust có instrument |
| `--normal-admin` | Chỉ dùng cùng S0–S5 control; chạy chẩn đoán hợp lệ và lưu receipt riêng |

Protocol đã chứa đầy đủ các cờ cho từng case nên không cần gõ sáu lệnh thủ công:

```bash
sudo python3 experiments/run_controls.py
```

Chỉ chạy khi cần tái lập. Lịch của protocol này mất khoảng 16 phút cộng chi phí kiểm tra/cleanup. Coordinator dùng khóa batch và hash source; không sửa source giữa chừng. Nếu một lần cập nhật source làm hash không khớp, khôi phục đúng bản đã chốt hoặc tạo protocol mới có ID/hash/tham số đã rà soát. Không tắt kiểm tra hash. Lượt mới có run ID mới, không ghi đè lượt cũ.

Trong mỗi run, `manifest.json` nói chạy gì; `timeline.ndjson` nói khi nào; receipt nói client/receiver đã thực hiện gì; `dataset.tar.gz` giữ raw, source và bản chuẩn hóa; `*-verification.json` là kết quả kiểm chứng tại thời điểm chạy. Báo cáo audit mới nằm ngoài run để phân biệt kết luận hậu kiểm với bằng chứng gốc.

## 7. Kiểm thử và trạng thái cuối

[Report kiểm thử](audits/s0-s5-tests-20261125.json) và [log chi tiết](audits/s0-s5-tests-20261125.log) ghi số test thực chạy, lỗi, skip và hash source: 109 test đạt, không skip. Có các kiểm tra âm: sửa seed, đổi node/env/resource, bỏ receipt quản trị, thêm TCP tới receiver trong control hoặc đổi manifest khác protocol đều phải bị từ chối.

[Lượt kiểm thử đầu](audits/s0-s5-tests-initial-20261125.json) được giữ cùng [log](audits/s0-s5-tests-initial-20261125.log): Windows có thể đóng/reset TCP khi receiver từ chối header trước khi đọc body, làm test sai endpoint lỗi transport thay vì nhận HTTP 400. Đã sửa helper test để chỉ chấp nhận transport đóng khi receiver thực sự ghi đúng lý do từ chối; không giả lập thành công và không đổi receiver dùng trong lab.

[Trạng thái lab sau batch](audits/s0-s5-final-state-20261125.json): 3 node Ready, không MemoryPressure, deployment ứng dụng đủ replica, loadgenerator gốc trở về 0, không còn tài nguyên tạm và receiver cổng 18080 đã đóng. 14 hash source đã khai báo vẫn khớp. Đây là trạng thái chụp tại thời điểm hậu kiểm, không phải cam kết cluster luôn giữ nguyên sau đó.

## 8. Tiếp theo làm gì?

1. Dùng [bản đồ schema](FEATURE-SCHEMA-MAP.md) để chốt feature và tiêu chí chọn lượt; chia tập theo run, tránh rò rỉ nhãn.
2. Lập protocol chính thức có thứ tự/seed lưu trước, thời lượng đã chốt, các lần lặp độc lập trên cả worker và S0 dài 15 phút theo kế hoạch. Đối chứng phải dùng cùng bộ quan sát/source/cấu hình phù hợp từng họ.
3. Kiểm tra dữ liệu chính thức rồi mới đánh giá detector GĐ5: precision/recall, báo nhầm trên nghiệp vụ và quản trị hợp lệ, độ trễ phát hiện. Đánh giá policy bật/tắt và overhead cần thí nghiệm riêng.

Phần vừa hoàn thành đủ để chốt **rà soát và bổ sung đối chứng pilot**. Chưa thể ghi “bộ attack/normal chính thức hoàn chỉnh” hoặc “đã chứng minh chặn/phát hiện S1–S5”.
