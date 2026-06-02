---
description: Binary time search — find when something first appeared online (VOD date, article, URL) using Wayback Machine
argument-hint: [movie-name or URL]
---

Find *when* something first appeared or changed online, using binary search through Wayback Machine snapshots.

**Input**: $ARGUMENTS — either a movie name or a full URL.

---

## Mode 1: Movie name (no "http")

Goal: Find when a movie first became available on VOD (rent/buy).

### Steps:

1. **Search TMDB** for the movie to get its title and confirm it exists:
   ```bash
   /usr/bin/python3 -c "
   import requests, os
   from dotenv import load_dotenv
   load_dotenv('/Users/hadrianbelove/Downloads/nrw-production/.env')
   key = os.environ.get('TMDB_API_KEY', '')
   r = requests.get('https://api.themoviedb.org/3/search/movie', params={'api_key': key, 'query': '$ARGUMENTS'})
   for res in r.json().get('results', [])[:5]:
       print(f'  {res[\"id\"]}  {res[\"title\"]} ({res.get(\"release_date\",\"\")[:4]})')
   "
   ```

2. **Build the JustWatch URL slug** from the title:
   - Lowercase, replace spaces with hyphens, strip special characters
   - URL: `https://www.justwatch.com/us/movie/<slug>`

3. **Query Wayback CDX API** for all snapshots:
   ```
   curl -s "https://web.archive.org/cdx/search/cdx?url=justwatch.com/us/movie/<slug>&output=json&filter=statuscode:200"
   ```
   This returns a JSON array. First row = headers, subsequent rows = snapshots with timestamps.

4. **Binary search** through the snapshots to find when VOD first appeared:

   a. **Check the most recent snapshot** — confirm VOD providers exist (rent/buy available). If not, report "not yet on VOD" and stop.

   b. **Check the oldest snapshot** — confirm VOD was NOT available yet. If VOD was already there, report "VOD available since at least [oldest date]".

   c. **Binary search the middle**: pick the midpoint snapshot, fetch it, check for VOD. Narrow the range. Repeat until adjacent snapshots are found (one without VOD, next with VOD).

5. **Detecting VOD in a snapshot**: Fetch the full page via:
   ```
   curl -s "https://web.archive.org/web/<TIMESTAMP>/https://www.justwatch.com/us/movie/<slug>"
   ```
   Then parse with inline Python — check for these signals:
   - JSON-LD `offers.offerCount` > 0 means VOD is available
   - JSON-LD `potentialAction` with `WatchAction` entries means providers exist
   - Text "Currently in theaters" means NOT yet on VOD
   - If `offerCount` is 0 or offers array is empty → no VOD

6. **Report**: The narrowest date range when VOD became available, e.g.:
   > "Hollywoodgate went to VOD somewhere between Dec 23, 2024 and Dec 27, 2025 (only 4 Wayback snapshots exist for this URL)."

   Also report total snapshots available and which providers appeared.

---

## Mode 2: Full URL (starts with "http")

Goal: Find when a URL first appeared online, or when specific content first appeared.

### Steps:

1. **Query Wayback CDX API**:
   ```
   curl -s "https://web.archive.org/cdx/search/cdx?url=<URL>&output=json&filter=statuscode:200"
   ```

2. **Report the earliest capture date** (first snapshot timestamp). Format as human-readable date.

3. **Report total number of snapshots** and the date range (earliest to latest).

4. If the user asks about specific content appearing, use binary search through snapshots to find when that content first shows up (grep for keywords in each fetched page).

---

## Important notes:
- Wayback snapshots are sparse — some URLs have only a handful of captures. Always report how many snapshots exist so the user understands the precision.
- Timestamp format in CDX results is `YYYYMMDDHHmmss` — convert to readable dates.
- Rate-limit fetches: add a 1-second delay between Wayback page fetches to be polite.
- Use `/usr/bin/python3` for any inline Python parsing.
