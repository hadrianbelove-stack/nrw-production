#!/usr/bin/env python3
"""
Confirm / reject reissue candidates from the "Confirm Reissues" curation stage.

Confirmed candidates are intaked into the tracking DB (status='tracking') with the
reissue flag + label so they surface on the wall via the normal discovery / virtual-screening
flow and carry their restoration badge. Rejected candidates are marked so they don't re-appear
in the pending list.

Row numbers refer to the table printed by scripts/reissue_table.py (same sort order).

Usage:
    # confirm rows 1 and 3, reject the rest of the shown pending list (drain):
    python3 scripts/confirm_reissue.py --confirm 1,3 --drain
    # confirm with a custom label on row 2:
    python3 scripts/confirm_reissue.py --confirm 2 --label "2=New 4K Restoration"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--confirm', default='', help='Comma-separated table row numbers to confirm')
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
    reject_nums = set(_parse_nums(args.reject))
    label_overrides = _parse_labels(args.label)

    def row(n):
        if 1 <= n <= len(pending):
            return pending[n - 1]
        print(f"  (row {n} out of range 1..{len(pending)} — skipped)")
        return None

    confirmed, rejected = [], []

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

    # Reject (explicit)
    for n in sorted(reject_nums):
        cand = row(n)
        if not cand or cand.get('status') != 'pending':
            continue
        cand['status'] = 'rejected'
        rejected.append(cand)

    # Drain the rest
    if args.drain:
        for cand in pending:
            if cand.get('status') == 'pending':
                cand['status'] = 'rejected'
                rejected.append(cand)

    print(f"Confirming {len(confirmed)}, rejecting {len(rejected)}.")
    for cand, label in confirmed:
        print(f"  ✅ {cand['title']} ({cand.get('year')}) — badge: “{label}”")
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

    # Persist candidate queue
    data['last_confirmed'] = datetime.datetime.now().isoformat()
    tmp = args.file + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, args.file)
    print("Candidate queue updated.")


if __name__ == '__main__':
    main()
