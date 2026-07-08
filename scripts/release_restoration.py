#!/usr/bin/env python3
"""Human ruling on version-gate-held restorations (Stage 4 release).

Discovery HOLDS a woken reissue in tracking instead of walling it — the open
question being whether the digital offer is the RESTORATION or an old transfer
of the same title. pipeline/version_check.py writes a grounded verdict; this
script is the ruling:

  --list           numbered table of held films, most-releasable first
  --release 1,3    it IS the restoration -> sets _version_verified; the NEXT
                   daily discovery run transitions it to the wall on the normal
                   rails (JustWatch re-verified, dated correctly)
  --repark 2       it is the OLD transfer -> captures a FRESH change-detection
                   baseline (including the provider that caused the false wake)
                   and puts the film back to sleep; it wakes again only on the
                   next NEW signal

Rows accept row numbers from --list or raw tmdb ids.

Usage:
    python3 scripts/release_restoration.py --list
    python3 scripts/release_restoration.py --release 1
    python3 scripts/release_restoration.py --repark 242582
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.tracking_db import get_tracking_db  # noqa: E402

import requests  # noqa: E402


def _tmdb_key():
    key = os.environ.get('TMDB_API_KEY')
    if not key and os.path.exists('.env'):
        for line in open('.env').read().splitlines():
            if line.startswith('TMDB_API_KEY'):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
    return key


def _fetch_us_type4_date(key, mid):
    """First US Type-4 date (mirrors generator.fetch_tmdb_type4_date). Raises on failure."""
    r = requests.get(f"https://api.themoviedb.org/3/movie/{mid}/release_dates",
                     params={'api_key': key}, timeout=15)
    r.raise_for_status()
    for entry in r.json().get('results', []):
        if entry.get('iso_3166_1') == 'US':
            for rel in entry.get('release_dates', []):
                if rel.get('type') == 4 and rel.get('release_date'):
                    return rel['release_date'][:10]
    return None


def _fetch_us_providers(key, mid):
    """Current US rent+buy+flatrate provider names. Raises on failure."""
    r = requests.get(f"https://api.themoviedb.org/3/movie/{mid}/watch/providers",
                     params={'api_key': key}, timeout=15)
    r.raise_for_status()
    us = r.json().get('results', {}).get('US', {})
    return [p['provider_name'] for kind in ('rent', 'buy', 'flatrate')
            for p in us.get(kind, [])]


def _verdict_rank(m):
    res = m.get('_version_check_result')
    if not isinstance(res, dict):
        return 3  # no verdict yet
    if res.get('on_vod'):
        return 0
    if (res.get('is_restoration_version') == 'no'
            or res.get('available') in ('no', 'theatrical_only', 'disc_only')):
        return 2
    return 1  # unclear


_RANK_LABEL = {0: 'RESTORATION ON VOD', 1: 'unclear', 2: 'old transfer / not digital',
               3: '(no verdict yet)'}


def held_rows(db):
    """Deterministic ruling order: releasable first, then unclear, then reparkable."""
    rows = [(mid, m) for mid, m in db['movies'].items()
            if m.get('_version_check_pending')]
    rows.sort(key=lambda im: (_verdict_rank(im[1]),
                              (im[1].get('_version_check_result') or {}).get('confidence', 'z'),
                              im[1].get('title', '')))
    return rows


def show_list(db):
    rows = held_rows(db)
    if not rows:
        print("No films held at the version gate.")
        return
    print(f"{len(rows)} film(s) held at the version gate "
          f"(release = it's the restoration; repark = old transfer):\n")
    for i, (mid, m) in enumerate(rows, 1):
        res = m.get('_version_check_result') or {}
        rank = _verdict_rank(m)
        plats = ', '.join((res.get('platforms') or m.get('_pending_platforms') or [])[:5]) or '—'
        src = (res.get('sources') or [''])[0]
        print(f"{i:3}. {m.get('title')} ({m.get('year')})  [{mid}]")
        print(f"     verdict: {_RANK_LABEL[rank]}"
              + (f"  [{res.get('confidence')}]" if res else '')
              + f"   held since {m.get('_version_check_since', '?')}"
              + f"   via {m.get('_pending_transition_source', '?')}")
        if res.get('basis'):
            print(f"     basis: {res['basis'][:160]}")
        print(f"     platforms: {plats}" + (f"   source: {src}" if src else ''))
        print(f"     -> python3 scripts/release_restoration.py "
              f"--{'release' if rank == 0 else 'repark' if rank == 2 else 'release/--repark'} {i}\n")


def _resolve(tokens, rows):
    """Row numbers or raw tmdb ids -> [(mid, movie)]."""
    picked = []
    for tok in tokens.split(','):
        tok = tok.strip()
        if not tok:
            continue
        if tok.isdigit() and 1 <= int(tok) <= len(rows):
            picked.append(rows[int(tok) - 1])
        else:
            hit = [(mid, m) for mid, m in rows if str(mid) == tok]
            if not hit:
                print(f"  ⚠ '{tok}' is neither a listed row nor a held tmdb id — skipped.")
                continue
            picked.append(hit[0])
    return picked


def do_release(db, tokens):
    rows = held_rows(db)
    released = 0
    for mid, m in _resolve(tokens, rows):
        m['_version_verified'] = True
        m['_restoration_stage'] = 'version_verified'
        m.pop('_version_check_pending', None)
        # keep _version_check_result + _version_check_since as the audit trail
        released += 1
        print(f"  ✅ {m.get('title')} ({mid}) released — the NEXT daily discovery run "
              f"puts it on the wall (JustWatch re-verified, dated correctly).")
    return released


def do_repark(db, tokens):
    key = _tmdb_key()
    if not key:
        print("ERROR: no TMDB key (env TMDB_API_KEY or .env) — cannot capture a fresh "
              "baseline; repark aborted.", file=sys.stderr)
        return 0
    rows = held_rows(db)
    today = datetime.now().strftime('%Y-%m-%d')
    reparked = 0
    for mid, m in _resolve(tokens, rows):
        # Fresh baseline MUST include the provider that caused the false wake,
        # or the film re-wakes tomorrow. A failed snapshot aborts this film.
        try:
            baseline_t4 = _fetch_us_type4_date(key, mid)
            baseline_provs = _fetch_us_providers(key, mid)
        except Exception as e:
            print(f"  ⚠ {m.get('title')} ({mid}): baseline snapshot failed ({e}) — "
                  f"left held; retry later.")
            continue
        m['_reissue_deferred'] = True
        m['_reissue_deferred_at'] = today
        m['_reissue_baseline_type4'] = baseline_t4
        m['_reissue_baseline_providers'] = baseline_provs
        m['_restoration_stage'] = 'announced'
        m['digital_date'] = None
        # Human ruled today's digital record = old transfer, so it also raises the
        # stale-Type-4 floor for the next wake.
        if baseline_t4 and baseline_t4 > (m.get('_reissue_woken_from_t4') or ''):
            m['_reissue_woken_from_t4'] = baseline_t4
        for k in ('_version_check_pending', '_version_check_since',
                  '_pending_transition_source', '_pending_platforms',
                  '_type4_pending', '_is_preorder'):
            m.pop(k, None)
        # keep _version_check_result as the audit trail of why it was reparked
        reparked += 1
        print(f"  😴 {m.get('title')} ({mid}) reparked — fresh baseline "
              f"({len(baseline_provs)} providers, type4 {baseline_t4 or '—'}); "
              f"wakes on the next NEW signal.")
    return reparked


def main():
    ap = argparse.ArgumentParser(description="Rule on version-gate-held restorations")
    ap.add_argument('--list', action='store_true', help='Show held films')
    ap.add_argument('--release', help='Rows/ids: verified as the restoration')
    ap.add_argument('--repark', help='Rows/ids: old transfer — back to sleep')
    args = ap.parse_args()

    tdb = get_tracking_db()
    db = tdb.load_all()

    if args.list or not (args.release or args.repark):
        show_list(db)
        return

    changed = 0
    if args.release:
        changed += do_release(db, args.release)
    if args.repark:
        changed += do_repark(db, args.repark)
    if changed:
        db['last_update'] = datetime.now().isoformat()
        tdb.save_all(db, export_json=True)
        print(f"\nSaved: {changed} ruling(s) applied.")


if __name__ == '__main__':
    main()
