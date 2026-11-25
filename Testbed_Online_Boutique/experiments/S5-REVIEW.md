# Rà soát S5 sau pilot ngày 25/11/2026

**Kết luận: hai pilot 60 payload vẫn đạt khi kiểm lại dữ liệu; bản triển khai đã được sửa thêm lỗi khởi động lại receiver và các khe hở kiểm tra. Có thể chốt ở mức pilot.** Chưa dùng kết quả này thay bộ official có lặp/đối chứng, đánh giá detector hoặc hiệu quả egress deny.

## 1. Những vấn đề đã tái hiện

| Vấn đề | Trước sửa | Sau sửa / bằng chứng |
| --- | --- | --- |
| Receiver khởi động lại khi socket còn TIME_WAIT | Có thể báo Errno 98 dù lượt trước đã dừng | Bật SO_REUSEADDR qua allow_reuse_address=True; thử Linux loopback tái hiện cấu hình cũ lỗi và cấu hình mới bind lại thành công |
| ACK HTTP 200 là JSON array thay vì object | AttributeError, chưa ghi được receipt cho thao tác lỗi | Kiểm kiểu ACK; ghi receipt outcome=failed, error=ValueError |
| Probe guard bị sửa thành false nhưng streak vẫn bằng 0 | Verifier vẫn passed | Tính lại chuỗi lỗi từ probe_ok; kiểm kiểu và từ chối bộ đếm không nhất quán hoặc ba lần lỗi liên tiếp |
| Image ID trong manifest không khớp Pod snapshot | Verifier vẫn passed | So UID/image actor và Locust với snapshot trước/sau; kiểm thêm IP và placement của actor |
| Smoke đã đánh dấu validated nhưng hậu kiểm bị lỗi | Audit tổng có thể vẫn passed vì chỉ chốt điều kiện hai pilot | Audit tổng yêu cầu mọi lượt completed/validated được đưa vào kiểm tra đều đạt |

Hai vấn đề guard/image được thử bằng cách cố ý sửa **bản sao tạm** của smoke, không phải phát hiện hai lỗi đó trong log thật. [Report verifier trước/sau](audits/s5-verifier-reproduction-20261125.json) lưu baseline commit 9911aa8 và hash của hai verifier.

[ACK sai kiểu](audits/s5-client-ack-reproduction-20261125.json) được thử với fake connection không đi mạng; test giao thức còn dùng HTTP loopback thật để xác nhận client xuất receipt lỗi. Lượt có lỗi này sẽ không đạt nghiệm thu upload.

[Report audit tổng trước/sau](audits/s5-audit-reproduction-20261125.json) dùng bản sao hai pilot và một smoke có manifest bị sửa. Verifier từ chối smoke ở cả hai lần; bản audit mới còn từ chối kết quả tổng thay vì che khuất lỗi đó bằng cohort pilot hợp lệ.

## 2. Lỗi TIME_WAIT và cách tự kiểm tra

Khi kết nối TCP vừa đóng, hệ điều hành có thể giữ trạng thái TIME_WAIT. Cấu hình receiver cũ tắt address reuse, nên bind lại ngay có thể thất bại. Cơ chế SO_REUSEADDR hỗ trợ dùng lại socket ở trạng thái này trên POSIX. [Python socket documentation](https://docs.python.org/3.10/library/socket.html#example).

Phép kiểm trên Linux dùng **cổng loopback ngẫu nhiên**, không đụng receiver 18080 hoặc Pod:

- Mô phỏng giá trị cũ allow_reuse_address=False: bind lại thất bại, errno=98.
- Dùng cấu hình mới True: bind lại thành công.
- Khi một listener còn hoạt động: listener thứ hai vẫn bị từ chối. Không kill hay thay thế dịch vụ đang giữ cổng.

[Bằng chứng Linux](audits/s5-review-network-20261125.json) có hash receiver và script kiểm tra. Có thể tự chạy trên lab-cp, từ thư mục Testbed_Online_Boutique:

```bash
python3 experiments/s5/check_rebind.py --output experiments/audits/my-s5-rebind.json
```

Đọc passed và ba kết quả trong report. Script này dành cho Linux; các phép kiểm giao thức/fixture khác có thể chạy trên máy có Python và dataset đi kèm.

## 3. Kiểm tra bổ sung trong verifier/audit

Ngoài những lỗi trên, bản kiểm tra mới xác minh node Ready/không MemoryPressure ở hai snapshot; timestamp resource phải tăng, không gián đoạn quá 35 giây và đúng kiểu matrix. Probe guard phải có kết quả boolean và chuỗi bộ đếm hợp lệ.

Audit so policy spec trước/sau từng lượt và giữa các pilot. Kiểm tra không sửa bằng chứng bao phủ cả cây file dưới từng run, kể cả raw/source nếu đã giải nén. Nhãn/background features và cửa sổ 10 giây tiếp tục được dựng lại từ raw rồi so toàn bộ bản ghi.

[88 kiểm thử kết hợp S4/S5](audits/s5-review-regression-20261125.json) đều đạt, 0 failure/error/skipped. Trong đó S5 có 39 test, S4 có 49 test. Các kiểm thử âm tính dùng bản sao và không ghi đè archive, manifest, receipt hoặc nhãn đã công bố.

## 4. Hồi quy bản mới trên lab

| Run mới | Vai trò | Kết quả |
| --- | --- | --- |
| [s5-20261125T064830Z-1608732](../runs/s5-20261125T064830Z-1608732/manifest.json) | Smoke w1, 12 payload | completed/validated, đủ nhận và native evidence |
| [s5-20261125T064955Z-1611951](../runs/s5-20261125T064955Z-1611951/manifest.json) | Smoke w2, 12 payload | completed/validated, đủ nhận và native evidence |
| [s5-20261125T065118Z-1615176](../runs/s5-20261125T065118Z-1615176/manifest.json) | SIGTERM khi đang upload | interrupted; receiver đã nhận 2 payload, cleanup đạt |

Hai smoke chạy tuần tự trên cùng port receiver. Tổng 24 payload smoke mới được lưu riêng; không cộng vào 120 payload của hai pilot cũ. Các run có source snapshot riêng và giữ nhãn smoke=unknown.

[Snapshot sau hồi quy](audits/s5-review-final-state-20261125.json) xác nhận source trên lab khớp hai smoke mới, cả ba node Ready/không MemoryPressure, ứng dụng đạt replica mong đợi, loadgenerator gốc=0, không còn tài nguyên thí nghiệm và port 18080 đã đóng.

[Audit toàn bộ S5 sau sửa](audits/s5-second-review-20261125.json) kiểm lại cả cohort cũ và các smoke mới. Hai pilot gốc tiếp tục có 120/120 payload, 7.864.320 byte body, checksum và connect/send khớp. Bảng số liệu lịch sử ở [kết quả pilot](S5-RESULTS.md) được giữ nguyên, cùng source/image của chính lượt đó.

## 5. Double check và giới hạn nghiệm thu

```bash
python3 -m unittest discover -s experiments -p 'test_s5*.py' -v
python3 experiments/s5/audit.py --output experiments/audits/my-s5-review.json
```

Lệnh audit không tạo tải mới. Đọc từng run, all_completed_validated_runs_passed, passed, source hash và lý do loại trừ. Lượt failed/interrupted không được tính là attack đã hoàn tất.

S5 đã chứng minh gửi dữ liệu giả đến receiver ngoài mạng Pod trong lab, có traffic normal chạy cùng và có bằng chứng ba phía. Cần thu các lượt official lặp, S0 đối chứng và thống nhất đặc trưng/schema trước khi đánh giá định lượng GĐ4/GĐ5. Kết quả hiện không suy ra khả năng exfiltration Internet hay hiệu quả chặn của policy.
