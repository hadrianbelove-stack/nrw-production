#!/usr/bin/env python3
"""
One-time migration: movie_tracking.json → movie_tracking.db (SQLite).

Run once after pulling this branch. Subsequent pipeline runs will keep
the SQLite DB in sync automatically. The JSON file remains as the Git
artifact (exported after every save).

Usage:
    /usr/bin/python3 scripts/migrate_to_sqlite.py
"""

import json
import os
import sys

# Ensure project root is on the path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from pipeline.tracking_db import TrackingDB

JSON_PATH = 'movie_tracking.json'
DB_PATH = 'movie_tracking.db'


def main():
    if not os.path.exists(JSON_PATH):
        print(f"❌  {JSON_PATH} not found — nothing to migrate.")
        sys.exit(1)

    # Count source records
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        source = json.load(f)
    source_count = len(source.get('movies', {}))
    print(f"📂  Source: {JSON_PATH} — {source_count:,} movies")

    if os.path.exists(DB_PATH):
        print(f"⚠️   {DB_PATH} already exists — re-importing to replace it.")
        os.remove(DB_PATH)

    print(f"⚙️   Importing into {DB_PATH}...")
    tdb = TrackingDB(db_path=DB_PATH, json_path=JSON_PATH)
    # _init_db already auto-imported from JSON since DB was missing.
    # Verify.
    db_count = tdb.count()

    if db_count == source_count:
        print(f"✅  Migration complete: {db_count:,} movies in SQLite DB")
    else:
        print(f"❌  Count mismatch: JSON={source_count:,}, DB={db_count:,}")
        sys.exit(1)

    # Status breakdown
    for status in ('tracking', 'available', 'removed', 'blocked'):
        n = tdb.count(status)
        if n:
            print(f"    {status}: {n:,}")

    print()
    print(f"ℹ️   {DB_PATH} is gitignored — movie_tracking.json remains the Git artifact.")
    print(f"ℹ️   The pipeline will keep both in sync going forward.")


if __name__ == '__main__':
    main()
