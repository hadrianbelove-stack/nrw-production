#!/usr/bin/env python3
"""Merge CI-generated curation caches into the local caches.

CI (daily-check.yml) does the slow pull-quote scraping and capsule
pre-generation, then ships the results as the "curation-caches" artifact.
local_daily.sh downloads that artifact and calls this script to fold the
results into the Mac's working caches.

KEY RULE — add-new-only. We NEVER overwrite an entry that already exists
locally. The local caches carry curation STATE the CI copy doesn't have:
  - pull_quotes_combined.json: the user's `selected: true` picks and trims
  - capsule_cache.json: any locally tweaked drafts
CI only fills GAPS (films it scraped/wrote that the Mac hasn't seen yet),
so a re-run can never reset a pick the user already made. This is the
"one writer per file" guarantee from the engineering review (rec #1):
the Mac owns its files; CI's data is merged in, not stamped over.

Usage:  merge_curation_caches.py <artifact_dir>
"""
import json
import os
import sys

# Cache filename -> (local path, artifact path basename)
CACHES = [
    "pull_quotes_combined.json",
    "capsule_cache.json",
]
LOCAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def merge_one(name, art_dir):
    art_path = os.path.join(art_dir, name)
    local_path = os.path.join(LOCAL_DIR, name)
    if not os.path.exists(art_path):
        print(f"  {name}: no artifact file — skipped")
        return 0
    art = _load(art_path)
    local = _load(local_path)
    if not isinstance(art, dict) or not isinstance(local, dict):
        print(f"  {name}: unexpected (non-dict) cache shape — skipped for safety")
        return 0
    added = 0
    for key, val in art.items():
        if key not in local:          # never overwrite local curation state
            local[key] = val
            added += 1
    if added:
        with open(local_path, "w") as f:
            json.dump(local, f, indent=2, ensure_ascii=False)
    print(f"  {name}: +{added} new entr{'y' if added == 1 else 'ies'} (existing preserved)")
    return added


def main():
    if len(sys.argv) != 2:
        print("usage: merge_curation_caches.py <artifact_dir>", file=sys.stderr)
        return 2
    art_dir = sys.argv[1]
    total = sum(merge_one(name, art_dir) for name in CACHES)
    print(f"Merged curation caches: {total} new entr{'y' if total == 1 else 'ies'} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
