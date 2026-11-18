# Biên bản dọn lab Kubernetes cũ

Ngày 15/11/2026, giờ Việt Nam. Ba VM đã được chuẩn bị để người vận hành cài K3s và dựng testbed mới. Trạng thái nghiệm thu Online Boutique, Prometheus, Grafana và traffic sẽ được xác nhận sau khi triển khai.

## Hiện trạng trước khi dọn

Ba VM Ubuntu Server 22.04.5 LTS, kernel 5.15.0-198-generic, mỗi máy 4 vCPU và khoảng 3.875 MiB RAM, cùng chạy một cụm kubeadm v1.37.1 dùng containerd và Flannel. Cả ba node đều Ready. Control plane có etcd cục bộ. Các namespace thử nghiệm là `eval-lab`, `lab-attack`, `lab-benign`, `lab-observe` và `kubearmor`. Tetragon 1.7.1 chạy trong `kube-system`. Helm có release KubeArmor ở trạng thái failed. API cũ không có PV hoặc PVC tại thời điểm kiểm kê. Không phát hiện Docker daemon, Prometheus hoặc Grafana đang chạy trên ba host.

## Việc đã thực hiện

1. Lưu bản kê namespace, workload, CRD và Helm trên control plane. Tạo snapshot etcd khoảng 9 MiB, kiểm tra SHA-256 và lưu cùng bản sao cấu hình kubeadm trong thư mục root-only `/root/boutique-pre-reset-2026-11-15`. Mỗi VM cũng lưu cấu hình CNI cũ, danh sách container/image và bản sao rules iptables trước khi dọn. Bản sao để trên VM và không chứa trong repo.
2. Chạy `kubeadm reset` trên hai worker rồi mới chạy trên control plane. Lệnh đưa cụm cũ và các namespace/workload/CRD/Helm release về trạng thái đã gỡ. Dừng và tắt tự khởi động `kubelet`. Di chuyển kubeconfig cũ của người dùng trên control plane vào thư mục sao lưu vì nó chỉ trỏ tới API cũ tại .142.
3. Dọn cấu hình Flannel đang hoạt động, trạng thái CNI cũ, interface `cni0` và `flannel.1` và các chain/rule IPv4/IPv6 thuộc Kubernetes và Flannel. Kiểm tra bộ rules trước khi nạp lại. Xóa các đối tượng BPF còn ghim đúng dưới `/sys/fs/bpf/tetragon`.
4. Xóa tham chiếu image cũ trong namespace containerd `k8s.io`. Xác nhận không còn container, task, image, snapshot hay lease. Hai worker có log timeout khi kubeadm dừng một Pod sandbox. Các kiểm tra tiếp theo xác nhận namespace runtime đã rỗng và không còn cổng tiến trình lab cũ.
5. Gỡ profile AppArmor có tiền tố `kubearmor-` khỏi kernel và chuyển file profile vào sao lưu. Chuyển log Pod/container cũ ra khỏi thư mục đang hoạt động. Dừng và tắt tự khởi động containerd hệ thống; gói đã cài vẫn có thể phục vụ phục hồi. K3s dùng containerd tích hợp với cấu hình mặc định này.
6. Cập nhật bộ cấu hình K3s theo các IP thực tế và interface `ens33`. Chép hướng dẫn và cấu hình node bằng SFTP vào `/home/sonth32/Testbed_Online_Boutique` trên cả ba VM. Máy .142 có thêm overlay Online Boutique và bộ kiểm tra cross-node. Đã so khớp SHA-256 các tệp đã chép.

Cách xử lý CNI, luật mạng và kubeconfig theo phạm vi đã kiểm kê. [Tài liệu kubeadm reset](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-reset/)

## Kết quả kiểm tra sau dọn

| VM | Vai trò K3s dự kiến | Tham chiếu image đã xóa | Profile KubeArmor đã gỡ | Đĩa trống ở / |
|---|---|---:|---:|---:|
| 192.168.141.142, manager | `lab-cp` | 36 | 0 | 6,2 GiB |
| 192.168.141.143, worker-1 | `lab-w1` | 67 | 12 | 9,4 GiB |
| 192.168.141.144, worker-2 | `lab-w2` | 60 | 11 | 9,6 GiB |

- SSH vẫn hoạt động trên cả ba VM. IP, gateway và interface quản trị vẫn như khi kiểm kê.
- Kubelet và containerd hệ thống đều đã dừng và ở trạng thái disabled. Không còn listener trên các cổng đã kiểm kê của cụm và công cụ cũ, gồm 6443, 2379–2380, 8472, 10250 và 2112. Không còn chain `KUBE-` hay `FLANNEL-` trong rules đang hoạt động. Các profile AppArmor KubeArmor đã được gỡ.
- Cả ba máy đọc được `/sys/kernel/btf/vmlinux`, không bật swap và truy cập HTTPS được tới `get.k3s.io`, `registry.k8s.io` và `us-central1-docker.pkg.dev`. Đây là kiểm tra kết nối, việc pull đầy đủ image sẽ được xác nhận khi chạy deployment.
- Mỗi VM có đĩa ảo 40 GB nhưng logical volume gốc hiện chỉ khoảng 19 GiB. Mỗi volume group còn khoảng 19 GiB chưa phân bổ. Nếu cần thêm dung lượng để giữ metrics/log dài hạn, có thể mở rộng phân vùng logic và kiểm tra filesystem trước. Chưa thay đổi cấp phát đĩa.

## Bắt đầu dựng testbed mới

SSH vào .142, vào thư mục đã chép rồi chạy phần cài server trong [hướng dẫn](README.md). Trên .143 dùng `cluster/lab-w1.yaml`, trên .144 dùng `cluster/lab-w2.yaml`. Dùng bộ cấu hình mới theo địa chỉ `192.168.141.142–144`. Lệnh `kubectl` cài sẵn là bản của cụm trước, hướng dẫn dùng `sudo k3s kubectl` để dùng client đi cùng server mới.

1. Đợi ba node Ready. Kiểm tra DNS và NetworkPolicy qua hai worker bằng thư mục `checks/`.
2. Áp overlay trong `boutique/`. Xác nhận 11 Pod ứng dụng Ready, thao tác xem sản phẩm, thêm giỏ hàng và checkout thành công. Loadgenerator để 0 replica ở baseline kiểm tra tay.
3. Sau khi baseline ổn, cấu hình Prometheus và Grafana cho testbed, ưu tiên thời gian giữ dữ liệu ngắn với dung lượng hiện tại. Xác minh Prometheus có target UP và Grafana truy vấn được nguồn dữ liệu. Overlay Online Boutique hiện chỉ triển khai ứng dụng.
4. Tạo pha traffic bình thường bằng một loadgenerator hoặc nguồn tải đã ghi cấu hình. Ghi thời gian, độ trễ, tỷ lệ lỗi, CPU/RAM và số Pod restart. Chỉ đánh dấu testbed ổn định sau khi có bằng chứng của pha này.

Đợt này kết thúc ở bước dọn cụm cũ và chuẩn bị file dựng. K3s mới, Online Boutique, Prometheus, Grafana và traffic chưa được chạy.


## Cập nhật dung lượng sau bàn giao

Đã cấp toàn bộ khoảng 19 GiB LVM còn trống cho volume gốc của cả ba VM. Trước khi mở rộng, sao lưu metadata LVM trên từng máy vào `/root/boutique-pre-reset-2026-11-15/ubuntu-vg-before-extend.vgcfg`. Sau đó chạy `lvextend --resizefs -l +100%FREE /dev/ubuntu-vg/ubuntu-lv` để mở rộng volume và filesystem ext4 đang mount. Không cần reboot.

| VM | Tổng dung lượng / theo df | Dung lượng trống / |
|---|---:|---:|
| 192.168.141.142 | 38 GiB | 25 GiB |
| 192.168.141.143 | 38 GiB | 28 GiB |
| 192.168.141.144 | 38 GiB | 28 GiB |

Đã xác nhận LVM không còn extents trống và SSH vẫn hoạt động trên cả ba máy. Mỗi đĩa ảo vẫn có 40 GiB, trong đó khoảng 2 GiB được dành cho `/boot`. Các số ở mục kiểm tra sau dọn bên trên phản ánh giai đoạn trước khi mở rộng.


## Chuẩn bị máy ảo và mạng trước khi cài K3s

Kiểm tra ngày 15/11/2026 theo giờ Việt Nam. Giữ tên hệ điều hành `manager`, `worker-1` và `worker-2`. K3s sẽ đăng ký tên node theo các YAML hiện có là `lab-cp`, `lab-w1` và `lab-w2`.

| Máy | IPv4 tĩnh trên ens33 | MAC | Tiền tố SHA-256 machine-id sau kiểm tra |
|---|---|---|---|
| manager | 192.168.141.142/24 | 00:0c:29:79:9e:f7 | 5768602384c8 |
| worker-1 | 192.168.141.143/24 | 00:0c:29:08:00:b4 | 26f8b30e8930 |
| worker-2 | 192.168.141.144/24 | 00:0c:29:db:c2:b9 | 3e7465b4ad33 |

- Ba VM có IP tĩnh qua Netplan với DHCPv4 tắt, cùng VMware VMnet8 NAT và default gateway `192.168.141.2`. Cấu hình K3s đã chốt `node-ip` theo từng máy và `flannel-iface: ens33`. Kiểm tra bảng route hiện tại của host và guest cho thấy chưa có mạng riêng hoặc route VPN đang sử dụng hai dải `10.42.0.0/16` và `10.43.0.0/16`.
- MAC đã khác sẵn. Ba bản clone ban đầu dùng chung `machine-id`, nên tạo ID mới cho hai worker và reboot để hệ thống dùng ID mới. Bản cũ được sao lưu root-only. Hai worker có lần chậm nhận kết nối từ host sau reboot. Kiểm tra qua VMware Tools cho thấy IP tĩnh đúng; ping từ guest tới host khôi phục chiều truy cập. Bổ sung `boutique-lab-network-ready.service` gửi hai ping tới `192.168.141.1` khi mạng online. Đã reboot lại và xác nhận cả hai worker tự nhận SSH, unit chạy thành công. SSH host keys của các bản clone vẫn giống nhau và chưa xoay.
- Áp dụng firewall riêng bằng service `boutique-lab-firewall.service` trên cả ba VM, đọc `/etc/boutique-lab/ingress.nft`. SSH TCP/22 từ host quản trị `192.168.141.1`; TCP/6443 trên .142 từ hai worker và host quản trị; UDP/8472 và TCP/10250 giữa ba node. Cho phép đường Pod nội bộ tới API và kubelet trên các interface Flannel phù hợp để phục vụ thành phần trong cluster. Các luật chỉ giới hạn các cổng đã nêu, giữ mặc định của lưu lượng khác. Đã gỡ ba bảng nftables KubeArmor còn sót trên mỗi worker sau khi lưu snapshot ruleset. Backup đọc bởi root tại `/root/boutique-pre-reset-2026-11-15/network-preflight/`. [Yêu cầu mạng K3s](https://docs.k3s.io/installation/requirements)
- Sau reboot, kiểm tra đạt 19 phép thử cổng với listener tạm thời. Gồm UDP/8472 và TCP/10250 hai chiều trên cả ba cặp node, TCP/6443 từ hai worker và host đến .142, chặn SSH giữa VM và chặn host truy cập TCP/10250. Listener thử đã dừng. Cả ba VM ping qua lại, phân giải DNS và truy cập HTTPS tới trang K3s và ba registry. NTP đồng bộ, swap tắt, fstab không có mục swap đang bật, BTF đọc được trên kernel 5.15.0-198-generic. Mỗi VM gán 4 GB RAM, `free` thấy khoảng 3,8 GiB.
- VMware DHCP của VMnet8 vẫn có pool `192.168.141.128–254`, chứa ba IP tĩnh. Không thấy lease đang cấp cho thiết bị khác ở .142–.144 trong file lease kiểm tra, nhưng dải chưa loại chúng. Tiến trình Windows hiện không có quyền quản trị để sửa cấu hình này. Giữ nguyên ba IP và nhờ người vận hành mở **Virtual Network Editor → Change Settings → VMnet8 → DHCP Settings**, đặt pool từ `192.168.141.145` tới `192.168.141.254` trước khi thêm máy DHCP khác hoặc dựng lab dài hạn. VMware NAT không có port forwarding được cấu hình khi kiểm tra.

K3s chưa cài và chưa tạo snapshot VMware. Bước tiếp theo là cài server ở .142 theo [mục 2 của hướng dẫn](README.md), rồi thử lại API thật, join worker và kiểm tra Pod qua hai node.


## Khắc phục worker không xuất hiện trong K3s

Ngày 15/11/2026. Kiểm tra thấy `.142` đã chạy K3s server nhưng file `/etc/rancher/k3s/config.yaml` trên máy này bị ghi đè bằng cấu hình `lab-w1`. Service `k3s-agent` cũng được cài trên .142 và lặp lỗi bind `127.0.0.1:6444` vì cổng do K3s server sử dụng. Hai VM .143 và .144 chưa có service agent. Lệnh `get nodes` vì vậy ban đầu chỉ trả về control plane.

- Lưu cấu hình sai tại `/root/boutique-pre-reset-2026-11-15/k3s-join-repair/` trên .142. Tắt và disable service agent cài nhầm, khôi phục file `cluster/lab-cp.yaml` và restart server K3s đã có.
- Cài K3s agent v1.35.9+k3s1 trên .143 và .144 với từng YAML tương ứng. Chuyển token server qua SSH vào file mode 600 trên từng worker.
- Xác nhận `lab-cp`, `lab-w1`, `lab-w2` đều `Ready`. Hai worker có label `lab.slot=w1` và `lab.slot=w2`. CoreDNS và metrics-server đều 1/1, và `kubectl top nodes` có số liệu cho cả ba node.
- Dùng Pod ở lab-w1 và HTTP server ở lab-w2 kiểm tra DNS nội bộ và NetworkPolicy. Trước policy, cả hai client gọi được qua Service. Sau policy, client hợp lệ vẫn nhận nội dung, client bị chặn nhận `Connection refused`. Gỡ policy thì client đó gọi được trở lại. Đã gửi lệnh dọn namespace kiểm thử tạm `policy-lab`.

Hướng dẫn trong workspace đã nêu rõ địa chỉ SSH của từng worker và thêm bước kiểm tra token không rỗng. Bước tiếp theo là áp overlay Online Boutique ở mục 4; ứng dụng và Prometheus/Grafana chưa được triển khai trong lần xử lý này.


## Kiểm tra trạng thái Online Boutique trước baseline S0

Ngày 15/11/2026, khoảng 21:29 giờ Việt Nam. Cụm 3 node Ready, CoreDNS và metrics-server 1/1. Kiểm tra 12 Deployment trong `boutique`: 11 Deployment ứng dụng có 1/1 replica, loadgenerator 0/0 đúng overlay. Cả 11 Service đều ClusterIP và có EndpointSlice. Checkout nằm trên lab-w1, payment nằm trên lab-w2. Không có Service frontend-external. File `boutique-rendered.yaml` đã tồn tại trên .142.

Gọi `http://127.0.0.1:8080/` từ .142 qua port-forward đang mở trả HTTP 200. Kiểm tra này chỉ xác nhận trang chủ. Một restart cũ ở emailservice (mã thoát 137, lý do Kubernetes báo `Error`) xuất hiện lúc khởi động, Pod hiện 1/1. Không có bằng chứng để quy mã thoát đó cho OOM. CPU tại lúc kiểm tra khoảng 78m/43m/33m và RAM khoảng 1.566/715/981 MiB theo thứ tự control plane, worker 1, worker 2.

Prometheus/Grafana chưa có và chưa bật traffic tự động. Tạo [hướng dẫn bước 5](monitoring/README.md) và [cấu hình Helm](monitoring/values-s0.yaml) cho lần chạy S0. `helm template` đã thành công với chart 93.3.0 và Kubernetes 1.35.9, tạo các cấu hình Prometheus/Grafana dự kiến, không tạo PVC. Chưa áp chart lên cụm. Các phép kiểm tra còn lại là checkout đầy đủ, scrape targets, Grafana hiển thị dữ liệu và ghi số liệu dưới tải.


## Lần chạy S0 ngắn và cách xem số liệu Grafana

Ngày 15/11/2026, lần chạy `runs/s0-20261115T153532Z` trên .142 ghi từ **22:35:32 đến 22:39:29** giờ Việt Nam (15:35:32–15:39:29 UTC). Locust đạt 10 người dùng ảo lúc 22:36:07. Dòng tổng hợp cuối trong log đã lưu có 440 request và 1 lỗi (0,23%). Thời lượng ghi 3 phút 57 giây, dùng làm lần kiểm tra pipeline. Loadgenerator hiện đã được đưa về 0 replica. Các tệp `locust.log`, `nodes-before.txt`, `nodes-after.txt`, `pods-before.txt` và `pods-after.txt` còn trên .142.

Prometheus có 19 target UP, gồm kubelet và node exporter ở cả ba node. Truy vấn CPU/RAM của namespace `boutique` có dữ liệu. Kiểm tra tại 22:38 xác nhận Prometheus đã ghi nhận loadgenerator có 1 replica khả dụng. Grafana có dashboard **Kubernetes / Compute Resources / Namespace (Pods)** và datasource Prometheus. Lab một cụm không đặt label `cluster`, nên ô Cluster trống là phù hợp. Chọn Namespace `boutique` và khoảng 22:34–22:41 hoặc mở Explore để chạy PromQL lọc namespace. Giá trị 440 là dòng tổng hợp cuối đã lưu, vì log được chụp trước khi scale về 0.


## Baseline S0 15 phút trước khi thêm cảm biến

Lần chạy `runs/s0-20261115T170523Z/` trên .142. Cửa sổ đo **00:05:23–00:20:23 ngày 16/11/2026** giờ Việt Nam, tương ứng 17:05:23–17:20:23 UTC ngày 15/11. Locust đã đạt 10 user khoảng 6 phút 41 giây trước khi bắt đầu đo và Prometheus ghi nhận loadgenerator 1 replica trong toàn bộ 31 điểm kiểm tra cách nhau 30 giây. Sau lần chạy loadgenerator đã trở về 0.

- Lấy bộ đếm Locust gần nhất trước hai mốc. Tổng request tăng từ 877 lên 2.834, tương ứng **1.957 request**, **2,17 request/giây** và **1 lỗi (0,051%)**. Checkout tăng từ 30 lên 114, tương ứng **84 lượt, 1 lỗi (1,19%)**. Ảnh chụp bộ đếm lệch mốc dưới 2 giây. Dòng cuối của file log rơi khoảng 5 phút sau khi hết cửa sổ nên không dùng để tính.
- Log frontend ghi một HTTP 500 tại checkout lúc khoảng 00:12:22 giờ Việt Nam, trong đường gọi Charge. Chưa xác định nguyên nhân gốc. Không thấy lỗi khác trong cửa sổ.
- Tổng CPU của namespace boutique, gồm loadgenerator, trung bình **87,47m**, khoảng **67,19–100,10m**. Tổng RAM working set trung bình **375,29 MiB**, khoảng **373,12–376,72 MiB**. RAM khả dụng thấp nhất trên hai worker lần lượt khoảng 2.260 và 2.389 MiB. Bộ đếm restart tổng giữ ở 1, là lần restart cũ của emailservice.
- Đây là mốc S0 dùng được cho phép thử kế tiếp ở cùng tải. Log có bộ đếm và độ trễ cộng dồn; chưa có p95 tách riêng cho đúng 15 phút. Khi so overhead, giữ cùng cấu hình monitoring, 10 user, tốc độ lên tải và cửa sổ làm nóng tương đương. Lặp nhiều lần cho mỗi cấu hình trước khi kết luận chênh lệch.

