---
description: Remove a movie from the NRW wall by title or TMDB ID
allowed-tools: Bash, Read, Grep, Edit
---

Remove a movie from the NRW wall permanently. This is a pull → work → push atomic operation so CI and local stay in sync. This is an AUTHORIZED override of the CLAUDE.md data rule.

**Argument**: $ARGUMENTS (movie title or TMDB ID)

---

## Step 1 — Pull latest from CI

Start by syncing with CI so we're working from the authoritative version.

```bash
git pull origin main
```

---

## Step 2 — Find the movie

```bash
/usr/bin/python3 -c "
import json
d = json.load(open('data.json'))
q = '$ARGUMENTS'.lower()
for m in d['movies']:
    if q in m['title'].lower() or str(m.get('id')) == q:
        wl = m.get('watch_links', {})
        links = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
        print(f'  ID:{m[\"id\"]}  {m[\"title\"]} ({m.get(\"year\")})  date:{m.get(\"digital_date\")}  links:{links}')
"
```

If multiple matches, show them and ask which one. Confirm title, ID, and digital_date with the user before proceeding.

---

## Step 3 — Remove from data.json + mark in tracking

```bash
/usr/bin/python3 -c "
import json
from datetime import date

MOVIE_ID = str('REPLACE_WITH_ID')

# Remove from data.json
with open('data.json') as f:
    data = json.load(f)

before = len(data['movies'])
removed_movie = next((m for m in data['movies'] if str(m.get('id')) == MOVIE_ID), None)
if not removed_movie:
    print(f'ERROR: {MOVIE_ID} not found in data.json')
    exit(1)

data['movies'] = [m for m in data['movies'] if str(m.get('id')) != MOVIE_ID]
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f'Removed from data.json: {removed_movie[\"title\"]}  ({before} → {len(data[\"movies\"])} movies)')

# Mark as removed in movie_tracking.json
with open('movie_tracking.json') as f:
    tracking = json.load(f)

today = date.today().isoformat()
movies = tracking.get('movies', {})
if MOVIE_ID in movies:
    movies[MOVIE_ID]['status'] = 'removed'
    movies[MOVIE_ID]['removed_date'] = today
    movies[MOVIE_ID]['removed_reason'] = 'manual_removal'
    # Clean diagnostic tags so movie doesn't linger on revert/fail reports
    for tag in ['_jw_revert_reason', '_jw_reverted_at', '_enrichment_error', '_enrichment_failed_at']:
        movies[MOVIE_ID].pop(tag, None)
else:
    # Not in tracking — create minimal entry so it can never be re-discovered
    movies[MOVIE_ID] = {
        'title': removed_movie['title'],
        'year': removed_movie.get('year'),
        'status': 'removed',
        'removed_date': today,
        'removed_reason': 'manual_removal',
    }

tracking['movies'] = movies
with open('movie_tracking.json', 'w') as f:
    json.dump(tracking, f, indent=2, ensure_ascii=False)
print(f'Marked status=removed in movie_tracking.json')
"
```

---

## Step 4 — Push both files

```bash
git add data.json movie_tracking.json
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Remove [TITLE] from NRW wall"
git push origin main
```

---

## Step 5 — Report

- Movie title + TMDB ID removed
- Wall count before → after
- Confirm push succeeded

---

## Why this works

The entire command is **pull → work → push** in one operation. CI never sees an inconsistent state.

- **data.json committed**: CI doesn't rebuild from scratch — it only adds/overlays. Without committing the removal, the movie stays on the wall.
- **movie_tracking.json with status=removed**: Blocks all re-discovery paths. Discovery only processes `status=tracking` movies. Intake skips any ID already in tracking regardless of status. Movie can never come back.
- **data_archive.json**: Not used here — that file is for movies that naturally aged out of the 90-day window, not manual removals. The tracking entry is the audit trail.
