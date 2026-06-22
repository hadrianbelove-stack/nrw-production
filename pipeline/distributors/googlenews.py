"""Source probe: Google News RSS keyword feeds for restoration / reissue EVENTS.

Format-agnostic (theatrical / VOD / disc) and restoration-explicit — closer to the
digital signal NRW cares about than a Blu-ray calendar. Plain XML, no 403.

This is an evaluation probe: it fetches several keyword feeds, dedupes, makes a
rough title guess, and prints them so we can judge the source. It writes nothing.

Run: python3 -m pipeline.distributors.googlenews
"""

import re
import sys
import datetime as dt
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

# Keyword phrases worth probing. Quoted = exact phrase. Mix of formats/wordings.
KEYWORDS = [
    '"4K restoration"',
    '"film restoration"',
    '"new restoration"',
    '"new 4K restoration"',
    '"restored re-release"',
    '"new director\'s cut"',
    '"2K restoration"',
    '"newly restored"',
    '"re-release"',
    '"rerelease"',
]

_TRIGGER = re.compile(
    r"\b(4K|2K|restoration|restored|remaster|re-?release|returns?|"
    r"director'?s cut|gets?|review|coming|hits?|heads?)\b", re.I)


def fetch_feed(phrase):
    url = BASE.format(q=quote(phrase))
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        # Google News titles end in " - Publisher"
        headline, _, source = title.rpartition(" - ")
        headline = headline or title
        pub = it.findtext("pubDate") or ""
        try:
            date = dt.datetime.strptime(pub[:16], "%a, %d %b %Y").date().isoformat()
        except ValueError:
            date = pub[:16]
        items.append({"headline": headline, "source": source,
                      "date": date, "link": it.findtext("link") or ""})
    return items


def guess_title(headline):
    m = re.search(r"[\"'‘’“”]([^\"'‘’“”]{2,70})[\"'‘’“”]", headline)
    if m:
        return m.group(1).strip()
    m = _TRIGGER.search(headline)
    if m and m.start() > 2:
        return headline[:m.start()].strip(" :–-’'s")
    return headline


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t.lower())).strip()


def collect():
    by_title = {}
    per_kw = {}
    for kw in KEYWORDS:
        try:
            items = fetch_feed(kw)
        except Exception as e:
            print(f"  ! {kw} failed: {e}", file=sys.stderr)
            items = []
        per_kw[kw] = len(items)
        for it in items:
            it["guess"] = guess_title(it["headline"])
            key = _norm(it["guess"])[:40]
            if key and key not in by_title:
                it["keyword"] = kw
                by_title[key] = it
    return by_title, per_kw


def _dry_run():
    by_title, per_kw = collect()
    print("Google News restoration probe — items per keyword:")
    for kw, n in per_kw.items():
        print(f"  {kw:28} {n}")
    print(f"\n{sum(per_kw.values())} raw items -> {len(by_title)} unique (by guessed title)\n")
    for it in sorted(by_title.values(), key=lambda x: x["date"], reverse=True):
        print(f"  {it['date']}  «{it['guess']}»  [{it['source']}]  ({it['keyword']})")
        print(f"      {it['headline']}")


if __name__ == "__main__":
    _dry_run()
