import json, os, threading
from pathlib import Path
_LOCK = threading.Lock()

def _read_json(p):
    p = Path(p)
    if not p.exists(): return {}
    try:
        return json.load(open(p))
    except Exception:
        return {}

def _write_json(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with _LOCK:
        json.dump(obj, open(tmp,"w"), ensure_ascii=False, indent=2)
        os.replace(tmp, p)

# Public helpers
def cache_get(cache_file, key):
    db = _read_json(cache_file)
    return db.get(str(key))

def cache_put(cache_file, key, value):
    db = _read_json(cache_file)
    db[str(key)] = value
    _write_json(cache_file, db)
