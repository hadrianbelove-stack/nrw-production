#!/usr/bin/env python3
"""News-gap recheck over PARKED restorations (Stage 2 signal, monthly per title).

The empirical pattern (docs/DISTRIBUTOR_TRACKING_PLAN.md, tested 2026-06-30):
a restoration that converts to VOD throws TWO press bursts — the announcement
cluster (Cannes / "4K restoration premieres"), a months-long gap, then a
home-release cluster ("now on 4K UHD / digital / streaming"). This pass
re-scans each parked title's Google News feed for that SECOND cluster: a
DIG-classified headline dated after the film's announcement.

A DIG hit is INFORMATIONAL ONLY — it stamps _news_dig_hit + advances
_restoration_stage to 'vod_announced', surfaces in the morning report, and
(budget-capped) runs one grounded version pre-check for context. It never
wakes or transitions the film: "digital" press is leaky (fires on
announcements, and on the OLD transfer's availability) — the TMDB wake gate
stays the sole operative trigger, and the Stage-4 version gate still guards
the wall.

Cadence: --cadence-days 30 matches the measured ~4-month median premiere->VOD
lag. Obscure titles generate ~1 article/month (low recall there by design —
the periodic research sweep owns the silent half).

Run daily by daily_orchestrator (non-critical), or manually:
    python3 pipeline/news_recheck.py --limit 15
    python3 pipeline/news_recheck.py --id 31767
"""

import os
import re
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vocab buckets from the validated /tmp sandbox tagger (plan doc "news-gap"):
# ANN announcement chatter · THE theatrical/screening · DISC physical media ·
# DIG home digital. A headline can hit several; DIG is the second-cluster signal.
_BUCKETS = {
    'ANN': re.compile(r'\b(restoration|restored|remaster|4k|2k|cannes|classics?|'
                      r'premieres?|unveil|announce)\w*', re.I),
    'THE': re.compile(r'\b(theatrical|theaters?|theatres?|cinemas?|screening|showtimes)\b', re.I),
    'DISC': re.compile(r'\b(blu-?ray|uhd|steelbook|criterion collection|box ?set|'
                       r'4k ultra|disc)\b', re.I),
    'DIG': re.compile(r'\b(digital|vod|stream(?:ing|s)?|rent(?:al)?|itunes|'
                      r'apple tv|amazon|prime video|criterion channel|max|hulu|'
                      r'netflix|on demand)\b', re.I),
}


def classify(headline):
    """Sorted list of bucket tags the headline hits."""
    return sorted(tag for tag, rx in _BUCKETS.items() if rx.search(headline))


def _n(t):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', t.lower())).strip()


def title_matches(headline, title):
    """Guard against same-name/near-name titles (live catch: a 'The Devils' scan
    hit a 'The Devil's Mouth' TV story). If the headline quotes phrases, one must
    BE our title — normalized EQUALITY, not substring; unquoted headlines fall
    back to whole-phrase containment."""
    quoted = [q for q in re.findall(r"[\"'‘’“”]([^\"'‘’“”]{2,70})[\"'‘’“”]", headline)
              if q.strip()]
    if quoted:
        return any(_n(q) == _n(title) for q in quoted)
    return _n(title) in _n(headline)


def _baseline_date(movie):
    """Headlines must be NEWER than this to count as the second cluster."""
    return (movie.get('_announcement_date')
            or movie.get('_reissue_deferred_at')
            or movie.get('intake_date') or '')


def recheck_movie(movie, fetch_feed):
    """Scan one parked film's news timeline. Returns the DIG hit dict or None."""
    title = movie.get('title', '')
    if not title:
        return None
    query = f'"{title}" 4K OR restoration OR Blu-ray OR streaming OR digital'
    items = fetch_feed(query)
    floor = _baseline_date(movie)
    for it in sorted(items, key=lambda x: x.get('date', ''), reverse=True):
        date = it.get('date', '')
        if not re.match(r'\d{4}-\d{2}-\d{2}', date) or (floor and date <= floor):
            continue
        headline = it.get('headline', '')
        # A second-cluster hit needs all three: home-digital vocab (DIG),
        # restoration context (ANN — else it's chatter about ANY same-name
        # title reaching streaming), and the title itself.
        tags = classify(headline)
        if 'DIG' in tags and 'ANN' in tags and title_matches(headline, title):
            return {'date': date, 'headline': headline,
                    'link': it.get('link', ''), 'tags': tags}
    return None


def run(limit=None, cadence_days=30, only_id=None, precheck_limit=3):
    from pipeline.tracking_db import get_tracking_db
    from pipeline.distributors.googlenews import fetch_feed

    tdb = get_tracking_db()
    db = tdb.load_all()
    today = datetime.now().strftime('%Y-%m-%d')

    parked = [(mid, m) for mid, m in db['movies'].items()
              if m.get('_reissue_deferred') and m.get('status') == 'tracking']
    if only_id:
        parked = [(mid, m) for mid, m in parked if str(mid) == str(only_id)]
        if not parked:
            print(f"News recheck: no parked film with id {only_id}.")
            return 0
    else:
        def _due(m):
            last = m.get('_news_last_checked', '')
            if not last:
                return True
            try:
                age = (datetime.strptime(today, '%Y-%m-%d')
                       - datetime.strptime(last, '%Y-%m-%d')).days
            except ValueError:
                return True
            return age >= cadence_days
        parked = [(mid, m) for mid, m in parked if _due(m)]
        parked.sort(key=lambda im: im[1].get('_news_last_checked', ''))
        if limit:
            parked = parked[:limit]

    if not parked:
        print("News recheck: nothing due (all parked titles checked within cadence).")
        return 0

    print(f"News recheck: {len(parked)} parked title(s) to scan...")
    dig_hits = 0
    prechecks = 0
    for i, (mid, m) in enumerate(parked, 1):
        try:
            hit = recheck_movie(m, fetch_feed)
        except Exception as e:
            print(f"  [{i}/{len(parked)}] {m.get('title')} — feed error: {e} (retries next cadence)")
            continue
        m['_news_last_checked'] = today
        if not hit:
            print(f"  [{i}/{len(parked)}] {m.get('title')} — no second cluster")
            continue
        dig_hits += 1
        first_hit = not m.get('_news_dig_hit')
        m['_news_dig_hit'] = hit
        # Stage advance is forward-only; a film already at the version gate keeps
        # its pending_version_check stage.
        if not m.get('_version_check_pending'):
            m['_restoration_stage'] = 'vod_announced'
        print(f"  [{i}/{len(parked)}] {m.get('title')} — DIG hit {hit['date']}: "
              f"{hit['headline'][:80]}")
        # Context pre-check (budget-capped): "news says digital — grounded check
        # says X" for the morning report. Never operative.
        if first_hit and prechecks < precheck_limit:
            prechecks += 1
            try:
                from gemini_scraper.restoration_vod import GeminiRestorationVODFinder
                verdict = GeminiRestorationVODFinder().find_restoration_vod_status(
                    m.get('title', ''), m.get('year') or 0,
                    restoration_note=(m.get('reissue_label', '') + '; news: '
                                      + hit['headline'][:120]))
                if verdict:
                    m['_version_check_result'] = dict(
                        verdict, checked_at=datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
                    print(f"        grounded pre-check: on_vod={verdict['on_vod']} "
                          f"[{verdict['confidence']}]")
            except Exception as e:
                print(f"        pre-check failed (non-fatal): {e}")

    db['last_update'] = datetime.now().isoformat()
    tdb.save_all(db, export_json=True)
    print(f"News recheck complete: {len(parked)} scanned, {dig_hits} DIG hit(s), "
          f"{prechecks} pre-check(s).")
    return dig_hits


def main():
    ap = argparse.ArgumentParser(description="News-gap second-cluster scan over parked restorations")
    ap.add_argument('--limit', type=int, default=None, help='Max titles this run')
    ap.add_argument('--cadence-days', type=int, default=30, help='Per-title recheck cadence')
    ap.add_argument('--id', dest='only_id', default=None, help='Scan one parked film (ignores cadence)')
    ap.add_argument('--precheck-limit', type=int, default=3,
                    help='Max grounded pre-checks per run on fresh DIG hits')
    args = ap.parse_args()
    run(limit=args.limit, cadence_days=args.cadence_days,
        only_id=args.only_id, precheck_limit=args.precheck_limit)


if __name__ == '__main__':
    main()
