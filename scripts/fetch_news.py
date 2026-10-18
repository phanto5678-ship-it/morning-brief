"""Collect the latest economy and politics headlines for the US, China and Korea
from public RSS feeds and write one JSON file per edition:

  data/news.json     Korean edition  (index.html)
  data/news-zh.json  Chinese edition (zh/index.html)

Articles that are not in the edition's language get a machine translation from
free endpoints (Google first, MyMemory as backup). The original stays alongside.

Standard library only, so it runs on GitHub Actions (or any Mac) without installs.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CNBC_ECON = "https://www.cnbc.com/id/20910258/device/rss/rss.html"
CNBC_POL = "https://www.cnbc.com/id/10000113/device/rss/rss.html"

EDITIONS = {
    "ko": {
        "out": ROOT / "data" / "news.json",
        "feeds": [
            # key,          source name,           RSS URL,                                  language
            ("us_economy",  "CNBC Economy",        CNBC_ECON,                                "en"),
            ("us_politics", "CNBC Politics",       CNBC_POL,                                 "en"),
            ("cn_economy",  "SCMP China Economy",  "https://www.scmp.com/rss/318421/feed",   "en"),
            ("cn_politics", "SCMP China Politics", "https://www.scmp.com/rss/318198/feed",   "en"),
            ("kr_economy",  "연합뉴스 경제",        "https://www.yna.co.kr/rss/economy.xml",  "ko"),
            ("kr_politics", "연합뉴스 정치",        "https://www.yna.co.kr/rss/politics.xml", "ko"),
        ],
    },
    "zh": {
        "out": ROOT / "data" / "news-zh.json",
        "feeds": [
            ("us_economy",  "CNBC Economy",        CNBC_ECON,                                         "en"),
            ("us_politics", "CNBC Politics",       CNBC_POL,                                          "en"),
            ("cn_economy",  "中国新闻网 财经",       "https://www.chinanews.com.cn/rss/finance.xml",    "zh"),
            ("cn_politics", "中国新闻网 时政",       "https://www.chinanews.com.cn/rss/china.xml",      "zh"),
            ("kr_economy",  "韩联社 经济",          "https://cn.yna.co.kr/RSS/economy.xml",            "zh"),
            ("kr_politics", "韩联社 政治",          "https://cn.yna.co.kr/RSS/politics.xml",           "zh"),
        ],
    },
}
# The free translator has a small daily allowance, so translated categories keep fewer items.
KEEP_NATIVE, KEEP_TRANSLATED = 8, 6
TRANSLATE_SUMMARIES = 3    # summaries translated per category (titles are always translated)
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


# ---------------------------------------------------------------- translation
_google_blocked = False
_mymemory_blocked = False
GOOGLE_LANG = {"ko": "ko", "zh": "zh-CN", "en": "en"}
MYMEMORY_LANG = {"ko": "ko-KR", "zh": "zh-CN", "en": "en-GB"}


def translate(text, src, dst):
    """Translate with free endpoints; None when both refuse (the page then shows the original)."""
    global _google_blocked, _mymemory_blocked
    if not text:
        return None
    if not _google_blocked:
        try:
            q = urllib.parse.urlencode({"client": "gtx", "sl": GOOGLE_LANG[src], "tl": GOOGLE_LANG[dst], "dt": "t", "q": text})
            data = json.loads(fetch("https://translate.googleapis.com/translate_a/single?" + q))
            out = "".join(part[0] for part in data[0] if part and part[0]).strip()
            if out:
                return out
        except Exception:
            _google_blocked = True  # rate-limited: stop asking for the rest of this run
    if not _mymemory_blocked:
        try:
            q = urllib.parse.urlencode({"q": text[:480], "langpair": f"{MYMEMORY_LANG[src]}|{MYMEMORY_LANG[dst]}"})
            data = json.loads(fetch("https://api.mymemory.translated.net/get?" + q))
            out = html.unescape((data.get("responseData") or {}).get("translatedText") or "").strip()
            if data.get("quotaFinished") or "MYMEMORY WARNING" in out.upper():
                _mymemory_blocked = True
            elif out:
                return out
        except Exception:
            pass
    return None


def add_translation(items, src, dst, cache):
    """Fill title_tr / summary_tr, reusing an earlier translation of the same article."""
    done = 0
    for i, x in enumerate(items):
        old = cache.get(x["url"], {})
        x["title_tr"] = (old.get("title_tr") if old.get("title") == x["title"] else None) or translate(x["title"], src, dst)
        if i < TRANSLATE_SUMMARIES and x["summary"]:
            x["summary_tr"] = (old.get("summary_tr") if old.get("summary") == x["summary"] else None) \
                or translate(x["summary"], src, dst)
        done += bool(x["title_tr"])
        time.sleep(0.3)  # be gentle with the free services
    return done


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
    tr_cache = {x["url"]: x for c in previous.values() for x in c.get("items", [])}

    categories, failures = {}, []
    for key, source, url, lang in cfg["feeds"]:
        native = lang == edition
        try:
            # Chinese and Korean leads carry more per character, so keep them shorter.
            limit = 220 if lang == "en" else 120
            if url not in raw_cache:
                raw_cache[url] = collect(url, now, KEEP_NATIVE, limit)
            items = [dict(x) for x in raw_cache[url][:KEEP_NATIVE if native else KEEP_TRANSLATED]]
            if not items:
                raise ValueError("no recent items")
            if not native:
                n = add_translation(items, lang, edition, tr_cache)
                print(f"[{edition}] {key}: translated {n}/{len(items)} titles")
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
