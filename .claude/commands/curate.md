---
description: Curate new arrivals — staff picks, sections, slop review, pull quotes, capsules
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

# /curate

**Flow:** Stage 0 Reissues → Stages 1–3 Combined Review (Selects · Sections · Slop — one message, one reply, one commit) → 4 Capsule+Quotes. Run in order.

**Rhythm (user preference):** curate **slop films too** — never skip or batch-drop. Go **straight through from #1** in queue order unless the user redirects. In Stage 4, present each film's **capsule and pull quotes together in one message**, one film at a time — never capsule-first-then-quotes, never as separate passes.

**State-based, no sessions.** Each run rebuilds from current state. Window = **last 7 days** of `digital_date` (90-day wall is the hard ceiling). Every stage **drains** as films are handled, so each film is shown once then disappears — skip as many days as you want, nothing goes stale. There is no resume logic and no progress file. To change the window, pass `--window N` to the list script.

**How a stage drains:**
- Stages **1/2/3** mark films in `admin/curate_reviewed.json` (the watermark) — see *Shared blocks → List + drain*.
- Stage **0** drains its own queue `admin/reissue_candidates.json` (confirm/reject flips status).
- Stage **4** has no watermark — a film drains when it gets a capsule (`admin/approved_capsules.json`) and a `pull_quotes` key in data.json.

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

## Stages 1–3 — Combined Review (Selects · Sections · Slop)

**One message, one reply, one commit.** Never present these as three separate waits — the user's replies here are seconds of decisions; the round-trips were the cost.

**Build** all three lists in one parallel batch:
```bash
/usr/bin/python3 scripts/curate_list.py --stage selects
/usr/bin/python3 scripts/curate_list.py --stage sections
/usr/bin/python3 scripts/curate_list.py --stage slop
```

**Present every non-empty stage in a SINGLE message**, in this order, each rendered per its Template block:
1. **Selects** — Templates → Selects table + the ★ Recommended block (see *Selects notes*).
2. **Sections** — Templates → Sections table.
3. **Slop** — Templates → Slop table. Below it, **flag contradictions** (any slop-flagged film that is also a Select — vouched-for but hidden by the default slop-free view) and **recommend likely false-positives** (recommend only — never pre-flip; the user decides). Do **not** treat capsules/quotes as slop signals — every film has them.

A stage with 0 rows is one line ("Selects: all caught up") inside the same message. All three empty → skip straight to Stage 4. End with one prompt: *"One reply covers all three — e.g. 'selects: none; sections: looks good; slop: 4 not slop'."*

**On reply, apply each part:**
- **Selects picks** → read `admin/staff_picks.json`, add the picked IDs (no duplicates), write back.
- **Section changes** → studio/indie → `admin/category_overrides.json`; restorations → `admin/restorations.json`.
- **Slop overrides** — for each, write the durable verdict to `admin/overrides.json` (the
  single override store, applied last in pipeline/display.py so rebuilds never
  revert it) and to data.json for immediate effect. Key by **ID**:
  ```bash
  cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
  import sys; sys.path.insert(0, '.')
  from pipeline.json_io import json_edit
  mid, is_slop_val = sys.argv[1], sys.argv[2] == 'true'
  with json_edit('admin/overrides.json') as ov:
      ov.setdefault(mid, {}).setdefault('set', {})['is_slop'] = is_slop_val
  with json_edit('data.json') as data:
      for m in data['movies']:
          if str(m.get('id')) == mid: m['is_slop'] = is_slop_val; break
  print('done')
  " "MOVIE_ID" "true_or_false"
  ```
  *(`json_edit` locks + writes atomically — never `json.dump` a shared file directly; concurrent windows erase each other's saves.)*
- **Drain all three** — picks *and* skips, overrides *and* "looks good"; every film shown this run:
  ```bash
  /usr/bin/python3 scripts/curate_list.py --mark selects <every shown id>
  /usr/bin/python3 scripts/curate_list.py --mark sections <every shown id>
  /usr/bin/python3 scripts/curate_list.py --mark slop <every shown id>
  ```
- **One commit for the lot** → COMMIT(every file touched above + `admin/curate_reviewed.json`, `"Curation review: selects/sections/slop"`)

### Selects notes
*(formerly "Staff Picks" — file is still `admin/staff_picks.json`)*
- Sort the table **by notability** (Buzz + acclaim, descending). Buzz (0–100) is computed overnight and stored on each record in `data.json` (`buzz_score`). If it shows `--`, the nightly research didn't reach that film — note it and proceed; a pipeline gap to fix later, **not** something to compute by hand during curation.
- Fill `★ Recommended:` from each shown film's `notability` block in `data.json` (`festival` / `awards` / `yearend_lists`, populated by the nightly research): the genuine finds, **notable facts only** (festivals, named awards, distributor/director), hyperlinking recognizable named entities to Wikipedia — **no plot, no editorializing**. The research already web-searched, so **do not hand-search here**. If nothing stands out, say so.

### Sections notes
- The `Sections` column is computed by the script from `movie.filters` (Indie/Foreign/Documentary/Virtual Screening/Restoration) and `movie.genres` (Horror/Action/Comedy/Family/Thriller); `(none)` if no filters. Selects is Stage-1 business — not shown here.
- Filters are auto-detected from TMDB (genres, language, distributor rules). To improve detection logic (e.g. new indie-distributor rules), update the **pipeline code** — not this command.

### Slop notes
- The false-negative pass, done **once per film**. Shows **all** remaining candidates (not just slop-flagged ones) so the user can catch misclassifications either way. All films stay on the site regardless — the slop toggle is a view mode, never removal.
- The script computes the `Slop?` and `Why` columns (`is_slop`/`_is_slop_guess` → `🗑 SLOP (auto)` / `🗑 SLOP (manual)` / `✅ Not slop`; `Why` = `_slop_reason`, or scores, or "no classifier signal").

---

## Stage 4 — Capsule + Pull Quotes

Capsule and quotes done **together, movie by movie** — not separate passes. Everything the user reads is **pre-rendered into a doc**; chat carries pointers and decisions only.

1. **Render + open the doc:**
   ```bash
   cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/render_stage4_doc.py && open cache/stage4_doc.html
   ```
   The script assembles every queued film's full presentation (3 variants with approach labels, factoid primer, pre-verified suggested links with Wikipedia's one-line descriptions, numbered pull quotes) from the overnight caches — <1s, no LLM, no network. It prints the queue (`#N Title (Year) — needs`). If it prints "nothing needs capsules or quotes", finish. The queue = films **missing a capsule** (not in `approved_capsules.json` by title) **or** missing a `pull_quotes` key. *(`pull_quotes: []` = reviewed-and-skipped, drains; **no key** = never queued. Not the same.)*
2. **Relay the printed queue** as the run's checklist and **pin the titles immediately** — from here on work by **title, never live position**, so a parallel window draining films can't shift you onto the wrong one. If the user redirects ("go to #5", "skip to Kraken"), continue from there.
3. **Walk films one at a time with SHORT pointer turns.** Do **not** re-present doc content in chat (only on request — "show it here"). Each pointer is just: `#N of TOTAL — Title (Year)` + one-line ⚠ reminders carried from the doc (no cached variants / links not cached / no quotes) + the pick prompt: *"capsule 1–3 or paste a rewrite · quote number, trim, or skip · suggested links ride along unless you say otherwise — details in the doc."*
4. **Save film N and point at film N+1 in the SAME turn.** After each reply, run the save-chain (Steps A/B/C below) as tightly batched tool calls, then end that same message with film N+1's pointer. The user should never wait on saves or pushes.
5. **Fallbacks, per film (the doc flags each):** `⚠ no cached variants` (arrived after the nightly run) → generate + present live in chat the old way (Step A.1 + capsule.md format). `⚠ links not cached` (pre-upgrade cache entry) → WebSearch entities live for that film only. `⚠ no quotes` → relay it and offer skip or `--custom`.

### Parallel-window slice (only when invoked with a number arg)
For `/curate 1-3`, `4,6`, etc. — Stages 0–3 were skipped. Build the queue above, keep only the requested positions, **pin them to their titles immediately**, and print **Templates → Stage 4 slice header** instead of the full checklist. From then on work by **title, not live position**, so a parallel window draining films can't shift you onto the wrong one. Skip out-of-range positions with a one-line note. Everything else below is unchanged. (Open parallel windows close together so they share one queue snapshot; use the printed titles to confirm no overlap.)

### Step A — Capsule
1. **Doc flow (default):** the variants, primer, and suggested links are already in the doc — no script run, no re-presentation. **Fallback only** (film flagged `⚠ no cached variants`): `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "TITLE" --variants 3 --skip-verify` generates live (1–3 min), then present in chat per `.claude/commands/capsule.md` Step 2 (the template for standalone/fallback presentations — `scripts/render_stage4_doc.py` owns the doc layout; a format change must touch both). No `--force` unless deliberately regenerating.
2. **Edited text the user pastes IS the final version.**
4. **After the user replies** (ONE reply covers capsule, quote, *and* links — the SUGGESTED LINKS already on screen are approved by that reply unless it says otherwise, e.g. "drop [Name]" / "no links"), if they picked/rewrote the capsule:
   1. Format: **bold** director + cast names; *italicize* other film titles in the text.
   2. Embed Wikipedia links (Step A-Links). **Variant picked as-is → embed silently and continue — no re-show, no second wait.** Rewrite pasted (or links changed in the reply) → one re-show for a final OK.
   3. Write final text to `cache/rewrite.txt`.
   4. `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "TITLE" --file cache/rewrite.txt`
   5. Write cast wiki links to data.json (Step A-Links).

### Step A-Links — Wikipedia links (inside Step A)
**Pass 1 — Cast + Director (silent, auto-approved, NOT shown in SUGGESTED LINKS):** read `movie.links.cast_wiki` and `movie.links.director_wiki`; embed each wherever the name appears in the capsule. No URL → skip silently (many actors lack pages).

**Pass 2 — Other named entities (user reviews these):** non-cast/non-director people, places, movements, or works named in the capsule text (a manga creator, historical figure, referenced filmmaker — up to 3). These are **pre-verified overnight** into the capsule cache (`suggested_links`, each with Wikipedia's one-line description as the wrong-person guard) and already shown in the doc — do **not** search live. WebSearch is the fallback only when the cache entry lacks them (`⚠ links not cached` in the doc, or a live fallback generation).

**Pre-embedding (after the user picks/rewrites):**
1. Scan the final text for any `**bold**` names not already listed; WebSearch each, add if found.
2. Embed all links: `**Name**` → `**[Name](url)**`; plain `Name` → `[Name](url)`; name not in text → skip (still save to cast_wiki for the metadata line).
3. **Variant picked as-is, links untouched** → the reply already approved what was on screen: this is final → write `cache/rewrite.txt`, do **not** re-show. **Rewrite pasted, or the reply removed/changed links** → show the capsule once with links visible ("Approve with these links — or say 'remove [Name]' to drop any"); strip and re-show on removal; on approval → write `cache/rewrite.txt`.

**Save cast wiki links (after the approve script runs)** — merge, don't overwrite; cast members only (not director/figures/events — those are text-only links). Encode `(`→`%28`, `)`→`%29` in URLs:
```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys; sys.path.insert(0, '.')
from pipeline.json_io import json_edit
title, cast_wiki_json = sys.argv[1], sys.argv[2]
cast_wiki = json.loads(cast_wiki_json)
with json_edit('data.json') as data:
    movies = data if isinstance(data, list) else data.get('movies', [])
    for m in movies:
        if m.get('title','').lower() == title.lower():
            m.setdefault('links', {})
            existing = m['links'].get('cast_wiki', {}); existing.update(cast_wiki)
            m['links']['cast_wiki'] = existing; break
" "MOVIE_TITLE" '{\"Ellie Bamber\": \"https://...\", \"Derek Jacobi\": \"https://...\"}'
```
*(`json_edit` locks + writes atomically — never `json.dump` data.json directly; concurrent windows erase each other's saves.)*

### Step B — Pull Quotes (same doc, same reply)
The film's quotes are already in the doc, numbered by the exact same ordering `--select --num N` uses (the renderer imports get_quotes' ordering function) — the number the user reads is the number that saves. The user's ONE reply covers capsule + quote + links (e.g. "capsule 2, quote 4").

All quote mechanics live in **`scripts/get_quotes.py`** — never read or edit `cache/pull_quotes_combined.json` directly (it's 3.5MB; the script extracts just this film). The Letterboxd cap (10) is `LB_MAX` in that script.

1. **Only when needed in chat** (user asks "show it here", or a fallback film):
   ```bash
   cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/get_quotes.py "TITLE" YEAR
   ```
   Present its output **verbatim** (it renders **Templates → Quotes block**). No pre-filtering/ranking. If the doc (or script) flags `⚠` (no cache entry / 0 quotes), relay it and offer skip. Never re-scrape; the morning batch (`scripts/batch_pull_quotes.py`) is canonical.
2. **On reply** (the quote part of the joint reply), one command does the whole save — verifies the `review_url` (bad/unloadable links saved as `review_url: null` with a `⚠` line), sets `selected: true` + final text in the cache, and injects `{text, critic, outlet, review_url}` into the movie's `pull_quotes` in data.json:
   - Number N → `/usr/bin/python3 scripts/get_quotes.py --select "TITLE" YEAR --num N`
   - Pasted trim → **that IS the final version** (never revert to original): write it to `cache/quote_trim.txt`, add `--text-file cache/quote_trim.txt` to the command above.
   - A quote not in the list → `--select "TITLE" YEAR --custom --critic "Name" --outlet "Outlet" --text-file cache/quote_trim.txt [--url URL]`
   - "skip" → `/usr/bin/python3 scripts/get_quotes.py --skip "TITLE" YEAR`, then COMMIT(`data.json`, `"Pull quotes: [TITLE] skipped"`). `[]` = reviewed/rejected (don't re-queue); **no key** = never queued.
3. **Relay any `⚠` the script prints.** If it dropped a link and the user says "keep link", re-run the same `--select` command with `--keep-url` (also the fix for short titles, where the verifier false-flags — see memory). Re-selecting the same critic+outlet replaces the saved quote, so re-trims are safe.

### Step C — Commit (once per movie, after both steps)
The approve script also appends to `admin/approved_capsules.json` (the git-tracked house-style bank CI reads) — commit it alongside data.json whenever a capsule was approved.
- Capsule only → COMMIT(`data.json admin/approved_capsules.json`, `"Capsule: [TITLE]"`)
- Pull quote only → COMMIT(`data.json`, `"Pull quotes: [TITLE]"`)
- Both → COMMIT(`data.json admin/approved_capsules.json`, `"Capsule + pull quote: [TITLE]"`)
- Quotes skipped → the empty `pull_quotes: []` commit from Step B.3 already covers it.

---

## Completion

After all 5 stages, render **Templates → Completion summary**.
