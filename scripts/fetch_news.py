"""Collect the latest economy and politics headlines for the US, China and Korea
from public RSS feeds and write one JSON file per edition:

  data/news.json     Korean edition  (index.html)
  data/news-zh.json  Chinese edition (zh/index.html)

Every article is kept in its original language; nothing is translated.

Standard library only, so it runs on GitHub Actions (or any Mac) without installs.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CNBC_ECON = "https://www.cnbc.com/id/20910258/device/rss/rss.html"
CNBC_POL = "https://www.cnbc.com/id/10000113/device/rss/rss.html"
CHINANEWS_ECON = "https://www.chinanews.com.cn/rss/finance.xml"
CHINANEWS_POL = "https://www.chinanews.com.cn/rss/china.xml"

EDITIONS = {
    "ko": {
        "out": ROOT / "data" / "news.json",
        "feeds": [
            # key,          source name,           RSS URL,                                  language
            ("us_economy",  "CNBC Economy",        CNBC_ECON,                                "en"),
            ("us_politics", "CNBC Politics",       CNBC_POL,                                 "en"),
            ("cn_economy",  "中国新闻网 财经",       CHINANEWS_ECON,                           "zh"),
            ("cn_politics", "中国新闻网 时政",       CHINANEWS_POL,                            "zh"),
            ("kr_economy",  "연합뉴스 경제",        "https://www.yna.co.kr/rss/economy.xml",  "ko"),
            ("kr_politics", "연합뉴스 정치",        "https://www.yna.co.kr/rss/politics.xml", "ko"),
        ],
    },
    "zh": {
        "out": ROOT / "data" / "news-zh.json",
        "feeds": [
            ("us_economy",  "CNBC Economy",        CNBC_ECON,                                         "en"),
            ("us_politics", "CNBC Politics",       CNBC_POL,                                          "en"),
            ("cn_economy",  "中国新闻网 财经",       CHINANEWS_ECON,                                    "zh"),
            ("cn_politics", "中国新闻网 时政",       CHINANEWS_POL,                                     "zh"),
            ("kr_economy",  "韩联社 经济",          "https://cn.yna.co.kr/RSS/economy.xml",            "zh"),
            ("kr_politics", "韩联社 政治",          "https://cn.yna.co.kr/RSS/politics.xml",           "zh"),
        ],
    },
}
KEEP = 8                   # items stored per category (the page shows 3, the rest behind "더 보기")
MAX_AGE = timedelta(days=3)  # wide enough to bridge weekends, when some desks go quiet

# Yonhap posts many small notices; skip those so real stories rise to the top.
SKIP_TITLE = re.compile(r"^\s*\[(게시판|인사|부고|포토|그래픽|사진|표|모멘트|이 시각|화보|속보)\]")
# Datelines at the start of a lead: "(서울=연합뉴스) 홍길동 기자 = ", "韩联社首尔10月18日电 ", "中新网成都10月18日电(张小丽)"
DATELINE = re.compile(
    r"^\s*(\([^)]*연합뉴스\)\s*[^=]{0,60}=\s*"
    r"|(韩联社|中新网|中新社)[^电]{0,24}电\s*(\([^)]{0,30}\)|（[^）]{0,30}）)?\s*)"
)
TAG = re.compile(r"<[^>]+>")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MorningBrief RSS reader)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


# ---------------------------------------------------------------- feeds
def clean(text, limit=220):
    text = html.unescape(TAG.sub(" ", html.unescape(text or "")))
    text = text.replace("　", " ")
    text = DATELINE.sub("", text.strip())
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        cut = cut.rsplit(" ", 1)[0] if " " in cut[-40:] else cut  # CJK text has no spaces to break on
        text = cut.rstrip(",.·，。、") + "…"
    return text


def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def collect(url, now, keep, limit):
    root = ET.fromstring(fetch(url))
    items = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"), 140)
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("http") or SKIP_TITLE.search(title):
            continue
        published = parse_date(it.findtext("pubDate") or "")
        if published and now - published > MAX_AGE:
            continue
        items.append({
            "title": title,
            "summary": clean(it.findtext("description"), limit),
            "url": link,
            "published": published.astimezone(timezone.utc).isoformat() if published else None,
            # Yonhap marks fuller, updated reports with (종합) — treat them as the day's main stories.
            "_rank": 0 if "(종합" in title else 1,
        })
    items.sort(key=lambda x: (x["_rank"], -(datetime.fromisoformat(x["published"]).timestamp() if x["published"] else 0)))
    seen, unique = set(), []
    for x in items:
        k = re.sub(r"\W+", "", x["title"])[:30]
        if k in seen:
            continue
        seen.add(k)
        x.pop("_rank")
        unique.append(x)
    return unique[:keep]


def build(edition, cfg, now, raw_cache):
    out = cfg["out"]
    previous = {}
    if out.exists():
        try:
            previous = json.loads(out.read_text(encoding="utf-8")).get("categories", {})
        except Exception:
            previous = {}

    categories, failures = {}, []
    for key, source, url, lang in cfg["feeds"]:
        try:
            # Chinese and Korean leads carry more per character, so keep them shorter.
            limit = 220 if lang == "en" else 120
            if url not in raw_cache:
                raw_cache[url] = collect(url, now, KEEP, limit)
            items = [dict(x) for x in raw_cache[url]]
            if not items:
                raise ValueError("no recent items")
            categories[key] = {"country": key[:2], "topic": key[3:], "source": source, "lang": lang, "items": items}
        except Exception as e:  # keep the previous items rather than leaving a hole
            failures.append(f"[{edition}] {key}: {e}")
            if key in previous:
                categories[key] = {**previous[key], "stale": True}

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"updatedAt": now.isoformat(), "categories": categories},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{edition}] saved {sum(len(c['items']) for c in categories.values())} items to {out.relative_to(ROOT)}")
    return failures, len(cfg["feeds"])


def main():
    now = datetime.now(timezone.utc)
    raw_cache = {}  # the same feed is shared by both editions; fetch it once
    total_fail, total = [], 0
    for edition, cfg in EDITIONS.items():
        failures, n = build(edition, cfg, now, raw_cache)
        total_fail += failures
        total += n
    for f in total_fail:
        print("WARN", f, file=sys.stderr)
    if len(total_fail) == total:
        sys.exit(1)


if __name__ == "__main__":
    main()
