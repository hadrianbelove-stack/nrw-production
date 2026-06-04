---
description: Curate new arrivals — staff picks, sections, pull quotes, capsules
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Curate movies added since last session. Runs 3 stages in order, each with a user prompt. Resumable — if interrupted, re-running picks up where you left off.

## Before You Start — pull latest

The daily CI rewrites `data.json` every morning. Start on fresh main so your edits don't conflict:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git pull origin main
```

If any `git push` in this session is rejected (CI or another writer pushed mid-session), run `git pull --rebase origin main` and push again — never resolve a data.json merge by hand (`--ours`/`--theirs` loses transitions; see CLAUDE.md).

## Resume Logic

Before starting, check for an existing session:

1. Read `cache/curation_progress.json` (if it exists)
2. Read `.claude/last_nrw_session.json` to get the session timestamp
3. If `curation_progress.session_start` matches the session timestamp → **resume**: skip stages marked `completed`, jump to first `pending` or `in_progress` stage
4. If no match or no file → **fresh start**: create new progress file with all stages `pending`

**Progress file format** (`cache/curation_progress.json`):
```json
{
  "session_start": "2026-05-18T15:29:11",
  "stages": {
    "staff_picks": "pending",
    "sections": "pending",
    "per_movie": "pending"
  }
}
```

Update the progress file after completing each stage (set to `completed`). Set a stage to `in_progress` when you begin it.

## Candidate List (shared by Stages 1 and 2)

Run this script to build the candidate list. Both Stage 1 and Stage 2 operate on this exact output — do not re-derive it:

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta

data = json.load(open('data.json'))
today = str(date.today())

try:
    sess = json.load(open('.claude/last_nrw_session.json'))
    from_date = sess['timestamp'][:10]
except Exception:
    from_date = str(date.today() - timedelta(days=7))

current_year = date.today().year
candidates = []
for m in data['movies']:
    dd = m.get('digital_date', '')
    if not (from_date < dd <= today):
        continue
    cats = m.get('filters', {})
    if cats.get('is_restoration'):
        continue
    title = m.get('title', '')
    year = m.get('year', 0) or 0
    if any(kw in title for kw in ('Remaster', 'Restoration', '4K')) or (year and current_year - int(year) >= 10):
        continue
    streaming = [s['service'] for s in m.get('watch_links', {}).get('streaming', [])]
    vod = [v['service'] for v in m.get('watch_links', {}).get('vod', [])]
    services = streaming + vod
    rt = m.get('rt_score') or '--'
    mc = m.get('metacritic_score') or '--'
    svc = ', '.join(services) if services else '--'
    candidates.append((dd, m.get('id'), title, m.get('year','?'), rt, mc, svc))

candidates.sort(key=lambda x: x[0], reverse=True)
print(f'{len(candidates)} candidate(s) since {from_date}:')
for i, (dd, mid, title, year, rt, mc, svc) in enumerate(candidates, 1):
    print(f'  {i}. {title} ({year}) — RT:{rt} | MC:{mc} | {svc}  [id:{mid}]')
"
```

If the output shows 0 candidates, report "No new arrivals to curate since [from_date]" and stop.

**Note**: Stage 3 (Per-Movie Curation) uses its own watermark-based candidate logic — see that stage for details.

---

## Stage 1: Staff Picks

Show a numbered list of all candidates:

```
STAFF PICKS — which movies are you vouching for?

 1. Title (Year) — RT: 85% | MC: 72 | Amazon, Apple TV
 2. Title (Year) — RT: -- | MC: -- | Netflix
 3. Title (Year) — RT: 92% | MC: 80 | Fandango At Home
 ...

Reply with numbers (e.g. "1, 7, 10") or "skip" to skip.
```

For each movie row show: title, year, RT score (or `--`), Metacritic score (or `--`), and which services it has watch links for.

**On user reply:**
- Parse the numbers, map to movie IDs
- Read `admin/staff_picks.json`, add new IDs (avoid duplicates), write back
- Commit + push: `git add admin/staff_picks.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Staff picks updated APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))`
- Mark stage `completed` in progress file

---

## Stage 2: Section Review

Show each candidate with its auto-detected filters (from TMDB genres, language, and distributor data). Review and correct any misses.

Present as a markdown table with columns: `#`, `Title (Year)`, `Sections`. Hyperlink the title to the movie's Wikipedia page if one exists in `movie.links.wikipedia` (or found via WebSearch). If no Wikipedia page, plain text. Categories should all be in the same column so they scan cleanly vertically.

```
FILTERS — check auto-detected assignments

| # | Title (Year) | Sections |
|---|--------------|----------|
| 1 | [Title (Year)](https://en.wikipedia.org/wiki/...) | Studio |
| 2 | [Title (Year)](https://en.wikipedia.org/wiki/...) | Foreign, Documentary |
| 3 | Title (Year) | Indie |
| 4 | Title (Year) | (none) |

Reply with changes (e.g. "2: remove foreign; 4: add indie") or "looks good" to confirm all.
```

For each movie, show **all active filters** — meaning everything a user could filter by on the site:

- From `movie.filters`: Indie, Foreign, Documentary, Virtual Screening, Restoration (check `is_indie`, `is_foreign`, `is_documentary`, `is_virtual_screening`, `is_restoration`)
- From `movie.genres`: Horror, Action, Comedy, Family, Thriller (check if genre name appears in the array)

Show as human-readable names. If no filters are active, show "(none)". Staff Picks is handled in Stage 1 — omit it here.

**On user reply:**
- For studio/indie overrides: read `admin/category_overrides.json`, add entries, write back
- For restoration overrides: read `admin/restorations.json`, add IDs, write back
- Commit + push any override file changes
- Mark stage `completed` in progress file

**Note**: All filters are auto-detected from TMDB data — genres (Comedy, Horror, Action), language (Foreign), and distributor rules (Indie, Studio, Documentary). To improve detection logic (e.g. add indie distributor rules), update the pipeline code — not this command.

---

## Stage 3: Per-Movie Curation (Capsule + Pull Quotes together)

Capsules and pull quotes are done together, movie by movie — not as separate passes.

**Find candidates**: Stage 3 uses watermark logic, not the Stage 1/2 candidate list. Take the union of:
- Movies needing a capsule: `digital_date` > capsule watermark (most recent `digital_date` among movies in `cache/approved_capsules.json`), not already in `cache/approved_capsules.json` by title, not a restoration
- Movies needing pull quotes: `digital_date` > pull quote watermark (most recent `digital_date` among movies with a `pull_quotes` array in `data.json`), not already having `pull_quotes`, not a restoration

Merge into one list, deduplicated, sorted by `digital_date` descending. For each movie, track which work it needs: capsule, quotes, or both.

If no candidates for either: report through-dates and mark stage `completed`.

**For each movie, in order:**

### Step A — Capsule (if needed)

1. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "TITLE" --force --variants 3 --skip-verify`
2. **Read `.claude/commands/capsule.md` Step 2** for the exact presentation format — that file is the single source of truth. Use it exactly: movie header (director/genres/runtime/country/platforms), keyword/badge line, three variants with approach labels, FACTOID PRIMER, SUGGESTED LINKS, pick prompt.
3. Wait for user response. **When user provides edited text, that IS the final version.**
4. If picked/rewritten:
   1. Apply standard formatting: **bold** the director's name and cast member names; *italicize* titles of other films mentioned in the text
   2. **Pre-embed Wikipedia links** into the chosen text (see Step A-Links below), then confirm with user before continuing
   3. Write final approved text to `cache/rewrite.txt`
   4. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "TITLE" --file cache/rewrite.txt`
   5. Write cast wiki links to data.json (see Step A-Links below)

### Step A-Links — Wikipedia Links (runs inside Step A)

**Generating SUGGESTED LINKS (shown below the factoid primer):**

Cast and director Wikipedia links are **auto-approved** — collect them silently for later embedding but do NOT list them in SUGGESTED LINKS for user review.

**Pass 1 — Cast + Director (silent, no user review):**
- Read `movie.links.cast_wiki` and `movie.links.director_wiki` from data.json.
- Embed whatever is there wherever their names appear in the capsule text. If a name has no URL, skip it silently — many actors don't have Wikipedia pages.

**Pass 2 — Other named entities in the capsule text (user reviews these):**
- Identify non-cast/non-director people, places, movements, or works that are named in the capsule text itself (e.g. a manga creator, historical figure, referenced filmmaker). Up to 3.
- WebSearch each for a Wikipedia page.
- If none exist, omit the SUGGESTED LINKS section entirely.

Present only Pass 2 results:
```
**SUGGESTED LINKS**
1. [Lucian Freud](https://en.wikipedia.org/wiki/Lucian_Freud) — painter, subject of film
```

If a person has no Wikipedia page, skip them silently.

**Pre-embedding links (after user picks a variant):**

Once the user picks a variant or provides a rewrite:
1. **Scan the final capsule text for any `**bold**` names not already in SUGGESTED LINKS.** WebSearch each unlisted bold name for a Wikipedia page and add to the list if found.
2. Embed ALL links into the text:
   - Entity name appears as `**bold**` → change to `**[Name](url)**`
   - Entity name appears as plain text → change to `[Name](url)`
   - Entity name not in the capsule text → skip (still save to cast_wiki for the metadata line)
3. Show the modified capsule with links visible in the markdown
4. Ask: "Approve with these links — or say 'remove [Name]' to drop any."
5. If user removes any: strip that link, show updated capsule again
6. When user approves: this is the final text — proceed to write cache/rewrite.txt

**Saving cast wiki links (after approve script runs):**

For each cast member that had a Wikipedia URL (from either data.json or WebSearch), write to `movie.links.cast_wiki` — merging with any existing entries, not overwriting:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys
title, cast_wiki_json = sys.argv[1], sys.argv[2]
cast_wiki = json.loads(cast_wiki_json)
with open('data.json') as f:
    data = json.load(f)
movies = data if isinstance(data, list) else data.get('movies', [])
for m in movies:
    if m.get('title', '').lower() == title.lower():
        m.setdefault('links', {})
        existing = m['links'].get('cast_wiki', {})
        existing.update(cast_wiki)
        m['links']['cast_wiki'] = existing
        break
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
" "MOVIE_TITLE" '{"Ellie Bamber": "https://...", "Derek Jacobi": "https://..."}'
```

Only include cast members in cast_wiki (not director, historical figures, or events — those are capsule-text links only). Wikipedia URLs with parentheses: encode `(` as `%28` and `)` as `%29`.

### Step B — Pull Quotes (immediately after capsule, same movie)

Show pull quotes for this movie right after the capsule is resolved (picked, skipped, or not needed).

**1. Get the quotes — read from cache**

The morning launchagent (`scripts/batch_pull_quotes.py`) scrapes pull quotes for all new arrivals before curation runs. Read from `cache/pull_quotes_combined.json` using the cache key `"{title}_{year}"`.

- If the movie **has quotes in cache**: use them. Do not re-scrape.
- If the movie is **absent from cache entirely**: show this flag and skip pull quotes for this movie:
  `⚠ No pull quotes in cache — morning batch may have missed this movie. Check Concerns in tomorrow's launchagent report.`

Do not re-scrape. The morning batch is the canonical source.

**2. Rank by taste profile**

Read `cache/taste_profile_pullquotes.json`. Rank all quotes from best match to worst. The profile consistently shows:
- **Prefers**: specific vivid language, punchy fragments, wit, emotional precision
- **Avoids**: vague generic praise ("brilliant", "stunning"), academic jargon, plot summary masquerading as criticism, quotes that repeat the movie title
- Top critics and known outlets rank higher when quotes are otherwise equal
- A short sharp fragment trimmed from a longer quote can outperform a full sentence

**3. Present — grouped by outlet, full list**

Show all usable quotes (up to ~12), grouped by outlet. Format exactly like this:

```
[Film Title] PULL QUOTES

**Outlet Name**
1. *"Quote text here."* — Critic Name  ▶ (top pick)

**Another Outlet**
2. *"Another quote."* — Critic Name
3. *"Third quote from same outlet."* — Critic Name

**Letterboxd**
4. *"Letterboxd quote."* — @username

Pick a number — paste a trim — or skip.
```

- Group quotes from the same outlet together
- Mark the top-ranked quote `▶` with a brief note (one phrase: "specific language", "punchy fragment", etc.)
- All quote text in *italics*
- Critic name after em-dash
- No ✓/✗ on every quote — only the `▶` pick gets a note

**4. Wait for user response**

- Number → use that quote verbatim
- Trimmed text → **that trimmed text IS the final version** (never revert to original)
- "skip" → move on

**4b. Verify the review URL** (for each chosen quote that has a `review_url`)

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import sys
sys.path.insert(0, '.')
from gemini_scraper.pull_quotes import verify_quote_url
result = verify_quote_url('REVIEW_URL', 'MOVIE_TITLE', 'CRITIC_NAME')
print(result)
"
```

- `ok` → proceed silently
- `bad_link` → show inline before saving: `⚠ Review link doesn't appear to be this movie/critic ([url]) — saving quote without URL. Say "keep link" to save it anyway.` Then save with `review_url: null` unless user says "keep link"
- `error` → show: `⚠ Review link couldn't be loaded ([url]) — saving without URL.` Save with `review_url: null`
- `no_url` → proceed silently

Run this for each selected quote. If the user selected multiple quotes, verify each one.

**5. Save**

Two writes required — both must happen:
- `cache/pull_quotes_combined.json`: find the quote entry (by critic + outlet), set `selected: true`, update `text` to the final version (original or trimmed). If no matching entry exists, create one.
- `data.json` `pull_quotes` array: inject the selected quote as `{text, critic, outlet, review_url}` (include `review_url` if available and verified — null if verification failed)

### Step C — Commit (once per movie, after both steps)

After both capsule and pull quote are resolved for a movie:

- If capsule only: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))`
- If pull quote only: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Pull quotes: [TITLE] APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))`
- If both: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule + pull quote: [TITLE] APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))`
- If both skipped: no commit needed, move to next movie

(`cache/*.json` files are gitignored — do not `git add` them.)

After all movies processed, mark stage `completed` in progress file.

---

## Completion

After all 3 stages, report a summary:
```
CURATION COMPLETE
- Staff picks: N added (M total)
- Sections: N overrides applied
- Capsules: N written | Pull quotes: N selected
```
