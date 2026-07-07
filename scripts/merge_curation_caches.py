#!/usr/bin/env python3
"""Merge CI-generated curation caches into the local caches.

CI (daily-check.yml) does the slow pull-quote scraping and capsule
pre-generation, then ships the results as the "curation-caches" artifact.
local_daily.sh downloads that artifact and calls this script to fold the
results into the Mac's working caches.

KEY RULE — never overwrite curation state. The local caches carry STATE the
CI copy doesn't have:
  - pull_quotes_combined.json: the user's `selected: true` picks and trims
  - capsule_cache.json: any locally tweaked drafts
New keys are added; existing entries are never replaced.

ONE exception (quotes only) — side-fill EMPTY halves. CI re-scrapes every
in-window film nightly, so its copy gains quotes as reviews accumulate.
Strict add-new-only froze films at their first-night scrape (often before
Letterboxd had reviews) and silently discarded every later improvement —
the Jul 2026 "no Letterboxd quotes" regression. An empty rt_quotes/lb_quotes
side holds no picks by definition, so filling it from CI cannot reset
anything the user did; a side with ANY quotes is still never touched.

Usage:  merge_curation_caches.py <artifact_dir>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.json_io import data_lock  # noqa: E402

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
    if not isinstance(art, dict):
        print(f"  {name}: unexpected (non-dict) artifact shape — skipped for safety")
        return 0
    # Locked read-modify-write: the user curates (get_quotes --select, the
    # admin flow) at the same hour this merge runs.
    with data_lock():
        local = _load(local_path)
        if not isinstance(local, dict):
            print(f"  {name}: unexpected (non-dict) cache shape — skipped for safety")
            return 0
        added = 0
        filled = 0
        for key, val in art.items():
            if key not in local:      # new film — take CI's entry whole
                local[key] = val
                added += 1
            elif name == "pull_quotes_combined.json" and isinstance(val, dict) \
                    and isinstance(local.get(key), dict):
                # Side-fill: only an EMPTY side (no quotes at all → no picks
                # to protect) takes CI's fresh scrape for that side.
                ent = local[key]
                changed = False
                for side in ("rt_quotes", "lb_quotes"):
                    if not ent.get(side) and val.get(side):
                        ent[side] = val[side]
                        changed = True
                if changed:
                    ent.pop("_no_quotes_tried", None)
                    filled += 1
        if added or filled:
            tmp = local_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(local, f, indent=2, ensure_ascii=False)
            os.replace(tmp, local_path)
    print(f"  {name}: +{added} new, {filled} side-filled (picks preserved)")
    return added + filled


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
