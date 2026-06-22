"""Match normalized distributor-calendar rows to TMDB ids — DRY RUN, no writes to
tracking or data.json.

Confidence:
  HIGH   normalized title matches AND year within +/-1  -> auto-matchable
  LOW    no result, year mismatch, or ambiguous         -> admin/distributor_unmatched.json

Bias toward HIGH-only auto-match; everything else goes to the human-review sink
(per docs/DISTRIBUTOR_TRACKING_PLAN.md). Clean matches are written to a preview
file for eyeballing; NOTHING is intaked here.

Run: python3 -m pipeline.distributors.tmdb_match
"""

import os
import re
import sys
import json
import time
import unicodedata
from pathlib import Path

import requests

from pipeline.distributors import physicalmedia

ROOT = Path(__file__).resolve().parents[2]
UNMATCHED_FILE = ROOT / "admin" / "distributor_unmatched.json"
PREVIEW_FILE = ROOT / "cache" / "distributor_match_preview.json"

_ARTICLES = ("the ", "a ", "an ")


def _tmdb_key():
    key = os.environ.get("TMDB_API_KEY")
    if not key:
        try:
            import yaml
            key = (yaml.safe_load((ROOT / "config.yaml").read_text())
                   .get("api", {}).get("tmdb_api_key"))
        except Exception:
            key = None
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("TMDB_API_KEY"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key


def _norm(title):
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    t = t.lower().strip()
    for art in _ARTICLES:
        if t.startswith(art):
            t = t[len(art):]
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _search(key, query, year=None):
    params = {"api_key": key, "query": query, "language": "en-US", "page": 1}
    if year:
        params["primary_release_year"] = year
    try:
        r = requests.get("https://api.themoviedb.org/3/search/movie",
                         params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:
        return []


def match_row(key, row):
    """Return (status, payload). status in {'high','low'}."""
    want_t, want_y = _norm(row["title"]), row["year"]
    results = _search(key, row["title"], want_y)
    if not results:                       # one fallback without the year
        results = _search(key, row["title"])

    def cand(m):
        ry = (m.get("release_date") or "")[:4]
        return {"tmdb_id": m.get("id"), "title": m.get("title"),
                "year": int(ry) if ry.isdigit() else None}

    for m in results[:8]:
        c = cand(m)
        if _norm(m.get("title", "")) == want_t and c["year"] and abs(c["year"] - want_y) <= 1:
            return "high", {**row, "tmdb_id": c["tmdb_id"],
                            "tmdb_title": c["title"], "tmdb_year": c["year"]}

    reason = "no_results" if not results else "no_confident_match"
    return "low", {"source_title": row["source_title"], "title": row["title"],
                   "year": want_y, "distributor": row["distributor"],
                   "release_date": row["release_date"], "source_url": row["source_url"],
                   "candidates": [cand(m) for m in results[:5]], "reason": reason}


def run():
    key = _tmdb_key()
    if not key:
        print("No TMDB key found.")
        return
    rows = physicalmedia.fetch()
    high, low = [], []
    for i, row in enumerate(rows, 1):
        status, payload = match_row(key, row)
        (high if status == "high" else low).append(payload)
        time.sleep(0.05)
        if i % 25 == 0:
            print(f"  ...{i}/{len(rows)}", file=sys.stderr)

    PREVIEW_FILE.write_text(json.dumps(high, indent=2))
    UNMATCHED_FILE.write_text(json.dumps(low, indent=2))

    print(f"\n{len(rows)} restoration rows  ->  {len(high)} HIGH-confidence, {len(low)} to review\n")
    print(f"=== HIGH-confidence matches (wrote {PREVIEW_FILE.relative_to(ROOT)}) ===")
    for r in sorted(high, key=lambda x: (x["release_date"], x["title"])):
        flag = "" if _norm(r["title"]) == _norm(r["tmdb_title"]) else "  (~title)"
        print(f"  {r['release_date']}  {r['title']} ({r['year']}) -> "
              f"tmdb:{r['tmdb_id']} {r['tmdb_title']} ({r['tmdb_year']}){flag}  [{r['distributor']}]")

    print(f"\n=== TO REVIEW (wrote {UNMATCHED_FILE.relative_to(ROOT)}) ===")
    for r in sorted(low, key=lambda x: x["title"]):
        cands = ", ".join(f"{c['title']} ({c['year']})" for c in r["candidates"][:3]) or "—"
        print(f"  {r['title']} ({r['year']}) [{r['distributor']}] — {r['reason']}: {cands}")


if __name__ == "__main__":
    run()
