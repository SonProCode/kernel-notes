# Kernel Notes

Blog tiếng Việt về Kubernetes, Zero Trust, di chuyển ngang và eBPF. Gồm 23 bài trong ba tuần học và phần lab thực tế, cùng một trang tra cứu nguồn.

[Đọc Tuần 3 trên GitHub Pages](https://sonprocode.github.io/kernel-notes/#tuan-3)

## Chỉnh sửa bài

Các bài nằm trong `content/`. Chạy `python -m pip install -r requirements.txt` rồi `python build.py` để tạo lại trang HTML. Dùng `python -m http.server 8000` để xem tại localhost. Commit cả Markdown nguồn và HTML đã tạo. GitHub Pages phục vụ file tĩnh từ thư mục gốc nhánh main.

Trang lưu tiến độ trên trình duyệt. Hai ảnh trong `assets/` là minh họa tạo bằng ImageGen cho blog này.

## Ảnh minh họa

- `hero.webp` — khối máy chủ kính xanh, góc nhìn 3/4, đường mạch đồng trên nền rừng tối, phong cách bìa tạp chí kỹ thuật.
- `runtime.webp` — ảnh macro vi mạch graphite, đường tín hiệu xanh bạc hà và hổ phách, nền rừng tối.

## Hướng dẫn lab và kết quả thực nghiệm

Repo lưu blog, học liệu, tài liệu nguồn và các file triển khai thực tế.

- [Hướng dẫn dựng Kubernetes và Online Boutique](Testbed_Online_Boutique/README.md)
- [Prometheus, Grafana và baseline S0](Testbed_Online_Boutique/monitoring/README.md)
- [GĐ3 và script Tetragon](Testbed_Online_Boutique/telemetry/README.md)
- [Kế hoạch GĐ4 và thiết kế dữ liệu S1–S5](Testbed_Online_Boutique/experiments/README.md)
- [Danh mục kết quả và cách mở log](Testbed_Online_Boutique/runs/README.md)
- [Tổng kiểm tra S0–S5 và đối chứng pilot](Testbed_Online_Boutique/experiments/S0-S5-REVIEW.md)
- [Học liệu tuần 1–2](HocLieu_Tuan1_Tuan2/)
- [Học liệu tuần 3](HocLieu_Tuan3/)
- [Tài liệu tham khảo và bản PDF](TaiLieu_Tuan1_Tuan2/)

Bản tổng hợp được đưa lên ngày 18/11/2026, giờ Việt Nam. Log chứa địa chỉ nội bộ và tên Pod của lab. File SHA256SUMS.txt trong thư mục testbed ghi mã kiểm tra của từng file thuộc testbed.

## Lab trên website

- [Dựng cụm K3s trên ba VM](https://sonprocode.github.io/kernel-notes/13-lab-k3s-thuc-te.html)
- [Prometheus, Grafana và tải S0](https://sonprocode.github.io/kernel-notes/14-prometheus-grafana-s0.html)
- [Thu log Tetragon trên hai worker](https://sonprocode.github.io/kernel-notes/15-tetragon-thu-telemetry.html)
- [Kết quả baseline thực tế](https://sonprocode.github.io/kernel-notes/16-ket-qua-baseline.html)
- [GĐ4 và tiến độ pilot](https://sonprocode.github.io/kernel-notes/17-gd4-thuc-nghiem.html)
- [Bắt đầu sử dụng S1, S2, S3](https://sonprocode.github.io/kernel-notes/20-huong-dan-s1-s2-s3.html)
- [S1 thăm dò Service và cổng](https://sonprocode.github.io/kernel-notes/21-s1-quet-service.html)
- [S4 tải nội bộ và đo tác động](https://sonprocode.github.io/kernel-notes/22-s4-tai-noi-bo.html)
- [S3 runtime abuse và hướng dẫn double check](https://sonprocode.github.io/kernel-notes/19-s3-runtime-abuse.html)
- [S2 và hướng dẫn double check](https://sonprocode.github.io/kernel-notes/18-s2-goi-api-trai-luong.html)

Các trang lab được build trực tiếp từ README trong thư mục Testbed_Online_Boutique để cập nhật hướng dẫn và kết quả khi chạy lại python build.py.

- [S5 gửi dữ liệu giả và đối chiếu ba nguồn bằng chứng](https://sonprocode.github.io/kernel-notes/23-s5-gui-du-lieu-gia.html)
- [S0–S5, kết quả hậu kiểm và đối chứng](https://sonprocode.github.io/kernel-notes/24-soat-xet-s0-s5-doi-chung.html)
