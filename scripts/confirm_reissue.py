#!/usr/bin/env python3
"""
Confirm / reject reissue candidates from the "Confirm Reissues" curation stage.

Three actions on a pending candidate:
  --confirm  Add to the WALL now (status=available, _added_manually) + enrich + not-slop.
             For a reissue whose home release has already landed.
  --defer    Intake into the tracking DB (status='tracking') with the reissue flag + label,
             so NORMAL discovery surfaces it the day it hits VOD or a streamer — same rails
             as every other tracked film. For a GENUINE reissue that is still theatrical-only
             (no VOD yet). The durable badge + not-slop layers are written up front, so it
             reads as a Restoration the moment it transitions. No memory note, no scheduled
             check — the digital release itself is the trigger.
  --reject   Not a real reissue (a plain re-run / re-screening). Marked so it never re-appears.

Rejected candidates are permanently skipped by intake Pass D; deferred ones are skipped too
(they're now in tracking), so neither re-queues.

Row numbers refer to the table printed by scripts/reissue_table.py (same sort order).

Usage:
    # confirm rows 1 and 3, reject the rest of the shown pending list (drain):
    python3 scripts/confirm_reissue.py --confirm 1,3 --drain
    # confirm with a custom label on row 2:
    python3 scripts/confirm_reissue.py --confirm 2 --label "2=New 4K Restoration"
    # defer a theatrical-only reissue to tracking until its VOD/streaming release:
    python3 scripts/confirm_reissue.py --defer 1 --label "1=Restoration"
    # reject specific rows only:
    python3 scripts/confirm_reissue.py --reject 4,5
"""

import os
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.reissue_table import sorted_pending, _suggested_label  # noqa: E402

CANDIDATES_FILE = 'admin/reissue_candidates.json'


def _parse_nums(s):
    if not s:
        return []
    out = []
    for part in str(s).replace(' ', '').split(','):
        if part.isdigit():
            out.append(int(part))
    return out


def _parse_labels(pairs):
    """['2=New 4K Restoration'] -> {2: 'New 4K Restoration'}"""
    out = {}
    for p in pairs or []:
        if '=' in p:
            n, label = p.split('=', 1)
            if n.strip().isdigit():
                out[int(n.strip())] = label.strip()
    return out


def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _intake_deferred(deferred):
    """Intake deferred reissues into the tracking DB (status='tracking') with the reissue
    flag + label, so the normal daily discovery (TMDB Type-4 digital date OR watch/providers)
    surfaces them the day they hit VOD/streaming — exactly like every other tracked film.

    No _added_manually: we WANT discovery to validate availability before it transitions.
    The durable badge (admin/reissue_labels.json) and not-slop (admin/overrides.json) layers
    are written up front, so the film reads as a Restoration the moment it lands on the wall.
    """
    import requests
    from pipeline.generator import DataGenerator
    from pipeline.tracking_db import get_tracking_db

    gen = DataGenerator(enrichment_enabled=False)
    tdb = get_tracking_db()
    db = tdb.load_all()
    db.setdefault('movies', {})

    labels = _load_json('admin/reissue_labels.json', {})
    overrides = _load_json('admin/overrides.json', {})
    today = datetime.date.today().strftime('%Y-%m-%d')

    intaked = 0
    for cand, label in deferred:
        mid = str(cand['tmdb_id'])
        is_tv = mid.startswith('tv_')

        # Don't clobber a film that's already live or tracked under a different flow.
        existing = db['movies'].get(mid)
        if existing and existing.get('status') == 'available':
            print(f"  ⚠ {cand['title']} ({mid}) already on the wall — skipping defer.")
            continue

        # Fetch TMDB metadata so the tracking entry is complete (mirrors add_movie.py).
        tmdb_data = (gen.get_tv_details(mid.replace('tv_', '')) if is_tv
                     else gen.get_movie_details(mid)) or {}
        title = tmdb_data.get('title') or tmdb_data.get('name') or cand.get('title') or f'Unknown ({mid})'
        rel = tmdb_data.get('release_date') or tmdb_data.get('first_air_date') or ''
        year = int(rel[:4]) if rel[:4].isdigit() else cand.get('year')
        poster = (f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}"
                  if tmdb_data.get('poster_path') else None)
        genres = [g['name'] for g in tmdb_data.get('genres', [])]

        # Current providers (binary signal for discovery; refreshed daily thereafter).
        rent_p = buy_p = stream_p = []
        try:
            base = ('tv/' + mid.replace('tv_', '')) if is_tv else ('movie/' + mid)
            pr = requests.get(f"https://api.themoviedb.org/3/{base}/watch/providers",
                              params={'api_key': gen.tmdb_key}, timeout=15)
            us = pr.json().get('results', {}).get('US', {}) if pr.ok else {}
            rent_p = [p['provider_name'] for p in us.get('rent', [])]
            buy_p = [p['provider_name'] for p in us.get('buy', [])]
            stream_p = [p['provider_name'] for p in us.get('flatrate', [])]
        except Exception as e:
            print(f"  ⚠ provider fetch failed for {title} ({mid}): {e}")

        # Baseline for change-detection: an old film usually already carries stale VOD
        # availability, so discovery must transition only when something NEW appears vs now —
        # a Type-4 digital date that wasn't there before, or a provider outside this set.
        baseline_t4 = gen.fetch_tmdb_type4_date(mid)
        baseline_provs = rent_p + buy_p + stream_p

        entry = existing or {}
        entry.update({
            'title': title,
            'status': 'tracking',          # discovery transitions it when VOD/streaming lands
            'digital_date': None,          # set by discovery on transition
            'premiere_date': rel or None,
            'enriched': False,
            'enrichment_date': None,
            'has_providers': bool(rent_p or buy_p or stream_p),
            'providers': {'rent': rent_p, 'buy': buy_p, 'streaming': stream_p},
            'poster': poster,
            'year': year,
            'genres': genres,
            '_discovery_source': 'reissue_deferred',
            '_reissue': True,              # read by display.py → Restoration badge + treat as arrival
            'reissue_label': label,
            '_reissue_deferred_at': today,
            '_reissue_deferred': True,     # discovery branches on this → change-detection only
            '_reissue_baseline_type4': baseline_t4,        # usually None for an old film
            '_reissue_baseline_providers': baseline_provs, # stale availability to ignore
        })
        if is_tv:
            entry['is_tv'] = True
        db['movies'][mid] = entry
        intaked += 1

        # Durable layers (survive rebuilds / apply the moment it transitions).
        if label:
            labels[mid] = label
        ov = overrides.get(mid, {})
        ov.setdefault('set', {})['is_slop'] = False   # a reissue is never slop
        overrides[mid] = ov

    db['last_update'] = datetime.datetime.now().isoformat()
    tdb.save_all(db, export_json=True)
    _save_json('admin/reissue_labels.json', labels)
    _save_json('admin/overrides.json', overrides)
    print(f"Deferred {intaked} reissue(s) to tracking — discovery will surface them "
          f"on VOD/streaming release (badge + not-slop already set).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--confirm', default='', help='Comma-separated table row numbers to confirm (add to wall now)')
    ap.add_argument('--defer', default='', help='Comma-separated table row numbers to defer to tracking (watch for VOD/streaming)')
    ap.add_argument('--reject', default='', help='Comma-separated table row numbers to reject')
    ap.add_argument('--drain', action='store_true',
                    help='Reject all remaining shown pending candidates not confirmed/rejected')
    ap.add_argument('--label', action='append', default=[],
                    help='Override label for a confirmed row, e.g. --label "2=New 4K Restoration"')
    ap.add_argument('--file', default=CANDIDATES_FILE)
    ap.add_argument('--no-enrich', action='store_true',
                    help='Skip auto-enrichment (default: confirmed films are enriched immediately)')
    ap.add_argument('--dry-run', action='store_true', help='Show actions without writing')
    args = ap.parse_args()
    no_enrich = args.no_enrich

    if not os.path.exists(args.file):
        print(f"No candidate queue at {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(args.file) as f:
        data = json.load(f)
    queue = data.get('candidates', {})
    pending = sorted_pending(queue)
    if not pending:
        print("No pending candidates to act on.")
        return

    confirm_nums = set(_parse_nums(args.confirm))
    defer_nums = set(_parse_nums(args.defer))
    reject_nums = set(_parse_nums(args.reject))
    label_overrides = _parse_labels(args.label)

    def row(n):
        if 1 <= n <= len(pending):
            return pending[n - 1]
        print(f"  (row {n} out of range 1..{len(pending)} — skipped)")
        return None

    confirmed, deferred, rejected = [], [], []

    # Confirm
    for n in sorted(confirm_nums):
        cand = row(n)
        if not cand:
            continue
        label = label_overrides.get(n) or _suggested_label(cand)
        cand['status'] = 'confirmed'
        cand['confirmed_label'] = label
        cand['confirmed_at'] = datetime.date.today().strftime('%Y-%m-%d')
        confirmed.append((cand, label))

    # Defer to tracking (genuine reissue, not yet on VOD/streaming)
    for n in sorted(defer_nums):
        cand = row(n)
        if not cand:
            continue
        label = label_overrides.get(n) or _suggested_label(cand)
        cand['status'] = 'deferred'
        cand['deferred_label'] = label
        cand['deferred_at'] = datetime.date.today().strftime('%Y-%m-%d')
        deferred.append((cand, label))

    # Reject (explicit)
    for n in sorted(reject_nums):
        cand = row(n)
        if not cand or cand.get('status') != 'pending':
            continue
        cand['status'] = 'rejected'
        rejected.append(cand)

    # Drain the rest (drain rejects — a deferral is always a deliberate choice)
    if args.drain:
        for cand in pending:
            if cand.get('status') == 'pending':
                cand['status'] = 'rejected'
                rejected.append(cand)

    print(f"Confirming {len(confirmed)}, deferring {len(deferred)}, rejecting {len(rejected)}.")
    for cand, label in confirmed:
        print(f"  ✅ {cand['title']} ({cand.get('year')}) — badge: “{label}”")
    for cand, label in deferred:
        print(f"  ⏳ {cand['title']} ({cand.get('year')}) → tracking — badge: “{label}” (waiting on VOD/streaming)")
    for cand in rejected:
        print(f"  ⨯  {cand['title']} ({cand.get('year')})")

    if args.dry_run:
        print("(dry run — no writes)")
        return

    # Add confirmed films to the WALL via add_movie.py (status=available, _added_manually),
    # then flag them as reissues. Confirming is an editorial decision to feature the film
    # NOW — exactly like /add-movie — not a tracking watch entry that waits on automated
    # discovery (a theatrical-only reissue would otherwise never surface). Date = the
    # reissue's release date so it lands correctly on the wall timeline.
    if confirmed:
        import subprocess
        from pipeline.tracking_db import get_tracking_db
        add_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add_movie.py')
        added_ids = []
        for cand, label in confirmed:
            mid = str(cand['tmdb_id'])
            date = (cand.get('recent_release') or {}).get('date') or None
            cmd = [sys.executable, add_script, mid] + (['--date', date] if date else [])
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                added_ids.append(mid)
            except subprocess.CalledProcessError as e:
                print(f"  ⚠ add_movie failed for {cand['title']} ({mid}): "
                      f"{(e.stderr or '')[-200:]}")

        # Flag the now-on-wall entries as reissues (badge + restoration filter)
        tdb = get_tracking_db()
        db = tdb.load_all()
        for cand, label in confirmed:
            mid = str(cand['tmdb_id'])
            if mid in db['movies']:
                db['movies'][mid]['_reissue'] = True
                db['movies'][mid]['reissue_label'] = label
        db['last_update'] = datetime.datetime.now().isoformat()
        tdb.save_all(db, export_json=True)
        print(f"Added {len(added_ids)}/{len(confirmed)} reissue(s) to the wall (status=available).")

        # Durable layer: write labels into admin/reissue_labels.json (display reads this
        # FIRST on every rebuild, so the badge + restoration filter survive any future
        # enrichment/regeneration even if the tracking entry is ever rebuilt).
        labels_path = 'admin/reissue_labels.json'
        labels = {}
        if os.path.exists(labels_path):
            try:
                with open(labels_path) as f:
                    labels = json.load(f)
            except Exception:
                labels = {}
        for cand, label in confirmed:
            if label:  # blank badges fall back to "RESTORED" on site; don't store empty
                labels[str(cand['tmdb_id'])] = label
        ltmp = labels_path + '.tmp'
        with open(ltmp, 'w') as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)
        os.replace(ltmp, labels_path)
        print(f"Durable labels written to {labels_path} ({len(labels)} total).")

        # Auto-enrich the newly added films (RT / Wikipedia / trailer / watch links) so
        # confirming is one complete action — found → labeled → on the wall → enriched,
        # exactly like every other film. Each failure is isolated; it never aborts the run.
        if added_ids and not no_enrich:
            print(f"\nEnriching {len(added_ids)} reissue(s)...")
            for mid in added_ids:
                try:
                    subprocess.run([sys.executable, 'generate_data.py', '--enrich-id', mid],
                                   check=True, capture_output=True, text=True)
                    print(f"  ✓ enriched {mid}")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠ enrich failed for {mid}: {(e.stderr or '')[-200:]}")
        elif added_ids:
            print(f"\n(--no-enrich) Skipped enrichment for {len(added_ids)} film(s); "
                  f"run later: for id in {' '.join(added_ids)}; do "
                  f"/usr/bin/python3 generate_data.py --enrich-id $id; done")

        # Auto not-slop: a confirmed reissue is never slop. Set is_slop=false in data.json
        # (the durable /marknotslop override — enrichment preserves a non-null is_slop and
        # the classifier skips re-classification). Done AFTER enrichment so it isn't
        # overwritten by the classifier that runs during enrich.
        if added_ids and not no_enrich and os.path.exists('data.json'):
            try:
                with open('data.json') as f:
                    dj = json.load(f)
                movies = dj['movies'] if isinstance(dj, dict) else dj
                idset = set(added_ids)
                n = 0
                for m in movies:
                    if str(m.get('id')) in idset:
                        m['is_slop'] = False          # human override: never slop
                        m['_is_slop_guess'] = False   # not a guess — a decision
                        n += 1
                dtmp = 'data.json.tmp'
                with open(dtmp, 'w') as f:
                    json.dump(dj, f, indent=2, ensure_ascii=False)  # match pipeline format
                os.replace(dtmp, 'data.json')
                print(f"Marked {n} reissue(s) not-slop (is_slop=false).")
            except Exception as e:
                print(f"  ⚠ not-slop marking failed: {e}")

    # Defer: intake into the tracking DB so normal discovery surfaces the film when its
    # VOD/streaming release lands — same rails as every other tracked film.
    if deferred:
        _intake_deferred(deferred)

    # Persist candidate queue
    data['last_confirmed'] = datetime.datetime.now().isoformat()
    tmp = args.file + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, args.file)
    print("Candidate queue updated.")


if __name__ == '__main__':
    main()
