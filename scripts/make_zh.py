"""Build the Chinese edition page (zh/index.html) from index.html.

The page's script picks its strings from <html lang>, so the Chinese page only
differs in its head, fonts and relative paths. Run this after editing index.html:

    python3 scripts/make_zh.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "index.html").read_text(encoding="utf-8")

REPLACEMENTS = [
    ('<html lang="ko">', '<html lang="zh-CN">'),
    ('<title>Morning Brief</title>', '<title>Morning Brief 中文版</title>'),
    ('content="미국·중국·한국 경제·정치 뉴스와 서울·상하이·LA 날씨"', 'content="中美韩经济与政治新闻，以及首尔、上海、洛杉矶天气"'),
    ('content="Brief"', 'content="Brief 中文"'),
    ('href="manifest.webmanifest"', 'href="manifest.webmanifest"'),  # zh/ has its own manifest
    ('href="icons/', 'href="../icons/'),
    ('family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Noto+Serif+KR:wght@600;800',
     'family=Noto+Sans+SC:wght@400;500;600;700&family=Noto+Serif+SC:wght@600;800'),
    ("--font-display:'Noto Serif KR', 'Apple SD Gothic Neo', Georgia, serif;",
     "--font-display:'Noto Serif SC', 'Songti SC', Georgia, serif;"),
    ("--font-body:'IBM Plex Sans KR', 'Apple SD Gothic Neo', system-ui, sans-serif;",
     "--font-body:'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;"),
    ('data-t="loading">뉴스를 불러오는 중…</div>', 'data-t="loading">正在加载新闻…</div>'),
    ("navigator.serviceWorker.register('sw.js')", "navigator.serviceWorker.register('../sw.js')"),
]

out = src
for old, new in REPLACEMENTS:
    if old not in out:
        raise SystemExit(f"index.html changed; update make_zh.py for: {old[:60]}")
    out = out.replace(old, new)

(ROOT / "zh").mkdir(exist_ok=True)
(ROOT / "zh" / "index.html").write_text(out, encoding="utf-8")
print("wrote zh/index.html")
