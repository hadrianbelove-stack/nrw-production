import json, sys, datetime as dt
IN="movie_tracking_enhanced.json"; OUT="current_releases.json"
try: db=json.load(open(IN))
except: sys.exit(f"Missing {IN}")
today=dt.date.today(); cutoff=today-dt.timedelta(days=14); out=[]
def get(d,*ks,default=None):
    for k in ks:
        if not isinstance(d,dict) or k not in d: return default
        d=d[k]
    return d
movies_dict=db.get("movies", {})
for movie_id, m in movies_dict.items():
    dig=m.get("digital_date")
    if not dig: continue
    try: d=dt.date.fromisoformat(dig[:10])
    except: continue
    if d<cutoff: continue
    providers_list=m.get("providers", [])
    def names(ptype): 
        return [p.get("name") for p in providers_list if p.get("type")==ptype]
    out.append({
        "id": int(movie_id),
        "title": m.get("title"),
        "year": (m.get("release_date") or "")[:4],
        "release_date": m.get("release_date"),
        "digital_date": dig,
        "overview": m.get("overview"),
        "poster_path": m.get("poster_path"),
        "providers": {"rent": names("rent"), "buy": names("buy"), "flatrate": names("flatrate")},
        "runtime": m.get("runtime"), "genres": m.get("genres",[]), "vote_average": m.get("vote_average"),
    })
json.dump(out, open(OUT,"w"), indent=2)
print(f"Wrote {len(out)} items to {OUT}")