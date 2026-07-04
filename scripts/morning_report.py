#!/usr/bin/env python3
"""Morning report sections for /morning. Read-only over local files.

Replaces the inline Python that used to live in .claude/commands/morning.md.
Output is identical to the old inline blocks.

Usage:
  morning_report.py --section overnight   # New Releases + Reverted (this run)
  morning_report.py --section backlog     # curation backlog + health scan
"""
import argparse
import json
import os
import signal
import sys
from datetime import date, timedelta

# Reuse /curate's exact slop-candidate + reviewed logic so the two never disagree.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curate_list import _skip_old, _load, REVIEWED

signal.signal(signal.SIGPIPE, signal.SIG_DFL)

WINDOW_DAYS = 7


def _needs_work(m, ct, rev, cy):
    """What curation work a film still needs — shared by backlog + quotes.
    Slop mirrors /curate Stage 3 (same candidate + reviewed sources), capsule/
    quotes mirror Stage 4's presence test, so /morning and /curate never
    disagree. Reissues (confirmed Pass D, _reissue) are normal arrivals; only
    AUTO-detected restorations are skipped."""
    needs = []
    if not _skip_old(m, cy) and "slop" not in rev.get(str(m.get("id")), {}):
        needs.append("slop?")
    skip_resto = m.get("filters", {}).get("is_restoration") and not m.get("_reissue")
    if m.get("title", "").lower() not in ct and not skip_resto:
        needs.append("capsule")
    if "pull_quotes" not in m and not skip_resto:
        needs.append("quotes")
    return needs


def _capsule_titles():
    """Lowercased titles with an approved capsule — Stage 4's presence source."""
    try:
        caps = json.load(open("admin/approved_capsules.json"))
        return set(t.lower() for t in (caps.keys() if isinstance(caps, dict)
                   else [c.get("title", "") for c in caps]))
    except Exception:
        return set()


def overnight():
    data = json.load(open("data.json"))
    ms = data["movies"] if isinstance(data, dict) else data
    disc = json.load(open("metrics/discovery_run.json"))
    run_date = disc.get("timestamp", "")[:10] or str(date.today())
    try:
        enr = json.load(open("metrics/enrichment_run.json"))
    except Exception:
        enr = {}
    deferred = enr.get("deferred_details", [])
    REASONS = {
        "justwatch_no_valid_offers": "Coming soon (JustWatch has no live offers yet)",
        "justwatch_theatrical_pvod": "In theaters / PVOD only",
        "justwatch_no_match": "No JustWatch listing yet",
        "zero_watch_links": "No watch links after enrichment",
    }

    def humanize(r):
        return REASONS.get(r.split("jw_revert:")[-1], r.split("jw_revert:")[-1])

    def plats(d):
        p = d.get("jw_platforms") or d.get("tmdb_platforms") or []
        return ", ".join(p) if p else "—"

    def first_rev(d):
        return d.get("first_reverted_at") or str(d.get("discovered_at", ""))[:10]

    new_rel = [m for m in ms if str(m.get("_discovered_at", ""))[:10] == run_date]
    print(f"New Releases: {len(new_rel)}")
    for m in sorted(new_rel, key=lambda m: not m.get("is_slop")):
        print(f'  • {m.get("title")} ({m.get("year")}) — {"slop" if m.get("is_slop") else "shown"}')

    reverts = [d for d in deferred if str(d.get("reason", "")).startswith("jw_revert:")]
    new_rev = [d for d in reverts if first_rev(d) == run_date]
    hidden = len(reverts) - len(new_rev)
    print(f"\nReverted (new this run): {len(new_rev)}")
    for d in new_rev:
        print(f'  • {d.get("title")} [{d.get("digital_date") or "—"}] — {humanize(d.get("reason",""))} | {plats(d)}')
    if hidden:
        print(f"  ({hidden} chronic/aged revert(s) not listed)")

    other = [d for d in deferred if not str(d.get("reason", "")).startswith("jw_revert:")]
    if other:
        print(f"\n⚠ Other enrichment deferrals (→ Concerns): {len(other)}")
        for d in other:
            print(f'  • {d.get("title")} — {d.get("reason")}')

    # Pre-orders held off the wall this run (store page not yet "available")
    held = disc.get("held_preorder_details", [])
    if held:
        print(f"\nHeld as pre-order (waiting on store availability): {len(held)}")
        for d in held:
            print(f'  • {d.get("title")}')

    # Store-page CAPTCHA blocks — only appears if it actually happened
    captchas = disc.get("captcha_block_titles", [])
    if captchas:
        print(f"\n⚠ Amazon CAPTCHA blocks (→ Concerns): {len(captchas)}")
        for t in captchas:
            print(f'  • {t} — store page blocked; held as pre-order this run (re-checked next run)')

    # Capsule generation failures (CI batch) — only appears when some failed this run
    try:
        cap = json.load(open("metrics/capsule_run.json"))
    except Exception:
        cap = {}
    cap_failed = cap.get("failed", 0)
    if cap_failed and str(cap.get("timestamp", ""))[:10] == run_date:
        print(f"\n⚠ Capsule generation failures (→ Concerns): {cap_failed}")
        for fdet in cap.get("failures", []):
            print(f'  • {fdet.get("title")} ({fdet.get("year")}) — {fdet.get("reason")}')


def backlog():
    def svc_names(val):
        # watch_links entries may be a list of dicts, a single dict (legacy
        # single-object form), or plain strings — normalize to service names.
        items = val if isinstance(val, list) else ([val] if val else [])
        out = []
        for s in items:
            if isinstance(s, dict):
                out.append(s.get("service", "?"))
            elif isinstance(s, str):
                out.append(s)
        return out

    data = json.load(open("data.json"))
    today = str(date.today())
    from_date = str(date.today() - timedelta(days=WINDOW_DAYS))

    # Capsule presence — same source /curate Stage 4 uses.
    ct = _capsule_titles()

    arrivals = [m for m in data["movies"]
                if from_date <= m.get("digital_date", "") <= today]
    arrivals.sort(key=lambda m: m.get("digital_date", ""), reverse=True)

    rev = _load(REVIEWED, {})
    cy = date.today().year

    # --- Curation backlog: state-based, mirrors /curate (NOT the raw arrivals count) ---
    bl = [(m, _needs_work(m, ct, rev, cy)) for m in arrivals]
    bl = [(m, n) for m, n in bl if n]

    print(f"{len(bl)} film(s) still need work:")
    if not bl:
        print("  Nothing outstanding — caught up.")
    for m, n in bl:
        print(f'  • {m.get("title")} ({m.get("year")}) [{m.get("digital_date")}] — {"+".join(n)}')

    # --- Health scan: all recent arrivals, but only print the flagged ones ---
    print()
    flagged = 0
    for m in arrivals:
        streaming = svc_names(m.get("watch_links", {}).get("streaming"))
        vod = svc_names(m.get("watch_links", {}).get("vod"))
        services = streaming + vod
        trailer_hosted = bool(m.get("links", {}).get("trailer_hosted", ""))
        trailer_yt = bool(m.get("links", {}).get("trailer", ""))
        has_links = bool(streaming or vod)
        plex_only = services == ["Plex"]
        t_flag = "trailer:hosted" if trailer_hosted else ("trailer:YT" if trailer_yt else "⚠ NO TRAILER")
        l_flag = ("⚠ PLEX ONLY" if plex_only else "links:ok") if has_links else "⚠ NO LINKS"
        if "⚠" in t_flag or "⚠" in l_flag:
            flagged += 1
            rt = m.get("rt_score") or "--"
            svc = ", ".join(services) if services else "—"
            print(f'  ⚠ {m.get("title")} ({m.get("year")}) — {svc} | RT:{rt} | {t_flag} | {l_flag}')
    clean = len(arrivals) - flagged
    if flagged == 0:
        print(f"Health scan: all {len(arrivals)} arrival(s) in the last {WINDOW_DAYS} days have a trailer and working links.")
    else:
        print(f"Health scan: {flagged} flagged above, {clean} clean (of {len(arrivals)} arrivals in {WINDOW_DAYS} days).")


def quotes():
    """Quote-scrape coverage — replaces reading the 3.5MB combined cache by
    hand in /morning. Cache size, scraped-today count, and any curation
    candidate (needs capsule or quotes) with no cache entry."""
    try:
        pq = json.load(open("cache/pull_quotes_combined.json"))
    except Exception:
        print("⚠ cache/pull_quotes_combined.json missing or unreadable — "
              "overnight quote scrape may not have run (→ Concerns).")
        return
    today = str(date.today())
    fresh = sum(1 for e in pq.values() if str(e.get("scraped_at", ""))[:10] == today)
    print(f"Quote cache: {len(pq)} movie entries ({fresh} scraped today).")

    data = json.load(open("data.json"))
    from_date = str(date.today() - timedelta(days=WINDOW_DAYS))
    ct = _capsule_titles()
    rev = _load(REVIEWED, {})
    cy = date.today().year
    cands = [m for m in data["movies"]
             if from_date <= m.get("digital_date", "") <= today
             and any(n in ("capsule", "quotes") for n in _needs_work(m, ct, rev, cy))]

    # Entry lookup mirrors get_quotes.py: exact "{title}_{year}" key, then
    # case-insensitive title+year.
    loose = {f'{str(e.get("title", "")).lower()}_{e.get("year", "")}' for e in pq.values()}
    missing = [m for m in cands
               if f'{m.get("title")}_{m.get("year")}' not in pq
               and f'{str(m.get("title", "")).lower()}_{m.get("year")}' not in loose]

    if not cands:
        print("No curation candidates in the window need quotes/capsules.")
    elif not missing:
        print(f"All {len(cands)} curation candidate(s) have a quote entry.")
    else:
        print(f"{len(missing)} of {len(cands)} candidate(s) have NO quote entry (→ Concerns):")
        for m in missing:
            print(f'  ⚠ No quotes yet: {m.get("title")} ({m.get("year")})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", required=True, choices=["overnight", "backlog", "quotes"])
    args = ap.parse_args()
    {"overnight": overnight, "backlog": backlog, "quotes": quotes}[args.section]()


if __name__ == "__main__":
    main()
