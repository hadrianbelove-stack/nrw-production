#!/usr/bin/env python3
import json, os, sys, datetime

SRC = os.path.join(os.path.dirname(__file__), "..", "current_releases.json")
DST = os.path.join(os.path.dirname(__file__), "..", "assets", "data.json")

def main():
    with open(SRC, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    if isinstance(raw, dict) and 'movies' in raw:
        movies = raw.get('movies', {})
        it = movies.items()
    elif isinstance(raw, list):
        it = [(str(i), m) for i, m in enumerate(raw)]
    else:
        it = []
    for k, m in it:
        item = {
            "id": m.get("tmdb_id") or k,
            "title": m.get("title"),
            "theatrical_date": m.get("theatrical_date"),
            "digital_date": m.get("digital_date"),
            "status": m.get("status"),
            "rt_score": m.get("rt_score"),
            "streaming_info": m.get("streaming_info"),
            "poster": None,
            "crew": {"director": None, "cast": []},
            "synopsis": None,
            "links": {"trailer": None, "rt": None, "wiki": None},
            "metadata": {"runtime": None, "studio": None}
        }
        out.append(item)

    # Sort by digital_date desc, then title
    def sort_key(x):
        dd = x.get("digital_date") or ""
        return (dd, x.get("title") or "")
    out.sort(key=sort_key, reverse=True)

    with open(DST, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                   "count": len(out),
                   "movies": out}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DST} with {len(out)} movies.")

if __name__ == "__main__":
    main()
