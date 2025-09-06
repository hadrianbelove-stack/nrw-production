
import json, pathlib, collections, datetime as dt
p=pathlib.Path("output/data.json"); d=json.load(p.open())
N=len(d)
have_rt=[x for x in d if x.get("rt_score") is not None]
miss_rt=[x for x in d if x.get("rt_score") is None]
by_src=collections.Counter((x.get("rt_source") or "unknown") for x in have_rt)
have_imdb=sum(1 for x in d if x.get("imdb_id"))
have_amz=sum(1 for x in d if x.get("amazon_url"))
have_prov=sum(1 for x in d if isinstance(x.get("providers"),dict) and any(x["providers"].get(k) for k in ("rent","buy","stream","flatrate")))
out={"timestamp":dt.datetime.utcnow().isoformat(timespec="seconds")+"Z",
     "items":N,"rt_coverage":len(have_rt),"missing_rt":len(miss_rt),
     "by_source":by_src,"have_imdb":have_imdb,"have_amazon":have_amz,"have_providers":have_prov}
path=pathlib.Path("reports/health.json"); path.write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
