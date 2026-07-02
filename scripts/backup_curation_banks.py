#!/opt/homebrew/bin/python3.11
"""
Back up the hand-curated curation banks to Backblaze B2.

cache/approved_capsules.json (capsule house-style few-shot bank) and
cache/taste_profile_pullquotes.json (pull-quote taste profile) are
deliberately gitignored — this Mac holds the ONLY copies. A disk failure
would permanently destroy months of hand curation, so local_daily.sh
uploads a dated copy to B2 whenever the content changes.

Restore: download the newest backups/curation/<name>.<date>.json from the
B2 bucket back to cache/<name>.json.

Usage:
    python3.11 scripts/backup_curation_banks.py            # backup if changed
    python3.11 scripts/backup_curation_banks.py --force    # backup regardless
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from trailer_uploader import load_env, get_b2_api

BANK_FILES = [
    os.path.join(PROJECT_ROOT, 'cache', 'approved_capsules.json'),
    os.path.join(PROJECT_ROOT, 'cache', 'taste_profile_pullquotes.json'),
]
# sha256 of each bank at last successful upload (gitignored via cache/*.json)
STATE_FILE = os.path.join(PROJECT_ROOT, 'cache', '.bank_backup_state.json')
REMOTE_PREFIX = 'backups/curation'


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Back up curation banks to B2')
    parser.add_argument('--force', action='store_true',
                        help='Upload even if content is unchanged')
    args = parser.parse_args()

    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
        except Exception as e:
            print(f'Warning: could not read backup state ({e}) — re-uploading all banks')

    pending = []
    for path in BANK_FILES:
        name = os.path.basename(path)
        if not os.path.exists(path):
            print(f'WARNING: {name} not found — nothing to back up')
            continue
        digest = file_sha256(path)
        if not args.force and state.get(name) == digest:
            continue  # unchanged since last successful backup
        pending.append((path, name, digest))

    if not pending:
        print('Curation banks unchanged — no backup needed')
        return 0

    load_env()
    _, bucket = get_b2_api()

    failures = 0
    for path, name, digest in pending:
        stem, ext = os.path.splitext(name)
        remote_name = f'{REMOTE_PREFIX}/{stem}.{date.today().isoformat()}{ext}'
        try:
            bucket.upload_local_file(local_file=path, file_name=remote_name,
                                     content_type='application/json')
            state[name] = digest
            print(f'Backed up {name} -> {remote_name}')
        except Exception as e:
            failures += 1
            print(f'ERROR: backup of {name} failed: {e}')

    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f'ERROR: could not write backup state: {e}')

    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
