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


def _build_tracking_entry(cand, label):
    today = datetime.date.today().strftime('%Y-%m-%d')
    return {
        'title': cand.get('title', 'Unknown'),
        'year': cand.get('year'),
        'status': 'tracking',          # discovery handles transition to available
        'intake_date': today,
        'digital_date': None,
        'providers': {},
        'intake_pass': 'D',
        '_reissue': True,
        'reissue_label': label,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--confirm', default='', help='Comma-separated table row numbers to confirm')
    ap.add_argument('--reject', default='', help='Comma-separated table row numbers to reject')
    ap.add_argument('--drain', action='store_true',
                    help='Reject all remaining shown pending candidates not confirmed/rejected')
    ap.add_argument('--label', action='append', default=[],
                    help='Override label for a confirmed row, e.g. --label "2=New 4K Restoration"')
    ap.add_argument('--file', default=CANDIDATES_FILE)
    ap.add_argument('--dry-run', action='store_true', help='Show actions without writing')
    args = ap.parse_args()

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

    # Intake confirmed films into tracking DB
    if confirmed:
        from pipeline.tracking_db import get_tracking_db
        tdb = get_tracking_db()
        db = tdb.load_all()
        added = 0
        for cand, label in confirmed:
            mid = str(cand['tmdb_id'])
            if mid in db['movies']:
                # already tracked — just flag it as a reissue + label
                db['movies'][mid]['_reissue'] = True
                db['movies'][mid]['reissue_label'] = label
            else:
                db['movies'][mid] = _build_tracking_entry(cand, label)
                added += 1
        db['last_update'] = datetime.datetime.now().isoformat()
        tdb.save_all(db, export_json=True)
        print(f"Tracking DB: {added} new reissue(s) added, {len(confirmed) - added} existing flagged.")

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

    # Persist candidate queue
    data['last_confirmed'] = datetime.datetime.now().isoformat()
    tmp = args.file + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, args.file)
    print("Candidate queue updated.")


if __name__ == '__main__':
    main()
