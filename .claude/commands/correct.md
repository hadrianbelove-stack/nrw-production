---
description: Correct wrong data for a movie on the wall — wrong poster, synopsis, trailer, links, TMDB ID, etc.
argument-hint: [movie title] [what's wrong / correct value]
allowed-tools: Bash, Read, Grep, Edit, WebSearch, WebFetch
---

Apply a manual correction to a movie on the NRW wall.

**This is an AUTHORIZED override of the CLAUDE.md data rule** — the user is explicitly requesting a data correction via this command.

**Argument**: $ARGUMENTS

---

## How this works

The user spotted something wrong and is telling you what to fix. Examples:
- "Bunny has the wrong poster — it's the Ben Jacobson NYC movie"
- "Wasteman should have an Amazon VOD link"
- "Wrong trailer for Driver's Ed — here's the right one: [URL]"
- "The synopsis for X is from the wrong movie"

**Two modes depending on scope:**

1. **Specific field fix** — user provides the correct value (a URL, a fact). Apply it directly.
2. **Wrong movie entirely** (wrong TMDB ID) — everything is suspect. Fix the ID, then re-enrich via the pipeline.

---

## Step 1 — Pull latest from CI

**CRITICAL**: Always pull before modifying data files to avoid overwriting CI discoveries or causing merge conflicts.

```bash
git pull origin main
```

---

## Step 2 — Find the movie

```bash
/usr/bin/python3 -c "
import json
d = json.load(open('data.json'))
query = '$ARGUMENTS'.lower().strip()
for m in d['movies']:
    if query in m.get('title','').lower() or str(m.get('id','')) == query:
        streaming = [s['service'] for s in m.get('watch_links',{}).get('streaming',[])]
        vod = [v['service'] for v in m.get('watch_links',{}).get('vod',[])]
        print(f\"{m['title']} ({m.get('year','?')}) ID:{m.get('id')}\")
        print(f\"  Text: {(m.get('capsule') or m.get('synopsis',''))[:80]}...\")
        print(f\"  Director:{m.get('crew',{}).get('director','?')}  Country:{m.get('country','?')}\")
        print(f\"  Enrichment:{m.get('_enrichment_status','?')}\")
        print(f\"  Streaming:{streaming or 'none'}  VOD:{vod or 'none'}\")
        print(f\"  Trailer YT:     {m.get('links',{}).get('trailer') or 'none'}\")
        print(f\"  Trailer hosted: {m.get('links',{}).get('trailer_hosted') or 'none'}\")
"
```

---

## Step 3 — Apply the fix

### Path A: Specific field override

If the user gave you a concrete correction (trailer URL, missing link, wrong synopsis text), apply it directly to data.json. This is the common case.

**Rules for manual edits:**
- **Trailer**: Edit `links.trailer` in the movie entry. If a hosted trailer exists at the old URL, note that `links.trailer_hosted` may need updating too.
- **Watch links / VOD**: Only allowed platforms are **Amazon, Apple TV, YouTube**. Fandango at Home only if it's the sole option. No Google Play, Plex, Vudu, or anything else. Amazon links must include `&tag=nrw04-20`. Use HD prices.
- **Poster**: If user says it's wrong but doesn't provide a replacement, check TMDB for the current poster_path.
- **Any field**: Just edit it. Don't overthink it.

After applying the override, set `"manually_corrected": true` on the movie entry.

### Path B: Wrong TMDB ID (wrong movie entirely)

If the poster, synopsis, director, and genres are ALL wrong — the movie is mapped to the wrong TMDB entry. This requires a full re-enrichment.

**Step B1 — Find the correct TMDB ID:**
```bash
/usr/bin/python3 -c "
import requests, os
from dotenv import load_dotenv
load_dotenv()
key = os.environ['TMDB_API_KEY']
r = requests.get('https://api.themoviedb.org/3/search/movie', params={'api_key': key, 'query': '\$TITLE'})
for res in r.json().get('results', [])[:8]:
    print(f'ID: {res[\"id\"]}  {res[\"title\"]} ({res.get(\"release_date\",\"?\")[:4]})')
    print(f'  {res.get(\"overview\",\"\")[:120]}')
"
```

Confirm the correct ID with the user if ambiguous.

**Step B2 — Fix the ID in both data files:**
```bash
/usr/bin/python3 -c "
import json

OLD_ID = '$OLD_ID'
NEW_ID = '$NEW_ID'

# Fix data.json
d = json.load(open('data.json'))
for m in d['movies']:
    if str(m.get('id','')) == OLD_ID:
        m['id'] = int(NEW_ID) if NEW_ID.isdigit() else NEW_ID
        m['tmdb_id'] = int(NEW_ID) if NEW_ID.isdigit() else NEW_ID
        m['_enrichment_status'] = 'pending'  # Force re-enrichment
        print(f'Fixed {m[\"title\"]} in data.json: {OLD_ID} -> {NEW_ID}')
        break
with open('data.json', 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write('\n')

# Fix movie_tracking.json
t = json.load(open('movie_tracking.json'))
if OLD_ID in t.get('movies', {}):
    t['movies'][NEW_ID] = t['movies'].pop(OLD_ID)
    t['movies'][NEW_ID]['tmdb_id'] = NEW_ID
    print(f'Fixed tracking: {OLD_ID} -> {NEW_ID}')
    with open('movie_tracking.json', 'w') as f:
        json.dump(t, f, indent=2, ensure_ascii=False)
        f.write('\n')
"
```

**Step B3 — Re-enrich via the pipeline:**
```bash
/usr/bin/python3 generate_data.py --enrich-id $NEW_ID 2>&1
```

This re-fetches TMDB data, re-runs JustWatch verification with correct platform filtering, rebuilds watch links, and updates all fields. The pipeline handles affiliate tags, platform allowlists, RT scores, Wikipedia, trailers — everything.

**Step B4 — Apply any user overrides ON TOP of enrichment:**

If the user also provided a specific correction (e.g., "and here's the correct trailer"), apply it now AFTER enrichment so it doesn't get overwritten.

Set `"manually_corrected": true`.

---

## Step 4 — Commit and push immediately

Push RIGHT AWAY before CI runs (CI runs at 9 AM UTC / 2 AM Pacific daily). data.json is accumulative — CI overlays enrichment, so your committed corrections persist.

```bash
git add data.json movie_tracking.json
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Correct [FIELD(S)] for [TITLE]"
git push origin main || (git pull --rebase origin main && git push origin main)
```

If the rebase fails (data.json merge conflict): STOP, do not force-push, tell the user to re-run after resolving.

---

## Step 5 — Report

Tell the user:
- What was changed
- If Path B: whether enrichment succeeded (check for watch links, RT score, etc.)
- Any fields that still need attention
