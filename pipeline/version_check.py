#!/usr/bin/env python3
"""Version-check pass over HELD restorations (Stage 4 of the restoration lifecycle).

The discovery version gate (pipeline/discoverer.py _hold_reissue_for_version_check)
holds a woken reissue in tracking with _version_check_pending=True instead of
walling it: TMDB/JustWatch confirm the TITLE has offers, not that the offer is
the RESTORATION — 44% of parked restorations have an old transfer already
streaming. This pass runs the grounded version-aware verifier
(gemini_scraper/restoration_vod.py, validated on Gold Rush / Fight Club / Yi Yi)
over held films and writes the verdict onto the tracking entry
(_version_check_result). It NEVER releases a film — the human ruling is
scripts/release_restoration.py --release/--repark, surfaced by
morning_report.py --section restorations.

Run daily by daily_orchestrator (non-critical), or manually:
    python3 pipeline/version_check.py --limit 15
    python3 pipeline/version_check.py --id 242582
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Matches the finder's cache TTL: availability changes over time, so a held film
# with a stale verdict gets re-asked — the finder cache dedupes the API cost.
RECHECK_DAYS = 14


def _needs_check(movie, today):
    res = movie.get('_version_check_result')
    if not isinstance(res, dict) or not res.get('checked_at'):
        return True
    try:
        age = (datetime.strptime(today, '%Y-%m-%d')
               - datetime.strptime(res['checked_at'][:10], '%Y-%m-%d')).days
    except ValueError:
        return True
    return age >= RECHECK_DAYS


def _restoration_note(movie):
    """Everything we know about the restoration, to anchor the version query."""
    bits = []
    if movie.get('reissue_label'):
        bits.append(movie['reissue_label'])
    if movie.get('_expected_distributor'):
        bits.append(f"distributor {movie['_expected_distributor']}")
    if movie.get('_expected_digital_date'):
        bits.append(f"disc street date {movie['_expected_digital_date']}")
    if movie.get('_announcement_headline'):
        bits.append(f"announced: {movie['_announcement_headline']} "
                    f"({movie.get('_announcement_date', '')})")
    if movie.get('_pending_platforms'):
        bits.append(f"US offers currently listed on {', '.join(movie['_pending_platforms'][:6])}")
    if movie.get('_version_check_since'):
        bits.append(f"offers first seen {movie['_version_check_since']}")
    return '; '.join(bits)


def run(limit=None, only_id=None, force=False):
    from pipeline.tracking_db import get_tracking_db
    from gemini_scraper.restoration_vod import GeminiRestorationVODFinder

    tdb = get_tracking_db()
    db = tdb.load_all()
    today = datetime.now().strftime('%Y-%m-%d')

    held = [(mid, m) for mid, m in db['movies'].items()
            if m.get('_version_check_pending')]
    if only_id:
        held = [(mid, m) for mid, m in held if str(mid) == str(only_id)]
        if not held:
            print(f"Version check: no held film with id {only_id}.")
            return 0
    else:
        held = [(mid, m) for mid, m in held if force or _needs_check(m, today)]
        # Never-checked first, then oldest verdict first
        held.sort(key=lambda im: (im[1].get('_version_check_result') or {}).get('checked_at', ''))
        if limit:
            held = held[:limit]

    if not held:
        print("Version check: nothing to do (no held films need a fresh verdict).")
        return 0

    finder = GeminiRestorationVODFinder()
    print(f"Version check: {len(held)} held film(s) to research...")
    done = 0
    for i, (mid, m) in enumerate(held, 1):
        verdict = finder.find_restoration_vod_status(
            m.get('title', ''), m.get('year') or 0,
            restoration_note=_restoration_note(m))
        if verdict is None:
            print(f"  [{i}/{len(held)}] {m.get('title')} — API failed, retries next run")
            continue
        m['_version_check_result'] = dict(
            verdict, checked_at=datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
        if verdict['on_vod']:
            call = 'RESTORATION ON VOD'
        elif (verdict['is_restoration_version'] == 'no'
              or verdict['available'] in ('no', 'theatrical_only', 'disc_only')):
            call = 'old transfer / not digital'
        else:
            call = 'unclear'
        print(f"  [{i}/{len(held)}] {m.get('title')} ({m.get('year')}) -> {call} "
              f"[{verdict['confidence']}]  {(verdict.get('basis') or '')[:100]}")
        done += 1

    if done:
        db['last_update'] = datetime.now().isoformat()
        tdb.save_all(db, export_json=True)
    print(f"Version check complete: {done} verdict(s) written. "
          f"Rule on them: python3 scripts/release_restoration.py --list")
    return done


def main():
    ap = argparse.ArgumentParser(description="Grounded version-check over held restorations")
    ap.add_argument('--limit', type=int, default=None, help='Max films to research this run')
    ap.add_argument('--id', dest='only_id', default=None, help='Check one held film by tmdb id')
    ap.add_argument('--force', action='store_true', help='Ignore the recheck TTL')
    args = ap.parse_args()
    run(limit=args.limit, only_id=args.only_id, force=args.force)


if __name__ == '__main__':
    main()
