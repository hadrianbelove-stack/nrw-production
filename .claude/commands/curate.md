---
description: Curate new arrivals — staff picks, sections, slop review, pull quotes, capsules
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

# /curate

**Flow:** Stage 0 Reissues → 1 Selects → 2 Sections → 3 Slop → 4 Capsule+Quotes. Run in order.

**Rhythm (user preference):** curate **slop films too** — never skip or batch-drop. Go **straight through from #1** in queue order unless the user redirects. In Stage 4, present each film's **capsule and pull quotes together in one message**, one film at a time — never capsule-first-then-quotes, never as separate passes.

**State-based, no sessions.** Each run rebuilds from current state. Window = **last 7 days** of `digital_date` (90-day wall is the hard ceiling). Every stage **drains** as films are handled, so each film is shown once then disappears — skip as many days as you want, nothing goes stale. There is no resume logic and no progress file. To change the window, pass `--window N` to the list script.

**How a stage drains:**
- Stages **1/2/3** mark films in `admin/curate_reviewed.json` (the watermark) — see *Shared blocks → List + drain*.
- Stage **0** drains its own queue `admin/reissue_candidates.json` (confirm/reject flips status).
- Stage **4** has no watermark — a film drains when it gets a capsule (`cache/approved_capsules.json`) and a `pull_quotes` key in data.json.

**Invocation:**
- `/curate` (no arg) → all five stages in order.
- `/curate N` / `N-M` / `N,M,…` (e.g. `3`, `1-3`, `4,6,9`) → **skip Stages 0–3, go straight to Stage 4** for those queue positions. Lets you run parallel windows. See *Stage 4 → Parallel-window slice*.

---

## Shared blocks

Referenced by name throughout. Defined once here.

### COMMIT(files, "msg")
```bash
git add <files> && NRW_ALLOW_DATA_COMMIT=1 git commit -m "<msg> APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && NRW_ALLOW_DATA_COMMIT=1 git push origin main))
```
`APPROVED: DELETE` clears the line-removal commit hook. If push is rejected, the rebase branch handles it — **never** resolve a data.json conflict by hand (`--ours`/`--theirs` loses transitions; see CLAUDE.md). `cache/*.json` is gitignored — never `git add` it.

### List + drain (`scripts/curate_list.py`)
One script builds every stage's list (filter + window + watermark live here, not in this file). Output is pipe-delimited rows (`i|||field|||…|||id`) after a one-line header — render as that stage's TEMPLATE.
```bash
/usr/bin/python3 scripts/curate_list.py --stage selects|sections|slop|capsule
```
If a stage prints 0 rows, report "<stage>: all caught up" and move to the next stage.

**Drain (Stages 1/2/3 only):** after the user replies, mark **every film shown this run** — picks *and* skips, overrides *and* "looks good" all count as reviewed. This is what stops re-showing them next run:
```bash
/usr/bin/python3 scripts/curate_list.py --mark selects|sections|slop ID1 ID2 ...
```
(`curate_reviewed.json` maps `str(id)` → `{"selects": date, "sections": date, "slop": date}`. A new arrival has no entry, so it still appears.)

### Link rules (every table)
- **Title** → hyperlink to `movie.links.wikipedia` when present (Stage 3 uses `movie.links.imdb` instead); plain text if absent.
- **Trailer** → `[▶](url)` using `movie.links.trailer_hosted`, falling back to `movie.links.trailer`; `—` if neither.
- The list script already emits the wiki/imdb/trailer URLs per row — use them, don't re-derive.

### Templates
All table/output mockups live in **`.claude/curate_templates.md`** (loaded on demand, not inline). **Read that file once** when you first need to present a table this run, then render the block named in each stage (e.g. *Templates → Selects table*). Slice runs and "all caught up" stages that present nothing never need to read it.

### Before you start — pull latest
The daily CI rewrites `data.json` every morning. Start on fresh main:
```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git pull origin main
```

---

## Stage 0 — Confirm Reissues

Old films (original release 10+ years ago) with a new theatrical 4K restoration, anniversary re-release, festival revival, or alt cut. Intake **Pass D** holds them in `admin/reissue_candidates.json`; they reach the wall only when confirmed here. Independent of the 7-day window and the watermark — drains as candidates are confirmed/rejected.

**1 — research stragglers** (CI already researched the rest in orchestrator Phase 1.2; usually a fast no-op):
```bash
cd /Users/hadrianbelove/Downloads/nrw-production && GEMINI_API_KEY=$(grep -rhoE "GEMINI_API_KEY[=:][^ ]*" .env* 2>/dev/null | head -1 | sed -E 's/.*[=:]//') /usr/bin/python3 pipeline/reissue_research.py
```

**2 — show the table** (already link-dense and sorted 🟢 likely → 🟡 maybe → ⚪ unlikely; ⭐DIST = known reissue label like Kino Lorber/Janus/Criterion):
```bash
/usr/bin/python3 scripts/reissue_table.py
```
If it prints "all caught up", move to Stage 1. Otherwise present it as-is and recommend the 🟢/⭐DIST rows. The user replies with row numbers to confirm (and any label edits).

**3 — apply the decision:**
```bash
# Example: "confirm 1 and 3, custom label on 3"
/usr/bin/python3 scripts/confirm_reissue.py --confirm 1,3 --label "3=New 4K Restoration" --drain
```
- `--confirm N[,N]` adds those films to the **wall now** (like `/add-movie`: `status=available`, `_added_manually=True`, `_reissue` + badge label), **auto-enriches** (RT/Wikipedia/trailer/links), and marks them **not-slop**. Theatrical-only reissues stay on the wall because `_added_manually` skips the JustWatch revert.
- `--label "N=Custom"` overrides the suggested badge for a confirmed row.
- `--drain` marks every other shown candidate rejected. Omit to leave undecided ones pending.
- `--no-enrich` only for a large batch where you want to defer enrichment (rare).

A confirmed reissue then behaves like a normal new arrival — it flows through Stage 4 like any wall film (only specials: its Reissues section + the not-slop lock). Reissues dated outside the 7-day window won't auto-appear in Stage 4 — curate those on demand with `/capsule` and `/enrich`.

**4 — commit.** `data.json` + `movie_tracking.json` are CI-authoritative — first confirm your change is purely additive (the N reissues, losing no CI discoveries/transitions), then:
> COMMIT(`admin/reissue_candidates.json admin/reissue_labels.json movie_tracking.json data.json`, `"Confirm Reissues: N added, M rejected"`)

---

## Stage 1 — Selects
*(formerly "Staff Picks" — file is still `admin/staff_picks.json`)*

1. Build the list: `curate_list.py --stage selects` (see *Shared blocks*). 0 rows → "Selects: all caught up", go to Stage 2.
   - The rows carry a **Buzz** score (0–100). If Buzz shows `--` for the candidates, the notability dossier is stale/missing — run `python3 scripts/notability_sandbox.py` first, then rebuild the list so Buzz + the Recommended facts are available.
2. Render as **Templates → Selects table**, **sorted by notability** (Buzz + acclaim, descending). Fill the `★ Recommended:` block from the dossier (`cache/notability_dossier_SANDBOX.json` → `films[].acclaim` + `explanation`): the genuine finds, **notable facts only** (festivals, named awards, distributor/director), hyperlinking recognizable named entities to Wikipedia — **no plot, no editorializing**. The dossier already web-searched, so **do not hand-search here**. If nothing stands out, say so.
3. **On reply** (numbers, or "skip"):
   - Read `admin/staff_picks.json`, add the picked IDs (no duplicates), write back.
   - **Drain:** `curate_list.py --mark selects <every shown id>` (picks *and* skips).
   - COMMIT(`admin/staff_picks.json admin/curate_reviewed.json`, `"Staff picks updated"`)

---

## Stage 2 — Sections

1. Build the list: `curate_list.py --stage sections`. 0 rows → "Sections: all caught up", go to Stage 3. The `Sections` column is computed by the script from `movie.filters` (Indie/Foreign/Documentary/Virtual Screening/Restoration) and `movie.genres` (Horror/Action/Comedy/Family/Thriller); `(none)` if no filters. Selects is handled in Stage 1 — not shown here.
2. Render as **Templates → Sections table**.
3. **On reply** (changes, or "looks good"):
   - Studio/indie overrides → read `admin/category_overrides.json`, add entries, write back.
   - Restoration overrides → read `admin/restorations.json`, add IDs, write back.
   - **Drain:** `curate_list.py --mark sections <every shown id>`.
   - COMMIT(the override file(s) changed `+ admin/curate_reviewed.json`, `"Sections updated"`)

**Note:** filters are auto-detected from TMDB (genres, language, distributor rules). To improve detection logic (e.g. new indie-distributor rules), update the **pipeline code** — not this command.

---

## Stage 3 — Slop

The false-negative pass, done **once per film**. Shows **all** remaining candidates (not just slop-flagged ones) so the user can catch misclassifications either way. All films stay on the site regardless — the slop toggle is a view mode, never removal.

1. Build the list: `curate_list.py --stage slop`. 0 rows → "Slop: all caught up", go to Stage 4. The script computes the `Slop?` and `Why` columns (`is_slop`/`_is_slop_guess` → `🗑 SLOP (auto)` / `🗑 SLOP (manual)` / `✅ Not slop`; `Why` = `_slop_reason`, or scores, or "no classifier signal").
2. Render as **Templates → Slop table**. Below it, **flag contradictions:** any slop-flagged film that is also a **Select** (vouched-for but hidden by the default slop-free view). Do **not** flag capsules/quotes — every film has them, so they carry no slop signal.
3. **On reply** (overrides, or "looks good"):
   - **For each override** — write the durable verdict to `admin/overrides.json` (the
     single override store, applied last in pipeline/display.py so rebuilds never
     revert it) and to data.json for immediate effect. Key by **ID**:
     ```bash
     cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
     import json, sys
     mid, is_slop_val = sys.argv[1], sys.argv[2] == 'true'
     ov = json.load(open('admin/overrides.json'))
     ov.setdefault(mid, {}).setdefault('set', {})['is_slop'] = is_slop_val
     json.dump(ov, open('admin/overrides.json','w'), indent=2, ensure_ascii=False)
     data = json.load(open('data.json'))
     for m in data['movies']:
         if str(m.get('id')) == mid: m['is_slop'] = is_slop_val; break
     json.dump(data, open('data.json','w'), indent=2, ensure_ascii=False)
     print('done')
     " "MOVIE_ID" "true_or_false"
     ```
   - **Drain:** `curate_list.py --mark slop <every shown id>` — even on "looks good" with no changes, so they don't re-show.
   - COMMIT(`data.json admin/overrides.json admin/curate_reviewed.json`, `"Slop review"`)

---

## Stage 4 — Capsule + Pull Quotes

Capsule and quotes done **together, movie by movie** — not separate passes.

1. Build the list: `curate_list.py --stage capsule`. This window includes films **missing a capsule** (not in `approved_capsules.json` by title) **or** missing a `pull_quotes` key. *(Note: `pull_quotes: []` = reviewed-and-skipped, drains; **no key** = never queued. Not the same.)* 0 rows → "nothing needs capsules or quotes in the last 7 days" and finish.
2. Render the full queue as **Templates → Stage 4 queue** (numbered checklist, totals, wiki + trailer links + RT). Numbering is for this run only; if the user redirects ("go to #5", "skip to Kraken"), continue from there.
3. Work each film in order. **Always lead with its position** — title every presentation `#N of TOTAL — Title (Year)`.

### Parallel-window slice (only when invoked with a number arg)
For `/curate 1-3`, `4,6`, etc. — Stages 0–3 were skipped. Build the queue above, keep only the requested positions, **pin them to their titles immediately**, and print **Templates → Stage 4 slice header** instead of the full checklist. From then on work by **title, not live position**, so a parallel window draining films can't shift you onto the wrong one. Skip out-of-range positions with a one-line note. Everything else below is unchanged. (Open parallel windows close together so they share one queue snapshot; use the printed titles to confirm no overlap.)

### Step A — Capsule
1. `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "TITLE" --variants 3 --skip-verify` — the nightly run pre-generates 3 variants into `cache/capsule_cache.json`, so this returns from cache instantly. Films arriving after the nightly run generate live. No `--force` (a cache hit is what makes it fast) unless deliberately regenerating.
2. **Read `.claude/commands/capsule.md` Step 2** — that file is the single source of truth for the presentation format (movie header, keyword/badge line, three variants with approach labels, FACTOID PRIMER, SUGGESTED LINKS, pick prompt). Use it exactly.
3. **Do not wait** — go straight to Step B and append this film's quotes in the *same* message. Wait for the user only after both are shown. **Edited text the user pastes IS the final version.**
4. **After the user replies** (one reply covers capsule *and* quote), if they picked/rewrote the capsule:
   1. Format: **bold** director + cast names; *italicize* other film titles in the text.
   2. Pre-embed Wikipedia links (Step A-Links), confirm with user.
   3. Write final text to `cache/rewrite.txt`.
   4. `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "TITLE" --file cache/rewrite.txt`
   5. Write cast wiki links to data.json (Step A-Links).

### Step A-Links — Wikipedia links (inside Step A)
**Pass 1 — Cast + Director (silent, auto-approved, NOT shown in SUGGESTED LINKS):** read `movie.links.cast_wiki` and `movie.links.director_wiki`; embed each wherever the name appears in the capsule. No URL → skip silently (many actors lack pages).

**Pass 2 — Other named entities (user reviews these):** non-cast/non-director people, places, movements, or works named in the capsule text (a manga creator, historical figure, referenced filmmaker — up to 3). WebSearch each for a Wikipedia page. If none exist, omit SUGGESTED LINKS entirely. Present only Pass 2, as **Templates → Suggested links**.

**Pre-embedding (after the user picks/rewrites):**
1. Scan the final text for any `**bold**` names not already listed; WebSearch each, add if found.
2. Embed all links: `**Name**` → `**[Name](url)**`; plain `Name` → `[Name](url)`; name not in text → skip (still save to cast_wiki for the metadata line).
3. Show the capsule with links visible. Ask: "Approve with these links — or say 'remove [Name]' to drop any." Strip and re-show on removal. On approval, this is final → write `cache/rewrite.txt`.

**Save cast wiki links (after the approve script runs)** — merge, don't overwrite; cast members only (not director/figures/events — those are text-only links). Encode `(`→`%28`, `)`→`%29` in URLs:
```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys
title, cast_wiki_json = sys.argv[1], sys.argv[2]
cast_wiki = json.loads(cast_wiki_json)
with open('data.json') as f: data = json.load(f)
movies = data if isinstance(data, list) else data.get('movies', [])
for m in movies:
    if m.get('title','').lower() == title.lower():
        m.setdefault('links', {})
        existing = m['links'].get('cast_wiki', {}); existing.update(cast_wiki)
        m['links']['cast_wiki'] = existing; break
with open('data.json','w') as f: json.dump(data, f, indent=2, ensure_ascii=False)
" "MOVIE_TITLE" '{\"Ellie Bamber\": \"https://...\", \"Derek Jacobi\": \"https://...\"}'
```

### Step B — Pull Quotes (SAME message as the capsule)
Append this film's quotes to the message showing its capsule variants (Step A.3) — do **not** wait for the capsule pick. User reviews both and replies at once (e.g. "capsule 2, quote 4").

**⚙ Config:** Letterboxd quotes to show = **10** (max; show all if ≤10).

1. **Read from cache** — the morning launchagent (`scripts/batch_pull_quotes.py`) scrapes all new arrivals before curation. Read `cache/pull_quotes_combined.json`, key `"{title}_{year}"`.
   - Has quotes → use them, do not re-scrape.
   - Absent entirely → show `⚠ No pull quotes in cache — morning batch may have missed this movie. Check Concerns in tomorrow's launchagent report.` and skip quotes for this film.
   - Never re-scrape; the morning batch is canonical.
2. **Present** as **Templates → Quotes block** — all RT/critic quotes (grouped by outlet, cache order) then up to 10 Letterboxd. No pre-filtering/ranking. **Wrap each quote to ~72 cols** via a `textwrap.fill` script (hanging indent, attribution on its own line) — the IDE side panel doesn't soft-wrap. Single `@` for Letterboxd usernames. Spoiler-protected reviews (text starts "This review may contain spoilers"): show `— @username → [read review](url)`.
3. **On reply** (the quote part of the joint reply):
   - Number → that quote verbatim.
   - Pasted text → **that IS the final version** (never revert to original).
   - "skip" → write `pull_quotes: []` to data.json for this film, then COMMIT(`data.json`, `"Pull quotes: [TITLE] skipped"`). `[]` = reviewed/rejected (don't re-queue); **no key** = never queued.
4. **Verify each chosen quote's `review_url`:**
   ```bash
   cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
   import sys; sys.path.insert(0, '.')
   from gemini_scraper.pull_quotes import verify_quote_url
   print(verify_quote_url('REVIEW_URL', 'MOVIE_TITLE', 'CRITIC_NAME'))
   "
   ```
   - `ok` / `no_url` → proceed silently.
   - `bad_link` → show `⚠ Review link doesn't appear to be this movie/critic ([url]) — saving quote without URL. Say "keep link" to save it anyway.` Save `review_url: null` unless user says keep.
   - `error` → show `⚠ Review link couldn't be loaded ([url]) — saving without URL.` Save `review_url: null`.
5. **Save** — both writes:
   - `cache/pull_quotes_combined.json`: find the entry (critic + outlet), set `selected: true`, set `text` to the final version. Create the entry if none exists.
   - `data.json` `pull_quotes`: inject `{text, critic, outlet, review_url}` (review_url null if verification failed).

### Step C — Commit (once per movie, after both steps)
- Capsule only → COMMIT(`data.json`, `"Capsule: [TITLE]"`)
- Pull quote only → COMMIT(`data.json`, `"Pull quotes: [TITLE]"`)
- Both → COMMIT(`data.json`, `"Capsule + pull quote: [TITLE]"`)
- Quotes skipped → the empty `pull_quotes: []` commit from Step B.3 already covers it.

---

## Completion

After all 5 stages, render **Templates → Completion summary**.
