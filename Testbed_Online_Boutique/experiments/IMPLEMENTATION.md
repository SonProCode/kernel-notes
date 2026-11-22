# Chạy bộ công cụ GĐ4 hiện tại

Ngày cập nhật 22/11/2026, giờ Việt Nam.

Người mới bắt đầu đọc [USAGE.md](USAGE.md). Chi tiết từng kịch bản: [S1.md](S1.md), [S2.md](S2.md), [S3.md](S3.md).

Bộ công cụ hỗ trợ S0, S1, S2 và S3 runtime. Hướng dẫn double check nằm trong [S2.md](S2.md) và [S3.md](S3.md). S3 có shell thật, curl/wget/nc/nmap và đọc projected token của actor. S4/S5 cùng các lượt official còn ở bước tiếp theo theo [kế hoạch](README.md).

## Thành phần đã triển khai

| File | Công dụng |
| --- | --- |
| expected-communications.csv | 17 cạnh cấu hình có nguồn chứng minh, trong đó 16 cạnh tới Service hiện đang triển khai |
| policies/observe-files.yaml | Quan sát security_file_permission cho fixture cũ và hai prefix ServiceAccount token trong boutique |
| actor.py | S1 thử TCP; S2 gọi RPC; S3 chạy runtime hoặc fixture smoke cũ |
| runner.py | Điều phối Pod, tải nền, log hai worker, snapshot, timeline và cleanup |
| label.py | Schema v4, nhãn v4; S3 ghép thêm container PID, binary/path và ancestry; tạo cửa sổ 10 giây |

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

Policy dùng security_file_permission, quyền đọc MAY_READ và selector cho fixture cùng prefix token (gồm đường dẫn symlink đã resolve). Sự kiện thể hiện kiểm tra quyền đọc file trong kernel. Receipt trong actor xác nhận thao tác đọc ở client đã hoàn tất. [Ví dụ upstream v1.8.0](https://github.com/cilium/tetragon/blob/v1.8.0/examples/quickstart/file_monitoring.yaml)

## Kiểm thử fixture cũ trên từng worker

```bash
sudo python3 experiments/runner.py --scenario S3 --mode smoke --node w1 \
  --warmup 10 --pre 5 --recovery 5
sudo python3 experiments/runner.py --scenario S3 --mode smoke --node w2 \
  --warmup 10 --pre 5 --recovery 5
```

Mỗi lượt có 3 lần đọc fixture giả. Cần operations_with_matched_event=3. Số file_read_permission có thể lớn hơn số thao tác đọc vì một thao tác ở thư viện có thể phát sinh nhiều lần kiểm tra quyền.

mode=smoke giữ nhãn các sự kiện thử là unknown. Đây là bước kiểm tra thiết bị đo. Muốn kiểm thử runtime mới, xem lệnh có --s3-profile runtime trong [S3.md](S3.md).

## Chạy S1 pilot

```bash
sudo python3 experiments/runner.py --scenario S1 --mode pilot --node w1 \
  --warmup 30 --pre 10 --recovery 10
```

Pilot này giảm thời gian các pha để kiểm tra pipeline. Danh sách đích là các Service hiện có trong boutique, với cổng ứng dụng đầu tiên và cổng 65000 trên mỗi Service IP. Mỗi lần thử timeout 1 giây, các thời điểm bắt đầu cách nhau tối thiểu 0,2 giây và chỉ chạy một kết nối đồng thời. Script từ chối danh sách lớn hơn 40 đích và địa chỉ ngoài 10.43.0.0/16.

Danh sách thực tế được lưu trong manifest.json. Thời lượng attack thực tế phụ thuộc timeout từng đích. Lượt chính thức cần giữ bộ tham số đã chốt trong kế hoạch và ghi thời lượng thực.

Mỗi receipt ghi operation_id, địa chỉ, cổng, thời gian và kết quả. Với cổng đóng, outcome có thể là timeout hoặc os_error. Telemetry còn phụ thuộc đường đi kernel, nên quality.json liệt kê operation không tìm được sự kiện đối chiếu. Bản rà soát 22/11 yêu cầu đủ mọi operation khớp, receipt đúng danh sách targets và raw Tetragon đúng hook/UID/đích/thời gian. Kết quả ở s1-verification.json. Các lượt S1 mới có source snapshot; đọc [S1.md](S1.md) để biết cách kiểm tra.

## Chạy S0 bằng cấu hình mới

```bash
sudo python3 experiments/runner.py --scenario S0 --mode official \
  --warmup 400 --measurement 900
```

Lượt S0 mới dùng policy file đã cài và schema v4. Giữ cùng release/policy/schema với attack trong cohort đối chứng. Lệnh này mất khoảng 22 phút cộng thời gian khởi động tải. S0 có phase=measurement và label=normal trong khoảng đo. Các sự kiện setup và warm-up giữ phase riêng và label=unknown.

## Nhãn và giới hạn hiện tại

Các lượt mới dùng schema_version=4 và label_version=v4. Bản v4 bổ sung PID trong container, arguments của actor và liên kết cha/con cho S3. Các lượt lịch sử v1/v2/v3 được giữ nguyên; đọc manifest và source snapshot để chọn bộ xử lý tương ứng.

- S1 gán attack khi Pod UID khớp actor, IP/cổng khớp receipt và timestamp nằm trong khoảng thực hiện operation.
- S3 runtime đối chiếu Pod UID, container PID, binary/path hoặc socket đích và thời gian; verifier kiểm tra parent_exec_id trên raw. Fixture smoke cũ vẫn có quy tắc riêng.
- Traffic nền trong pre_attack/recovery có nhãn normal theo quy tắc bối cảnh của runner.
- Traffic nền trong pha attack, response chưa liên kết được và sự kiện thiếu căn cứ giữ unknown.
- Thời điểm kernel trước/sau biên receipt có thể khiến một thao tác chưa được khớp. Dữ liệu gốc và danh sách unmatched được giữ để kiểm tra.
- label.py giữ binary, PID, quan hệ exec, socket, file path và kết quả hook. V4 xuất arguments cho actor. Nội dung token không được ghi vào receipt hoặc dataset.
- S2 dùng receipt gRPC và log server để chứng minh API; riêng TCP event không đủ chứng minh RPC thành công. S3 dùng thêm kết quả từng công cụ và receipt đọc file.
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

Các lần chạy mới lưu thêm snapshot Prometheus về trạng thái scrape và các bộ đếm lỗi export/mất sự kiện tại hai mốc trước/sau. Cần đối chiếu các response gốc và khoảng scrape khi diễn giải mức mất dữ liệu. Sau pilot S3, bổ sung receiver S5 và client đo request latency cho S4. Các lượt chính thức có nhãn được chạy sau khi từng pilot đã được kiểm chứng.
