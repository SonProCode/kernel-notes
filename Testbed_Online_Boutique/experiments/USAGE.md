# Bắt đầu sử dụng S1, S2, S3 từ con số 0

Cập nhật 22/11/2026. Đọc bài này trước, rồi chọn [S1](S1.md), [S2](S2.md) hoặc [S3](S3.md). [Báo cáo rà soát](REVIEW-S1-S2-S3.md) ghi rõ đã kiểm chứng gì và giới hạn nào còn lại.

## 1. Ta đang làm gì trong lab?

Online Boutique là cửa hàng mẫu, gồm nhiều chương trình nhỏ gọi nhau để xem sản phẩm, quản lý giỏ và thanh toán. Kubernetes chạy các chương trình đó trong Pod. Một namespace giống một ngăn tổ chức tài nguyên; ứng dụng của bạn nằm trong ngăn tên `boutique`.

Ta tạo một Pod tạm đóng vai điểm xuất phát đã bị chiếm quyền chạy lệnh. Pod đó gọi là **actor**. Chương trình điều khiển toàn bộ lượt thử gọi là **runner**. Runner vừa bật traffic mua hàng bình thường, vừa cho actor thực hiện một hành vi đã biết trước, rồi thu bằng chứng.

| Kịch bản | Ví dụ dễ hình dung | Hành vi thực tế trong script |
| --- | --- | --- |
| S1 · Thăm dò | Thử nhiều cửa để biết cửa nào mở | Thử TCP tới từng Service, ở cổng ứng dụng và cổng 65000 |
| S2 · Gọi trái luồng | Một vai trò không phải checkout gọi thẳng bộ phận thanh toán | Actor gọi API gRPC Charge của paymentservice với dữ liệu giả |
| S3 · Runtime abuse | Người lạ mở trình lệnh trong Pod, dùng công cụ mạng rồi đọc credential | Shell + curl/wget/nc/nmap + đọc token của ServiceAccount tạm |

Các hành vi là dữ liệu có chủ đích cho GĐ4. Tetragon cung cấp quan sát kernel; nhãn attack do ta đối chiếu kịch bản với bằng chứng. Xây detector ở GĐ5 và chặn/cô lập tự động ở GĐ6 là các sản phẩm tiếp theo.

## 2. Chạy lệnh trên máy nào?

| Máy | Địa chỉ | Vai trò |
| --- | --- | --- |
| Máy Windows của bạn | Máy mở trình duyệt/terminal | SSH vào lab và xem website/Grafana |
| lab-cp | 192.168.141.142 | Chạy toàn bộ lệnh runner trong hướng dẫn này |
| lab-w1 | 192.168.141.143 | Kubernetes đặt actor và workload lên đây |
| lab-w2 | 192.168.141.144 | Worker thứ hai để thử lại placement |

Mở PowerShell trên Windows hoặc dùng MobaXterm, kết nối:

```powershell
ssh sonth32@192.168.141.142
```

Nhập mật khẩu khi SSH hỏi. Sau khi đăng nhập, terminal đang chạy Linux trên lab-cp; các lệnh Bash/Python phía dưới được gõ ở đó. Không cần SSH sang worker để chạy từng công cụ.

Vào thư mục đã đồng bộ trên lab-cp:

```bash
cd ~/Testbed_Online_Boutique
pwd
ls experiments/runner.py
```

`cd` đổi thư mục hiện tại. `~` là thư mục nhà của tài khoản đang đăng nhập. `pwd` in nơi bạn đang đứng; với tài khoản sonth32, mong đợi `/home/sonth32/Testbed_Online_Boutique`. `ls` kiểm tra file runner có tồn tại.

Nếu bạn vừa clone repo GitHub thành một thư mục mới, đường dẫn thường là `~/kernel-notes/Testbed_Online_Boutique`; hãy `cd` vào đó và kiểm tra `ls experiments/runner.py`. Chọn **một bản làm việc** cho cả lượt, tránh chạy script một nơi rồi tìm kết quả ở nơi khác.

### Đọc cú pháp lệnh cho đúng

- Chỉ chép phần trong khối lệnh; không chép dấu nhắc như `sonth32@manager:~$`.
- `sudo` chạy lệnh với quyền quản trị. Lúc gõ mật khẩu sudo, màn hình thường không hiện ký tự; đó là hành vi bình thường.
- `python3 experiments/runner.py` nghĩa là dùng Python chạy file runner, không cần tự mở các file Python để chạy từng hàm.
- `--scenario S1` là một tham số và giá trị. Hai dấu `--` phải được giữ.
- Dấu `\` ở cuối dòng Bash nối câu lệnh sang dòng tiếp theo; không thêm khoảng trắng sau nó. Các lệnh chạy thử dưới đây được viết một dòng để dễ chép.
- Tên biến như `RUN` chỉ tồn tại trong terminal đang dùng. Mở terminal mới cần gán lại.
- Các tên chứa `<run_id>` trong lời giải thích là chỗ thay thế. Không gõ nguyên dấu `<`/`>` vào lệnh shell.

## 3. Kiểm tra trước khi chạy

Trên lab-cp, từ thư mục có `experiments/`:

```bash
sudo k3s kubectl get nodes
sudo k3s kubectl -n boutique get deployments
sudo k3s kubectl -n telemetry get pods -o wide
sudo k3s kubectl -n boutique get pods -l app=gd4-actor
sudo k3s kubectl -n boutique get serviceaccounts -l experiment-run
df -h .
date -u
```

Ý nghĩa và kết quả cần đọc:

| Lệnh/thông tin | Mong đợi |
| --- | --- |
| get nodes | Ba node Ready |
| get deployments | Các ứng dụng available; riêng loadgenerator ở 0 trước khi chạy |
| get pods trong telemetry | Hai Pod Tetragon, mỗi Pod 2/2 Running; operator là Pod khác |
| actor và ServiceAccount thí nghiệm | Không còn lượt cũ đang chạy/dọn |
| df -h . | Đĩa chứa thư mục kết quả còn dung lượng; log tăng theo thời gian |
| date -u | Giờ UTC để đối chiếu timeline/Grafana |

`sudo k3s kubectl` là cách gọi công cụ quản trị Kubernetes tích hợp trong K3s. `-n boutique` chọn namespace; `get` đọc trạng thái; `-l` lọc theo label. Các lệnh này chưa tạo cuộc thử nào.

Nếu một runner khác đang chạy, chờ lượt đó hoàn tất. Runner dùng khóa chung để tránh hai cuộc thử chồng nhau. Không tự xóa file khóa để vượt qua việc đang có lượt hoạt động.

Với S3 runtime, policy file cần đang được cài và bundle công cụ cần đúng hash:

```bash
sudo python3 experiments/s3/build_tools.py
sudo k3s kubectl apply --dry-run=server -f experiments/policies/observe-files.yaml
sudo k3s kubectl apply -f experiments/policies/observe-files.yaml
sudo k3s kubectl -n boutique get tracingpoliciesnamespaced
```

`--dry-run=server` nhờ API server kiểm tra cấu hình nhưng chưa áp dụng. Lệnh apply sau đó mới ghi policy. `build_tools.py` dùng lại bundle hợp lệ đã có; khi thiếu bundle mới tạo builder tạm để chuẩn bị.

## 4. Chạy thử theo thứ tự S1 → S2 → S3

Chạy **từng lệnh một**, đợi lệnh trả về dấu nhắc rồi kiểm tra kết quả. Runner tự tạo actor, bật Locust, đợi đủ 10 người dùng ảo, warm-up, chạy hành vi, thu recovery và dọn tài nguyên. Bạn không cần bật thêm loadgenerator bằng tay, cũng không cần giữ port-forward frontend để actor hoạt động.

### S1: pilot ngắn, đủ danh sách đích

```bash
sudo python3 experiments/runner.py --scenario S1 --mode pilot --node w1 --warmup 10 --pre 5 --recovery 5
```

Lab hiện có 11 Service, mỗi Service thử hai cổng nên có 22 thao tác. Nếu danh sách Service thay đổi, số thao tác sẽ theo `manifest.targets`; luôn đọc số thực tế. Chi tiết trong [bài S1](S1.md).

### S2: smoke một lời gọi để học quy trình

```bash
sudo python3 experiments/runner.py --scenario S2 --mode smoke --node w1 --s2-calls 1 --warmup 5 --pre 5 --recovery 5
```

Mong đợi một RPC Charge trả OK, một UUID và một log handler tương quan. Smoke giữ nhãn thử là unknown. Sau khi hiểu, dùng pilot 30 lời gọi theo [bài S2](S2.md).

### S3: smoke một vòng runtime

```bash
sudo python3 experiments/runner.py --scenario S3 --mode smoke --s3-profile runtime --s3-rounds 1 --node w1 --warmup 5 --pre 5 --recovery 5
```

Mong đợi 6/6 thao tác. Cần giữ `--s3-profile runtime`: mode smoke không có tham số này mặc định là phép thử fixture giả cũ. Một vòng runtime có shell, bốn công cụ và một lần đọc projected token. Đọc [bài S3](S3.md) trước khi chạy profile này để hiểu token thật và metadata được xuất.

### Các tham số chung có ý nghĩa gì?

| Tham số | Ý nghĩa |
| --- | --- |
| --scenario | Chọn hành vi S1, S2 hoặc S3 |
| --mode smoke | Thử đường chạy/thiết bị đo; sự kiện thử giữ unknown |
| --mode pilot | Chạy thử chức năng; sự kiện khớp hành vi được gán attack |
| --mode official | Đánh dấu lượt thuộc profile chính thức; vẫn phải tự giữ đúng tham số đã chốt |
| --node w1 / w2 | Đặt actor trên lab-w1 hoặc lab-w2; runner vẫn chạy trên lab-cp |
| --warmup | Số giây làm nóng sau khi Locust đã đủ user |
| --pre | Số giây quan sát trước hành vi |
| --recovery | Số giây quan sát sau hành vi |
| --s2-calls | Số lời gọi S2, từ 1 đến 30 |
| --s3-rounds | Số vòng runtime S3, từ 1 đến 3 |

Chỉ đổi `--mode official` không làm một pilot ngắn trở thành dataset đủ tiêu chuẩn. Lượt chính thức cần profile và số lượt lặp đã chốt, cùng release/policy/schema và S0 đối chứng.

## 5. Khi script đang chạy, nhìn gì?

Runner in dòng như `Run: /home/sonth32/Testbed_Online_Boutique/runs/s1-...`. Đó là thư mục của **lượt mới**, cần giữ lại. Các dòng tiếp theo là các pha:

```text
setup → warmup → pre_attack → attack → recovery → finalize
```

Warm-up có thể im lặng vài chục hoặc vài trăm giây đúng theo tham số. Chưa thấy dòng mới không đồng nghĩa chương trình treo. Kết thúc thuận lợi có dòng `Completed: ...`; sau đó vẫn phải đọc verifier và manifest.

Mở SSH thứ hai vào lab-cp để xem mà không ngắt terminal đang chạy:

```bash
sudo k3s kubectl -n boutique get pods -o wide
sudo k3s kubectl -n boutique get deployment loadgenerator
sudo k3s kubectl top nodes
```

Trong Grafana, dashboard CPU/RAM cho biết tài nguyên của namespace/workload. Nó không tự hiển thị toàn bộ raw Tetragon hoặc tự tạo alert S1–S3. Chọn đúng khoảng giờ của lượt; dùng UTC hoặc quy đổi UTC+7. Mỗi lần chạy có timeline riêng để xác định pha attack.

## 6. Chọn đúng thư mục kết quả, rồi kiểm tra

Mỗi lượt tạo một tên khác nhau. Có thể chọn lượt gần nhất của từng kịch bản trong terminal đang dùng:

```bash
RUN=$(sudo find runs -mindepth 1 -maxdepth 1 -type d -name 's1-*' | sort | tail -n 1)
printf '%s\n' "$RUN"
```

Đổi `'s1-*'` thành `'s2-*'` hoặc `'s3-*'` khi cần. Lệnh này chọn tên theo thời gian UTC; hãy so tên in ra với dòng Run của lượt bạn muốn xem. Nếu đang dùng bản clone có nhiều run lịch sử, chọn bằng tên cụ thể từ danh mục để tránh nhầm.

```bash
sudo cat "$RUN/manifest.json"
sudo cat "$RUN/quality.json"
```

`manifest.status=completed` cho biết thực hiện đã đi hết. `dataset_status=validated` cho biết các kiểm tra của phiên bản runner đó đã đạt. Các lượt lịch sử có thể chưa có trường dataset_status, nên cần xem báo cáo rà soát độc lập. `interrupted` là bị dừng; `failed` hoặc `failed_validation` cần tìm nguyên nhân.

Sau khi chọn RUN của đúng kịch bản, dùng **một** lệnh verifier tương ứng:

```bash
sudo python3 experiments/s1_verify.py "$RUN"
```

```bash
sudo python3 experiments/s2_verify.py "$RUN"
```

```bash
sudo python3 experiments/s3_verify.py "$RUN"
```

Không chạy cả ba verifier lên cùng một RUN. S2/S3 verifier cập nhật file xác minh dẫn xuất trong run; raw và receipt vẫn được giữ. Muốn rà soát archive mà giữ nguyên toàn bộ run lịch sử, dùng công cụ ở mục 9.

| Kịch bản | Điều kiện chính |
| --- | --- |
| S1 | expected_operations = receipts = operations_with_native_event; hiện tại 22/22, unmatched rỗng, passed=true |
| S2 | Số API thành công, UUID, operation có network và server match bằng số calls; passed=true |
| S3 runtime | 6 × rounds operation đạt; có exec/lineage/connect/file và token metadata đúng; passed=true |

`22/22` hoặc `18/18` là độ phủ đối chiếu hành vi đã tạo. Các con số đó chưa phải recall của detector. Ví dụ một TCP connect có thể sinh một event; một HTTP request có nhiều send; một lần đọc token có hai kiểm tra quyền. Không quy đổi số dòng log thành số request.

## 7. Những file nào để làm gì?

| File/thư mục | Cách hiểu đơn giản |
| --- | --- |
| manifest.json | Phiếu thông tin lượt chạy: ai, ở đâu, tham số, phiên bản, trạng thái |
| timeline.ndjson | Mỗi dòng là một mốc chuyển pha UTC |
| actor-receipts.ndjson | Nhật ký từng việc actor đã làm và kết quả client |
| raw/lab-w1.ndjson, raw/lab-w2.ndjson | Log Tetragon gốc trên từng worker |
| normalized.ndjson | Các event đã đưa về bộ trường thống nhất, có nhãn và raw reference |
| labeled-windows.ndjson | Gom event theo Pod UID trong cửa sổ 10 giây |
| quality.json | Kiểm tra thu log, restart, dòng lỗi, số thao tác có sự kiện |
| s1/s2/s3-verification.json | Kết quả kiểm tra riêng cho kịch bản, nếu runner phiên bản đó tạo |
| paymentservice.log, server-matches.ndjson | Riêng S2: log phía nhận và dòng handler khớp từng RPC |
| source/ và script_sha256 | Bản sao/hash nguồn của lượt, khi phiên bản runner có lưu |
| metrics-before/after.json | Response Prometheus ở hai thời điểm; cần đọc cả lỗi query/series thiếu |
| dataset.tar.gz | Bản nén khi đưa lên GitHub, không phải file runner luôn tự tạo |

NDJSON nghĩa là mỗi dòng là một JSON độc lập. Để xem vài receipt đầu và đếm số thao tác:

```bash
sudo head -n 2 "$RUN/actor-receipts.ndjson"
sudo wc -l "$RUN/actor-receipts.ndjson"
```

Schema của manifest và schema của event là hai định dạng riêng. Runner hiện ghi manifest schema 3 và normalized event schema 4/label v4. Các run cũ còn label v2/v3; dữ liệu lịch sử được giữ nguyên.

## 8. Dữ liệu lấy từ GitHub cần giải nén trước

Trên lab-cp, run vừa tạo có raw/normalized trực tiếp. Bản repo thường gói chúng trong `dataset.tar.gz`. Phải giải nén **trước** khi chạy verifier cần những file đó.

Ví dụ cụ thể sau dùng một run S2 đã công bố, từ thư mục Testbed_Online_Boutique của bản clone:

```bash
RUN='runs/s2-20261120T161015Z-1242543'
tar -xzf "$RUN/dataset.tar.gz" -C "$RUN"
python3 experiments/s2_verify.py "$RUN"
```

Nếu thư mục là kết quả root tạo trên VM, thao tác đọc/giải nén có thể cần sudo. Với bản clone do chính bạn sở hữu, thường không cần. Công cụ runner thực thi lab dùng Linux; phân tích archive bằng audit_scenarios.py dùng Python chuẩn và có thể chạy trên máy quản trị.

## 9. Kiểm tra lại nhiều lượt mà giữ nguyên dữ liệu cũ

Từ Testbed_Online_Boutique:

```bash
python3 experiments/audit_scenarios.py --output experiments/audits/my-review.json
```

Trên VM có run chỉ root đọc được, thêm sudo. Tool đọc archive hoặc dữ liệu trực tiếp, chạy verifier trong thư mục tạm, kiểm tra raw/source và ghi báo cáo riêng. Nó rà các **pilot hoàn tất**, đồng thời liệt kê các lượt smoke, interrupted và failed dưới nhóm loại khỏi tập pilot. Đây không phải lệnh sinh tấn công mới.

Mong đợi `passed=true`, `pilots_passed=pilots_reviewed`. Mở report để đọc limitations: một số S1 cũ và pilot S2 đầu chưa có source snapshot, nên kiểm tra được raw hành vi nhưng chưa tái dựng được toàn bộ source từ archive của lượt đó.

## 10. Dừng và kiểm tra dọn dẹp

Đợi bình thường là cách hoàn tất một lượt. Khi cần dừng, nhấn Ctrl+C trong terminal runner và chờ cleanup. Lượt dừng được giữ status interrupted; giữ dữ liệu để kiểm tra và chạy một lượt mới khi lab đã về trạng thái nghỉ.

```bash
sudo k3s kubectl -n boutique get deployment loadgenerator
sudo k3s kubectl -n boutique get pods -l app=gd4-actor
sudo k3s kubectl -n boutique get serviceaccounts -l experiment-run
```

Mong đợi loadgenerator 0; không còn Pod/SA thí nghiệm. Pod có thể ở Terminating vài chục giây rồi biến mất. Các Pod ứng dụng Online Boutique và agent Tetragon vẫn cần hoạt động.

Nếu SSH mất kết nối hoặc bị tắt đột ngột, kiểm tra trạng thái thực tế trước khi bật lại. Không xóa toàn bộ namespace boutique để dọn một run.

## 11. Các lỗi người mới thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra | Cách xử lý |
| --- | --- | --- |
| No such file runner.py | Đứng sai thư mục | pwd; ls experiments/runner.py; cd lại đúng bản làm việc |
| Permission denied khi đọc runs | Run do sudo/root tạo | Dùng sudo cho lệnh đọc, không đổi quyền toàn bộ cluster |
| loadgenerator must have 0 replicas | Tải đang chạy từ lượt khác hoặc bạn bật tay | Kiểm tra terminal runner/trạng thái; kết thúc lượt cũ trước |
| Resource temporarily unavailable / lock | Một runner đang giữ khóa | Chờ lượt đó hoặc dừng nó có cleanup |
| expected one agent / node not Ready | Agent hoặc worker chưa sẵn sàng | get nodes; get pods -n telemetry -o wide; xử lý hạ tầng trước |
| rollout timeout / ImagePullBackOff | Pod chưa chạy, image/network/resource có lỗi | describe Pod; xem Events; chưa kết luận thành công |
| normalized.ndjson không có trong clone | Dữ liệu đang ở archive | Giải nén dataset.tar.gz trước verifier |
| S3 chỉ có 3 lần đọc fixture | Dùng smoke không ghi runtime profile | Dùng đúng --s3-profile runtime |
| S1 có timeout | Cổng đích không đáp ứng, trong đó cổng 65000 là đối chứng | Đọc receipt và event; timeout vẫn là một lần thăm dò |
| passed=false | Bằng chứng thiếu hoặc kiểm tra không đạt | Xem unmatched_operations, actor.stderr, raw/*.stderr và manifest.error |
| Grafana không có alert S1–S3 | Dashboard hiện chủ yếu hiển thị metric | Đọc raw/verifier; detector/alert sẽ triển khai ở GĐ5 |

Giữ tên run, câu lệnh đã chạy và error đầy đủ khi kiểm tra lỗi. Những thông tin này giúp phân biệt lỗi môi trường, hành vi và đường thu dữ liệu.
