"""Collect the latest economy and politics headlines for the US, China and Korea
from public RSS feeds and write them to data/news.json.

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

FEEDS = [
    # key,          country, topic,   source name,              RSS URL
    ("us_economy",  "us", "economy",  "CNBC Economy",           "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("us_politics", "us", "politics", "CNBC Politics",          "https://www.cnbc.com/id/10000113/device/rss/rss.html"),
    ("cn_economy",  "cn", "economy",  "SCMP China Economy",     "https://www.scmp.com/rss/318421/feed"),
    ("cn_politics", "cn", "politics", "SCMP China Politics",    "https://www.scmp.com/rss/318198/feed"),
    ("kr_economy",  "kr", "economy",  "연합뉴스 경제",           "https://www.yna.co.kr/rss/economy.xml"),
    ("kr_politics", "kr", "politics", "연합뉴스 정치",           "https://www.yna.co.kr/rss/politics.xml"),
]
KEEP = 8                   # items stored per category (the page shows 3, the rest behind "더 보기")
MAX_AGE = timedelta(days=3)  # wide enough to bridge weekends, when some desks go quiet
# Yonhap posts many small notices; skip those so real stories rise to the top.
SKIP_TITLE = re.compile(r"^\s*\[(게시판|인사|부고|포토|그래픽|사진|표|모멘트|이 시각|화보|속보)\]")
YONHAP_BYLINE = re.compile(r"^\s*\([^)]*연합뉴스\)\s*[^=]{0,60}=\s*")
TAG = re.compile(r"<[^>]+>")

OUT = Path(__file__).resolve().parent.parent / "data" / "news.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MorningBrief RSS reader)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def clean(text, limit=220):
    text = html.unescape(TAG.sub(" ", html.unescape(text or "")))
    text = YONHAP_BYLINE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.·") + "…"
    return text


def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def collect(key, source, url, now):
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
            "summary": clean(it.findtext("description")),
            "url": link,
            "published": published.astimezone(timezone.utc).isoformat() if published else None,
            # Yonhap marks fuller, updated reports with (종합) — treat them as the day's main stories.
            "_rank": 0 if "(종합" in title else 1,
        })
    # Main stories first, then newest first.
    items.sort(key=lambda x: (x["_rank"], -(datetime.fromisoformat(x["published"]).timestamp() if x["published"] else 0)))
    seen, unique = set(), []
    for x in items:
        k = re.sub(r"\W+", "", x["title"])[:30]
        if k in seen:
            continue
        seen.add(k)
        x.pop("_rank")
        unique.append(x)
    return unique[:KEEP]


def main():
    now = datetime.now(timezone.utc)
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8")).get("categories", {})
        except Exception:
            previous = {}

    categories, failures = {}, []
    for key, country, topic, source, url in FEEDS:
        try:
            items = collect(key, source, url, now)
            if not items:
                raise ValueError("no recent items")
            categories[key] = {"country": country, "topic": topic, "source": source, "items": items}
        except Exception as e:  # keep yesterday's items rather than leaving a hole
            failures.append(f"{key}: {e}")
            if key in previous:
                categories[key] = {**previous[key], "stale": True}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updatedAt": now.isoformat(), "categories": categories},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {sum(len(c['items']) for c in categories.values())} items to {OUT}")
    for f in failures:
        print("WARN", f, file=sys.stderr)
    if len(failures) == len(FEEDS):
        sys.exit(1)


if __name__ == "__main__":
    main()
