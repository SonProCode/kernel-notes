# Rà soát mức đáp ứng S2 theo đề cương

Ngày rà soát 20/11/2026, giờ Việt Nam.

Kết luận là S2 đã có bằng chứng đáp ứng hành vi mô phỏng và đường thu dữ liệu ở mức pilot GĐ4. Phần thực nghiệm chính thức và các kết quả phát hiện/giảm thiểu của toàn luận văn vẫn cần được thực hiện theo các giai đoạn tương ứng.

Đối chiếu trực tiếp mục 5, 6.2, 9 và 11 của đề cương. Mục 9 mô tả S2 là Pod A gọi trực tiếp payment/checkout ngoài luồng hợp lệ, với dấu hiệu kỳ vọng là cạnh service-call trái baseline và cơ chế giảm thiểu gợi ý là Istio AuthorizationPolicy deny. Mục 11 phân việc tạo dữ liệu có nhãn ở GĐ4, phát hiện ở GĐ5 và mitigation ở GĐ6. [Đề cương gốc](https://github.com/SonProCode/kernel-notes/blob/main/de_tai_ebpf_zero_trust_microservices%20%281%29.docx)

## 1. Bằng chứng đã kiểm tra lại

Kiểm tra lại độc lập từ file raw của hai lượt 30 RPC, thay vì chỉ đọc cờ passed trong s2-verification.json.

| Kiểm tra | Kết quả |
| --- | --- |
| Gọi API thật của ứng dụng demo | 30/30 Charge trả OK và UUID ở mỗi worker |
| Chạy từ nguồn ngoài vai trò checkout | Actor dùng SA gd4-1242543 hoặc gd4-1246649; caller hợp lệ trong snapshot dùng SA checkoutservice |
| Đích và phương thức | paymentservice:50051, /hipstershop.PaymentService/Charge |
| Quan hệ kỳ vọng | Matrix đã lưu trong source snapshot xác định checkoutservice là caller được cấu hình tới paymentservice |
| Truy vết sự kiện mạng | Từng sự kiện được gán attack có raw_line đúng, Pod UID khớp actor, IP/cổng khớp đích và timestamp trong khoảng RPC |
| Độ phủ thao tác | 30/30 thao tác ở mỗi lượt có ít nhất một sự kiện mạng khớp |
| Log gốc đã kiểm | 34 sự kiện TCP ở lượt w1 và 35 ở lượt w2 |
| Snapshot mã nguồn | Các hash đã ghi trong manifest khớp source snapshot trong archive |
| Bằng chứng server | Mỗi thao tác có đúng một log handler khớp payload giả và thời gian theo verifier |
| Trạng thái lab khi rà soát | Ba node Ready; hai agent Running; payment/checkout sẵn sàng; loadgenerator=0; không còn actor |

Các con số trên xác nhận đường thực hiện, thu thập và đối chiếu dữ liệu. Việc phát hiện bằng detector sẽ được đánh giá khi có module GĐ5.

Script s2_audit.py kiểm tra lại identity, matrix, source hash và các dòng raw. Nó đọc dataset.tar.gz trên bản clone GitHub hoặc raw/normalized trực tiếp trên VM.

```bash
sudo python3 experiments/s2_audit.py \
  runs/s2-20261120T161015Z-1242543

sudo python3 experiments/s2_audit.py \
  runs/s2-20261120T161240Z-1246649
```

Kết quả nằm trong s2-audit.json của từng lượt. functional_pilot_checks_passed=true có phạm vi là các kiểm tra chức năng đã liệt kê trong script.

## 2. Đối chiếu từng yêu cầu và phạm vi kết luận

| Nội dung | Mức đáp ứng hiện tại | Phần còn lại |
| --- | --- | --- |
| Mô phỏng nguồn đã bị compromise | Đã dùng actor đại diện, có identity riêng và mô tả rõ vai trò | Khi cần mở rộng, có thể thêm biến thể dùng identity của một service nghiệp vụ ngoài checkout |
| Gọi trực tiếp service nhạy cảm | Đã gọi Charge của payment | Phạm vi hiện tại là payment; đề cương nêu payment/checkout và chưa ấn định phải làm cả hai |
| Cạnh trái luồng bình thường | Đã có source-role ngoài checkout và bằng chứng mạng tới payment, đối chiếu matrix | Cần đóng băng ma trận quyền/luồng kỳ vọng trong tập chính thức; đây sẽ là đầu vào cho detector |
| Script tái lập | Có runner, proto, fixture, wheel khóa hash, source snapshot và cleanup | Chốt một release chung cho các lượt official |
| Dữ liệu attack/normal | Có nhãn từ nhật ký thao tác; có traffic Locust nền; sự kiện thiếu căn cứ giữ unknown | Thu S0 chính thức cùng cấu hình/schema và mô tả tập được dùng để huấn luyện/đánh giá |
| Phát hiện cạnh bất thường | Đã có dữ liệu để xây detector | Xây và đánh giá module ở GĐ5 |
| AuthorizationPolicy deny | Đã chuẩn bị identity nguồn/đích trong metadata | Triển khai và kiểm thử ở GĐ6 |
| Recall, precision, FPR, detection/mitigation latency | Chưa đo các chỉ số này | Đánh giá khi các module tương ứng hoạt động |

Theo giả định của đề cương, có thể mô phỏng một điểm xuất phát đã bị compromise. Việc khai thác lỗ hổng thực không phải bước bắt buộc của S2 trong phạm vi này.

Actor mới tạo thể hiện một vai trò ngoài quyền nghiệp vụ checkout. Bản mô phỏng này cần được mô tả đúng như vậy trong luận văn. Biến thể mang identity của một service nghiệp vụ khác có thể tăng độ bao phủ, nhưng cần được ghi thành biến thể thí nghiệm mới.

## 3. Những điểm cần hoàn thiện trước tập chính thức

### Cùng cấu hình và phiên bản

Hai lượt 30 RPC hiện đều mode=pilot, warm-up 30 giây, pre_attack 10 giây và recovery 10 giây. Thời gian hành vi quan sát được khoảng 61,965 giây ở w1 và 62,886 giây ở w2.

Trong quá trình hoàn thiện, hai lượt dùng hai bản runner khác nhau. Hash runner bắt đầu a3faa71808b9 ở lượt w1 và f0b0eba1be28 ở lượt w2. Lượt w2 có thêm verifier trong danh mục hash. Image actor giống nhau và nguồn từng lượt được lưu, nên có thể kiểm tra chính xác phần đã chạy.

Tập official cần dùng cùng một release cùng profile đã chốt. Các lượt pilot này được giữ làm bằng chứng phát triển và kiểm thử.

### Baseline và đối chứng

Đã có traffic mua hàng bình thường chạy song song trong các lượt S2 và baseline S0 cũ. Với cấu hình telemetry/schema mới, lượt S0 hiện có mới là smoke 15 giây.

Theo kế hoạch GĐ4 đã thống nhất, cần thu các lượt S0 chính thức theo cấu hình mới để so sánh. Có thể bổ sung một lượt đối chứng API hợp lệ cùng profile, nhằm kiểm tra việc phân biệt nguồn hợp lệ với nguồn ngoài quyền.

Đề cương không ấn định số lần lặp hoặc số RPC. Ba lượt chính thức và profile cụ thể là phương án đề xuất trong kế hoạch triển khai của lab.

### Cách diễn giải số liệu

30 RPC cùng một lượt dùng lại kênh gRPC. Các RPC có liên hệ thời gian và cùng điều kiện hệ thống. Khi đánh giá thống kê, cần ghi rõ đơn vị thí nghiệm là lượt chạy và số lần lặp độc lập.

30/30 thao tác có log khớp là độ phủ đối chiếu dữ liệu trong lượt đó. Recall của detector cần dựa vào cảnh báo do detector phát ra và nhãn ground truth độc lập.

Tên phương thức API trong bản ghi chuẩn hóa lấy từ receipt. Log Tetragon cung cấp bằng chứng kernel về tiến trình và socket. Log handler server được đối chiếu bằng payload giả và thời gian, với dung sai 2 giây được ghi công khai. Đây là tương quan nhiều nguồn; quan sát kernel hiện tại chưa giải mã payload gRPC.

Các sự kiện unknown được giữ nguyên. Khi xây tập đánh giá, cần nêu rõ quy tắc sử dụng hoặc loại các mẫu này thay vì tự chuyển toàn bộ thành normal.

## 4. Đề xuất nghiệm thu

Có thể chốt checkpoint chức năng S2 của GĐ4 ở mức pilot với phạm vi đã mô tả. Trước khi chốt dataset chính thức, hoàn thành các lượt S0/S2 theo cùng release và profile đã chọn, giữ manifest cùng source snapshot và xác minh lại bằng các script hiện có.

Bộ phát hiện và chính sách chặn sẽ được nghiệm thu theo GĐ5/GĐ6. Khi đó cần thử nguồn hợp lệ vẫn gọi được, nguồn ngoài quyền bị chặn và đo các chỉ số đề cương yêu cầu.

Báo cáo S2 nên dùng cách diễn đạt “đã tái lập hành vi và xác minh dữ liệu pilot” cho kết quả hiện tại.
