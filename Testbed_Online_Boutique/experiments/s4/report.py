"""Build an observational S4 pilot summary and optional SVG from verified run reports."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parents[2] / "runs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--figure", type=Path)
    args = parser.parse_args()
    records = []
    for run in sorted(p for p in args.runs_root.iterdir() if p.is_dir() and (p / "manifest.json").exists()):
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        if "s4" not in manifest or manifest["mode"] != "pilot" or manifest.get("dataset_status") != "validated":
            continue
        verification = json.loads((run / "s4-verification.json").read_text(encoding="utf-8"))
        assert verification["passed"]
        phase = "measurement" if manifest["s4"]["profile"] == "control" else "attack"
        locust = verification["locust_by_phase"][phase]
        records.append({"run_id": run.name, "node": manifest["node"], "rate": manifest["s4"]["rate"],
                        "requests": verification["http_operations"], "matched": verification["operations_with_native_event"],
                        "concurrency": manifest["s4"]["concurrency"], "duration_seconds": manifest["s4"]["duration_seconds"],
                        "actor_achieved_rps": verification["client"]["achieved_rps_over_configured_window"] if verification["client"] else 0,
                        "actor_failures": verification["client"]["http_summary"]["failures"] if verification["client"] else 0,
                        "skipped_busy": verification["client"]["skipped_busy"] if verification["client"] else 0,
                        "skipped_late": verification["client"]["skipped_late"] if verification["client"] else 0,
                        "locust_phase": locust,
                        "locust_before": verification["locust_by_phase"]["pre_attack"],
                        "locust_recovery": verification["locust_by_phase"]["recovery"],
                        "frontend_cpu_mean": verification["resources_by_phase"]["frontend_cpu_cores"].get(phase, {}).get("mean"),
                        "frontend_memory_mean": verification["resources_by_phase"]["frontend_memory_bytes"].get(phase, {}).get("mean")})
    assert records, "No verified S4 pilot/control runs"
    records.sort(key=lambda r: (r["node"], r["rate"], r["run_id"]))
    report = {"runs": records, "analysis_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "Observational pilots; one profile per level, no statistical or causal effect claim"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    lines = ["# Kết quả pilot S4 ngày 23/11/2026", "", "Các số dưới đây lấy từ verifier từng run. Rate là tải phụ; Locust vẫn có 10 người dùng bình thường.", "",
             "| Rate / worker | Request tải phụ khớp | Lỗi tải phụ | Locust: số mẫu / lỗi trong pha đo | Locust p95 trước / trong / hồi phục (ms) | CPU frontend trung bình trong pha (core) |",
             "| --- | --- | --- | --- | --- | --- |"]
    def fmt(value): return f"{value:.2f}" if value is not None else "—"
    for r in records:
        l = r["locust_phase"]
        cpu = f"{r['frontend_cpu_mean']:.3f}" if r["frontend_cpu_mean"] is not None else "—"
        lines.append(f"| {r['rate']} RPS / {r['node']} | {r['matched']}/{r['requests']} | {r['actor_failures']} | {l['requests']} / {l['failures']} | {fmt(r['locust_before']['p95_ms'])} / {fmt(l['p95_ms'])} / {fmt(r['locust_recovery']['p95_ms'])} | {cpu} |")
    lines += ["", "Control 0/0 nghĩa là không bật client tải phụ; các request mua hàng Locust vẫn được đo. P95 tính trên HTTP 200 không có exception; request vắt qua biên pha giữ riêng. CPU dùng rate cửa sổ một phút, có làm mượt. Các profile chạy tuần tự, route mix và số mẫu có thể khác; chưa dùng những số này làm kết luận nhân quả hoặc ngưỡng DoS.", "", "## Mở bằng chứng từng lượt", ""]
    total = sum(r["requests"] for r in records)
    skipped = sum(r["skipped_busy"] + r["skipped_late"] for r in records)
    lines[lines.index("## Mở bằng chứng từng lượt"):lines.index("## Mở bằng chứng từng lượt")] = [
        "## Quan sát từ cohort này", "",
        f"Có {total} request tải phụ thực sự được gửi, tất cả có native event đối chiếu. Có {skipped} slot được bỏ qua do giới hạn concurrency hoặc scheduler; đó không phải request đã gửi rồi thất bại. Lỗi HTTP của tải phụ trong cohort: {sum(r['actor_failures'] for r in records)}.", "",
        "Đọc p95 trước/trong/hồi phục và CPU của từng profile cùng control. Cohort ngắn, control tự có dao động p95 và chưa khóa seed; cần lặp thêm cùng profile để ước lượng tác động ổn định.", "",
        "Cờ verifier passed xác nhận đường chạy, đối chiếu và chất lượng xuất theo các kiểm tra đã nêu. Hãy đọc failure ratio, số mẫu và recovery cùng cờ này. Không dùng passed làm kết luận đã phát hiện/chặn DoS.", ""]
    for r in records:
        lines.append(f"- [{r['run_id']}](../runs/{r['run_id']}/s4-verification.json): [manifest](../runs/{r['run_id']}/manifest.json), [timeline](../runs/{r['run_id']}/timeline.ndjson), [archive](../runs/{r['run_id']}/dataset.tar.gz).")
    lines += ["", "[Audit source/native và tính đồng nhất release](audits/s4-pilots-audit-20261123.json).", "",
              "[Trạng thái lab sau đo và hash source đang triển khai](audits/lab-state-s4-20261123.json): loadgenerator gốc=0, không còn Pod/Deployment/ConfigMap/SA thí nghiệm; ba node Ready và frontend/checkout/payment available.", ""]
    args.markdown.write_bytes("\n".join(lines).encode())
    if args.figure:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
        labels = [f"{r['rate']} RPS\n{r['node']}" for r in records]
        colors = ["#74c7af" if r["rate"] == 0 else "#dba66b" for r in records]
        fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
        fig.patch.set_facecolor("#f5f6f4")
        for ax, field, title, unit in zip(axes,
            ("actor_achieved_rps", "locust_p95", "frontend_cpu_mean"),
            ("Tải phụ thực đạt", "Độ trễ người mua trong pha đo", "CPU frontend trung bình"),
            ("request/giây", "p95 HTTP 200 (ms)", "CPU cores · rate[1m]")):
            values = [r["locust_phase"]["p95_ms"] if field == "locust_p95" else r[field] for r in records]
            ax.bar(labels, values, color=colors, width=0.65)
            ax.set(title=title, ylabel=unit);ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=0.15);ax.set_axisbelow(True);ax.yaxis.set_major_locator(MaxNLocator(5))
        fig.suptitle("Online Boutique · S4 pilot · 30 giây mỗi pha đo", fontsize=14, fontweight="bold")
        args.figure.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.figure, format="svg", metadata={"Date": None})
        fig.savefig(args.figure.with_suffix(".png"), dpi=170)
        plt.close(fig)
    print("Summarized verified S4 pilots:", len(records))


if __name__ == "__main__": main()
