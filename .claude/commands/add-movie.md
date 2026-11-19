---
description: Add a movie to the NRW wall immediately with enrichment
argument-hint: [tmdb-id or title]
allowed-tools: Bash, Read, Grep, Edit, WebSearch
---

Add a movie or miniseries to the NRW wall with full enrichment and CI-safe git push.
This is an AUTHORIZED override of the CLAUDE.md data rule — the user is explicitly requesting addition via this command.

**Argument**: $ARGUMENTS (TMDB ID, or "tv_NNNN" for a TV miniseries, or a title to search for)

---

## Step 1 — Confirm the movie

If $ARGUMENTS is not a numeric ID (or tv_NNNNN), search TMDB to find the right match:
```bash
/usr/bin/python3 -c "
import requests, sys
key = open('config.yaml').read()
import re
k = re.search(r'tmdb_api_key:\s*(.+)', key).group(1).strip()
q = '$ARGUMENTS'
r = requests.get('https://api.themoviedb.org/3/search/multi', params={'api_key': k, 'query': q})
for res in r.json().get('results', [])[:5]:
    mid = res.get('id')
    media = res.get('media_type','movie')
    title = res.get('title') or res.get('name')
    year = (res.get('release_date') or res.get('first_air_date',''))[:4]
    prefix = 'tv_' if media == 'tv' else ''
    print(f'  ID: {prefix}{mid}  [{media}]  {title} ({year})')
"
```
Ask the user to confirm the correct ID before proceeding.

---

## Step 2 — Wait out today's update, then pull latest from CI

```bash
gh run list --workflow daily-check.yml --limit 1 --json status
```

If the status is anything but `completed`, today's update is still running on GitHub: stop and add the film after it finishes (usually within the hour). A push meanwhile can collide with the update's own push (certain for a film you reverted: the update rechecks it), and then that day's whole update fails to publish. If `gh` can't answer, go ahead.

**CRITICAL**: Always pull before modifying data files to avoid overwriting CI discoveries.

```bash
git pull origin main
```

---

## Step 3 — Check for duplicates

```bash
/usr/bin/python3 -c "
import json, sys
mid = str('$TMDB_ID')
d = json.load(open('data.json'))
t = json.load(open('movie_tracking.json'))
in_wall = any(str(m.get('id')) == mid for m in d['movies'])
in_tracking = mid in t.get('movies', {})
if in_wall:
    m = next(m for m in d['movies'] if str(m.get('id')) == mid)
    if m.get('hidden') or m.get('_enrichment_status') == 'reverted':
        print(f'REVERTED/HIDDEN: {m[\"title\"]} is not on the wall -- safe to add (this puts it back)')
    else:
        print(f'ALREADY ON WALL: {m[\"title\"]} (links: {sum(len(v) for v in m.get(\"watch_links\",{}).values())})')
elif in_tracking:
    mt = t['movies'][mid]
    print(f'IN TRACKING: {mt.get(\"title\")} status={mt.get(\"status\")}')
else:
    print('Not found — safe to add')
"
```

If already on wall with links, stop and tell the user. REVERTED/HIDDEN (a film the owner sent back, or one hidden for another reason) is fine: adding it puts it back on the wall. If in tracking as "tracking" (not yet available), that's fine — the script will set it to available.

---

## Step 4 — Add to tracking + data.json

Run the add_movie script. For a standard movie:
```bash
/usr/bin/python3 scripts/add_movie.py $TMDB_ID
```

For a miniseries/limited series (tv_ ID or known series):
```bash
/usr/bin/python3 scripts/add_movie.py $TMDB_ID --series
```

For a movie you know had an earlier digital date (recovery):
```bash
/usr/bin/python3 scripts/add_movie.py $TMDB_ID --date YYYY-MM-DD
```

A film the owner reverted (REVERTED/HIDDEN above) goes back dated today unless `--date` is given. To undo a mis-clicked revert, pass `--date` with the date it had on the wall.

---

## Step 5 — Run single-movie enrichment

This enriches just this one movie (~1-3 minutes): Wikipedia, RT score, trailer, watch links via JustWatch.

```bash
/usr/bin/python3 generate_data.py --enrich-id $TMDB_ID 2>&1
```

Watch the output for:
- `JustWatch pre-check: justwatch_no_match → reverted to tracking` — JustWatch can't find it. Not on our platforms. Don't force it.
- `Links: 0` after enrichment — no watch links found. Check if movie is actually available.
- `✅ enriched, N link(s)` — success, ready to commit.

**If JW pre-check reverts the movie**: Stop. The movie is not available on Amazon/Apple/YouTube/Netflix. Let the pipeline discover it naturally when it becomes available.

**If 0 links after enrichment**: Movie might be Amazon-only but JustWatch mismatch. Check TMDB providers and consider whether to force it or wait.

---

## Step 6 — Commit and push immediately

Push RIGHT AWAY, before CI's nightly run (scheduled 7:30 AM UTC: 11:30 PM PST / 12:30 AM PDT; GitHub often starts it later).

```bash
git add data.json movie_tracking.json
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Add [TITLE] to NRW wall"
git push origin main || (git pull --rebase origin main && git push origin main)
```

---

## Step 7 — Report

Tell the user:
- Movie title, digital date used
- Enrichment results: RT score, Wikipedia found?, trailer URL, watch links (platform + count)
- Push status
- If anything was reverted or had 0 links, explain why

---

## Why this workflow is CI-safe

data.json is not rebuilt from scratch by CI — it accumulates. CI only:
- ADDS new discoveries (new minimal entries)
- OVERLAYS enrichment data

So once you commit a movie with watch_links into data.json, CI preserves it.
The only way a movie disappears after commit is if CI's enrichment reverts it for 0 links (which means it's genuinely not available on our platforms).

**If CI still loses the movie after commit**: The tracking entry has `status=available` and `_added_manually=true`. Run `/add-movie` again to re-add it.
