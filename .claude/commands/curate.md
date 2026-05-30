---
description: Curate new arrivals — staff picks, sections, pull quotes, capsules
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Curate movies added since last session. Runs 4 stages in order, each with a user prompt. Resumable — if interrupted, re-running picks up where you left off.

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

## Candidate List (shared by all stages)

Load movies from `data.json` where `digital_date` is after the session timestamp in `.claude/last_nrw_session.json` AND `digital_date` is today or earlier (exclude future pre-orders). If the session file doesn't exist, default to 7 days ago. Exclude reissues/restorations (`is_restoration` flag, or title contains "Remaster"/"Restoration"/"4K", or `year` is 10+ years before current year).

Sort by `digital_date` descending (most recent first).

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
- Commit + push: `git add admin/staff_picks.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Staff picks updated APPROVED: DELETE" && git push origin main`
- Mark stage `completed` in progress file

---

## Stage 2: Section Review

Show each candidate with its **pipeline-assigned categories** (from `data.json` `categories` object). This is what the pipeline already detected — the user reviews and corrects.

```
SECTIONS — review what the pipeline assigned

 1. Title (Year) — Studio
 2. Title (Year) — Foreign, Documentary
 3. Title (Year) — Indie
 4. Title (Year) — (none)
 ...

Reply with changes (e.g. "2: remove foreign; 4: add indie") or "looks good" to confirm all.
```

For each movie, list all active categories from its `categories` object (is_studio, is_indie, is_foreign, is_documentary, is_exploitation, is_virtual_screening, is_restoration, is_series). Show as human-readable names. If no categories are set, show "(none)".

**On user reply:**
- For studio/indie overrides: read `admin/category_overrides.json`, add entries, write back
- For restoration overrides: read `admin/restorations.json`, add IDs, write back
- Commit + push any override file changes
- Mark stage `completed` in progress file

**Note**: Most categories (foreign, documentary, exploitation, virtual screening, miniseries) are auto-detected by the pipeline in `pipeline/display.py` using `category_config.json`. To improve detection logic (e.g. add indie distributor rules), update the pipeline code — not this command.

---

## Stage 3: Per-Movie Curation (Capsule + Pull Quotes together)

Capsules and pull quotes are done together, movie by movie — not as separate passes.

**Find candidates**: Take the union of:
- Movies needing a capsule: `digital_date` > capsule watermark (most recent `digital_date` among movies in `cache/approved_capsules.json`), not already approved, not a restoration
- Movies needing pull quotes: `digital_date` > pull quote watermark (most recent `digital_date` among movies with a `pull_quotes` array in `data.json`), not already having `pull_quotes`, not a restoration

Merge into one list, deduplicated, sorted by `digital_date` descending. For each movie, track which work it needs: capsule, quotes, or both.

If no candidates for either: report through-dates and mark stage `completed`.

**For each movie, in order:**

### Step A — Capsule (if needed)

1. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "TITLE" --force --variants 3 --skip-verify`
2. Present in this **exact format** — always, no exceptions:
   - Three numbered variants with word counts (full text, not summaries)
   - **FACTOID PRIMER** section below (full bullet list — never summarize or abbreviate it)
   - **SUGGESTED LINKS** section below the primer (see below)
   - Pick prompt: "Pick 1, 2, or 3 — paste a rewrite — or skip."
3. Wait for user response. **When user provides edited text, that IS the final version.**
4. If picked/rewritten:
   1. Apply standard formatting (**bold** names, *italic* titles)
   2. **Pre-embed Wikipedia links** into the chosen text (see Step A-Links below), then confirm with user before continuing
   3. Write final approved text to `cache/rewrite.txt`
   4. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "TITLE" --file cache/rewrite.txt`
   5. Write cast wiki links to data.json (see Step A-Links below)

### Step A-Links — Wikipedia Links (runs inside Step A)

**Generating SUGGESTED LINKS (shown below the factoid primer):**

Identify up to 5 linkable entities for this film:
- **Always**: WebSearch the top 3 cast members from `movie.crew.cast` for their Wikipedia pages
- **Also**: up to 3 notable historical figures, events, movements, or organizations referenced by the film. Skip the director (already linked in the site header).

Present as:
```
**SUGGESTED LINKS**
- [Ellie Bamber](https://en.wikipedia.org/wiki/Ellie_Bamber) — cast
- [Derek Jacobi](https://en.wikipedia.org/wiki/Derek_Jacobi) — cast
- [Lucian Freud](https://en.wikipedia.org/wiki/Lucian_Freud) — painter, subject of film
```

If a cast member has no Wikipedia page, skip them silently.

**Pre-embedding links (after user picks a variant):**

Once the user picks a variant or provides a rewrite:
1. Embed ALL suggested links into the text:
   - Entity name appears as `**bold**` → change to `**[Name](url)**`
   - Entity name appears as plain text → change to `[Name](url)`
   - Entity name not in the capsule text → skip (will still be saved to cast_wiki for the metadata line)
2. Show the modified capsule with links visible in the markdown
3. Ask: "Approve with these links — or say 'remove [Name]' to drop any."
4. If user removes any: strip that link, show updated capsule again
5. When user approves: this is the final text — proceed to write cache/rewrite.txt

**Saving cast wiki links (after approve script runs):**

For each cast member that had a Wikipedia URL in SUGGESTED LINKS, write to `movie.links.cast_wiki`:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys
title, cast_wiki_json = sys.argv[1], sys.argv[2]
cast_wiki = json.loads(cast_wiki_json)
data = json.load(open('data.json'))
for m in data['movies']:
    if m.get('title', '').lower() == title.lower():
        m.setdefault('links', {})
        m['links']['cast_wiki'] = cast_wiki
        break
json.dump(data, open('data.json', 'w'), indent=2, ensure_ascii=False)
" "MOVIE_TITLE" '{"Ellie Bamber": "https://...", "Derek Jacobi": "https://..."}'
```

Only include cast members (not historical figures or events — those are for capsule text only). Wikipedia URLs with parentheses: encode `(` as `%28` and `)` as `%29`.

### Step B — Pull Quotes (immediately after capsule, same movie)

Show pull quotes for this movie right after the capsule is resolved (picked, skipped, or not needed).

**1. Get the quotes — always scrape fresh**

Run the validated scraper (not just cache):

```python
from gemini_scraper.pull_quotes import GeminiPullQuoteFinder
finder = GeminiPullQuoteFinder()
quotes = finder.find_pull_quotes(
    title="TITLE", year=YEAR, director="DIRECTOR",
    num_quotes=10, deep_read=True,
    rt_url=movie.get('links',{}).get('rt'),
    mc_url=movie.get('links',{}).get('mc')
)
```

After scraping, update `cache/pull_quotes_combined.json` with any new quotes found (merge, don't overwrite existing selected quotes).

**Filter noise before presenting**: drop any quotes from YouTube, generic news blurbs (Mashable "what's new this week" type), or press releases. Keep critics, publications, and Letterboxd.

**2. Rank by taste profile**

Read `cache/taste_profile_pullquotes.json`. Rank all quotes from best match to worst. The profile consistently shows:
- **Prefers**: specific vivid language, punchy fragments, wit, emotional precision
- **Avoids**: vague generic praise ("brilliant", "stunning"), academic jargon, plot summary masquerading as criticism, quotes that repeat the movie title
- Top critics and known outlets rank higher when quotes are otherwise equal
- A short sharp fragment trimmed from a longer quote can outperform a full sentence

**3. Present — grouped by outlet, full list**

Show all usable quotes (up to ~12), grouped by outlet. Format exactly like this:

```
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

**5. Save**

Two writes required — both must happen:
- `cache/pull_quotes_combined.json`: find the quote entry (by critic + outlet), set `selected: true`, update `text` to the final version (original or trimmed). If no matching entry exists, create one.
- `data.json` `pull_quotes` array: inject the selected quote as `{text, critic, outlet, review_url}` (include `review_url` if available in the cache entry)

### Step C — Commit (once per movie, after both steps)

After both capsule and pull quote are resolved for a movie:

- If capsule only: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && git push origin main`
- If pull quote only: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Pull quotes: [TITLE] APPROVED: DELETE" && git push origin main`
- If both: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule + pull quote: [TITLE] APPROVED: DELETE" && git push origin main`
- If both skipped: no commit needed, move to next movie

(`cache/*.json` files are gitignored — do not `git add` them.)

After all movies processed, mark stage `completed` in progress file.

---

## Completion

After all 4 stages, report a summary:
```
CURATION COMPLETE
- Staff picks: N added (M total)
- Sections: N overrides applied
- Capsules: N written | Pull quotes: N selected
```
