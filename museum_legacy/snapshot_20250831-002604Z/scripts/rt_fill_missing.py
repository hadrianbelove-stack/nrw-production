#!/usr/bin/env python3
import json, os, time, datetime
from rt_agent import fetch_rt_for_title

DATA="output/data.json"
BACK="output/data.backup.rt.json"

def days_old(iso):
    try:
        d=datetime.datetime.fromisoformat(iso[:10])
        return (datetime.datetime.utcnow()-d).days
    except: return 9999

def main():
    d=json.load(open(DATA))
    changed=0; tried=0
    for m in d:
        if m.get("rt_score"): continue
        # only try items at least 7 days after primary/digital release
        rel = m.get("digital_date") or m.get("release_date") or ""
        if days_old(rel) < 7: continue

        tried+=1
        r = fetch_rt_for_title(m.get("title",""), m.get("year"))
        if not r: continue
        if r.get("critic_score") is not None:
            m["rt_score"]  = r["critic_score"]
            m["rt_method"] = r["method"]
            if r.get("rt_url"): m["rt_url"] = r["rt_url"]
            if r.get("audience_score") is not None:
                m["rt_audience"] = r["audience_score"]
            changed+=1
        time.sleep(1.0)  # be polite

    if changed:
        os.makedirs(os.path.dirname(BACK), exist_ok=True)
        open(BACK,"w").write(json.dumps(d, indent=2, ensure_ascii=False))
        open(DATA,"w").write(json.dumps(d, indent=2, ensure_ascii=False))
    print(f"rt_fill_missing: changed={changed} tried={tried}")

if __name__=="__main__":
    main()