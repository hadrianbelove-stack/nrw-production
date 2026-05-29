---
description: Re-run enrichment for a specific movie on the wall — refreshes watch links, RT score, Wikipedia, trailer
argument-hint: [movie title or TMDB ID]
allowed-tools: Bash, Read
---

Re-enrich a specific movie that's already on the wall. Use this when a movie has missing links, a stale RT score, no Wikipedia entry, or a broken trailer.

**This is an AUTHORIZED data operation** — enrichment only overlays metadata, it never removes movies.

**Argument**: $ARGUMENTS

---

## Step 1 — Find the movie ID

```bash
/usr/bin/python3 -c "
import json
q = '$ARGUMENTS'.lower().strip()
d = json.load(open('data.json'))
for m in d['movies']:
    if q in m.get('title','').lower() or q == str(m.get('id','')) or q == str(m.get('tmdb_id','')):
        links = m.get('watch_links', {})
        vod = links.get('vod', [])
        stream = links.get('streaming', [])
        print(f\"Found: {m['title']} ({m.get('year','?')})\")
        print(f\"  ID: {m.get('id')}  |  Enrichment status: {m.get('_enrichment_status','unknown')}\")
        print(f\"  RT: {m.get('rt_score','none')}  |  Wiki: {'yes' if m.get('wiki_url') else 'no'}  |  Trailer: {'yes' if m.get('links',{}).get('trailer') else 'no'}\")
        print(f\"  Watch links: {[v['service'] for v in vod]} (VOD)  {[s['service'] for s in stream]} (stream)\")
"
```

If the argument is already a numeric ID, skip to Step 2.

---

## Step 2 — Pull latest first

```bash
git pull origin main
```

---

## Step 3 — Run single-movie enrichment

```bash
/usr/bin/python3 generate_data.py --enrich-id $MOVIE_ID 2>&1
```

Where `$MOVIE_ID` is the numeric ID from Step 1. Watch for:
- `JustWatch pre-check: justwatch_no_match → reverted to tracking` — JustWatch can't find it. Don't force it. The movie is not available on our platforms.
- `✅ enriched, N link(s)` — success.
- `Links: 0` after enrichment — movie may be streaming-only (no VOD) or JustWatch mismatch.

---

## Step 4 — Show what changed

```bash
/usr/bin/python3 -c "
import json
q = '$ARGUMENTS'.lower().strip()
d = json.load(open('data.json'))
for m in d['movies']:
    if q in m.get('title','').lower() or q == str(m.get('id','')) or q == str(m.get('tmdb_id','')):
        links = m.get('watch_links', {})
        vod = links.get('vod', [])
        stream = links.get('streaming', [])
        print(f\"After enrichment: {m['title']}\")
        print(f\"  RT: {m.get('rt_score','none')}  |  Wiki: {'yes' if m.get('wiki_url') else 'no'}  |  Trailer: {'yes' if m.get('links',{}).get('trailer') else 'no'}\")
        print(f\"  Watch links: {[v['service'] for v in vod]} (VOD)  {[s['service'] for s in stream]} (stream)\")
        print(f\"  Enrichment status: {m.get('_enrichment_status','?')}\")
"
```

---

## Step 5 — Commit if improved

Only commit if enrichment actually added or fixed something:

```bash
git add data.json movie_tracking.json 2>/dev/null || git add data.json
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Re-enrich [TITLE]: [what changed]"
git push origin main
```

---

## Report to user

Tell them:
- What was there before vs. after (links added, RT score, Wikipedia found, trailer)
- If enrichment reverted the movie: why (JW no match, or all excluded platforms)
- If 0 links: whether it's streaming-only vs. genuinely unavailable
