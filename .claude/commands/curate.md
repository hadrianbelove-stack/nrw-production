---
description: Curate new arrivals — staff picks, sections, pull quotes, capsules
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob
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
    "pull_quotes": "pending",
    "capsules": "pending"
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

## Stage 3: Pull Quote Curation

**Find the window**: Scan `data.json` for all movies that already have a `pull_quotes` array. Find the most recent `digital_date` among those — that's the watermark (where curation last left off). If no movies have pull quotes yet, default to 7 days ago.

**Find candidates** from `data.json` where ALL of these are true:
- `digital_date` is after the watermark AND `digital_date` is today or earlier (exclude future pre-orders)
- Movie has an `rt_score`
- Movie does NOT already have a `pull_quotes` array
- Movie is NOT a reissue/restoration (`is_restoration` flag, or title contains "Remaster"/"Restoration"/"4K", or `year` is 10+ years before current year)

If no candidates: report "No new movies need pull quotes — curated through [watermark date]." and mark stage `completed`.

If candidates exist:
1. Check `cache/pull_quotes_cache.json` for existing scraped quotes
2. Scrape any uncached movies using `GeminiPullQuoteFinder` from `gemini_scraper.pull_quotes`
3. Present each movie **one at a time, most recent first**, showing:
   - Movie title, year, RT score, digital date
   - All quotes numbered, with full text, critic name, and outlet
4. Wait for user response: numbers to select, "skip", or trimmed text (an edit)
5. **When the user shortens a quote, that trimmed text IS the final version** — they are editing
6. For reissues/restorations: only show quotes specifically about the reissue, not original-era reviews

**Key: persist to the cache FIRST, then inject — per-movie, not at the end.**

⚠️ The master list the pipeline rebuilds from is `cache/pull_quotes_combined.json`. If you only write to data.json, the quotes WILL be silently deleted on the next local `generate_data.py` run (the inject treats the cache as source of truth). So after each movie's quotes are selected/edited:

1. **Write the selections into the cache** `cache/pull_quotes_combined.json`. For each chosen quote, set `selected: true` and store the user's FINAL (edited) text under `text`. If the movie has no entry, create one: `{"title", "year", "rt_quotes": [...], "lb_quotes": []}`. If a matching quote already exists, flip it to `selected: true` and overwrite its `text` with the edit. Schema per quote: `text`/`critic`/`outlet`/`source`/`review_url`/`selected`.
2. **Then inject** the selected quotes into that movie's `pull_quotes` array in `data.json` using the same logic as `pipeline/display.py`'s `inject_selected_pull_quotes()` — so data.json and the cache always agree.
3. Commit + push: `git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Pull quotes: [TITLE] APPROVED: DELETE" && git push origin main`
   (The `cache/*.json` files are gitignored — they stay LOCAL as the source of truth and are not committed. Do not `git add` them; it's a silent no-op.)

After all movies are processed, mark stage `completed` in progress file.

---

## Stage 4: Capsule Rewrites

**Find the window**: Find the most recent `digital_date` among movies in `data.json` whose ID appears in `cache/approved_capsules.json`. That's the capsule watermark. If no approved capsules exist, default to 7 days ago.

**Find candidates** from `data.json` where ALL of these are true:
- `digital_date` is after the capsule watermark AND `digital_date` is today or earlier (exclude future pre-orders)
- Movie is NOT already in `cache/approved_capsules.json`
- Movie is NOT a reissue/restoration (`is_restoration` flag, or title contains "Remaster"/"Restoration"/"4K", or `year` is 10+ years before current year)

If no candidates: report "No new movies need capsules — curated through [watermark date]." and mark stage `completed`.

If candidates exist, process each movie **one at a time, most recent first**:
1. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "TITLE" --force --variants 3 --skip-verify`
2. Present the capsule variants in this **exact format** — always, every movie, no exceptions:
   - Three numbered variants with word counts
   - Then a **FACTOID PRIMER** section below the variants (bullet list of production facts, director quotes, BTS, festival context, distribution story)
   - Then the pick prompt: "Pick 1, 2, or 3 — paste a rewrite — or skip."
   - NEVER drop the factoid primer from the formatted message. It is the user's cheat sheet for editing.
3. Wait for user response: pick a number, provide a rewrite, or "skip"
4. **When the user provides edited text, that IS the final version** — they are editing
5. If picked/rewritten:
   1. Apply standard capsule formatting (**bold** names, *italic* titles)
   2. Write final text to `cache/rewrite.txt`
   3. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "TITLE" --file cache/rewrite.txt`
   4. Commit + push: `cd /Users/hadrianbelove/Downloads/nrw-production && git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && git push origin main`
      (Commit only `data.json`. `cache/approved_capsules.json` and `cache/capsule_cache.json` are gitignored local source-of-truth — don't `git add` them; it's a silent no-op.)

After all movies are processed, mark stage `completed` in progress file.

---

## Completion

After all 4 stages, report a summary:
```
CURATION COMPLETE
- Staff picks: N added (M total)
- Sections: N overrides applied
- Pull quotes: N movies curated
- Capsules: N movies rewritten
```
