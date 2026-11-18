"""Summarize TCP sends using the Kubernetes snapshots from the same run."""
import argparse
from collections import Counter, defaultdict
import csv
import ipaddress
from datetime import datetime
import json
from pathlib import Path
import re
import tarfile


def canonical_ip(value):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return str(address)


def analyze(run):
    items = []
    for phase in ("before", "after"):
        items.extend(json.loads((run / f"boutique-{phase}.json").read_text())["items"])
    ip_names = defaultdict(set)
    listen = defaultdict(set)
    for item in items:
        name = item["metadata"]["name"]
        if item["kind"] == "Service":
            for ip in item["spec"].get("clusterIPs", []):
                ip_names[canonical_ip(ip)].add(name)
            for port in item["spec"]["ports"]:
                listen[name].add(port["port"])
                target = port.get("targetPort", port["port"])
                if isinstance(target, int):
                    listen[name].add(target)
        if item["kind"] == "EndpointSlice":
            service = item["metadata"]["labels"]["kubernetes.io/service-name"]
            for endpoint in item["endpoints"]:
                for ip in endpoint["addresses"]:
                    ip_names[canonical_ip(ip)].add(service)
            listen[service].update(p["port"] for p in item["ports"] if p.get("port"))
    edges, minutes, unknown, roles = Counter(), Counter(), Counter(), Counter()
    sizes = Counter()
    total = 0
    start = datetime.fromisoformat((run / "measure-start.txt").read_text().strip().replace("Z", "+00:00"))
    with tarfile.open(run / "dataset.tar.gz") as archive:
        # Learn ephemeral workload IPs, including loadgenerator, from event metadata.
        for line in archive.extractfile("telemetry.ndjson"):
            e = json.loads(line)
            if e.get("socket") and e.get("workload"):
                ip_names[canonical_ip(e["socket"]["src_ip"])].add(e["workload"])
        for line in archive.extractfile("telemetry.ndjson"):
            e = json.loads(line)
            if e["event_type"] != "tcp_send":
                continue
            total += 1
            sock = e["socket"]
            sock["dst_ip"] = canonical_ip(sock["dst_ip"])
            source = e.get("workload") or e["pod"]
            candidates = ip_names[sock["dst_ip"]]
            target = next(iter(candidates)) if len(candidates) == 1 else sock["dst_ip"]
            if len(candidates) != 1:
                unknown[(sock["dst_ip"], sock["dst_port"])] += 1
            # A server can also send on this socket. Use known listening ports
            # to distinguish sends toward the server from sends toward the client.
            if sock["dst_port"] in listen[target]:
                role = "toward_server"
            elif sock["src_port"] in listen[source]:
                role = "toward_client"
            else:
                role = "unclassified"
            key = (source, target, sock["dst_port"], role)
            edges[key] += 1
            roles[role] += 1
            sizes[key] += int(e.get("bytes_requested") or 0)
            when = datetime.fromisoformat(re.sub(r"\.(\d{6})\d+", r".\1", e["timestamp"]).replace("Z", "+00:00"))
            minute = int((when - start).total_seconds() // 60)
            minutes[(minute, *key)] += 1
    output = run / "analysis"
    output.mkdir(exist_ok=True)
    with (output / "edges.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["source", "destination", "destination_port", "direction", "tcp_send_events", "bytes_requested"])
        for key, count in edges.most_common():
            writer.writerow([*key, count, sizes[key]])
    with (output / "per-minute.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["minute_from_start", "source", "destination", "destination_port", "direction", "tcp_send_events"])
        for key, count in sorted(minutes.items()):
            writer.writerow([*key, count])
    by_minute = Counter()
    for (minute, *_), count in minutes.items():
        by_minute[minute] += count
    unknown_ips = Counter()
    for (ip, port), count in unknown.items():
        unknown_ips[ip] += count
    expected = json.loads((run / "summary.json").read_text())["events_by_type"]["tcp_send"]
    assert sum(edges.values()) == total == expected, "Unexpected run totals"
    results = {
        "tcp_send_events": total,
        "mapped_events": total - sum(unknown.values()),
        "unresolved_destinations": [{"ip": ip, "events": count} for ip, count in unknown_ips.most_common()],
        "direction_counts": dict(roles),
        "distinct_server_edges": sum(key[3] == "toward_server" for key in edges),
        "events_per_minute": dict(sorted(by_minute.items())),
    }
    (output / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for (source, target, port, role), count in edges.most_common():
        if role == "toward_server":
            rows.append(f"| {source} | {target} | {port} | {count:,} |")
    report = """# Phân tích baseline 15 phút

Phân tích sự kiện tcp_send trong cửa sổ đo của lượt này. Đích được đối chiếu với Service ClusterIP, EndpointSlice của hai snapshot và IP nguồn có danh tính workload trong log. Việc suy ra phía server dựa trên cổng lắng nghe trong Service và EndpointSlice.

"""
    report += f"Tổng cộng **{total:,}** sự kiện gửi TCP. Ánh xạ được **{total - sum(unknown.values()):,}** sự kiện tới một workload đích duy nhất. Có **{results['distinct_server_edges']}** luồng nguồn–đích–cổng gửi về phía server.\n\n"
    report += "| Nguồn | Đích | Cổng đích quan sát được | Sự kiện gửi về phía server |\n| --- | --- | ---: | ---: |\n"
    report += "\n".join(rows)
    report += "\n\nSố lần gửi bao gồm hoạt động giao thức trên socket. Một lần gửi có thể chứa một phần hoặc nhiều thông điệp. bytes_requested là kích thước yêu cầu gửi tại hook. File edges.csv cũng chứa chiều gửi từ server về client, thường có cổng đích tạm thời.\n\n"
    report += "Có " + str(sum(unknown.values())) + " sự kiện gửi tới IP chưa ánh xạ thành workload: " + ", ".join(f"{ip} ({count} sự kiện)" for ip, count in unknown_ips.items()) + ". Các địa chỉ này cần được đối chiếu với mạng CNI, kubelet và cấu hình probe. Phân loại chiều gửi dựa trên cổng là suy luận, cần kiểm chứng bằng cấu hình ứng dụng.\n\n"
    report += "## Theo từng phút\n\n| Phút tính từ mốc bắt đầu | Sự kiện gửi TCP |\n| --- | ---: |\n"
    report += "\n".join(f"| {minute} | {count:,} |" for minute, count in sorted(by_minute.items()))
    report += "\n\n## Bước tiếp theo\n\nĐối chiếu các luồng gửi về phía server với cấu hình và mã nguồn Online Boutique để xây danh sách giao tiếp kỳ vọng. Chạy một kịch bản thử có nhãn riêng, chẳng hạn Pod thử kết nối tới một dịch vụ ngoài danh sách giao tiếp kỳ vọng, rồi kiểm tra hệ thống ghi nhận được nguồn, đích và thời điểm. Lưu kết quả này cùng một lượt traffic bình thường để đánh giá phát hiện. Baseline hiện tại đại diện cho 10 user và cửa sổ 15 phút, nên các luồng vắng mặt cần được kiểm chứng thêm.\n"
    (output / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    analyze(parser.parse_args().run)
