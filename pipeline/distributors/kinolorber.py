"""Source: Kino Lorber's OWN calendar — the authoritative per-label schedule.

`kinolorber.com/list/view/code/now-playing-amp-coming-soon` is Cloudflare-protected
(403 to any plain fetch, even with a UA) but renders fine under headless Playwright
(verified 2026-06-22). It's a dated list: month <h5>, `<li class="date">` headers, then
`<li>Title <a href="/product/slug">Format</a></li>` per film. Richer than the third-party
disc aggregators — official, exact street dates, real formats.

Caveat vs the aggregator: the listing has NO release year, so TMDB matching by title alone
is weaker; year enrichment (product page or TMDB best-guess) is a downstream step.

Read-only dry-run: python3 -m pipeline.distributors.kinolorber
"""

import re
import sys
import json
import datetime as dt

from bs4 import BeautifulSoup

URL = "https://www.kinolorber.com/list/view/code/now-playing-amp-coming-soon"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DISTRIBUTOR = "Kino Lorber"
_DISC = re.compile(r"\b(DVD|Blu-?ray|4K|UHD)\b", re.I)


def fetch_html(url=URL):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=UA)
        pg.goto(url, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(3000)
        html = pg.content()
        b.close()
    return html


def _parse_date(text):
    text = text.strip()
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    for ul in soup.find_all("ul"):
        lis = ul.find_all("li", recursive=False)
        if not any("date" in (li.get("class") or []) for li in lis):
            continue
        current = None
        for li in lis:
            if "date" in (li.get("class") or []):
                strong = li.find("strong")
                if strong:
                    current = _parse_date(strong.get_text(" ", strip=True))
                continue
            if not current:
                continue
            anchors = li.find_all("a", href=re.compile(r"^/product/"))
            formats = [a.get_text(" ", strip=True) for a in anchors if a.get_text(strip=True)]
            urls = [a["href"] for a in anchors]
            title = li.get_text(" ", strip=True)
            for f in formats:
                title = title.replace(f, "")
            title = re.sub(r"\s+", " ", title).strip(" -–")
            if not title:
                continue
            kind = "disc" if any(_DISC.search(f) for f in formats) else "other"
            key = (title.lower(), current)
            if key not in rows:                       # dedupe slick-carousel clones
                rows[key] = {
                    "title": title,
                    "year": None,                     # not on the listing; enrich later
                    "release_date": current,
                    "distributor": DISTRIBUTOR,
                    "formats": formats,
                    "kind": kind,
                    "source_url": "https://www.kinolorber.com" + urls[0] if urls else URL,
                }
    return list(rows.values())


def fetch():
    return parse_rows(fetch_html())


def _dry_run():
    rows = parse_rows(fetch_html())
    print(f"Kino Lorber own calendar — {len(rows)} dated entries\n")
    for r in sorted(rows, key=lambda x: (x["release_date"] or "", x["title"])):
        print(f"  {r['release_date']}  {r['title']}  [{'/'.join(r['formats']) or r['kind']}]")
    if "--json" in sys.argv:
        print("\n" + json.dumps(rows, indent=2))


if __name__ == "__main__":
    _dry_run()
