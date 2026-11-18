# Từ log đến dữ liệu phân tích luận văn

## Câu hỏi nghiên cứu quyết định dữ liệu cần thu

Ví dụ câu hỏi “Có thể phát hiện nguồn gọi payment ngoài luồng với ít cảnh báo sai không?” cần biết quyền hoặc luồng hợp lệ, định danh nguồn, đích và kết quả. Nếu dữ liệu chỉ có IP/cổng, câu hỏi đo được là “Có thể nhận ra kết nối tới đích ngoài tập cho phép không?”. Muốn phân tích từng thao tác thanh toán, bổ sung dữ liệu phía ứng dụng, proxy hoặc trace có method và status.

Giữ riêng:

- **Raw** chứa sự kiện nguyên bản theo công cụ và node. Lưu với quyền phù hợp vì argv và log có thể chứa dữ liệu nhạy cảm.
- **Normalized** chứa trường thống nhất để phân tích. Giữ đường dẫn, định danh hoặc vị trí để truy lại raw.
- **Ground truth** ghi thời gian, hành vi và kết quả từ bộ điều phối và đối chứng phía đích.
- **Metadata** chứa cấu hình, snapshot workload, phiên bản công cụ và thay đổi giữa lần chạy.

## Mẫu bản ghi và cách đọc

JSON dưới đây là dữ liệu minh họa. Nó thể hiện một lần thử TCP; công cụ thực tế có thể dùng tên trường và cấu trúc khác.

```json
{
  "schema_version": 1,
  "run_id": "lab-004",
  "event_id": "node-a-000132",
  "event_time": "2026-11-15T02:00:01.200Z",
  "ingest_time": "2026-11-15T02:00:01.240Z",
  "collector": "tetragon",
  "event_type": "connect_attempt",
  "node": "node-a",
  "namespace": "boutique",
  "pod_uid": null,
  "src_workload": "runtime-probe",
  "dst_ip": "10.43.10.8",
  "dst_port": 50051,
  "dst_workload": "paymentservice",
  "dst_mapping": "service_snapshot",
  "result": null
}
```

`null` biểu thị trường chưa biết. Trong ví dụ, người phân tích biết đích dựa vào Service snapshot, vẫn chưa biết TCP thành công. Giữ IP nguyên bản và nguồn ánh xạ. Nếu nhiều endpoint có thể khớp, đánh dấu mơ hồ và lưu phương án tra cứu. Snapshot nên có thời điểm vì Pod IP có thể được tái sử dụng. Khi chạy nhiều cluster, lưu thêm cluster ID. Nếu join các nguồn, quản lý lệch đồng hồ và dấu thời gian UTC.

## Baseline và tập đặc trưng

**Baseline** mô tả hoạt động bình thường trong phạm vi đã chạy. Thu các pha startup, warm-up, tải ổn định và thay đổi hợp lệ như rollout, health check hoặc debug đã ghi nhận. Dữ liệu nên có đủ luồng nghiệp vụ như đọc sản phẩm và checkout, vì mỗi luồng có các cạnh khác nhau.

Một **cạnh** là hướng giao tiếp từ một workload tới workload khác trong mô hình. Chọn ý nghĩa cho trọng số, ví dụ số TCP attempts quan sát trong 30 giây. RPC count là một biến khác.

| Cửa sổ 30 giây | Nguồn | Đích khác nhau | Thử kết nối | Giải thích cần kiểm tra |
|---|---|---:|---:|---|
| A | checkoutservice | 4 | 5 | Hành trình đặt hàng mẫu |
| B | runtime-probe | 8 | 10 | Kiểm tra phạm vi đích trong kịch bản dò |
| C | checkoutservice | 4 | 11 | Có thể là tải tăng hoặc reconnect |

Các số chỉ để minh họa. Có thể thêm số cổng đích, số cạnh mới, tỷ lệ kết quả thất bại **trong số sự kiện có kết quả**, số exec shell và số lần truy cập file trong danh sách quan sát. Ghi phương pháp lọc DNS, probe và traffic nền. Hiệu chỉnh ngưỡng trên một nhóm lần chạy rồi đánh giá trên nhóm lần chạy khác. Tách theo `run_id` giúp các cửa sổ cùng lần chạy không rơi vào cả hai tập.

## Thiết kế các lần chạy

| Mã | Kịch bản trong cluster lab | Bằng chứng và đối chứng |
|---|---|---|
| S0 | Browse, thêm giỏ, checkout dưới tải ghi trước | Ghi kết quả user journey, thời điểm, config và log |
| S1 | Probe thử một tập đích/cổng được chỉ định, với tần suất giới hạn | Ghi đích cố định và kết quả từng lần; so với tải hợp lệ |
| S2 | Probe thử kết nối tới payment giả lập | Dùng checkout hợp lệ đối chứng; nếu đo API thì ghi status phía đích |
| S3 | Chạy shell và mở file đánh dấu vô hại | Ghi exec và file riêng; thử thêm một thao tác bình thường |
| S4 | Tăng tần suất yêu cầu tới listener lab | So với spike tải hợp lệ và ghi giới hạn tải |
| S5 | Gửi dữ liệu giả lập tới endpoint lab riêng | Ghi endpoint, lượng dữ liệu và kết quả trước/sau egress policy |

Tên và mục tiêu dựa theo khung kịch bản trong đề cương. Có thể bắt đầu bằng S0 và một phép thử S2 hoặc S3. Ghi trạng thái policy, đích thực và kết quả từng lần. `kubectl exec` hoặc Pod probe là phương pháp tạo tình huống. Cảnh báo của detector là kết quả dự đoán.

Mẫu nhãn có thể bắt đầu bằng CSV:

```csv
run_id,scenario,start_utc,end_utc,source,target,attempted,observed_outcome
lab-004,S2,2026-11-15T02:00:01Z,2026-11-15T02:00:04Z,runtime-probe,paymentservice,true,tcp_timeout
```

## Đánh giá bảo mật và hiệu năng

Định nghĩa đơn vị trước khi đếm, ví dụ mỗi run chứa một cửa sổ mục tiêu hoặc dùng cửa sổ 30 giây. Gắn cảnh báo với nhãn bằng thời gian, nguồn và loại hành vi đã quy định.

- **TP** là đơn vị có hành vi mục tiêu và có phát hiện. **FN** là đơn vị có hành vi mục tiêu bị bỏ sót.
- **FP** là đơn vị bình thường bị cảnh báo. **TN** là đơn vị bình thường được dự đoán đúng.
- **Precision** = TP / (TP + FP). **Recall** = TP / (TP + FN). **FPR** = FP / (FP + TN). Nếu mẫu số bằng 0, ghi chỉ số chưa xác định.
- **Độ trễ phát hiện** = thời điểm alert trừ thời điểm bắt đầu hành vi.
- **Độ trễ giảm thiểu** = thời điểm kiểm chứng vừa bị chặn trừ thời điểm alert. Định kỳ probe giúp báo giới hạn độ phân giải phép đo.

Ví dụ có 10 lần tấn công và 100 cửa sổ bình thường, phát hiện đúng 8 lần và báo nhầm 4 cửa sổ. Nếu quy ước phân tích coi mỗi lần tấn công là một cửa sổ mục tiêu, TP=8, FN=2, FP=4, TN=96. Precision = 66,7%, recall = 80%, FPR = 4%. Với nhiều alert trên cùng cửa sổ, thống nhất cách gộp trước khi tính.

Throughput là lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ 80 request thành công mỗi giây. Latency là thời gian xử lý một yêu cầu. p95 bằng 200 ms nghĩa là khoảng 95% mẫu có độ trễ không quá 200 ms. p50 cho thấy độ trễ ở giữa tập mẫu, còn p99 giúp quan sát nhóm chậm nhất. Ghi cách xử lý request lỗi và timeout để so sánh nhất quán.

Đo overhead ở tải được kiểm soát: ứng dụng gốc → thêm collector → thêm detector → thêm thực thi. Báo số lần lặp, throughput, p50/p95/p99 latency, CPU/RAM, số event mất nếu tool báo được và số luồng hợp lệ bị ảnh hưởng. Đo blast radius theo số đích tiếp cận được từ **cùng nguồn** và **cùng tập đích** trước/sau policy. Ví dụ 6/10 đích giảm còn 2/10 là giảm 4 đích trong phép thử ở mức đã định nghĩa.

## Tự kiểm tra

1. **Tại sao có thể recall cao nhưng precision thấp?** Hệ thống phát hiện nhiều mẫu tấn công và đồng thời tạo nhiều cảnh báo nhầm.
2. **Không thấy alert thì kết luận gì?** Cần đối chiếu nhãn, độ phủ collector và log thô trước khi giải thích.
3. **Một lần đo p99 có đủ so sánh không?** Cần số mẫu, cách phát tải, thời gian đo và các lần lặp để đánh giá biến động.
4. **Khi chạy policy sai làm checkout lỗi, cần lưu gì?** Lưu policy, log và kết quả luồng hợp lệ để phản ánh chi phí phản ứng.

Dùng [mẫu bàn giao](09-tra-cuu.md#mẫu-bàn-giao-cho-phiên-phân-tích-tiếp-theo) khi chuyển lần chạy cho người hoặc phiên khác.



