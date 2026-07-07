"""Match normalized distributor-calendar rows to TMDB ids.

Confidence:
  HIGH   normalized title matches AND year within +/-1  -> auto-matchable
  LOW    no result, year mismatch, or ambiguous         -> human-review sink
  ERROR  TMDB unreachable for the row                   -> retry next run, never sink

Bias toward HIGH-only auto-match (per docs/DISTRIBUTOR_TRACKING_PLAN.md).
Intake Pass E consumes match_rows() and owns the real accumulated sink
(admin/distributor_unmatched.json). Running this module directly is a DRY RUN:
it writes previews under cache/ and intakes nothing.

Run: python3 -m pipeline.distributors.tmdb_match
"""

import os
import re
import json
import time
import unicodedata
from pathlib import Path

import requests

from pipeline.distributors import physicalmedia

ROOT = Path(__file__).resolve().parents[2]
# Dry-run outputs are previews under cache/ — the REAL accumulated review sink is
# admin/distributor_unmatched.json, owned by intake Pass E (merge-only; a bare
# overwrite here would destroy rows that already slid off the calendar page).
UNMATCHED_PREVIEW_FILE = ROOT / "cache" / "distributor_unmatched_preview.json"
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
    """Search results list, or None on a transport/API failure — a failed fetch
    must never read as 'no results' (it would flood the review sink with junk
    rows during a TMDB outage)."""
    params = {"api_key": key, "query": query, "language": "en-US", "page": 1}
    if year:
        params["primary_release_year"] = year
    try:
        r = requests.get("https://api.themoviedb.org/3/search/movie",
                         params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:
        return None


def match_row(key, row):
    """Return (status, payload). status in {'high','low','error'} — 'error' means
    TMDB was unreachable for this row (retry next run, do NOT sink it)."""
    want_t, want_y = _norm(row["title"]), row["year"]
    results = _search(key, row["title"], want_y)
    if not results:                       # [] or None — one fallback without the year
        results = _search(key, row["title"])
        if results is None:
            return "error", dict(row)

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


def match_rows(key, rows, sleep=0.05):
    """Programmatic entry for intake Pass E: returns (high, low, errors) with no
    printing and no file writes — the caller owns the unmatched sink. 'errors'
    are transport failures to retry next run; they must never enter the sink."""
    high, low, errors = [], [], []
    buckets = {"high": high, "low": low, "error": errors}
    for row in rows:
        status, payload = match_row(key, row)
        buckets[status].append(payload)
        time.sleep(sleep)
    return high, low, errors


def run():
    key = _tmdb_key()
    if not key:
        print("No TMDB key found.")
        return
    rows = physicalmedia.fetch()
    high, low, errors = match_rows(key, rows)

    PREVIEW_FILE.write_text(json.dumps(high, indent=2))
    UNMATCHED_PREVIEW_FILE.write_text(json.dumps(low, indent=2))

    print(f"\n{len(rows)} restoration rows  ->  {len(high)} HIGH-confidence, "
          f"{len(low)} to review, {len(errors)} lookup errors\n")
    print(f"=== HIGH-confidence matches (wrote {PREVIEW_FILE.relative_to(ROOT)}) ===")
    for r in sorted(high, key=lambda x: (x["release_date"], x["title"])):
        flag = "" if _norm(r["title"]) == _norm(r["tmdb_title"]) else "  (~title)"
        print(f"  {r['release_date']}  {r['title']} ({r['year']}) -> "
              f"tmdb:{r['tmdb_id']} {r['tmdb_title']} ({r['tmdb_year']}){flag}  [{r['distributor']}]")

    print(f"\n=== TO REVIEW (wrote {UNMATCHED_PREVIEW_FILE.relative_to(ROOT)}) ===")
    for r in sorted(low, key=lambda x: x["title"]):
        cands = ", ".join(f"{c['title']} ({c['year']})" for c in r["candidates"][:3]) or "—"
        print(f"  {r['title']} ({r['year']}) [{r['distributor']}] — {r['reason']}: {cands}")
    if errors:
        print(f"\n=== LOOKUP ERRORS (TMDB unreachable — retry later) ===")
        for r in errors:
            print(f"  {r['title']} ({r['year']}) [{r['distributor']}]")


if __name__ == "__main__":
    run()
