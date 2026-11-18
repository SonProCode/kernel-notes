# Chạy bộ công cụ GĐ4 hiện tại

Ngày cập nhật 18/11/2026, giờ Việt Nam.

Bản triển khai đầu tiên phục vụ phần chuẩn bị tuần 11 và pilot S1. runner.py hỗ trợ S0, S1 và kiểm thử đọc file của S3. Kế hoạch đầy đủ ở README.md mô tả các bước S2, S3 mở rộng, S4 và S5 sẽ triển khai tiếp.

## Thành phần đã triển khai

| File | Công dụng |
| --- | --- |
| expected-communications.csv | 17 cạnh cấu hình có nguồn chứng minh, trong đó 16 cạnh tới Service hiện đang triển khai |
| policies/observe-files.yaml | Quan sát security_file_permission cho đường dẫn fixture /tmp/gd4-fixture/token trong boutique |
| actor.py | S1 thử TCP có giới hạn, hoặc đọc token giả để kiểm thử S3 |
| runner.py | Điều phối Pod, tải nền, log hai worker, snapshot, timeline và cleanup |
| label.py | Chuẩn hóa schema v3, gán nhãn từ Pod UID/thời gian/đích và tạo mẫu cửa sổ 10 giây |

Ma trận giao tiếp được đối chiếu từ Deployment snapshot và mã nguồn Online Boutique v0.10.7. Cột deployed=False ghi cạnh tới shoppingassistantservice, thành phần tùy chọn chưa có Service trong lab. Cạnh đó được giữ để người đọc thấy khác biệt giữa cấu hình và hệ thống thực tế.

Cột evidence là đường dẫn mã nguồn cho từng biến môi trường. Thông tin trong ma trận mô tả phụ thuộc được cấu hình. Khi dùng nó làm chính sách L7, cần bổ sung phương thức API và quyền cụ thể.

## Trước khi chạy

Chạy trên lab-cp, từ thư mục Testbed_Online_Boutique. Cụm phải có hai agent Tetragon đang hoạt động và loadgenerator ở 0 replica. Script giữ khóa cùng đường dẫn với script S0 cũ để ngăn hai lượt điều phối đồng thời. Cấu hình Locust được kiểm tra là USERS=10 và RATE=1.

Cài policy file một lần và kiểm tra cả hai agent.

```bash
sudo k3s kubectl apply --dry-run=server -f experiments/policies/observe-files.yaml
sudo k3s kubectl apply -f experiments/policies/observe-files.yaml
sudo k3s kubectl -n boutique get tracingpoliciesnamespaced
```

Policy này dùng mẫu security_file_permission của Tetragon và giới hạn đúng một đường dẫn fixture cùng quyền đọc. Sự kiện thể hiện kiểm tra quyền đọc file trong kernel. Receipt trong actor xác nhận thao tác đọc ở client đã hoàn tất. [Ví dụ upstream v1.8.0](https://github.com/cilium/tetragon/blob/v1.8.0/examples/quickstart/file_monitoring.yaml)

## Kiểm thử file trên từng worker

```bash
sudo python3 experiments/runner.py --scenario S3 --mode smoke --node w1 \
  --warmup 10 --pre 5 --recovery 5
sudo python3 experiments/runner.py --scenario S3 --mode smoke --node w2 \
  --warmup 10 --pre 5 --recovery 5
```

Mỗi lượt có 3 lần đọc fixture giả. Cần operations_with_matched_event=3. Số file_read_permission có thể lớn hơn số thao tác đọc vì một thao tác ở thư viện có thể phát sinh nhiều lần kiểm tra quyền.

mode=smoke giữ nhãn các sự kiện thử là unknown. Đây là bước kiểm tra thiết bị đo. Khi chạy bộ dữ liệu attack chính thức, dùng mode phù hợp sau khi chốt thao tác S3 đầy đủ.

## Chạy S1 pilot

```bash
sudo python3 experiments/runner.py --scenario S1 --mode pilot --node w1 \
  --warmup 30 --pre 10 --recovery 10
```

Pilot này giảm thời gian các pha để kiểm tra pipeline. Danh sách đích là các Service hiện có trong boutique, với cổng ứng dụng đầu tiên và cổng 65000 trên mỗi Service IP. Mỗi lần thử timeout 1 giây, các thời điểm bắt đầu cách nhau tối thiểu 0,2 giây và chỉ chạy một kết nối đồng thời. Script từ chối danh sách lớn hơn 40 đích và địa chỉ ngoài 10.43.0.0/16.

Danh sách thực tế được lưu trong manifest.json. Thời lượng attack thực tế phụ thuộc timeout từng đích. Lượt chính thức cần giữ bộ tham số đã chốt trong kế hoạch và ghi thời lượng thực.

Mỗi receipt ghi operation_id, địa chỉ, cổng, thời gian và kết quả. Với cổng đóng, outcome có thể là timeout hoặc os_error. Telemetry còn phụ thuộc đường đi kernel, nên quality.json liệt kê operation không tìm được sự kiện đối chiếu. Điều kiện hoàn tất hiện tại yêu cầu có ít nhất một operation khớp và capture_checks_passed=true. Cần đọc cả độ phủ thao tác trước khi nghiệm thu dữ liệu.

## Chạy S0 bằng cấu hình mới

```bash
sudo python3 experiments/runner.py --scenario S0 --mode official \
  --warmup 400 --measurement 900
```

Lượt S0 mới dùng policy file đã cài và schema v3. Lệnh này mất khoảng 22 phút cộng thời gian khởi động tải. S0 có phase=measurement và label=normal trong khoảng đo. Các sự kiện setup và warm-up giữ phase riêng và label=unknown.

## Nhãn và giới hạn hiện tại

Các bản ghi đã xử lý lại dùng label_version=v2, với pha finalize tách khỏi cửa sổ đo. Mỗi bản ghi có schema_version=3 và scenario_id lấy từ manifest. Các schema cũ tiếp tục được giữ trong dữ liệu lịch sử.

- S1 gán attack khi Pod UID khớp actor, IP/cổng khớp receipt và timestamp nằm trong khoảng thực hiện operation.
- Kiểm thử file đối chiếu thêm đường dẫn fixture và loại sự kiện.
- Traffic nền trong pre_attack/recovery có nhãn normal theo quy tắc bối cảnh của runner.
- Traffic nền trong pha attack, response chưa liên kết được và sự kiện thiếu căn cứ giữ unknown.
- Thời điểm kernel trước/sau biên receipt có thể khiến một thao tác chưa được khớp. Dữ liệu gốc và danh sách unmatched được giữ để kiểm tra.
- label.py giữ binary, PID, quan hệ exec, socket, file path và kết quả hook. Nội dung đối số tiến trình hiện chưa được xuất vào schema v3. Có thể đối chiếu raw khi cần và mở rộng bộ lọc dữ liệu trong bước tiếp theo.
- Chưa diễn giải response TCP thành một cuộc gọi API. Các quy tắc liên kết L7 sẽ được bổ sung khi viết S2.
- File labeled-windows.ndjson tạo cửa sổ 10 giây cho từng Pod UID. Đơn vị này giữ số sự kiện attack/normal/unknown, cùng nhãn tổng hợp.

## Kết quả và khôi phục

Runner in đường dẫn runs/<run_id> khi bắt đầu. Mỗi lượt có manifest.json, timeline.ndjson, actor-receipts.ndjson, raw, normalized.ndjson, labeled-windows.ndjson và quality.json khi đi hết bước chuẩn hóa.

manifest.status mô tả tiến trình thực hiện. dataset_status mô tả kết quả kiểm tra capture sau khi chuẩn hóa. Hai trường này cần được đọc cùng operations_with_matched_event và unmatched_operations.

Ctrl+C hoặc SIGTERM kích hoạt cleanup. Runner dừng tải do mình bật, đóng collector, lưu snapshot cuối và xóa Pod actor của lượt đó. Nếu máy mất điện hoặc bị SIGKILL, người vận hành kiểm tra trạng thái trước khi chạy tiếp.

```bash
sudo k3s kubectl -n boutique get pods -l app=gd4-actor
sudo k3s kubectl -n boutique get deployment loadgenerator
```

Nếu xảy ra lỗi, xem manifest.error, actor.stderr và raw/*.stderr. Các lượt lỗi được giữ trong runs để đối chiếu nguyên nhân.

## Công việc tiếp theo

Các lần chạy mới lưu thêm snapshot Prometheus về trạng thái scrape và các bộ đếm lỗi export/mất sự kiện tại hai mốc trước/sau. Cần đối chiếu các response gốc và khoảng scrape khi diễn giải mức mất dữ liệu. Sau pilot S1, bổ sung receipt/API cho S2, chuỗi shell/công cụ cho S3, receiver S5 và client đo request latency cho S4. Các lượt chính thức có nhãn được chạy sau khi từng pilot đã được kiểm chứng.
