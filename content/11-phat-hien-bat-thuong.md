# Phát hiện bất thường từ tiến trình và đồ thị mạng

**Bất thường** là hành vi khác kỳ vọng đã định nghĩa. Một tiến trình mới xuất hiện sau rollout có thể do phiên bản mới. Một API nhạy cảm bị gọi bằng binary cũ cũng có thể là tấn công. Vì vậy, detector cần chỉ ra nó đã thấy gì, so với chuẩn nào và cần bằng chứng bổ sung nào.

## Ba mức phát hiện để so sánh

| Hướng | Đầu vào tối thiểu | Ví dụ kết quả |
|---|---|---|
| Luật cố định | Tên/đường dẫn executable, workload, kết nối, hoặc quyết định policy | Shell xuất hiện trong payment, chuyển sang điều tra. |
| Baseline thực thi | Tập thuộc tính chuẩn của workload và event tương ứng | Executable mới hoặc đường dẫn thay đổi sau khi Pod Ready. |
| Đồ thị mạng | Nguồn, đích, thời gian và đặc trưng luồng có độ phủ phù hợp | Cạnh recommendation → payment mới xuất hiện. |

Luật cố định dễ diễn giải và là mốc so sánh cho luận văn. Baseline giúp tìm tín hiệu ngoài danh sách luật. Đồ thị thêm cấu trúc ai giao tiếp với ai. Mỗi hướng chỉ quan sát được các hành vi có dấu vết trong dữ liệu đầu vào.

## R24 PROCATCH và hướng phù hợp để thử trước

**PROCATCH: Detecting Execution-based Anomalies in Single-Instance Microservices** tận dụng giả thuyết microservice chuyên trách có hành vi thực thi khá ổn định. Nhóm tác giả chụp thuộc tính các tiến trình đang chạy khi Pod vừa đạt trạng thái Ready, nhận diện nhóm tiến trình thông qua cgroup, rồi dùng Falco để theo dõi thay đổi. Tên executable, đường dẫn tuyệt đối, inode và thư mục làm việc là các trường chính. Inode là một số nhận diện đối tượng file trong phạm vi filesystem. Cùng một số inode ở hai filesystem không đảm bảo là cùng file. [R24 PROCATCH, mục II–IV](https://conand.me/publications/elkhairi-procatch-2025.pdf)

Bài báo đánh giá trên mười kịch bản tấn công trong môi trường do nhóm tác giả thiết kế. Precision trung bình 99,77% và recall 100% là kết quả trong phạm vi đó. Khi đặt câu hỏi về di chuyển ngang, cần thêm tín hiệu mạng hoặc ứng dụng, nhất là khi đối thủ dùng tiến trình hiện có để tạo request. Nhóm tác giả giả định hành vi đối thủ gây ra thay đổi quan sát được ở lớp thực thi. [R24 PROCATCH, mục III và V–VI](https://conand.me/publications/elkhairi-procatch-2025.pdf)

### Bài thực hành lấy cảm hứng từ PROCATCH

Ví dụ bên dưới là detector đơn giản để học. Nó so khớp đường dẫn được chuẩn hóa với baseline minh họa, trong khi PROCATCH dùng nhiều thuộc tính và phương pháp tạo baseline riêng.

```python
baseline = {"/app/paymentserver"}
examples = [
    {"binary": "/app/paymentserver", "phase": "normal"},
    {"binary": "/bin/sh", "phase": "simulated"},
    {"binary": None, "phase": "normal"},
]
for event in examples:
    binary = event["binary"]
    if not binary:
        decision = "missing_telemetry"
    elif binary in baseline:
        decision = "within_baseline"
    else:
        decision = "review_new_executable"
    print(event["phase"], decision)
```

Thay baseline minh họa bằng dữ liệu chuẩn thực tế của một container. Ghi phiên bản image, UID Pod, thời điểm Ready và tiến trình tại thời điểm tạo baseline. Dùng tập chạy sạch để lập chuẩn, sau đó xem đợt tải bình thường và đợt có thao tác mô phỏng độc lập. Nếu cần lưu baseline theo workload thay vì từng Pod, dùng ít nhất định danh workload, container và phiên bản image để tránh trộn rollout. Với Falco, thu **dòng sự kiện thực thi cần cho detector**; chỉ giữ alert shell đã lọc sẽ làm mất phần đối chứng. Tetragon có process exec event để thử phiên bản đơn giản, nhưng kết quả gọi đúng là hệ thống lấy cảm hứng từ R24. [R24 cách tạo và đối chiếu baseline](https://conand.me/publications/elkhairi-procatch-2025.pdf), [R16 Execution Monitoring](https://tetragon.io/docs/getting-started/execution/)

**Ví dụ diễn giải.** Khi health probe hợp lệ tạo binary mới, detector có thể báo sai. Khi checkout bị điều khiển thực hiện thêm một request bằng binary vốn hợp lệ, detector đường dẫn có thể bỏ sót. Tạo riêng hai tình huống này để đo giới hạn thay vì chỉ thử shell.

## R23 GATAKU và hướng phát hiện theo đồ thị

R23 xây mô hình GATAKU trên telemetry mạng từ Cilium trong testbed Kubernetes. Nhóm tác giả chuẩn bị dữ liệu và đặc trưng, huấn luyện mô hình đồ thị và so sánh với SVM và Random Forest. Phần cần lấy cho đề tài là cách biểu diễn quan hệ giữa các thành phần và thiết kế baseline so sánh. Khi thay telemetry Cilium bằng dữ liệu Tetragon, cần ghi lại sự khác biệt về độ phủ và cấu trúc sự kiện. [R23 Anomaly Detection in Microservices Architecture Using Graph Neural Networks](https://digitalcollection.zhaw.ch/bitstreams/15ae5877-9515-4c65-9712-aa32a2a2cc89/download)

**Đồ thị** gồm node và cạnh. Trong ví dụ học, một node là workload logic. Cạnh có hướng biểu diễn nguồn → đích trong 30 giây. Có thể giữ số lần thử kết nối, số lần thành công đã xác minh và độ đa dạng cổng. GNN là mạng nơ-ron có thể tính biểu diễn một node từ đặc trưng của nó và của các node hàng xóm theo cạnh. Nhờ vậy, mô hình có thể xét ngữ cảnh giao tiếp cùng lúc. Đây là cách giải thích và đề xuất thiết kế, không phải mô tả nguyên xi dataset GATAKU.

| Cửa sổ | Cạnh | Nhận xét |
|---|---|---|
| Chuẩn | checkout → payment | Có trong luồng nghiệp vụ. |
| Chuẩn | recommendation → catalog | Có trong luồng gợi ý. |
| Thử nghiệm | recommendation → payment | Cạnh mới, cần tra lại định danh và policy, rồi xác nhận kết quả request. |

Thử detector cạnh mới bằng phép so tập cạnh trước khi triển khai GNN. Chuẩn bị bảng có `run_id`, `window_start`, `src_workload`, `dst_workload`, `connect_attempts`, `outcome_known`, `label`. Dữ liệu mạng L4 mô tả kết nối, còn dữ liệu proxy hoặc API mô tả yêu cầu gRPC. Khi có đủ lần chạy độc lập, tách train, validation và test theo run rồi giữ tập test cố định cho mọi mô hình. Đọc [cách chuẩn hóa và gán nhãn](../HocLieu_Tuan1_Tuan2/08-du-lieu-va-thuc-nghiem.md).

## Tự kiểm tra

1. **Baseline học được nhiều lần gọi tới một đích có đồng nghĩa đích đó được phép?** Kiểm kê hành vi và quyết định phân quyền là hai việc riêng. Đối chiếu chính sách và nguồn gốc dữ liệu đã dùng để học.
2. **Cạnh mới có luôn là tấn công?** Có thể là rollout hợp lệ hoặc thay đổi ánh xạ IP. Kiểm tra phiên bản, nguồn và kết quả request.
3. **Nên dùng R24 hay R23 cho tuần này?** Nếu đã thu process events và có ít run, thử R24 trước. Nếu có telemetry mạng đủ phủ và nhiều run có nhãn, triển khai detector cạnh mới để chuẩn bị cho R23.

Tiếp theo [đánh giá detector và phản ứng](12-danh-gia-va-phan-ung.md).
