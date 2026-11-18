# Kế hoạch GĐ4 mô phỏng S1–S5 và xây dựng dữ liệu có nhãn

Ngày lập kế hoạch 18/11/2026, giờ Việt Nam.

Kế hoạch bám mục 5, 6.2, 9 và 11 của đề cương luận văn. GĐ4 kéo dài tuần 11–14, với sản phẩm bàn giao là bộ dữ liệu attack/normal có nhãn và script tái lập S1–S5. Các mức tải, thời lượng, số lượt lặp và ngưỡng dừng dưới đây là phương án triển khai đề xuất cho lab ba VM, mỗi VM 4 GB RAM. Sau lượt thử ngắn, ghi cấu hình đã chốt vào manifest và giữ cố định trong các lượt so sánh.

## 1. Mục tiêu và điểm bắt đầu

GĐ4 đưa vào lab những hành vi đã biết trước nguồn, đích và thời điểm. Telemetry được đối chiếu với nhật ký thực hiện để tạo nhãn có thể kiểm tra lại. Detector ở GĐ5 sẽ dùng dữ liệu này để học hoặc đánh giá. Cơ chế giảm thiểu tự động thuộc GĐ6.

Lab hiện có các thành phần sau.

| Thành phần | Hiện trạng được ghi nhận |
| --- | --- |
| Kubernetes | K3s, một control-plane và hai worker |
| Control-plane | lab-cp, 192.168.141.142 |
| Worker | lab-w1, 192.168.141.143 và lab-w2, 192.168.141.144 |
| Workload | Online Boutique v0.10.7 trong namespace boutique |
| Giám sát | Prometheus và Grafana |
| Agent | Tetragon 1.8.0 trên cả hai worker |
| Quan sát mạng | tcp_connect và tcp_sendmsg |
| Quan sát tiến trình | process_exec và process_exit |
| S0 đã có | 10 user ảo, warm-up 400 giây, đo 900 giây |
| Log S0 | 141.642 sự kiện, gồm 141.639 sự kiện gửi TCP |
| Phân tích ban đầu | 16 luồng gửi về phía server, suy ra từ cổng Service và EndpointSlice |

Các kết quả này cho phép bắt đầu GĐ4. Trước khi chạy S3, cần bổ sung sự kiện truy cập file. Sau khi cập nhật cấu hình thu, chạy lại S0 bằng chính cấu hình mới để so sánh với các lượt attack.

Baseline hiện tại là một mẫu quan sát. Các luồng được phép cần được đối chiếu với mã nguồn và cấu hình ứng dụng. Ví dụ, checkoutservice có thể gọi paymentservice theo nghiệp vụ. Một cạnh vắng mặt trong mẫu S0 vẫn cần được kiểm chứng trước khi gán ý nghĩa vi phạm.

## 2. Những gì phải chuẩn bị trong tuần 11

### 2.1. Chốt danh sách giao tiếp kỳ vọng

Lập file expected-communications.csv từ cấu hình và mã nguồn Online Boutique. Mỗi hàng gồm nguồn, đích, giao thức, cổng Service, cổng Pod, phương thức API nếu có, lý do nghiệp vụ và tài liệu hoặc vị trí mã nguồn chứng minh.

Đối chiếu danh sách này với 16 luồng đã quan sát. Chuẩn hóa IPv4 và địa chỉ IPv4-mapped IPv6 trước khi tra cứu. Ghi riêng các địa chỉ chưa xác định, gồm 10.42.1.1 và 10.42.2.1 trong lượt S0 hiện tại. Cần kiểm tra interface CNI, probe và đường NAT trước khi đặt tên cho các địa chỉ đó.

Tài liệu này là căn cứ chọn nguồn trái luồng ở S2 và diễn giải kết quả về sau.

### 2.2. Hoàn thiện đường thu telemetry

| Loại tín hiệu | Dùng cho | Việc chuẩn bị |
| --- | --- | --- |
| Lần thử mở TCP | S1, S2, S5 | Giữ tcp_connect, kiểm thử cả kết nối thành công và thất bại |
| Gửi dữ liệu qua TCP | S2, S4, S5 | Giữ tcp_sendmsg, lưu socket và bytes_requested |
| Chạy tiến trình | S1, S2, S3, S5 | Lưu binary, PID nếu có, exec_id, parent_exec_id và đối số được phép lưu |
| Truy cập file | S3 | Bổ sung policy phù hợp kernel, kiểm thử nhận diện đường dẫn file và kết quả thao tác |
| Ngữ cảnh Kubernetes | Tất cả | Lưu Pod UID, container ID, node, namespace, workload, image và service account qua metadata/snapshot |
| Chất lượng đường thu | Tất cả | Ghi agent UID/restart, lỗi export, mất sự kiện, stderr và lượng log |
| Kết quả ứng dụng | S2, S4, S5 | Lưu receipt phía client, metric Locust và receipt phía nhận nếu có |

Trước khi dùng policy file trong thí nghiệm, phải kiểm thử bằng một thao tác đọc file đã biết trên mỗi worker. Chọn hook cụ thể sau khi xác nhận nó hoạt động trên kernel 5.15 của lab. Tài liệu triển khai sẽ ghi tên hook, trường dữ liệu và giới hạn quan sát thực tế.

Bộ chuẩn hóa phải nhận các policy mới. File normalize.py hiện gắn scenario=S0 và chỉ nhận hai hook mạng. Khi mở rộng, scenario phải lấy từ manifest của lượt chạy. Giữ bộ log cũ với phiên bản schema gốc và ghi phiên bản schema mới trong các lượt tiếp theo.

Tetragon hiện lọc namespace boutique. Pod mô phỏng nguồn tấn công sẽ ở boutique để đường thu hiện tại quan sát được nó. Thành phần nhận dữ liệu của S5 có thể ở máy hoặc namespace riêng.

### 2.3. Chuẩn bị bộ điều phối thí nghiệm

Bộ điều phối, còn gọi là runner, thực hiện một lượt từ đầu tới cuối. Nó phải làm được các việc sau.

1. Kiểm tra worker, ứng dụng, agent, dung lượng đĩa và đồng hồ UTC.
2. Ghi manifest cùng phiên bản script, image và policy.
3. Thu log hai worker và chụp topology trước khi chạy tải.
4. Bật Locust 10 user, RATE=1 và đợi đủ user.
5. Warm-up 400 giây, sau đó thu khoảng bình thường trước attack.
6. Ghi mốc bắt đầu, thực hiện một kịch bản và ghi kết quả từng thao tác.
7. Dừng hành vi mô phỏng, thu tiếp giai đoạn hồi phục.
8. Lưu snapshot cuối, metric, log ứng dụng và dữ liệu chuẩn hóa.
9. Gán nhãn từ nhật ký thao tác và kiểm tra chất lượng dữ liệu.
10. Dọn tài nguyên của lượt chạy và đưa loadgenerator về trạng thái trước lượt đo.

Runner dùng khóa chung để tránh hai lượt thí nghiệm chạy chồng nhau, kể cả khi một terminal đang chạy script S0 cũ. Nếu thu log bị đứt hoặc nhận Ctrl+C, vẫn lưu kết quả đã thu, dừng client mô phỏng và đánh dấu lượt bị gián đoạn.

### 2.4. Chuẩn bị Pod mô phỏng

Tạo Pod có tên riêng theo run_id, label ghi mã kịch bản, placement xác định và image được pin phiên bản hoặc digest. Pod được đặt requests/limits, không có quyền đặc biệt và tắt automount token khi kịch bản không cần token.

Pod này đại diện cho điểm xuất phát đã bị compromise. Việc giả lập bằng một Pod riêng cần được mô tả trong báo cáo để phân biệt với trường hợp thực sự chạy lệnh trong container ứng dụng.

Với S2, chốt vai trò nguồn mô phỏng và quyền kỳ vọng trước lượt chạy. Với S3, chuẩn bị fixture token giả. Khi cần mở rộng sang projected service account token thật ở bước sau, phải ghi rõ phạm vi thử mới và bảo đảm collector không lưu nội dung token.

## 3. Quy trình chung của một lượt

Mỗi lượt chỉ chạy một kịch bản chính để gán nhãn rõ nguồn gây tác động. Locust tiếp tục tạo traffic bình thường trong các lượt S1–S5.

| Pha | Thời lượng đề xuất | Mục đích |
| --- | ---: | --- |
| Setup | Theo thời gian khởi động | Tạo Pod, kiểm tra endpoint, hoàn tất công việc chuẩn bị |
| Warm-up | 400 giây sau khi Locust đủ user | Đưa ứng dụng vào trạng thái có tải |
| Pre-attack | 120 giây | Ghi hoạt động bình thường ngay trước attack |
| Attack | Tùy S1–S5 | Thực hiện hành vi theo manifest |
| Recovery | 120 giây | Kiểm tra tác động có kết thúc và dịch vụ hồi phục |
| Finalize | Theo lượng dữ liệu | Đóng luồng thu, chuẩn hóa, gán nhãn, kiểm tra và đóng gói |

Các pha dùng UTC và khoảng thời gian dạng [start, end). Setup và warm-up được giữ trong log gốc và gắn phase riêng.

Mốc thời gian lấy từ bộ điều phối và client. Kiểm tra chênh lệch đồng hồ giữa các node trước lượt đo. Nếu sai lệch vượt mức dung sai đã chọn cho độ phân giải nhãn, lưu độ lệch và sửa đồng bộ trước lượt chính thức.

## 4. Thiết kế từng kịch bản

### S1 quét service và cổng nội bộ

Mục tiêu là tạo hành vi thăm dò nhiều đích trong danh sách đã xác định.

- Nguồn là Pod mô phỏng trong boutique.
- Danh sách đích lấy từ Service của Online Boutique, gồm cổng ứng dụng và một số cổng đóng đã chỉ định.
- Mỗi lượt dự kiến kéo dài tối đa 120 giây, tối đa 5 lần thử kết nối mỗi giây, concurrency tối đa 2 và timeout mỗi lần 1 giây.
- Lưu một receipt cho từng lần thử với địa chỉ, cổng, thời điểm và kết quả open/refused/timeout/error.
- Giới hạn tổng số lần thử bằng cả số mục tiêu và thời gian. Ghi lại thứ tự hoặc seed để tái lập.

Telemetry cần có danh tính nguồn, đích và các lần thử mở kết nối. Đếm số đích, số cổng và số lần thử trong từng cửa sổ thời gian.

Một lần mở kết nối thất bại vẫn có thể là bằng chứng hành vi thăm dò. Receipt client cung cấp kết quả kết nối. Hook tcp_connect có phạm vi phụ thuộc đường đi trong kernel, nên phải đối chiếu số lần thử và số sự kiện thực sự quan sát được.

Nghiệm thu khi biết rõ các đích đã thử, kết quả từng lần và mức độ đối chiếu được giữa receipt với telemetry. Các thao tác thiếu sự kiện phải được thống kê.

### S2 gọi service ngoài luồng được phép

Mục tiêu là tạo một cuộc gọi từ vai trò nguồn đã xác định là không có quyền nghiệp vụ đến paymentservice hoặc checkoutservice.

- Bắt đầu với paymentservice và một API cụ thể, ghi đầy đủ phương thức gRPC trong manifest.
- Chuẩn bị protobuf/client tương thích phiên bản v0.10.7 trước khi đo. Lưu checksum của định nghĩa API.
- Dùng dữ liệu giao dịch giả của ứng dụng demo.
- Mỗi lượt dự kiến 60 giây, 1 lần gọi mỗi 2 giây, tổng tối đa 30 lần.
- Lưu phương thức, số thứ tự thao tác, request_id nếu có, thời gian và mã kết quả gRPC.

Phân biệt các mức bằng chứng gồm đã thử TCP, đã kết nối, đã tới phương thức API và API trả kết quả. Chỉ gọi health check thì phạm vi kết luận là truy cập health endpoint. Để kiểm tra API nhạy cảm, cần gọi đúng phương thức đã chốt.

Ở GĐ4, ứng dụng có thể chấp nhận cuộc gọi vì chính sách chặn sẽ được triển khai ở GĐ6. Nhãn attack của S2 thể hiện nguồn và hành vi trái với ma trận quyền đã xác định, có căn cứ trong manifest.

Nghiệm thu khi có bằng chứng nguồn và đích, phương thức đã thử cùng kết quả client. Ghi rõ mức độ chứng minh được ở tầng TCP và tầng API.

### S3 lạm dụng runtime và đọc token mô phỏng

Mục tiêu là thu cả chuỗi tiến trình và hành vi truy cập file.

Chia thành các thao tác có operation_id riêng.

1. Mở shell trong Pod mô phỏng.
2. Chạy công cụ mạng tới endpoint đã biết trong lab.
3. Đọc file fixture token giả, bỏ nội dung đọc và ghi receipt cho biết thao tác đã chạy.
4. Kết thúc tiến trình thử và ghi trạng thái trả về.

Mỗi lượt dự kiến 90 giây. Các thao tác có khoảng nghỉ cố định để dễ đối chiếu timestamp và quan hệ cha–con.

File fixture chứa chuỗi dữ liệu giả tại đường dẫn được chốt và lưu trong manifest. Việc dùng token giả chứng minh khả năng quan sát thao tác đọc file nhạy cảm mô phỏng. Báo cáo phải ghi rõ giới hạn này khi so với hành vi lấy credential thật.

Telemetry cần có exec_id và parent_exec_id nếu nguồn cung cấp, binary, đường dẫn file và kiểu thao tác. Collector chỉ lưu metadata về truy cập file. Các trường đối số có nguy cơ chứa credential cần được lọc trước khi xuất dữ liệu.

Nghiệm thu khi kiểm tra được cả shell/công cụ và thao tác file, đối chiếu với operation_id. Process event đơn lẻ chưa chứng minh file đã được đọc.

### S4 DoS nội bộ mức nhẹ

Mục tiêu là tạo tải phụ có kiểm soát và đo tác động lên một service trong khi Locust vẫn chạy.

- Chọn frontend ở bước đầu, gọi một URL đọc dữ liệu đã xác định.
- Tạo client tải riêng, lưu mỗi request với timestamp, mã HTTP, thời gian phản hồi và lỗi.
- Thử pilot tại 3 request/giây, concurrency tối đa 2.
- Nếu lab giữ ổn định, có thể nâng thử lên 6 rồi 10 request/giây, concurrency tối đa 4.
- Mỗi profile giữ 30 giây trong lượt pilot. Chọn một profile và thời lượng 90 giây cho bộ dữ liệu chính thức.
- Nếu profile được chọn tạo tác động thấp, ghi đúng mức tác động quan sát được và điều chỉnh có lưu phiên bản.

Đây là mục tiêu gửi tối đa. Client phải ghi tốc độ thực đạt được. Thời gian timeout, concurrency và chi phí xử lý có thể làm tốc độ thực thấp hơn cấu hình.

Theo dõi request rate, lỗi HTTP, độ trễ và CPU/RAM của đích. Thu riêng số liệu từ client tải phụ và người dùng Locust. Muốn tính p95 theo pha, cần dữ liệu latency theo request hoặc histogram có cửa sổ phù hợp. Log Locust tích lũy hiện có cần được mở rộng cho mục đích này.

Ngưỡng dừng đề xuất cho pilot gồm node MemoryPressure, workload OOM hoặc tăng restart, hoặc probe frontend timeout 3 lần liên tiếp. Bộ giám sát kiểm tra mỗi 5 giây và ghi lý do dừng. Ngưỡng cảnh báo lỗi/latency bổ sung sẽ được chốt sau khi đo độ biến động của S0.

Nghiệm thu khi có cấu hình tải, tốc độ thực tế, mức tác động đo được và trạng thái hồi phục. Nếu runner dừng sớm, giữ lượt đó với trạng thái interrupted và thời lượng thực.

### S5 gửi dữ liệu giả tới endpoint lab

Mục tiêu là thu hành vi gửi payload giả tới một đích ngoài nhóm dịch vụ nghiệp vụ của Boutique.

- Chạy receiver HTTP do mình kiểm soát tại một VM trong mạng lab, ngoài mạng Pod. Phương án đầu tiên là lab-cp:18080.
- Kiểm tra route từ Pod và cấu hình firewall để nguồn lab dự kiến tới được receiver.
- Receiver chỉ phục vụ payload giả, có giới hạn kích thước và thời gian hoạt động.
- Payload đề xuất 64 KiB mỗi lượt gửi, một lần mỗi giây trong 60 giây, tổng khoảng 3,75 MiB.
- Mỗi lần gửi có operation_id, checksum và số byte payload.
- Receiver lưu thời gian, operation_id, số byte thực nhận và checksum.

Việc đặt receiver trên lab-cp cần được ghi trong topology. Khi đo overhead, tách tiến trình receiver khỏi tài nguyên ứng dụng vì nó cùng chạy trên một VM của lab.

Nếu không dùng được receiver ngoài mạng Pod, có thể làm pilot với receiver ở namespace riêng. Khi đó ghi topology là endpoint lab trong cluster và chỉ kết luận trong phạm vi đã kiểm chứng.

Đối chiếu bytes_requested ở hook với số byte phía client/receiver. Có thể có header HTTP, phân mảnh lần ghi và gửi lỗi, nên hai bộ đếm có ý nghĩa khác nhau.

Nghiệm thu khi biết Pod gửi, endpoint nhận, thời điểm và checksum của dữ liệu giả. Kết nối TCP thành công đơn lẻ chưa chứng minh receiver đã nhận payload.

## 5. Cách gán nhãn và tránh nhãn sai

### 5.1. Phân biệt bối cảnh lượt chạy và nhãn sự kiện

Một lượt S2 có thể đồng thời chứa người dùng mua hàng bình thường và Pod mô phỏng gọi payment. Vì vậy scenario_id=S2 mô tả kịch bản của lượt chạy. Trường label cho biết từng bản ghi hoặc cửa sổ được xác định như thế nào.

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| run_id | s2-<utc>-r01 | Mã duy nhất của lượt |
| scenario_id | S0…S5 | Kịch bản được thực hiện |
| phase | setup/warmup/pre_attack/attack/recovery | Pha của lượt |
| operation_id | s2-call-0007 | Thao tác do script thực hiện |
| label | normal/attack/unknown | Nhãn của bản ghi hoặc đơn vị mẫu |
| attack_type | unauthorized_service_call | Kiểu hành vi |
| evidence | actor_receipt / process_lineage / matched_socket | Căn cứ gán nhãn |
| outcome | attempted/connected/api_reached/received/failed | Mức kết quả đã chứng minh |
| label_version | v1 | Phiên bản quy tắc nhãn |

Nhãn lấy từ nhật ký thực nghiệm và bằng chứng thực hiện. Các cảnh báo của detector về sau được lưu riêng để so sánh với nhãn này.

Các thao tác chuẩn bị Pod, tải image, kiểm tra tool và thử kết nối trước attack được đánh dấu phase tương ứng. Nếu cùng một shell chạy cả chuẩn bị và attack, timestamp và operation_id phải đủ để phân biệt.

### 5.2. Nhãn ở mức sự kiện

- Sự kiện từ tiến trình mô phỏng, trong thời gian thao tác đã ghi nhận, được gán attack khi khớp loại hành vi cần mô phỏng và danh tính Pod/tiến trình.
- Sự kiện tiến trình con có thể liên kết bằng exec_id/parent_exec_id khi đủ thông tin.
- Traffic nền có nguồn và ngữ cảnh xác định được gán normal theo quy tắc đã ghi.
- Sự kiện chưa đủ bằng chứng hoặc có nhiều cách ánh xạ được gán unknown.
- Response của server có thể liên quan đến attack. Cần đối chiếu socket, thời gian, NAT và receipt trước khi gán nhãn quan hệ đó. Cờ attack_related có thể lưu riêng khi chỉ chứng minh được quan hệ với thao tác.
- Mỗi bản ghi chuẩn hóa giữ liên kết tới file raw, số dòng hoặc mã định danh sự kiện để truy vết.

### 5.3. Nhãn ở mức cửa sổ

Tạo mẫu theo Pod UID và cửa sổ 10 giây. Đây là giá trị khởi đầu đề xuất, có thể so sánh thêm cửa sổ khác ở GĐ5.

Một cửa sổ lưu số thao tác attack đã xác nhận, số sự kiện normal và số sự kiện unknown. Cửa sổ có thao tác attack được xác nhận có thể mang nhãn attack ở cấp cửa sổ, đồng thời giữ các bộ đếm trên.

Khi tách dữ liệu để đánh giá ở GĐ5, chia theo lượt chạy. Ghi trước nhóm lượt dùng để phát triển và nhóm giữ lại để đánh giá. Các bản ghi gần nhau trong một lượt có liên hệ thời gian, nên cần tránh trộn chúng qua các tập một cách ngẫu nhiên.

### 5.4. Các trường hợp bình thường dễ gây nhầm

Bổ sung lượt bình thường có thao tác quản trị được ghi lại, chẳng hạn shell kiểm tra hoặc wget chẩn đoán. Lượt này giúp GĐ5 kiểm tra quy tắc cảnh báo có nhầm mọi shell hoặc công cụ mạng thành attack hay không.

Nhãn normal cho hành vi quản trị phải có nhật ký người thực hiện, mục đích và thời gian. Các trường hợp này được lưu riêng với normal user traffic.

## 6. Số lượt và thứ tự thực hiện

Phương án bộ dữ liệu ban đầu gồm ba lượt S0 theo cấu hình telemetry mới và ba lượt cho mỗi S1–S5. Tổng cộng 18 lượt chính thức, cùng các lượt pilot và một số lượt quản trị bình thường đã ghi nhãn.

Trong mỗi kịch bản, lần lượt đặt actor ở w1, w2 rồi w1. Ghi rõ phân bố node còn lệch khi phân tích. Khi cần so sánh định lượng giữa node, mở rộng thành bốn lượt mỗi kịch bản để có hai lượt trên mỗi worker.

| Nhóm | Pilot | Lượt chính thức đề xuất |
| --- | --- | --- |
| S0 | Kiểm tra thu đủ event và metric | 3 × 15 phút, dùng telemetry mới |
| S1 | Kiểm tra danh sách đích và receipt | 3 lượt, attack tối đa 120 giây |
| S2 | Kiểm tra client/API | 3 lượt, attack 60 giây |
| S3 | Kiểm tra hook file ở cả hai worker | 3 lượt, attack 90 giây |
| S4 | Thử 3/6/10 request mỗi giây có giới hạn | 3 lượt với profile đã chốt, 90 giây |
| S5 | Kiểm tra receiver và checksum | 3 lượt, attack 60 giây |
| Normal quản trị | Ghi rõ thao tác được phép | Bổ sung ít nhất một lượt có shell/tool chẩn đoán |

Thực hiện pilot theo thứ tự S1, S2, S3, S5 rồi S4 để kiểm tra các đường thu trước khi tạo tải cao. Trong tập chính thức, xen kẽ các lượt S0 và thay đổi thứ tự kịch bản có ghi seed hoặc thứ tự cụ thể để giảm ảnh hưởng do trạng thái cụm thay đổi theo thời gian.

Các lượt pilot được đánh dấu riêng. Nếu cấu hình telemetry hoặc profile thay đổi sau pilot, manifest của lượt chính thức phải thể hiện cấu hình cuối.

## 7. Kế hoạch tuần 11–14

| Tuần | Công việc | Sản phẩm bàn giao | Kiểm tra trước khi chuyển việc |
| --- | --- | --- | --- |
| 11 | Chốt ma trận giao tiếp, bổ sung file events/schema, viết runner và quy tắc nhãn | Manifest mẫu, smoke test telemetry, script điều phối khung, tài liệu nhãn | Thu được mạng/tiến trình/file trên hai worker, runner dọn được khi dừng |
| 12 | Viết và pilot S1/S2, thu S0 mới và một số lượt có nhãn | Script scan/gọi API, receipt, tập dữ liệu thử S0/S1/S2 | Đối chiếu được client với telemetry, phân biệt API và kết nối |
| 13 | Viết và pilot S3/S5/S4, hoàn thiện nguồn đo ứng dụng | File events, receiver receipt, request-level latency, script từng kịch bản | Chứng minh đọc file, nhận payload, tạo và dừng tải có kiểm soát |
| 14 | Chạy các lượt lặp, kiểm tra nhãn, kiểm tra tái lập và đóng gói | Dataset v1, báo cáo, dashboard, checksum, script tái lập | Đủ các kịch bản hoặc ghi rõ trường hợp chưa đạt, không bỏ lượt lỗi khỏi kiểm kê |

Nếu thu thập sớm xong, có thể chạy lặp ngay trong tuần 12–13. Mốc tuần là kế hoạch công việc, không bắt buộc phải chờ hết tuần mới chuyển bước.

## 8. Cấu trúc file dự kiến

Các tên dưới đây mô tả bộ deliverable sẽ triển khai sau khi chốt kế hoạch.

```text
Testbed_Online_Boutique/
  experiments/
    README.md
    expected-communications.csv
    labeling.md
    manifests/
      actor.yaml
      file-fixture.yaml
    policies/
      observe-files.yaml
    scenarios/
      s1-recon.sh
      s2-service-call.sh
      s3-runtime-abuse.sh
      s4-load.sh
      s5-exfil-sim.sh
    runner.sh
    label.py
    summarize.py
    receiver.py
  runs/
    s2-<utc>-r01/
      manifest.json
      timeline.ndjson
      actor-receipts.ndjson
      receiver-receipts.ndjson
      topology-before.json
      topology-after.json
      raw/
        lab-w1.ndjson
        lab-w2.ndjson
      normalized.ndjson
      labeled-events.ndjson
      labeled-windows.csv
      application-metrics/
      quality.json
      summary.md
      SHA256SUMS.txt
```

Một số file chỉ có ở kịch bản tương ứng, ví dụ receiver-receipts ở S5. Chỉ tạo file cho dữ liệu thực tế đã thu.

Manifest phải ghi image digest, Git commit của script, phiên bản chart/agent, policy hash, schema version, thời lượng cấu hình và thực tế, placement, seed, danh sách đích, cấu hình Locust, kết quả dừng và lý do nếu có.

Receiver/client giữ nội dung payload ở mức dữ liệu giả cần đối chiếu. Dữ liệu nhạy cảm thật và nội dung credential không thuộc dataset dự kiến.

## 9. Tiêu chí nghiệm thu GĐ4

GĐ4 được chốt khi đạt các mục sau.

1. Có script/YAML chạy lại được S1–S5 và tài liệu nêu hành vi mô phỏng, nguồn, đích, giới hạn và cách dọn.
2. Mỗi kịch bản có ít nhất một lượt chứng minh end-to-end. Bộ dữ liệu ban đầu hướng tới ba lượt mỗi kịch bản và ba lượt S0 mới.
3. Có nhật ký thao tác độc lập với telemetry để đối chiếu nhãn và kết quả.
4. Thu được loại tín hiệu phù hợp cho từng kịch bản, đặc biệt file events cho S3 và receipt phía nhận cho S5.
5. Mọi lượt đều có trạng thái completed/interrupted/failed và thời lượng thực. Danh mục dataset giữ cả các lượt chưa đạt cùng nguyên nhân.
6. Chất lượng thu được báo cáo bằng số dòng không hợp lệ, metadata thiếu, sự kiện chưa ánh xạ, agent restart, lỗi export và metric mất sự kiện nếu có.
7. Có đối chiếu trước/sau về workload, traffic bình thường và tài nguyên. Biểu đồ dùng đúng mốc UTC của lượt.
8. Có schema, phiên bản quy tắc nhãn, checksum và hướng dẫn mở dữ liệu từ GitHub.
9. Có bằng chứng chạy lại một lượt từ hướng dẫn với cùng cấu hình và xác nhận hành vi cần mô phỏng tái xuất hiện.
10. Các giới hạn như tải nhẹ chưa gây giảm dịch vụ, endpoint S5 trong lab, fixture token giả và IP chưa xác định được ghi trong báo cáo.

Các số liệu recall, precision, false positive rate, detection latency và mitigation latency được đánh giá khi triển khai module tương ứng ở GĐ5/GĐ6. Trong GĐ4, trọng tâm là hành vi thực hiện được và dữ liệu có nhãn đủ tin cậy cho bước đó.

## 10. Việc làm đầu tiên sau kế hoạch

Bắt đầu bằng ma trận giao tiếp kỳ vọng và phiên bản schema/manifest cho thí nghiệm. Tiếp theo bổ sung hook file, sửa collector nhận scenario, ghi timeline cùng receipt, rồi kiểm thử runner với lượt rất ngắn.

Khi đường thu và nhãn đã được kiểm chứng, thực hiện S1 pilot. Kết quả pilot sẽ quyết định cấu hình cụ thể của những lượt chính thức.



## Tiến độ triển khai ngày 18/11/2026

Đã bắt đầu phần chuẩn bị tuần 11 và pilot S1. Hướng dẫn dùng bộ công cụ hiện tại nằm trong [IMPLEMENTATION.md](IMPLEMENTATION.md). Ma trận [expected-communications.csv](expected-communications.csv) có 17 cạnh cấu hình, gồm 16 cạnh tới dịch vụ đang triển khai và một cạnh tới thành phần tùy chọn.

Hai lượt smoke file trên lab-w1 và lab-w2 đã đối chiếu được 3/3 thao tác đọc fixture ở mỗi lượt. Lượt S1 pilot đầu trên lab-w1 đã đối chiếu được 22/22 thao tác TCP và gán 22 sự kiện attack theo receipt. Đây là kết quả pilot với warm-up và cửa sổ trước/sau rút ngắn.

Các kịch bản S2, chuỗi runtime abuse S3 đầy đủ, S4 và S5 nằm trong các bước tiếp theo. Bộ dữ liệu chính thức và các lượt lặp sẽ được thu sau khi kiểm chứng từng pilot.

Báo cáo checkpoint và các lượt kiểm thử nằm trong [RESULTS.md](RESULTS.md).
