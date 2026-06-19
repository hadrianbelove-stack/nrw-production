---
description: Curate new arrivals — staff picks, sections, slop review, pull quotes, capsules
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Curate recent arrivals. Runs 4 stages in order, each with a user prompt. **State-based and cumulative** — every run shows everything from the **last 7 days** that still needs work (slop unconfirmed / no capsule / no quotes), newest first. There are no "sessions" to resume or finish: skip as many days as you want and the next run simply shows whatever is still outstanding in the window. Nothing goes stale.

**Rhythm (user preference):** always curate **slop films too** — never skip or batch-drop them. Go **straight through from #1** in queue order unless the user redirects. In Stage 4, present each film's **capsule and pull quotes together** (back-to-back, same film), then move to the next — not as separate passes across all films.

## Before You Start — pull latest

The daily CI rewrites `data.json` every morning. Start on fresh main so your edits don't conflict:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git pull origin main
```

If any `git push` in this session is rejected (CI or another writer pushed mid-session), run `git pull --rebase origin main` and push again — never resolve a data.json merge by hand (`--ours`/`--theirs` loses transitions; see CLAUDE.md).

## The model — state-based, no sessions

There is **no resume logic and no session/progress file**. Each run rebuilds everything from current state, so a film stays in the queue until it is actually handled — no matter how many days you skip. The rolling window is the **last 7 days** of `digital_date` (the 90-day wall is the hard ceiling). Every stage drains as it's handled, so a film is shown **once** and then not re-shown:

- **Stage 1 (Selects)** operates on in-window arrivals **not yet marked `selects`** in `admin/curate_reviewed.json`. Replying (picks *or* "skip") marks every film shown, so the queue drains.
- **Stage 2 (Sections)** operates on in-window arrivals **not yet marked `sections`** in `admin/curate_reviewed.json`. Confirming ("looks good" or changes) marks every film shown, so the queue drains.
- **Stage 3 (Slop)** operates on in-window films where `_is_slop_guess == True` (unconfirmed). Confirming clears the flag, so the queue drains.
- **Stage 4 (Capsule + Quotes)** operates on in-window films missing a capsule (`approved_capsules.json`) or missing a `pull_quotes` key.

**`admin/curate_reviewed.json`** is the watermark for Stages 1 and 2 (which write nothing per-film on the wall otherwise). It maps `str(movie_id)` → which stages are signed off, e.g. `{"1398655": {"selects": "2026-06-18", "sections": "2026-06-18"}}`. Marking a film as reviewed for a stage = recording the date under its id. A genuinely new arrival has no entry and still appears.

To change the window, edit `WINDOW_DAYS` below.

## Candidate List (shared by Stages 1, 2, and 3)

Run this script to build the candidate list. Stages 1, 2, and 3 operate on this exact output — do not re-derive it:

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta

WINDOW_DAYS = 7

data = json.load(open('data.json'))
today = str(date.today())
from_date = str(date.today() - timedelta(days=WINDOW_DAYS))

current_year = date.today().year
candidates = []
for m in data['movies']:
    dd = m.get('digital_date', '')
    if not (from_date <= dd <= today):
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
print(f'{len(candidates)} candidate(s) in the last {WINDOW_DAYS} days (since {from_date}):')
for i, (dd, mid, title, year, rt, mc, svc) in enumerate(candidates, 1):
    print(f'  {i}. {title} ({year}) — RT:{rt} | MC:{mc} | {svc}  [id:{mid}]')
"
```

If the output shows 0 candidates, report "No arrivals in the last 7 days to curate" and stop.

**Note**: Stage 4 (Per-Movie Curation) re-derives its own list from current state (capsule / pull-quote presence) within the same 7-day window — see that stage.

---

## Stage 1: Selects (formerly "Staff Picks" — file is still admin/staff_picks.json)

**Filter first:** show only candidates **not yet marked `selects`** in `admin/curate_reviewed.json`. This script prints the Stage 1 list, already filtered and re-numbered for this run:

```bash
/usr/bin/python3 -c "
import json, os
from datetime import date, timedelta
WINDOW_DAYS = 7
data = json.load(open('data.json'))
today = str(date.today()); from_date = str(date.today() - timedelta(days=WINDOW_DAYS))
cy = date.today().year
rev = json.load(open('admin/curate_reviewed.json')) if os.path.exists('admin/curate_reviewed.json') else {}
rows = []
for m in data['movies']:
    dd = m.get('digital_date','')
    if not (from_date <= dd <= today): continue
    if m.get('filters',{}).get('is_restoration'): continue
    t = m.get('title',''); y = m.get('year',0) or 0
    if any(k in t for k in ('Remaster','Restoration','4K')) or (y and cy-int(y)>=10): continue
    if 'selects' in rev.get(str(m.get('id')), {}): continue   # already reviewed
    L = m.get('links',{})
    rows.append((dd, m.get('id'), t, m.get('year','?'), m.get('rt_score') or '--',
                 m.get('metacritic_score') or '--', L.get('wikipedia','') or '',
                 L.get('trailer_hosted','') or L.get('trailer','') or ''))
rows.sort(key=lambda x: x[0], reverse=True)
print(f'Stage 1 Selects — {len(rows)} unreviewed candidate(s):')
for i,(dd,mid,t,y,rt,mc,w,tr) in enumerate(rows,1):
    print(f'{i}|||{t}|||{y}|||{rt}|||{mc}|||{w}|||{tr}|||{mid}')
"
```

If the script prints 0 candidates, report "Selects: all caught up" and move to Stage 2. Otherwise show a numbered table of the remaining candidates, then recommend 2–4 picks with brief reasoning.

```
SELECTS — which movies are you vouching for?

| # | Title (Year) | RT | MC | Trailer |
|---|---|---|---|---|
| 1 | [Title (Year)](https://en.wikipedia.org/wiki/...) | 85% | 72 | [▶](trailer-url) |
| 2 | Title (Year) | -- | -- | [▶](trailer-url) |
| 3 | [Title (Year)](https://en.wikipedia.org/wiki/...) | 92% | 80 | — |

★ Recommended: 1 (strong RT/MC), 3 (RT 92%, critical darling)

Reply with numbers (e.g. "1, 7, 10") or "skip" to skip.
```

For each movie row show: title (hyperlinked to its Wikipedia page from `movie.links.wikipedia` when one exists; plain text if absent), year, RT score (or `--`), Metacritic score (or `--`), and a Trailer link (`[▶](url)` using `movie.links.trailer_hosted`, falling back to `movie.links.trailer`; `—` if neither exists). Do not show watch-link services in this table.

**Recommendations**: After the list, add a `★ Recommended:` line with 2–4 suggested picks and a short reason for each (scores, notable director, awards, distributor quality signal, etc.). Base this only on data already in data.json — do not web search at this step. If nothing stands out, say so.

**On user reply:**
- Parse the numbers, map to movie IDs
- Read `admin/staff_picks.json`, add new IDs (avoid duplicates), write back
- **Mark every film shown this run** (picks *and* non-picks — "skip" still counts as reviewed) as `selects` in `admin/curate_reviewed.json`, using the script below. This is what drains the queue so these films aren't re-shown next run.
- Commit + push: `git add admin/staff_picks.json admin/curate_reviewed.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Staff picks updated APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))`

```bash
# Pass the str(id) of every film shown in the Stage 1 table (space-separated).
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, os, sys
from datetime import date
path = 'admin/curate_reviewed.json'
rev = json.load(open(path)) if os.path.exists(path) else {}
for mid in sys.argv[1:]:
    rev.setdefault(mid, {})['selects'] = str(date.today())
json.dump(rev, open(path,'w'), indent=2)
print(f'Marked {len(sys.argv)-1} film(s) selects-reviewed')
" ID1 ID2 ID3 ...
```

---

## Stage 2: Section Review

**Filter first:** show only candidates **not yet marked `sections`** in `admin/curate_reviewed.json` (same pattern as Stage 1 — swap `'selects'` for `'sections'` in the filter script). If 0 remain, report "Sections: all caught up" and move to Stage 3. Re-number the rest `1…N` for this run.

Show each remaining candidate with its auto-detected filters (from TMDB genres, language, and distributor data). Review and correct any misses.

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

Show as human-readable names. If no filters are active, show "(none)". Selects is handled in Stage 1 — omit it here.

**On user reply:**
- For studio/indie overrides: read `admin/category_overrides.json`, add entries, write back
- For restoration overrides: read `admin/restorations.json`, add IDs, write back
- **Mark every film shown this run** (changes *and* unchanged — "looks good" still counts as reviewed) as `sections` in `admin/curate_reviewed.json` (use the Stage 1 marking script, but set the `'sections'` key instead of `'selects'`). This drains the queue.
- Commit + push: include `admin/curate_reviewed.json` in the `git add` along with any override file changes.

**Note**: All filters are auto-detected from TMDB data — genres (Comedy, Horror, Action, Thriller), language (Foreign), and distributor rules (Indie, Studio, Documentary). To improve detection logic (e.g. add indie distributor rules), update the pipeline code — not this command.

---

## Stage 3: Slop Review

Show all candidates in a table so the user can confirm or correct the auto-classifier's slop determinations.

Build the table by reading `movie.is_slop`, `movie._is_slop_guess`, and `movie._slop_reason` from `data.json` for each candidate. Show **all candidates** — not just the ones flagged as slop — so the user can catch false negatives (real movies misclassified as not-slop, or vice versa).

```
SLOP REVIEW — confirm or correct auto-classifications

| # | Title (Year) | Slop? | RT | IMDb | Links | Why |
|---|--------------|-------|----|------|-------|-----|
| 1 | [Title (Year)](imdb-url) | ✅ Not slop | 85% | 7.2 | [RT](url) · [LB](url) | score:1(good_imdb) |
| 2 | [Title (Year)](imdb-url) | 🗑 SLOP (auto) | -- | -- | [LB](url) | score:5(no_wiki,no_rt) |

"auto" = classifier made the call. Reply with overrides (e.g. "2: not slop; 5: slop") or "looks good" to confirm all.
```

**Table column rules:**
- `Title` — hyperlink to the movie's IMDb page (`movie.links.imdb`); plain text if absent
- `Slop?` column:
  - `is_slop=True` + `_is_slop_guess=True` → `🗑 SLOP (auto)`
  - `is_slop=True` + `_is_slop_guess=False` → `🗑 SLOP (manual)`
  - `is_slop=False` → `✅ Not slop`
- `RT` / `IMDb` — `movie.rt_score` and `movie.imdb_rating` (`--` if absent)
- `Links` — clickable [RT](movie.links.rt) and [LB](movie.links.letterboxd) when present, so the user can identity-check each film
- `Why` column: show `_slop_reason` if present; otherwise show RT/MC scores or "no classifier signal"

**Flag contradictions** below the table: any slop-flagged movie that is also a **Select** — a film the user explicitly vouched for but the default slop-free view filters out. Do **not** flag capsules or pull quotes as contradictions: every film gets a capsule and quotes, so they carry no signal about slop and are irrelevant here. (All movies are on the site regardless of slop flag — the toggle is a view mode, never removal.)

**On user reply:**

For each override the user specifies:

1. **Update `data.json`** — set `is_slop` and clear `_is_slop_guess`:
```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys
title, is_slop_val = sys.argv[1], sys.argv[2] == 'true'
with open('data.json') as f:
    data = json.load(f)
for m in data.get('movies', []):
    if m.get('title', '').lower() == title.lower():
        m['is_slop'] = is_slop_val
        m['_is_slop_guess'] = False
        break
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('done')
" "MOVIE_TITLE" "true_or_false"
```

2. **Update `scripts/slop_classifier.py` MANUAL_OVERRIDES** — add a durable entry so rebuilds don't revert it. Read the file, find the `MANUAL_OVERRIDES` dict (around line 22), and add `numeric_int_id: True/False,  # Title`. The numeric ID must be an integer (not a string) — read `movie.id` from data.json and cast to int.

3. Commit + push after all overrides applied:
```bash
git add data.json scripts/slop_classifier.py && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Slop review APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))
```

If "looks good" with no changes: no commit needed.

---

## Stage 4: Per-Movie Curation (Capsule + Pull Quotes together)

Capsules and pull quotes are done together, movie by movie — not as separate passes.

**Find candidates** — state-based, same 7-day window as Stages 1–3 (no watermark). Build the union of:
- Movies needing a capsule: `digital_date` within the last 7 days, **not** in `cache/approved_capsules.json` by title, not a restoration
- Movies needing pull quotes: `digital_date` within the last 7 days, **no** `pull_quotes` **key** in `data.json` (check key presence — an empty array `[]` means "reviewed and skipped", not "needs quotes"), not a restoration

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta
WINDOW_DAYS = 7
data = json.load(open('data.json'))
caps = json.load(open('cache/approved_capsules.json'))
ct = set((c.get('title','') if isinstance(c,dict) else '').lower() for c in caps)
today = str(date.today()); from_date = str(date.today() - timedelta(days=WINDOW_DAYS))
rows = []
for m in data['movies']:
    dd = m.get('digital_date','') or ''
    if not (from_date <= dd <= today): continue
    if m.get('filters',{}).get('is_restoration'): continue
    needs = []
    if m.get('title','').lower() not in ct: needs.append('capsule')
    if 'pull_quotes' not in m: needs.append('quotes')
    if not needs: continue
    rows.append((dd, str(m.get('id')), m.get('title',''), m.get('year','?'), '+'.join(needs), m.get('rt_score') or '--'))
rows.sort(key=lambda r: r[0], reverse=True)
print(f'STAGE 4 — {len(rows)} movie(s) to curate')
for i,(dd,mid,t,y,needs,rt) in enumerate(rows,1):
    print(f'  #{i}  {t} ({y})  RT {rt}  — {needs}  [id:{mid}]')
"
```

This list is **rebuilt fresh every run** from current state — there is no persisted queue file. Number the films `#1 … #N` in the printed order for this run only; if the user redirects ("go to #5", "skip to Kraken"), continue from there. A film that's already been handled simply won't appear next run.

Print the full queue once before starting, as a numbered checklist with the total. For each film show: **title hyperlinked to its Wikipedia page (`movie.links.wikipedia`) when one exists** (plain text if absent), **a trailer hyperlink (`movie.links.trailer_hosted`, falling back to `movie.links.trailer`)**, and the RT score so standouts are visible.

```
STAGE 4 — 35 movies to curate
  #1  [The Jealous Bride (2026)](wiki-url) · [▶ trailer](trailer-url)   RT --   — capsule+quotes
  #2  [Double Happiness (2026)](wiki-url) · [▶ trailer](trailer-url)    RT 73%  — capsule+quotes
  ...
  #35 Wetiko (2025) · [▶ trailer](trailer-url)                         RT --   — quotes   (no wiki page)
```

If no candidates for either: report "nothing needs capsules or quotes in the last 7 days" and finish.

**For each movie, in order — always lead with its queue position:**

Every time you present a movie (capsule variants *and* pull quotes), title the section **`#N of TOTAL — Title (Year)`** so the user always sees where they are. The user may redirect at any point — "go to #5", "jump to #5", "skip to Kraken" — in which case continue from that index. Progress isn't tracked in a file: a handled film (capsule written / `pull_quotes` key set) just won't reappear when the list is rebuilt next run.

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

**⚙ Configuration** *(change these to adjust output)*
- Letterboxd quotes to show: **10** (max; show all if 10 or fewer)

**1. Get the quotes — read from cache**

The morning launchagent (`scripts/batch_pull_quotes.py`) scrapes pull quotes for all new arrivals before curation runs. Read from `cache/pull_quotes_combined.json` using the cache key `"{title}_{year}"`.

- If the movie **has quotes in cache**: use them. Do not re-scrape.
- If the movie is **absent from cache entirely**: show this flag and skip pull quotes for this movie:
  `⚠ No pull quotes in cache — morning batch may have missed this movie. Check Concerns in tomorrow's launchagent report.`

Do not re-scrape. The morning batch is the canonical source.

**2. Present — critics first, Letterboxd after**

Show **all** RT/critic quotes, then up to **10** Letterboxd quotes (the Configuration number — show all if 10 or fewer). No pre-filtering, no reordering, no ranking markers. For spoiler-protected reviews (text starts with "This review may contain spoilers"), show the review URL as a clickable link so the user can read it: `— @username → [read review](url)`. Format exactly:

```
[Film Title] PULL QUOTES

**Outlet Name**
1. *"Quote text here."* — Critic Name, Outlet Name

**Another Outlet**
2. *"Another quote."* — Critic Name, Another Outlet
3. *"Third quote from same outlet."* — Critic Name, Another Outlet

**Letterboxd**
4. *"Letterboxd quote."* — @username
5. *"Another Letterboxd quote."* — @username

Pick a number — paste a trim — or skip.
```

- Group RT/critic quotes by outlet; maintain cache order within each section
- Each RT/critic quote line must show both critic name AND outlet: `— Critic Name, Outlet`
- Letterboxd quotes: username only (`— @username`), no outlet suffix needed
- Letterboxd section always comes last
- All quote text in *italics*
- **Wrap each quote to ~72 columns** — print via a script using `textwrap.fill` with a hanging indent and the attribution on its own line. The user reads this in the IDE's Bash-output side panel, which does **not** soft-wrap, so long single lines force horizontal scrolling. Use a single `@` for Letterboxd usernames (strip any leading `@` from the cache).

**3. Wait for user response**

- Number → use that quote verbatim
- Pasted text → **that text IS the final version** (never revert to original)
- "skip" → write `pull_quotes: []` (empty array) to `data.json` for this movie, then commit: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Pull quotes: [TITLE] skipped APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))`. An empty array signals "reviewed, nothing selected" and prevents this film from reappearing in the queue. **Remember:** `pull_quotes: []` and no `pull_quotes` key are NOT the same. `[]` = the user reviewed this movie and rejected everything — do not re-queue it. No key = never been through the queue.

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
- If pull quotes skipped (capsule also skipped or not needed): commit the empty `pull_quotes: []` written in Step B rule 3 above

(`cache/*.json` files are gitignored — do not `git add` them.)

---

## Completion

After all 4 stages, report a summary:
```
CURATION COMPLETE
- Staff picks: N added (M total)
- Sections: N overrides applied
- Slop review: N overrides (N→slop, N→not slop)
- Capsules: N written | Pull quotes: N selected
```
