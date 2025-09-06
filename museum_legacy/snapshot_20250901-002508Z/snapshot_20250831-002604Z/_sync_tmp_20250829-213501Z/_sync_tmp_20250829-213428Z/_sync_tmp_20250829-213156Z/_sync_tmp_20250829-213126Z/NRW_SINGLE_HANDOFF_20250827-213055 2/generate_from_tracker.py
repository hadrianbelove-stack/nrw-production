import json, sys, datetime as dt, os

ENH="movie_tracking_enhanced.json"
LEG="movie_tracking.json"
OUT="current_releases.json"

def load_db():
    if os.path.exists(ENH):
        with open(ENH) as f: db=json.load(f)
        movies_dict=db.get("movies", {})
        movies=list(movies_dict.values()) if isinstance(movies_dict, dict) else movies_dict
        return "enh", movies
    elif os.path.exists(LEG):
        with open(LEG) as f: db=json.load(f)
        movies_dict=db.get("movies", {})
        movies=list(movies_dict.values()) if isinstance(movies_dict, dict) else movies_dict
        return "leg", movies
    sys.exit("No tracking DB found")

def to_legacy_items(kind, movies, days=14):
    today=dt.date.today(); cutoff=today-dt.timedelta(days=days); out=[]
    def get(d,*ks,default=None):
        for k in ks:
            if not isinstance(d,dict) or k not in d: return default
            d=d[k]
        return d
    for m in movies:
        if not isinstance(m, dict): continue
        dig = m.get("digital_date") or get(m,"digital","date") or get(m,"state","digital_since")
        if not dig: continue
        try: d=dt.date.fromisoformat(dig[:10])
        except: continue
        if d < cutoff: continue
        providers = m.get("providers", [])
        def names(key):
            if isinstance(providers, list):
                return [p.get("name") for p in providers if p.get("type") == key]
            elif isinstance(providers, dict):
                v=providers.get(key,[])
                return [p.get("provider_name") for p in v] if isinstance(v,list) else (v if isinstance(v,list) else [])
            return []
        out.append({
            "id": m.get("tmdb_id") or m.get("id"),
            "title": m.get("title") or m.get("name"),
            "year": (m.get("release_date") or "")[:4] or "2025",
            "release_date": m.get("release_date"),
            "digital_date": dig,
            "overview": m.get("overview"),
            "poster_path": m.get("poster_path"),
            "providers": {"rent": names("rent"), "buy": names("buy"), "flatrate": names("flatrate")},
            "runtime": m.get("runtime"),
            "genres": m.get("genres"),
            "vote_average": m.get("vote_average"),
        })
    return out

def main():
    days = int(sys.argv[1]) if len(sys.argv)>1 else 14
    kind, movies = load_db()
    out = to_legacy_items(kind, movies, days)
    with open(OUT,"w") as f: json.dump(out, f, indent=2)
    print(f"[generator] {kind}→{OUT}: {len(out)} items for last {days} days")

if __name__ == "__main__":
    main()