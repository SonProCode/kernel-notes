# Phân tích baseline 15 phút

Phân tích sự kiện tcp_send trong cửa sổ đo của lượt này. Đích được đối chiếu với Service ClusterIP, EndpointSlice của hai snapshot và IP nguồn có danh tính workload trong log. Việc suy ra phía server dựa trên cổng lắng nghe trong Service và EndpointSlice.

Tổng cộng **141,639** sự kiện gửi TCP. Ánh xạ được **132,163** sự kiện tới một workload đích duy nhất. Có **16** luồng nguồn–đích–cổng gửi về phía server.

| Nguồn | Đích | Cổng đích quan sát được | Sự kiện gửi về phía server |
| --- | --- | ---: | ---: |
| frontend | productcatalogservice | 3550 | 23,036 |
| frontend | currencyservice | 7000 | 14,172 |
| frontend | cartservice | 7070 | 4,365 |
| frontend | recommendationservice | 8080 | 3,591 |
| recommendationservice | productcatalogservice | 3550 | 3,588 |
| frontend | adservice | 9555 | 2,798 |
| cartservice | redis-cart | 6379 | 2,643 |
| loadgenerator | frontend | 80 | 2,435 |
| frontend | shippingservice | 50051 | 1,328 |
| checkoutservice | currencyservice | 7000 | 604 |
| checkoutservice | productcatalogservice | 3550 | 498 |
| checkoutservice | shippingservice | 50051 | 431 |
| checkoutservice | cartservice | 7070 | 334 |
| frontend | checkoutservice | 5050 | 249 |
| checkoutservice | emailservice | 5000 | 234 |
| checkoutservice | paymentservice | 50051 | 166 |

Số lần gửi bao gồm hoạt động giao thức trên socket. Một lần gửi có thể chứa một phần hoặc nhiều thông điệp. bytes_requested là kích thước yêu cầu gửi tại hook. File edges.csv cũng chứa chiều gửi từ server về client, thường có cổng đích tạm thời.

Có 9476 sự kiện gửi tới IP chưa ánh xạ thành workload: 10.42.1.1 (2186 sự kiện), 10.42.2.1 (7290 sự kiện). Các địa chỉ này cần được đối chiếu với mạng CNI, kubelet và cấu hình probe. Phân loại chiều gửi dựa trên cổng là suy luận, cần kiểm chứng bằng cấu hình ứng dụng.

## Theo từng phút

| Phút tính từ mốc bắt đầu | Sự kiện gửi TCP |
| --- | ---: |
| 0 | 10,361 |
| 1 | 9,883 |
| 2 | 9,031 |
| 3 | 9,033 |
| 4 | 8,791 |
| 5 | 9,176 |
| 6 | 9,967 |
| 7 | 9,576 |
| 8 | 8,701 |
| 9 | 9,102 |
| 10 | 9,985 |
| 11 | 9,538 |
| 12 | 9,197 |
| 13 | 10,525 |
| 14 | 8,773 |

## Bước tiếp theo

Đối chiếu các luồng gửi về phía server với cấu hình và mã nguồn Online Boutique để xây danh sách giao tiếp kỳ vọng. Chạy một kịch bản thử có nhãn riêng, chẳng hạn Pod thử kết nối tới một dịch vụ ngoài danh sách giao tiếp kỳ vọng, rồi kiểm tra hệ thống ghi nhận được nguồn, đích và thời điểm. Lưu kết quả này cùng một lượt traffic bình thường để đánh giá phát hiện. Baseline hiện tại đại diện cho 10 user và cửa sổ 15 phút, nên các luồng vắng mặt cần được kiểm chứng thêm.
