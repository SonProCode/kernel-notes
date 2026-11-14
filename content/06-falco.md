# Falco và cảnh báo theo quy tắc

## Falco xử lý sự kiện như thế nào

Một driver thu các sự kiện kernel mà Falco hỗ trợ. Falco bổ sung ngữ cảnh tiến trình, file descriptor và container khi có thể, sau đó đánh giá rule. Mỗi rule có tên, mô tả, điều kiện, nội dung cảnh báo và mức ưu tiên. **Macro** đặt tên cho đoạn điều kiện dùng lại. **List** gom các giá trị như tên shell. **Exception** mô tả trường hợp hợp lệ được loại trừ trong rule phù hợp. [R14 Falco Rules](../TaiLieu_Tuan1_Tuan2/PDF/R14-Falco-Rules.pdf)

Falco hỗ trợ Modern eBPF hoặc kernel module tùy môi trường và bản cài. Nếu luận văn đo **eBPF**, ghi nhận driver thực tế từ cấu hình và log khởi động. Một số sự kiện đến trước lúc metadata có sẵn; theo dõi các trường rỗng hoặc `<NA>`. [Falco Kernel Events](https://falco.org/docs/concepts/event-sources/kernel/), [Missing Fields in Falco Logs](https://falco.org/docs/troubleshooting/missing-fields/).

## Lab mẫu trên cluster một node

Tạo file `falco-values.yaml` trong thư mục làm lab. Rule minh họa tìm tiến trình shell trong namespace `boutique`, kể cả khi mục đích là gỡ lỗi hợp lệ. `spawned_process` và `container` là macro từ bộ luật mặc định; giữ bộ luật đó khi thử cấu hình sau. Đối chiếu Helm values với chart đã chọn.

```yaml
driver:
  kind: modern_ebpf
falco:
  json_output: true
customRules:
  lab-shell.yaml: |-
    - list: lab_shells
      items: [sh, bash, dash, ash]
    - rule: Lab Shell in Boutique
      desc: Observe shell execution in the boutique namespace
      condition: spawned_process and container and k8s.ns.name = boutique and proc.name in (lab_shells)
      output: "lab shell (ns=%k8s.ns.name pod=%k8s.pod.name proc=%proc.name parent=%proc.pname container=%container.id)"
      priority: NOTICE
      source: syscall
      tags: [lab, process]
```

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update
helm search repo falcosecurity/falco --versions
# Thay giá trị dưới đây bằng phiên bản chart đã chọn.
FALCO_CHART_VERSION='THAY_BANG_PHIEN_BAN'
helm show values falcosecurity/falco --version "$FALCO_CHART_VERSION"
helm upgrade --install falco falcosecurity/falco --namespace falco \
  --create-namespace --version "$FALCO_CHART_VERSION" -f falco-values.yaml
kubectl -n falco get pods -o wide
```

Kiểm tra driver, rule có tải thành công và Pod agent có mặt trên node thử. Nếu tên DaemonSet hoặc container khác với tên ví dụ, dùng tên thực tế. [R14 hướng dẫn Helm](../TaiLieu_Tuan1_Tuan2/PDF/R14-Falco-Kubernetes-Helm.pdf), [Falco chart values](https://github.com/falcosecurity/charts/blob/master/charts/falco/values.yaml).

## Tạo sự kiện đã biết và đọc JSON

Trong namespace lab đã tồn tại, tạo Pod thử. Ghi thời điểm UTC ngay trước khi chạy lệnh `exec`.

```bash
kubectl -n boutique run runtime-probe --image=busybox:1.36.1 \
  --restart=Never --command -- sleep 3600
kubectl -n boutique wait --for=condition=Ready pod/runtime-probe --timeout=120s
date -u +%FT%TZ
kubectl -n boutique exec runtime-probe -- /bin/sh -c 'echo falco-smoke'
kubectl -n falco logs daemonset/falco -c falco --since=5m
```

Trong log, tìm rule `Lab Shell in Boutique` và pod `runtime-probe`. Falco có thể phát cảnh báo từ các rule mặc định trong cùng thời gian. Bộ nhập liệu nên tách dòng JSON hợp lệ khỏi thông báo khởi động, giữ `time`, `rule`, `priority`, `source` và `output_fields`. Với nhiều node, thu log của từng agent và ghi node tương ứng. [R14 Alert Formatting](../TaiLieu_Tuan1_Tuan2/PDF/R14-Falco-Alert-Formatting.pdf), [Falco fields](https://falco.org/docs/reference/rules/supported-fields/).

**Đối chứng.** Thử exec một binary không nằm trong danh sách, chẳng hạn `/bin/true` nếu image có binary đó. Rule shell dự kiến không phát. Giữ thời gian và kết quả của cả hai lần chạy. Nếu chưa thấy alert mong đợi, kiểm tra node, driver, bộ luật, điều kiện namespace, tên tiến trình và log báo mất sự kiện.

Falco báo khi rule khớp. Phân tích tỷ lệ kết nối bình thường cần một nguồn đủ phủ cả hoạt động không khớp rule. Một alert về shell cho biết điều kiện phát hiện xảy ra; dùng audit hoặc dữ liệu điều phối để biết đó là kiểm thử, bảo trì hay hành vi của đối thủ.

## Tự kiểm tra

1. **Priority NOTICE có phải xác suất tấn công không?** Đó là mức được đặt trong rule.
2. **Rule có tự cách ly Pod không?** Luồng ở bài này xuất cảnh báo; cách ly cần cơ chế phản ứng riêng.
3. **Metadata bị thiếu ảnh hưởng thế nào?** Điều kiện dựa trên namespace có thể bỏ qua event chưa được bổ sung trường đó.

Xem [bài 8](08-du-lieu-va-thuc-nghiem.md) để thiết kế phép đánh giá cho rule.

