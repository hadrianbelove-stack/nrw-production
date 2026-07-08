"""Google News RSS keyword feeds for restoration / reissue EVENTS.

Format-agnostic (theatrical / VOD / disc) and restoration-explicit — the SIGNAL
side of the restoration lane (the disc calendar is the lead pool). Plain XML,
no 403. Headlines are the triage cue: intake Pass F consumes
collect(CLEAN_KEYWORDS); flagged-but-unresolved headlines get their article
read by the Gemini fallback (Phase 3).

Run as a probe (all keywords incl. the noisy ones, prints only):
    python3 -m pipeline.distributors.googlenews
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

# Production keyword set — measured clean (docs/DISTRIBUTOR_TRACKING_PLAN.md
# "keyword findings"): precise restoration signals, near-zero off-domain noise.
CLEAN_KEYWORDS = [
    '"4K restoration"',
    '"2K restoration"',
    '"film restoration"',
    '"newly restored"',
]

# Probe-only extras — measured noisy ("re-release" = games/sneakers/ecology) or
# redundant. Kept for the dry-run probe so keyword quality stays observable.
PROBE_KEYWORDS = [
    '"new restoration"',
    '"new 4K restoration"',
    '"restored re-release"',
    '"new director\'s cut"',
    '"re-release"',
    '"rerelease"',
]

KEYWORDS = CLEAN_KEYWORDS + PROBE_KEYWORDS

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
    """(candidates, quoted) — ALL quoted phrases (capped at 3), not just the first:
    a headline can quote several titles ('UK "suedehead" subculture film "Bronco
    Bullfrog" gets new 2K restoration') and picking the first parks the wrong
    film. The caller tries each; only an unambiguous single resolution counts.
    Trigger-word truncations are rough single guesses — the article-reading
    fallback owns them when they fail to match."""
    quoted = [q.strip() for q in
              re.findall(r"[\"'‘’“”]([^\"'‘’“”]{2,70})[\"'‘’“”]", headline) if q.strip()]
    if quoted:
        return quoted[:3], True
    m = _TRIGGER.search(headline)
    if m and m.start() > 2:
        return [headline[:m.start()].strip(" :–-’'s")], False
    return [headline], False


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t.lower())).strip()


def collect(keywords=None):
    by_title = {}
    per_kw = {}
    for kw in (keywords or KEYWORDS):
        try:
            items = fetch_feed(kw)
        except Exception as e:
            print(f"  ! {kw} failed: {e}", file=sys.stderr)
            items = []
        per_kw[kw] = len(items)
        for it in items:
            it["guesses"], it["quoted"] = guess_title(it["headline"])
            it["guess"] = it["guesses"][0]      # display + dedupe key
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
