"""Collect the key economy and politics stories for the US, China and Korea
and write them to data/news.json (Korean page) and data/news-zh.json (Chinese page).

How "key" is decided, without any AI:
  1. Google News section feeds (Business / Politics) for each country, in that
     country's language, list stories in Google's importance order, and each
     story lists the other outlets covering it. That order and the outlet count
     are kept as-is.
  2. Google News gives no summary, so each story is matched to the same story
     in a wire service's own RSS (CNBC, China News Service, Yonhap) by title
     similarity; when found, that outlet's lead paragraph becomes the summary
     and its direct link is kept.
  3. If Google News cannot be reached, the category falls back to the newest
     articles from the wire service's section feed.

Every article stays in its original language; nothing is translated.
Standard library only, so it runs on GitHub Actions (or any Mac) without installs.
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = [ROOT / "data" / "news.json", ROOT / "data" / "news-zh.json"]


def google_news(section, lang):
    edition = {"en": ("en-US", "US", "US:en"), "zh": ("zh-CN", "CN", "CN:zh-Hans"), "ko": ("ko", "KR", "KR:ko")}[lang]
    hl, gl, ceid = edition
    return f"https://news.google.com/rss/headlines/section/topic/{section}?" + urllib.parse.urlencode(
        {"hl": hl, "gl": gl, "ceid": ceid})


# Wire-service feeds: used for summaries (matched by title) and as the fallback list.
WIRE = {
    "us": ["https://www.cnbc.com/id/20910258/device/rss/rss.html",   # economy
           "https://www.cnbc.com/id/10000113/device/rss/rss.html",   # politics
           "https://www.cnbc.com/id/100003114/device/rss/rss.html"], # top news
    "cn": ["https://www.chinanews.com.cn/rss/finance.xml",
           "https://www.chinanews.com.cn/rss/china.xml",
           "https://www.chinanews.com.cn/rss/importnews.xml",
           "https://www.chinanews.com.cn/rss/scroll-news.xml"],
    "kr": ["https://www.yna.co.kr/rss/economy.xml",
           "https://www.yna.co.kr/rss/politics.xml",
           "https://www.yna.co.kr/rss/news.xml"],
}

CATEGORIES = [
    # key,          language, Google News section,            fallback wire feed (newest first)
    ("us_economy",  "en", google_news("BUSINESS", "en"), WIRE["us"][0]),
    ("us_politics", "en", google_news("POLITICS", "en"), WIRE["us"][1]),
    ("cn_economy",  "zh", google_news("BUSINESS", "zh"), WIRE["cn"][0]),
    ("cn_politics", "zh", google_news("POLITICS", "zh"), WIRE["cn"][1]),
    ("kr_economy",  "ko", google_news("BUSINESS", "ko"), WIRE["kr"][0]),
    ("kr_politics", "ko", google_news("POLITICS", "ko"), WIRE["kr"][1]),
]
KEEP = 8                    # stories per category (the page shows 3, the rest behind "더 보기")
MAX_AGE = timedelta(days=3)

# Yonhap posts many small notices; skip those so real stories rise to the top.
SKIP_TITLE = re.compile(r"^\s*\[(게시판|인사|부고|포토|그래픽|사진|표|모멘트|이 시각|화보)\]")
# Datelines at the start of a lead: "(서울=연합뉴스) 홍길동 기자 = ", "中新网成都10月18日电(张小丽)"
DATELINE = re.compile(
    r"^\s*(\([^)]*연합뉴스\)\s*[^=]{0,60}=\s*"
    r"|(韩联社|中新网|中新社)[^电]{0,24}电\s*(\([^)]{0,30}\)|（[^）]{0,30}）)?\s*)"
)
TAG = re.compile(r"<[^>]+>")
LI = re.compile(r"<li>.*?</li>", re.S)
FONT = re.compile(r"<font[^>]*>(.*?)</font>", re.S)
ANCHOR = re.compile(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.S)
RELATED = 2                 # other outlets' headlines shown under each story


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MorningBrief RSS reader)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


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


def iso(d):
    return d.astimezone(timezone.utc).isoformat() if d else None


def recent(d, now):
    return d is None or now - d <= MAX_AGE


# ---------------------------------------------------------------- title matching
def shingles(title, lang):
    """Word set for English, character pairs for Chinese and Korean (no reliable word breaks)."""
    t = re.sub(r"[\W_]+", " ", title.lower()).strip()
    if lang == "en":
        stop = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "as", "at", "is", "with", "by", "from", "after"}
        return {w for w in t.split() if w not in stop and len(w) > 1}
    t = t.replace(" ", "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ---------------------------------------------------------------- feeds
def wire_items(url, now, limit):
    """Articles from a wire service's own feed, with their lead paragraph."""
    out = []
    for it in ET.fromstring(fetch(url)).iter("item"):
        title = clean(it.findtext("title"), 140)
        link = (it.findtext("link") or "").strip()
        published = parse_date(it.findtext("pubDate") or "")
        if not title or not link.startswith("http") or SKIP_TITLE.search(title) or not recent(published, now):
            continue
        out.append({"title": title, "summary": clean(it.findtext("description"), limit),
                    "url": link, "published": iso(published), "outlet": None,
                    "_rank": 0 if "(종합" in title else 1})
    return out


def google_items(url, now):
    """Stories in Google News's importance order, with the number of outlets covering each."""
    out, seen = [], set()
    for it in ET.fromstring(fetch(url)).iter("item"):
        outlet = (it.findtext("source") or "").strip()
        title = html.unescape(it.findtext("title") or "").strip()
        # Google appends " - Outlet" to every headline (sometimes with a longer outlet name).
        head, sep, tail = title.rpartition(" - ")
        if sep and head and len(tail) <= 40:
            title = head.strip()
        published = parse_date(it.findtext("pubDate") or "")
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("http") or not recent(published, now):
            continue
        key = re.sub(r"\W+", "", title)[:30]
        if key in seen:
            continue
        seen.add(key)
        # The description lists the other outlets covering the same story: count them,
        # and keep a couple of their headlines as context, since Google gives no summary.
        desc = it.findtext("description") or ""
        outlets, related = {outlet} if outlet else set(), []
        for li in LI.findall(desc):
            name = html.unescape(" ".join(FONT.findall(li))).strip()
            a = ANCHOR.search(li)
            if not name:
                continue
            outlets.add(name)
            if a and name != outlet and len(related) < RELATED:
                rel_title = html.unescape(TAG.sub("", a.group(2))).strip()
                if rel_title and rel_title != title:
                    related.append({"outlet": name, "title": rel_title, "url": html.unescape(a.group(1))})
        out.append({"title": title, "summary": "", "url": link, "published": iso(published),
                    "outlet": outlet, "coverage": len(outlets), "related": related})
    return out


def build_category(key, lang, gn_url, fallback_url, now, pools):
    limit = 220 if lang == "en" else 120
    pool = pools[key[:2]]
    try:
        stories = google_items(gn_url, now)[:KEEP]
        if len(stories) < 3:
            raise ValueError(f"only {len(stories)} stories")
    except Exception as e:
        print(f"WARN {key}: Google News unavailable ({e}); using newest wire articles", file=sys.stderr)
        items = wire_items(fallback_url, now, limit)
        items.sort(key=lambda x: (x["_rank"], -(datetime.fromisoformat(x["published"]).timestamp() if x["published"] else 0)))
        for x in items:
            x.pop("_rank", None)
        return items[:KEEP], "wire"

    # Borrow a summary (and a direct link) from the same story in the wire feeds.
    matched = 0
    for s in stories:
        sh = shingles(s["title"], lang)
        best, score = None, 0.0
        for w in pool:
            sc = similarity(sh, w["_sh"])
            if sc > score:
                best, score = w, sc
        if best and score >= (0.5 if lang == "en" else 0.45):
            s["summary"] = best["summary"]
            s["direct"] = best["url"]
            matched += 1
    print(f"{key}: {len(stories)} stories by importance, {matched} with a summary")
    return stories, "google"


def main():
    now = datetime.now(timezone.utc)
    pools = {}
    for country, urls in WIRE.items():
        pool, seen = [], set()
        lang = {"us": "en", "cn": "zh", "kr": "ko"}[country]
        for u in urls:
            try:
                for w in wire_items(u, now, 220 if lang == "en" else 120):
                    if w["url"] not in seen and w["summary"]:
                        seen.add(w["url"])
                        w["_sh"] = shingles(w["title"], lang)
                        pool.append(w)
            except Exception as e:
                print(f"WARN wire feed {u}: {e}", file=sys.stderr)
        pools[country] = pool

    previous = {}
    if OUTPUTS[0].exists():
        try:
            previous = json.loads(OUTPUTS[0].read_text(encoding="utf-8")).get("categories", {})
        except Exception:
            previous = {}

    categories, failures = {}, 0
    for key, lang, gn_url, fallback_url in CATEGORIES:
        try:
            items, ranking = build_category(key, lang, gn_url, fallback_url, now, pools)
            if not items:
                raise ValueError("no recent items")
            categories[key] = {"country": key[:2], "topic": key[3:], "lang": lang, "ranking": ranking,
                               "source": "Google News" if ranking == "google" else urllib.parse.urlparse(fallback_url).hostname,
                               "items": items}
        except Exception as e:  # keep the previous items rather than leaving a hole
            failures += 1
            print(f"WARN {key}: {e}", file=sys.stderr)
            if key in previous:
                categories[key] = {**previous[key], "stale": True}

    body = json.dumps({"updatedAt": now.isoformat(), "categories": categories}, ensure_ascii=False, indent=1)
    for out in OUTPUTS:  # both pages show the same stories; only the page's own labels differ
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
    print(f"saved {sum(len(c['items']) for c in categories.values())} stories")
    if failures == len(CATEGORIES):
        sys.exit(1)


if __name__ == "__main__":
    main()
