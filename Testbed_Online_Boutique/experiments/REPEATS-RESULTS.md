# Trạng thái batch đo lặp ngày 26/11/2026

Trạng thái cuối: **failed**. Hoàn tất **5/24** lượt đã lên lịch.
Batch: batch-repeats-20261125T181112Z-2519845. Protocol: gd4-repeats-20261126-v1.
Kết thúc UTC: 2026-11-25T19:38:53.250834+00:00.

Lỗi được giữ nguyên: TimeoutExpired: Command '['k3s', 'kubectl', 'get', 'nodes', '-o', 'json']' timed out after 12 seconds


| Case | Trạng thái | Bằng chứng |
| --- | --- | --- |
| r1-s1-action | completed | [s1-20261125T181115Z-2520089](../runs/s1-20261125T181115Z-2520089/manifest.json) |
| r1-s4-control | completed | [s0-s4-control-20261125T182317Z-2540872](../runs/s0-s4-control-20261125T182317Z-2540872/manifest.json) |
| r1-s4-action | completed | [s4-20261125T183702Z-2569785](../runs/s4-20261125T183702Z-2569785/manifest.json) |
| r1-s2-action | completed | [s2-20261125T185037Z-2598301](../runs/s2-20261125T185037Z-2598301/manifest.json) |
| r1-s0-action | completed | [s0-20261125T190326Z-2620476](../runs/s0-20261125T190326Z-2620476/manifest.json) |
| r1-s5-control | failed | [s0-s5-control-20261125T192603Z-2658384](../runs/s0-s5-control-20261125T192603Z-2658384/manifest.json) |
| r1-s5-action | pending | Chưa tạo run |
| r1-s3-action | pending | Chưa tạo run |
| r2-s0-action | pending | Chưa tạo run |
| r2-s3-action | pending | Chưa tạo run |
| r2-s4-action | pending | Chưa tạo run |
| r2-s4-control | pending | Chưa tạo run |
| r2-s1-action | pending | Chưa tạo run |
| r2-s5-action | pending | Chưa tạo run |
| r2-s5-control | pending | Chưa tạo run |
| r2-s2-action | pending | Chưa tạo run |
| r3-s1-action | pending | Chưa tạo run |
| r3-s4-control | pending | Chưa tạo run |
| r3-s4-action | pending | Chưa tạo run |
| r3-s5-control | pending | Chưa tạo run |
| r3-s5-action | pending | Chưa tạo run |
| r3-s2-action | pending | Chưa tạo run |
| r3-s3-action | pending | Chưa tạo run |
| r3-s0-action | pending | Chưa tạo run |

[Batch và thứ tự thực hiện](../runs/batch-repeats-20261125T181112Z-2519845/batch.json).

[Hướng dẫn lịch, giới hạn và cách tự kiểm tra](REPEATS.md).

## Cập nhật hậu kiểm và tiếp nối 28/11/2026

5/5 case completed đã được hậu kiểm đạt và dữ liệu gốc không đổi. S5 control cũng qua kiểm tra hậu kỳ với verifier đọc theo dòng, nhưng lịch sử v1 vẫn là failed, không được sửa thành 6/24.

Bản tiếp nối `gd4-repeats-20261128-v2` đã khởi chạy: batch `batch-repeats-20261128T035224Z-2912209`, unit `boutique-repeats-20261128-v2`. Ở checkpoint 03:52:47 UTC ngày 28/11, **5/24 là các lượt kế thừa đã xác nhận; 0 lượt mới hoàn tất; còn 19 lượt phải thực hiện**. Case hiện tại là r1-s5-control, được chạy lại bằng run ID mới.

[Checkpoint v2](audits/repeats-recovery-launch-20261128.json) · [Hậu kiểm 5 case](audits/repeats-partial-review-20261128.json) · [Giải thích chi tiết và cách tái hiện](REPEATS-RECOVERY.md).

Đây là snapshot khi cập nhật tài liệu, không phải màn hình tiến độ trực tiếp. Chỉ khi có report cuối mới được kết luận đủ các vòng lặp.
