#!/usr/bin/env python3
import os, json, sys, re
from pathlib import Path

root = Path(__file__).resolve().parent
cur_path = root/"curated_selections.json"
out_dir = root/"output"; out_dir.mkdir(exist_ok=True)
out_data = out_dir/"data.json"

# 0) Load curated selections (dict of id -> {status: approved/...})
cur = {}
if cur_path.exists():
    try:
        obj = json.load(open(cur_path))
        if isinstance(obj, dict): cur = obj
    except Exception as e:
        print("WARN: curated_selections.json unreadable:", e, file=sys.stderr)

approved_ids = set()
for k,v in cur.items():
    # Handle both old format {"status": "approved"} and new format "approved"/"feature"
    status = v.get("status") if isinstance(v, dict) else v
    if status in ("approve", "approved", "feature"):
        try: approved_ids.add(int(k))
        except: pass
print(f"Approved IDs: {len(approved_ids)}")

# 1) Resolve full catalog
full = os.environ.get("FULL_CATALOG")
candidates = []
if not full:
    # scan for the largest plausible JSON containing "tmdb_id"
    for p in root.rglob("*.json"):
        if p.name in ("curated_selections.json","output.json","data.json"): continue
        try:
            sz = p.stat().st_size
            if sz < 4096: continue
            with open(p, "rb") as fh:
                head = fh.read(2_000_000)
            if b'"tmdb_id"' in head and head.strip().startswith(b"["):
                candidates.append((sz, p))
        except Exception:
            pass
    candidates.sort(reverse=True)
    if candidates:
        full = str(candidates[0][1])
        print("Auto-detected FULL_CATALOG:", full)
    else:
        print("ERROR: could not find full catalog JSON. Set env FULL_CATALOG=/path/file.json", file=sys.stderr)
        sys.exit(1)

full_path = Path(full)
if not full_path.exists():
    print("ERROR: FULL_CATALOG not found:", full_path, file=sys.stderr); sys.exit(1)

# 2) Load full catalog
try:
    full_data = json.load(open(full_path))
except Exception as e:
    print("ERROR: cannot read full catalog:", e, file=sys.stderr); sys.exit(1)

# Handle nested structure (movies.{id} or flat array)
movies_data = full_data.get("movies", full_data) if isinstance(full_data, dict) else full_data

def get_id(m):
    for k in ("tmdb_id","id"):
        if k in m:
            try: return int(m[k])
            except: return None
    return None

# 3) Filter to approved
index = {}
if isinstance(movies_data, dict):
    # movies_data is {id: movie_object}
    for tid_str, m in movies_data.items():
        try:
            tid = int(tid_str)
            if isinstance(m, dict):
                m["tmdb_id"] = tid  # Ensure tmdb_id is present
                index[tid] = m
        except: pass
else:
    # movies_data is [movie_objects]
    for m in movies_data:
        if isinstance(m, dict):
            tid = get_id(m)
            if tid is not None:
                index[tid] = m

dataset = [index[i] for i in approved_ids if i in index]
print(f"Matched approved in full catalog: {len(dataset)}")

# 4) Provider-truth flags
for m in dataset:
    prov = m.get("providers") or []
    m["has_digital"] = bool(prov)
    m["date_key"] = m.get("date_key") or m.get("theatrical_date") or m.get("release_date")

# 5) Write output/data.json
json.dump(dataset, open(out_data,"w"), ensure_ascii=False, indent=2)
print("Wrote:", out_data)