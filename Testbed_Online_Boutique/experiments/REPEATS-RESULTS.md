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
