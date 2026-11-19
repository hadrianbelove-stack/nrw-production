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
from collections import Counter
from datetime import date, timedelta

# Reuse /curate's exact slop-candidate + reviewed logic so the two never disagree.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curate_list import _skip_old, _load, _in_window, REVIEWED

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


HOLD_LABELS = {
    "justwatch_no_valid_offers": "JustWatch has it, no offer yet",
    "justwatch_no_match": "JustWatch can't find it",
    "justwatch_theatrical_pvod": "in theaters, still a pre-order",
    "zero_watch_links": "no watch links yet",
    "owner_revert": "you sent it back (not out yet)",
}
DATE_SOURCES = {
    "jw_first_offer": "the day JustWatch first listed a way to watch it",
    "putback_evidence": "TMDB's digital release date",
    "jw_first_verified": "the day JustWatch first confirmed it",
    "putback_after_hold": "the day after it was last seen not out yet",
    "putback_review": "no date evidence — the day JustWatch confirmed it",
    "jw_offer_start": "the day Amazon's rental went live (after you reverted it)",
}


def held_and_put_back(ms, run_date):
    """Films held because they aren't out yet are checked every run until they land
    (pipeline/putback.py). Held films are COUNTED (chronic holds aren't listed — report
    noise rule); every film PUT BACK today is listed, with how it was dated, whether
    it is on the wall or went straight to the archive, and any date to review."""
    try:
        trk = json.load(open("movie_tracking.json"))
        trk = trk.get("movies", trk)
    except Exception:
        print("\n⚠ Held / put back: movie_tracking.json unreadable — skipped (→ Concerns)")
        return
    held = [r for r in trk.values() if r.get("status") == "tracking" and r.get("_jw_revert_reason")]

    checked = held   # every held film is checked daily, reverted reissues included
    if checked:
        # A film you sent back stays "you sent it back" whatever its latest check said.
        by = Counter(HOLD_LABELS["owner_revert"] if r.get("_reverted_by_owner")
                     else HOLD_LABELS.get(r["_jw_revert_reason"], r["_jw_revert_reason"]) for r in checked)
        parts = ", ".join(f"{n} {label}" for label, n in by.most_common())
        print(f"\nHeld, checked daily until they come out: {len(checked)} ({parts})")
    # Films you sent back that are taking long: JustWatch can't find one, or it has waited a
    # week with its TMDB date passed (or none) and nothing new on JustWatch -- out only on a
    # store whose page can't be read, say. Few (each one is your own revert). Information only:
    # each is still checked daily and comes back by itself.
    stale = []
    for r in held:
        rev = str(r.get("_reverted_by_owner") or "")[:10]
        if not rev:
            continue
        try:
            waited = (date.fromisoformat(run_date[:10]) - date.fromisoformat(rev)).days
        except ValueError:
            continue
        dd = str(r.get("digital_date") or "")[:10]
        if (r.get("_jw_revert_reason") == "justwatch_no_match"
                or (waited >= 7 and (not dd or dd <= run_date[:10]))):
            stale.append((r, waited))
    if stale:
        print(f"Sent back by you, still waiting: {len(stale)} — each is checked daily and comes back by "
              f"itself when JustWatch shows it watchable:")
        for r, waited in sorted(stale, key=lambda x: -x[1]):
            why = ("JustWatch can't find it" if r.get("_jw_revert_reason") == "justwatch_no_match"
                   else f"waiting {waited} days, nothing new on JustWatch")
            print(f'  • {r.get("title")} ({r.get("year")}) — sent back {str(r["_reverted_by_owner"])[:10]}; {why}')
    # On the wall but hidden: JustWatch couldn't check them in enrichment (an error, or the
    # 100-film limit). Re-checked first next run; shown once the check passes.
    waiting = [m for m in ms if m.get("_jw_unconfirmed")]
    stuck = [m for m in waiting if (m.get("_enrichment_attempts") or 0) >= 5]
    if len(waiting) > len(stuck):
        print(f"Waiting hidden for a JustWatch check (error or enrichment limit): {len(waiting) - len(stuck)} — "
              f"re-checked first next run")
    if stuck:
        print(f"⚠ Hidden and stuck (→ Concerns): {len(stuck)} — enrichment failed 5 times since "
              f"they arrived, so they are no longer retried (/enrich <id> retries one):")
        for m in stuck:
            print(f'  • {m.get("title")} ({m.get("year")}) — hidden since {m.get("_jw_unconfirmed")}; '
                  f'last enrichment: {m.get("_enrichment_status") or "unknown"}')
    # Only put-backs that stuck: a film sent back again later in the same run is still
    # held (counted above), not "put back".
    back = [(mid, r) for mid, r in trk.items()
            if str(r.get("_put_back_on", ""))[:10] == run_date and r.get("status") == "available"]
    if not back:
        return
    on_wall = {str(m.get("id")) for m in ms if not m.get("hidden")}
    hidden_on_wall = {str(m.get("id")) for m in ms if m.get("hidden")}
    try:
        arc = json.load(open("data_archive.json"))
        arc = arc.get("movies", arc) if isinstance(arc, dict) else arc
        in_archive = {str(m.get("id")) for m in (arc.values() if isinstance(arc, dict) else arc)
                      if isinstance(m, dict) and m.get("_enrichment_status") != "reverted"}
    except Exception:
        in_archive = set()
    review = sum(1 for _, r in back if r.get("_date_needs_review"))
    print(f"\nPut back today (came out after a hold): {len(back)}"
          f"{f' — {review} need a date check (→ Concerns)' if review else ''}")
    for mid, r in sorted(back, key=lambda x: (not x[1].get("_date_needs_review"), x[1].get("digital_date") or "")):
        where = ("wall" if mid in on_wall else "archive (out more than 90 days)" if mid in in_archive
                 else "hidden — waiting for a JustWatch check" if mid in hidden_on_wall
                 and any(str(m.get("id")) == mid and m.get("_jw_unconfirmed") for m in ms)
                 else "NOT on the wall or archive — check (→ Concerns)")
        if r.get("_date_needs_review"):
            how = (f"DATE NEEDS REVIEW — dated {r.get('digital_date') or 'no date'} "
                   f"({DATE_SOURCES.get(r.get('_digital_date_source'), r.get('_digital_date_source'))}): "
                   f"weak evidence — the hold went unchecked, or TMDB couldn't be reached")
        else:
            how = f"dated {r.get('digital_date')} ({DATE_SOURCES.get(r.get('_digital_date_source'), r.get('_digital_date_source'))})"
        print(f'  • {r.get("title")} ({r.get("year")}) — {how} | held since {r.get("_held_since") or "?"} | {where}')


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
        "justwatch_theatrical_pvod": "In theaters, still a pre-order",
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
        _shown = ("hidden — waiting for a JustWatch check" if m.get("_jw_unconfirmed")
                  else "pre-order" if m.get("_is_preorder") else "shown")
        print(f'  • {m.get("title")} ({m.get("year")}) — {"slop" if m.get("is_slop") else _shown}')

    reverts = [d for d in deferred if str(d.get("reason", "")).startswith("jw_revert:")]
    new_rev = [d for d in reverts if first_rev(d) == run_date]
    hidden = len(reverts) - len(new_rev)
    print(f"\nReverted (new this run): {len(new_rev)}")
    for d in new_rev:
        print(f'  • {d.get("title")} [{d.get("digital_date") or "—"}] — {humanize(d.get("reason",""))} | {plats(d)}')
    if hidden:
        print(f"  ({hidden} chronic/aged revert(s) not listed)")

    held_and_put_back(ms, run_date)

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

    # JustWatch errors / outage during discovery — only appears if it actually happened.
    # Those films just wait (no strike) and are checked again next run.
    _res = disc.get("results", {})
    if _res.get("jw_errors") or _res.get("jw_healthy") is False:
        print(f"\n⚠ JustWatch trouble during discovery (→ Concerns): {_res.get('jw_errors') or 0} lookup "
              f"error(s){'; outage detected' if _res.get('jw_healthy') is False else ''} — those films "
              f"wait for the next run (no strike)")

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

    # Same window as /curate: dated this week, or landed this week with an older date
    # (a film put back after a hold keeps its real date).
    arrivals = [m for m in data["movies"] if _in_window(m, from_date, today)]
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
             if _in_window(m, from_date, today)
             and any(n in ("capsule", "quotes") for n in _needs_work(m, ct, rev, cy))]

    # Entry lookup mirrors get_quotes.py: exact "{title}_{year}" key, then
    # case-insensitive title+year. An entry whose quote lists are all empty
    # counts as missing too — the scraper ran but found nothing, and
    # get_quotes.py treats that the same as no entry.
    def _has_quotes(e):
        return any((q.get("text") or "").strip()
                   for q in (e.get("rt_quotes") or []) + (e.get("lb_quotes") or []))

    loose = {f'{str(e.get("title", "")).lower()}_{e.get("year", "")}': e
             for e in pq.values()}
    missing = []
    for m in cands:
        e = pq.get(f'{m.get("title")}_{m.get("year")}') or \
            loose.get(f'{str(m.get("title", "")).lower()}_{m.get("year")}')
        if e is None or not _has_quotes(e):
            missing.append(m)

    if not cands:
        print("No curation candidates in the window need quotes/capsules.")
    elif not missing:
        print(f"All {len(cands)} curation candidate(s) have quotes.")
    else:
        print(f"{len(missing)} of {len(cands)} candidate(s) have NO quotes (→ Concerns):")
        for m in missing:
            print(f'  ⚠ No quotes yet: {m.get("title")} ({m.get("year")})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", required=True,
                    choices=["overnight", "backlog", "quotes", "all"])
    args = ap.parse_args()
    if args.section == "all":
        for fn in (overnight, backlog, quotes):
            print(f"\n=== {fn.__name__.upper()} ===")
            fn()
    else:
        {"overnight": overnight, "backlog": backlog, "quotes": quotes}[args.section]()


if __name__ == "__main__":
    main()
