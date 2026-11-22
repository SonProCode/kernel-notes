from pathlib import Path
from html import escape
import os
import re
import math
import markdown
import posixpath
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
ARTICLES = [
    ("01-nen-tang-kubernetes", "Nền tảng Kubernetes", "Từ một lần bấm mua hàng đến Service, Pod và tiến trình thực sự xử lý yêu cầu.", "R6", "layers"),
    ("02-zero-trust-threat-model", "Zero Trust & mô hình đe dọa", "Theo chân một pod bị xâm nhập và xác định bằng chứng cho từng bước di chuyển ngang.", "R1 · R2", "shield"),
    ("03-bao-mat-kubernetes-networkpolicy", "Bảo mật Kubernetes & NetworkPolicy", "Thử nghiệm ba Pod để biết luồng nào được phép và luồng nào bị chặn.", "R3 · R6 · R7", "network"),
    ("04-testbed-online-boutique", "Dựng lab Online Boutique", "Đưa cửa hàng mẫu lên cluster và kiểm tra luồng xem sản phẩm, thêm giỏ, đặt hàng.", "R8", "shop"),
    ("05-ebpf-runtime-telemetry", "eBPF & telemetry runtime", "Lần theo một sự kiện từ syscall, qua kernel, đến bản ghi có ngữ cảnh Kubernetes.", "R11", "pulse"),
    ("06-falco", "Phát hiện với Falco", "Viết rule quan sát shell trong Pod và đọc cảnh báo JSON.", "R14", "terminal"),
    ("07-tetragon", "Quan sát với Tetragon", "Dùng TracingPolicy để hiểu tiến trình, truy cập file và kết nối.", "R16", "scope"),
    ("08-du-lieu-va-thuc-nghiem", "Từ log đến thực nghiệm", "Tạo baseline, gắn nhãn độc lập và tính precision, recall, độ trễ phát hiện.", "Thực hành", "chart"),
    ("10-istio-policy-enforcement", "Thực thi chính sách với Istio", "Dùng mTLS và AuthorizationPolicy để chỉ cho checkout gọi Charge, rồi kiểm chứng bằng hai danh tính.", "R19 · R20", "shield"),
    ("11-phat-hien-bat-thuong", "Phát hiện bất thường", "So sánh baseline tiến trình kiểu PROCATCH với đồ thị giao tiếp của microservices.", "R23 · R24", "scope"),
    ("12-danh-gia-va-phan-ung", "Đánh giá detector và phản ứng", "Đo độ trễ, đánh giá luồng bị chặn và giữ checkout hoạt động trong từng lần thử.", "R18", "chart"),
    ("13-lab-k3s-thuc-te", "Dựng cụm K3s trên ba VM", "Cấu hình ba máy, triển khai Online Boutique và kiểm tra luồng giao tiếp.", "Lab · R8", "shop"),
    ("14-prometheus-grafana-s0", "Prometheus, Grafana và tải S0", "Cài bộ giám sát, mở dashboard và sinh traffic bình thường bằng Locust.", "Lab · S0", "chart"),
    ("15-tetragon-thu-telemetry", "Thu log Tetragon trên hai worker", "Hiểu từng bước cài agent, quan sát TCP và chạy script thu baseline 15 phút.", "GĐ3 · R16", "scope"),
    ("16-ket-qua-baseline", "Đọc kết quả baseline thực tế", "Đối chiếu 141.642 sự kiện, hiểu kết nối tái sử dụng và tải bộ log để phân tích.", "GĐ3 · Kết quả", "pulse"),
    ("17-gd4-thuc-nghiem", "GĐ4 · Tạo dữ liệu attack và normal", "Kế hoạch S1–S5, quy tắc nhãn và tiến độ pilot trên hai worker.", "GĐ4 · S1–S5", "terminal"),
    ("20-huong-dan-s1-s2-s3", "Bắt đầu sử dụng S1, S2, S3", "Từ SSH và thư mục làm việc tới chạy thử, đọc log, kiểm tra đạt và xử lý lỗi.", "Thực hành · Bắt đầu", "terminal"),
    ("21-s1-quet-service", "S1 · Thăm dò Service và cổng", "Hiểu từng lần thử TCP và đối chiếu đủ danh sách đích với log kernel gốc.", "GĐ4 · S1", "network"),
    ("18-s2-goi-api-trai-luong", "S2 · Gọi API payment trái luồng", "Tái lập lời gọi gRPC và double check bằng phản hồi API, log server cùng Tetragon.", "GĐ4 · S2", "network"),
    ("19-s3-runtime-abuse", "S3 · Shell, công cụ mạng và token", "Tái lập runtime abuse và đối chiếu từng tiến trình, kết nối, lần đọc file với raw Tetragon.", "GĐ4 · S3", "terminal"),
]
WEEKS = [
    (0, 3, "Nền tảng bảo mật", "Hiểu hệ thống, danh tính và đường đi của một cuộc tấn công."),
    (3, 8, "Quan sát và thực hành", "Dựng lab, đọc telemetry và kiểm chứng giả thuyết."),
    (8, 11, "Thực thi và phát hiện bất thường", "Giới hạn quyền gọi payment, xây detector và đo kết quả."),
    (11, len(ARTICLES), "Lab thực tế và kết quả đo", "Thực hành trên ba VM, thu telemetry và đọc bộ baseline đã chạy."),
]
ICONS = {
    "layers":"M2 8l10-5 10 5-10 5L2 8Z M2 12l10 5 10-5 M2 16l10 5 10-5",
    "shield":"M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z M8 12l3 3 5-6",
    "network":"M5 4h4v4H5z M15 16h4v4h-4z M5 16h4v4H5z M7 8v8 M7 12h10v4",
    "shop":"M4 9l2-5h12l2 5v11H4V9Z M4 9h16 M9 20v-6h6v6",
    "pulse":"M2 12h5l3-7 4 14 3-7h5",
    "terminal":"M3 5h18v14H3z M7 9l3 3-3 3 M13 15h4",
    "scope":"M12 2v5 M12 17v5 M2 12h5 M17 12h5 M12 5a7 7 0 1 0 0 14 7 7 0 0 0 0-14Z",
    "chart":"M4 4v16h16 M8 16v-4 M13 16V8 M18 16V5",
}
SOURCE = {
    "R1":"https://doi.org/10.6028/NIST.SP.800-207",
    "R2":"https://attack.mitre.org/tactics/TA0008/",
    "R3":"https://kubernetes-top10.owasp.org/",
    "R6":"https://kubernetes.io/docs/concepts/",
    "R7":"https://kubernetes.io/docs/concepts/services-networking/network-policies/",
    "R8":"https://github.com/GoogleCloudPlatform/microservices-demo/tree/v0.10.7",
    "R11":"https://ebpf.io/what-is-ebpf/",
    "R14":"https://falco.org/docs/",
    "R16":"https://tetragon.io/docs/",
}
PDF_URLS = {
    "RBAC-Good-Practices":"https://kubernetes.io/docs/concepts/security/rbac-good-practices/",
    "Service-Accounts":"https://kubernetes.io/docs/concepts/security/service-accounts/",
    "Kubernetes-Helm":"https://falco.org/docs/setup/kubernetes/",
    "Falco-Rules":"https://falco.org/docs/concepts/rules/basic-elements/",
    "Alert-Formatting":"https://falco.org/docs/concepts/outputs/formatting/",
    "Kubernetes-Install":"https://tetragon.io/docs/getting-started/install-k8s/",
    "Execution-Monitoring":"https://tetragon.io/docs/getting-started/execution/",
    "File-Access":"https://tetragon.io/docs/getting-started/file-events/",
    "Network-Monitoring":"https://tetragon.io/docs/getting-started/network/",
    "Tracing-Policy":"https://tetragon.io/docs/concepts/tracing-policy/",
}
def icon(key):
    return f'<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{ICONS[key]}"/></svg>'

def layout(title, body, meta="Học bảo mật Kubernetes và eBPF từ đầu với Online Boutique."):
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta)}">
<link rel="icon" href="assets/icon.svg"><link rel="stylesheet" href="assets/site.css"><script defer src="assets/site.js"></script></head>
<body><a class="skip" href="#main">Đến nội dung</a><header class="top"><div class="shell bar">
<a class="logo" href="./">{icon("layers")}<span>Kernel<span class="mint">Notes</span></span></a>
<nav aria-label="Điều hướng chính"><a href="./#lo-trinh">Lộ trình</a><a href="09-tra-cuu.html">Tra cứu</a><a href="./#tuan-4">Lab thực tế</a></nav>
<a class="nav-cta" href="./#lo-trinh">Đọc bài <span aria-hidden="true">↗</span></a>
</div></header><main id="main">{body}</main><footer class="shell footer"><a class="logo" href="./">{icon("layers")} Kernel<span class="mint">Notes</span></a><span>Bảo mật Kubernetes và eBPF</span><a href="09-tra-cuu.html">Tài liệu tham khảo ↗</a></footer></body></html>"""

LAB_SOURCES = {
    "20-huong-dan-s1-s2-s3": "Testbed_Online_Boutique/experiments/USAGE.md",
    "21-s1-quet-service": "Testbed_Online_Boutique/experiments/S1.md",
    "19-s3-runtime-abuse": "Testbed_Online_Boutique/experiments/S3.md",
    "18-s2-goi-api-trai-luong": "Testbed_Online_Boutique/experiments/S2.md",
    "17-gd4-thuc-nghiem": "Testbed_Online_Boutique/experiments/README.md",
    "13-lab-k3s-thuc-te": "Testbed_Online_Boutique/README.md",
    "14-prometheus-grafana-s0": "Testbed_Online_Boutique/monitoring/README.md",
    "15-tetragon-thu-telemetry": "Testbed_Online_Boutique/telemetry/README.md",
    "16-ket-qua-baseline": "Testbed_Online_Boutique/runs/README.md",
}

def read(slug):
    if slug not in LAB_SOURCES:
        return (CONTENT/f"{slug}.md").read_text(encoding="utf-8-sig")
    source = LAB_SOURCES[slug]
    text = (ROOT/source).read_text(encoding="utf-8-sig")
    if slug == "20-huong-dan-s1-s2-s3":
        report = ROOT / "Testbed_Online_Boutique/experiments/REVIEW-S1-S2-S3.md"
        text += "\n\n" + report.read_text(encoding="utf-8").replace("# Rà soát", "## Rà soát", 1)
    if slug == "17-gd4-thuc-nghiem":
        progress = ROOT / "Testbed_Online_Boutique/experiments/RESULTS.md"
        text += "\n\n" + progress.read_text(encoding="utf-8").replace("# Kết quả khởi động", "## Kết quả khởi động", 1)
    if slug == "16-ket-qua-baseline":
        report = ROOT / "Testbed_Online_Boutique/runs/s0-tetragon-20261117T162618Z-3967383/analysis/README.md"
        text += "\n\n" + report.read_text(encoding="utf-8").replace("# Phân tích baseline", "## Phân tích baseline", 1)

    def repository_link(match):
        target = match[1]
        if target.startswith(("#", "http:", "https:", "mailto:")):
            return match[0]
        location = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
        document, separator, anchor = location.partition("#")
        page = next((key for key, value in LAB_SOURCES.items() if value == document), None)
        if document == "Testbed_Online_Boutique/experiments/REVIEW-S1-S2-S3.md":
            return "](20-huong-dan-s1-s2-s3.html#ra-soat-s1-s2-s3-va-huong-dan-su-dung)"
        if page:
            return "](" + page + ".html" + ("#" + anchor if separator else "") + ")"
        return "](https://github.com/SonProCode/kernel-notes/blob/main/" + quote(location, safe="/#") + ")"
    return re.sub(r"\]\(([^)]+)\)", repository_link, text)

def minutes(slug):
    return max(4, math.ceil(len(read(slug).split())/220))

def convert_pdf_link(match):
    filename = match[1]
    special = next((url for pattern, url in PDF_URLS.items() if pattern in filename), None)
    return "(" + (special or SOURCE[filename.split("-")[0]]) + ")"

def article_html(slug):
    text = read(slug)
    text = re.sub(r"\(\.\./TaiLieu_Tuan1_Tuan2/PDF/([^)]*\.pdf)\)", convert_pdf_link, text)
    text = text.replace("../TaiLieu_Tuan1_Tuan2/R8-Online-Boutique-v0.10.7.zip", "https://github.com/GoogleCloudPlatform/microservices-demo/archive/refs/tags/v0.10.7.zip")
    text = text.replace("../TaiLieu_Tuan1_Tuan2/Muc_luc.html", "#muc-doc-theo-ma-r")
    text = text.replace("](README.md)", "](./)")
    text = re.sub(r"\]\((?:\.\./HocLieu_Tuan1_Tuan2/)?(\d{2}-[\w-]+)\.md(?:#([^)]*))?\)", lambda m:f"]({m[1]}.html" + ("#" + slugify(m[2]) if m[2] else "") + ")", text)
    engine = markdown.Markdown(extensions=["fenced_code","tables","toc"], extension_configs={"toc":{"slugify":lambda value, separator:slugify(value)}})
    body = engine.convert("\n".join(text.splitlines()[1:]))
    return body, engine.toc

def slugify(value):
    import unicodedata
    ascii_value = unicodedata.normalize("NFKD",value.lower().replace("đ","d")).encode("ascii","ignore").decode()
    return re.sub(r"[^a-z0-9_-]+","-",ascii_value).strip("-")

def week_for(index):
    return next(week for week, (start, end, _, _) in enumerate(WEEKS, 1) if start <= index < end)

def card(index, article):
    slug,title,desc,refs,key=article
    week = week_for(index)
    return f"""<article class="card" data-week="{week}" data-search="{escape(title+' '+desc+' '+refs, quote=True)}">
<div class="card-top"><span class="topic-icon">{icon(key)}</span><span class="card-number">BÀI {index+1:02d}</span></div>
<h3><a href="{slug}.html">{escape(title)}</a></h3><p>{escape(desc)}</p>
<div class="card-foot"><span>{refs} <b>·</b> {minutes(slug)} phút</span><span class="done-status" data-slug="{slug}"></span><span class="arrow" aria-hidden="true">↗</span></div></article>"""

def home():
    groups=[]
    filter_buttons = []
    for i,(a,b,title,desc) in enumerate(WEEKS,1):
        groups.append(f'<section class="week" id="tuan-{i}" data-group="{i}"><header><span>{i:02d}</span><div><h2>{title}</h2><p>{desc}</p></div></header><div class="cards">{"".join(card(j,ARTICLES[j]) for j in range(a,b))}</div></section>')
        filter_buttons.append(f'<button aria-pressed="false" data-filter="{i}">{"Lab thực tế" if i == 4 else f"Tuần {i}"}</button>')
    body=f"""<section class="shell hero"><div class="hero-copy"><div class="kicker"><i></i> NHẬT KÝ HỌC BẢO MẬT CLOUD NATIVE</div>
<h1>Bảo mật từ <em>kernel</em><br>đến Kubernetes<span class="mint">.</span></h1>
<p>Học cách các microservice giao tiếp, lần theo dấu vết bằng eBPF và bảo vệ cluster với Zero Trust. Thực hành trên một cửa hàng mô phỏng.</p>
<div class="hero-actions"><a class="button" href="{ARTICLES[0][0]}.html">Bắt đầu học <span>→</span></a><a class="quiet" href="16-ket-qua-baseline.html">Xem kết quả baseline ↗</a></div>
</div><figure class="hero-visual"><img src="assets/hero.webp" alt="Các khối máy chủ xanh trong mô hình mạng phát sáng" decoding="async" fetchpriority="high"><figcaption><span>●</span> KERNEL LAB <b>01 / {len(WEEKS):02d}</b></figcaption></figure></section>
<div class="shell facts"><div><b>{len(WEEKS):02d}</b> chặng học</div><div><b>{len(ARTICLES):02d}</b> bài hướng dẫn</div><div><b>01</b> lab Online Boutique</div><div class="progress-tile"><span data-progress>0 / {len(ARTICLES)} bài đã đọc</span><progress value="0" max="{len(ARTICLES)}" aria-label="Tiến độ đọc"></progress></div></div>
<section class="shell curriculum" id="lo-trinh"><div class="section-head"><div><div class="eyebrow">ĐỌC THEO THỨ TỰ HOẶC CHỌN CHỦ ĐỀ</div><h2>Lộ trình học</h2></div><label class="search"><span aria-hidden="true">⌕</span><input id="search" type="search" placeholder="Tìm bài hoặc mã R…" aria-label="Tìm bài hoặc mã nguồn tham khảo"></label></div>
<div class="filters" aria-label="Lọc theo tuần"><button aria-pressed="true" data-filter="all">Tất cả bài</button>{"".join(filter_buttons)}</div><p id="empty" hidden>Chưa tìm thấy bài phù hợp. Thử tên chủ đề hoặc mã R.</p>
{"".join(groups)}</section>"""
    return layout("Kernel Notes — Bảo mật Kubernetes & eBPF", body)

def article_page(index, record):
    slug,title,desc,refs,_=record
    body,toc=article_html(slug)
    cover = '<figure class="article-cover"><img src="assets/runtime.webp" alt="Vi mạch graphite với các đường tín hiệu xanh và hổ phách"></figure>' if slug == "05-ebpf-runtime-telemetry" else ""
    prev = f'<a href="{ARTICLES[index-1][0]}.html">← {escape(ARTICLES[index-1][1])}</a>' if index>0 else '<a href="./#lo-trinh">← Lộ trình</a>'
    next_link = f'<a href="{ARTICLES[index+1][0]}.html">{escape(ARTICLES[index+1][1])} →</a>' if index+1<len(ARTICLES) else '<a href="09-tra-cuu.html">Tra cứu →</a>'
    return layout(title+" · Kernel Notes", f"""<div class="read-progress" aria-hidden="true"></div><header class="shell article-head"><a class="back" href="./#tuan-{week_for(index)}">← Lộ trình học</a><div class="eyebrow">BÀI {index+1:02d} · {"LAB THỰC TẾ" if week_for(index) == 4 else f"TUẦN {week_for(index)}"} · {refs} · {minutes(slug)} PHÚT ĐỌC</div>
<h1>{escape(title)}</h1><p>{escape(desc)}</p></header>
<div class="shell reading"><article class="prose">{cover}{body}<div class="finish"><button class="button" data-complete="{slug}" aria-pressed="false">Đánh dấu đã đọc</button></div><nav class="article-nav" aria-label="Bài liền kề">{prev}{next_link}</nav></article><aside class="toc-panel"><h2>Trong bài này</h2>{toc}</aside></div>""",desc)

(ROOT/"index.html").write_text(home(),encoding="utf-8")
for i, record in enumerate(ARTICLES):
    (ROOT/f"{record[0]}.html").write_text(article_page(i,record),encoding="utf-8")
body,toc=article_html("09-tra-cuu")
(ROOT/"09-tra-cuu.html").write_text(layout("Tra cứu · Kernel Notes",f'<header class="shell article-head"><a class="back" href="./#lo-trinh">← Lộ trình học</a><h1>Tra cứu tài liệu</h1><p>Thuật ngữ, nguồn chính thức và mẫu bàn giao lần chạy.</p></header><div class="shell reading"><article class="prose">{body}</article><aside class="toc-panel"><h2>Trong trang này</h2>{toc}</aside></div>'),encoding="utf-8")


