"""Source: physicalmedia.news/upcoming — aggregator of upcoming Blu-ray/4K releases.

Verified 2026-06-21: returns HTTP 200 to a plain requests.get WITH a browser
User-Agent (a naive no-UA fetch gets 403). No headless browser needed.

RESTORATION LANE only: we keep rows from a curated restoration label AND with a
10+ year gap between the film's year and the disc release date (an actual
restoration/reissue, not a recent catalog disc). The label list and the gap
threshold both come from admin/restoration_config.json, so adding a label there
is all it takes to widen coverage. The recent-arthouse / indie-distribution lane
is a separate effort, deferred.

This module does NOT write anything — TMDB matching + tracking intake are
downstream, gated on user review. Run
`python3 -m pipeline.distributors.physicalmedia` for a dry-run.
"""

import re
import sys
import json
import datetime as dt
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://physicalmedia.news/upcoming/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

ROOT = Path(__file__).resolve().parents[2]
RESTORATION_CONFIG = ROOT / "admin" / "restoration_config.json"

# Generic words stripped when reducing a label to its distinctive token(s).
_STOPWORDS = {"film", "films", "pictures", "picture", "collection", "media",
              "group", "releasing", "entertainment", "the", "co", "inc", "llc",
              "and", "of"}

_DATE_RE = re.compile(r"^([A-Z][a-z]{2}) (\d{1,2}), (\d{4})$")
_YEAR_PAREN_RE = re.compile(r"\((\d{4})(?:-\d{4})?\)")


def load_restoration_config():
    cfg = json.loads(RESTORATION_CONFIG.read_text())
    return cfg.get("year_gap_threshold", 10), cfg.get("restoration_distributors", [])


def build_keywords(labels):
    """Distinctive lowercase tokens (len>=4) from each curated label."""
    kws = set()
    for label in labels:
        for tok in re.findall(r"[a-z]+", label.lower()):
            if tok not in _STOPWORDS and len(tok) >= 4:
                kws.add(tok)
    return kws


def fetch_html(url=URL, timeout=20):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.text


def _parse_date(text):
    try:
        return dt.datetime.strptime(text.strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _clean_title(title_raw):
    title = re.sub(r"\b4K\b", "", title_raw)
    title = re.sub(r"\([^)]*\)", "", title)        # drop alt-title / edition parens
    title = title.replace('"', "").replace("“", "").replace("”", "")
    title = re.sub(r"\s+\)", "", title)            # stray unbalanced close paren
    title = re.sub(r"\s+\.", ".", title)           # " ." -> "."
    return re.sub(r"\s+", " ", title).strip()


def _parse_li(li, release_date):
    text = re.sub(r"\s+", " ", li.get_text(" ", strip=True))
    if " - " not in text:
        return None
    body, distributor = text.rsplit(" - ", 1)
    distributor = distributor.strip()

    years = list(_YEAR_PAREN_RE.finditer(body))
    if not years:
        return None
    last = years[-1]
    year = int(last.group(1))
    title_raw = body[:last.start()].strip()

    fmt = "4K" if re.search(r"\b4K\b", title_raw) else "Blu-ray"
    a = li.find("a", href=True)
    source_url = a["href"] if a else f"{URL}#{release_date}"

    return {
        "source_title": title_raw,
        "title": _clean_title(title_raw),
        "year": year,
        "release_date": release_date,   # disc date — proxy for digital availability
        "distributor": distributor,
        "format": fmt,
        "kind": "disc",
        "source_url": source_url,
    }


def parse_rows(html):
    """Every release row on the page, in document order."""
    soup = BeautifulSoup(html, "html.parser")
    rows, current_date = [], None
    for el in soup.find_all(["p", "ul"]):
        if el.name == "p":
            d = _parse_date(el.get_text(" ", strip=True))
            if d:
                current_date = d
        elif el.name == "ul" and current_date:
            for li in el.find_all("li", recursive=False):
                row = _parse_li(li, current_date)
                if row:
                    rows.append(row)
    return rows


def restoration_rows(html=None):
    """Curated-label rows with a 10+ year gap, deduped by (title, year)."""
    if html is None:
        html = fetch_html()
    threshold, labels = load_restoration_config()
    keywords = build_keywords(labels)
    rows = parse_rows(html)

    deduped = {}
    for row in rows:
        d = row["distributor"].lower()
        if not any(k in d for k in keywords):
            continue
        gap = int(row["release_date"][:4]) - row["year"]
        if gap < threshold:                       # too recent → indie lane, not a restoration
            continue
        key = (row["title"].lower(), row["year"])
        if key in deduped:
            deduped[key]["formats"].add(row["format"])
        else:
            row = dict(row)
            row["formats"] = {row.pop("format")}
            deduped[key] = row
    out = list(deduped.values())
    for r in out:
        r["formats"] = sorted(r["formats"])
    return out, len(rows)


def fetch():
    """Public entry: deduped restoration-lane rows."""
    rows, _total = restoration_rows()
    return rows


def _dry_run():
    rows, total = restoration_rows(fetch_html())
    threshold, labels = load_restoration_config()
    print(f"physicalmedia.news/upcoming — {total} total rows; "
          f"{len(rows)} restoration-lane (curated label + {threshold}+ yr gap, deduped)\n")
    for r in sorted(rows, key=lambda x: (x["release_date"], x["title"])):
        gap = int(r["release_date"][:4]) - r["year"]
        print(f"  {r['release_date']}  {r['title']} ({r['year']}, {gap}yr) "
              f"{'/'.join(r['formats'])}  — {r['distributor']}")
    if "--json" in sys.argv:
        print("\n" + json.dumps(rows, indent=2))


if __name__ == "__main__":
    _dry_run()
