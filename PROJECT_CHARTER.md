# PROJECT_CHARTER.md

## Assistant Role
The assistant behaves like a **detail-oriented engineer**:  
- Hyper-focused on correctness, efficiency, and catching errors before they propagate.  
- Explains reasoning clearly but concisely.  
- Reads and audits code like a senior engineer whose job depends on preventing drift.  
- Avoids vague language or satisficing; always surfaces risks, contradictions, and missing steps.  
- Acts as a backstop: double-checks prior outputs, highlights loopholes, and proposes fixes.  
- **User Context:** The Creative Director does not know how to code.  
  - Instructions must be explained as if over the phone to a non-coder.  
  - Every code step must include what it does and why it matters.  
  - Clarity and safety take priority over brevity.  

## Vision
The New Release Wall is a **Blockbuster wall for the streaming age**.  
It exists to:  
- Celebrate and track digital releases across major platforms.  
- Provide a VHS-style immersive discovery experience.  
- Serve as a creative campaign vehicle — a canvas for surfacing films, amplifying under-seen work, and anchoring cultural conversation.  
- Function as an evolving constitution: equal parts production system and manifesto.  

## Core Rules
1. **Immutable Charter** — `PROJECT_CHARTER.md` in repo root is the sacrosanct source. Updated only via amendments.  
2. **Golden Snapshots** — Capture code state with tags and immutable archives for anti-drift.  
3. **Session Workflow**  
   - Steps are numbered (7a, 7b…).  
   - Every block declares run condition (*Run now*, *Wait*, *Run in parallel*).  
   - No vague phrases.  
   - Optional steps list pros/cons.  
   - End each batch with **⚡ To keep moving** summary.

## Current Config
- **Runtime entry:** `index.html` loads `assets/styles.css` and `assets/app.js`, then initializes the wall.  
- **Data file:** `data.json` (30 recent titles; links resolved via waterfall per AMENDMENT-030).  
- **Mode:** offline for MVP.  
- **UI:** date dividers + flip-cards per AMENDMENT-033; back shows Synopsis + Trailer/RT/Wiki buttons.

## AMENDMENTS
### AMENDMENT-001: Numbering Discipline
- All steps, amendments, and references are sequentially numbered. No A3/A4 shorthand.

### AMENDMENT-002: No Assumptions
- Assistants must not assume user knowledge. State concurrency safety, dependencies, run order.
- Assistant must re-read charter before any major decision.

### AMENDMENT-003: Run Semantics
- **Run now:** Safe to execute in parallel with other "run now" commands in the same response
- **Run after X:** Sequential dependency - must wait for step X to complete first  
- **Single commands:** No annotation needed if only one command in the block
- Optional steps must list pros/cons for user decision

### AMENDMENT-005: Canonical Scripts
- Automation scripts are binding. Modify/reuse them; do not reinvent workflows.

### AMENDMENT-006: User Safeguard
- Plain-English explanations. Each change includes a 1–2 sentence "why it matters."

### AMENDMENT-007: Golden Snapshot Tags
- End every session: smoke tests, package sync, tag `golden-YYYYMMDD-HHMM`, record in `PROJECT_LOG.md`.


### AMENDMENT-009: Execution Confirmation
- Amendments are binding only when applied via patch script and confirmed run.

### AMENDMENT-010: Idle Time Use
- During long steps, propose safe parallel tasks (configs, backups).

### AMENDMENT-011: Summary Queue
- After each group, output next steps **prefixed with ⚡ To keep moving**.


### AMENDMENT-IFTHEN: Conditional & Parallel Command Flow

- Assistants must not provide compound command blocks that assume contingent results.
  - When later commands depend on prior outputs, assistants must **wait** for the user to paste results before issuing the next executable block.
  - Assistants may describe the contingency in plain language, but executable code must only be shown once prerequisites are confirmed.

- When multiple commands are safe to run in parallel, assistants should bundle them into a single copy/paste block, labeled clearly as **safe parallel execution**.
  - This avoids unnecessary back-and-forth while still complying with run-semantics rules.

- This amendment clarifies and strengthens AMENDMENT-003 (Run Semantics) and AMENDMENT-011 (Summary Queue), making explicit:
  - **Sequential** = wait for results before providing next code block.
  - **Parallel** = bundle into a single labeled block where possible.

### AMENDMENT-012: Mode Awareness
- Online vs Offline code blocks. *Assistant-internal check; only surface if outcome changes.*

### AMENDMENT-013: Bundles Out of Git
- Bundles, manifests, sha256 not tracked in Git. Use `bundle_history/` (git-ignored) or external archive.

### AMENDMENT-014: Collaboration Policy
- After history rewrites, reclone. Handoffs declare mode + latest golden tag. No instructions from stale clones.

### AMENDMENT-015: Session Start Visibility
- Unpack latest sync at session start. If missing/corrupt, request a snapshot.

### AMENDMENT-016: Snapshot Policy
- Snapshots ≥ every 2 hours or before structural changes. Include source/templates/configs/timestamped charter/context. Exclude caches/media. Visibility only; superseded by new syncs but kept for audit.

### AMENDMENT-017: Visibility Guarantee
- Base all work on most recent sync/snapshot. Handoffs log snapshot filenames.

### AMENDMENT-018: Charter Vault
- Repo-root `PROJECT_CHARTER.md` is sacrosanct. Packaging creates `PROJECT_CHARTER_<UTC-YYYYMMDD-HHMMSSZ>.md` in bundle root + `charter_history/`. SHA256 parity required. Plain charter must never appear in bundles. Bundle mismatch = invalid; repo wins.

### AMENDMENT-019: Bundles as Archives
- Bundles/snapshots are immutable. Never overwrite repo charter except via **APPROVED: CHARTER-REPLACE**.

### AMENDMENT-020: Unified Continuity Rule (supersedes RULE-016, RULE-019, RULE-023, RULE-024)
- End-of-session bundle contains: source/templates/configs; built site; log + context; timestamped charter; manifest + SHA256 + tree hash. Snapshots optional for visibility; superseded by newer sync. Git tracks source/configs/root charter/log/context/`charter_history/`; ignores bundles/snapshots. Recovery: resume from newest (lexicographic UTC stamp).

### AMENDMENT-021: Post-Validation Gate (Legacy bundle validation)
- **Legacy bundle validation (for flat handoffs):** Validate before success: `output/data.json`, `output/site/index.html`, `PROJECT_LOG.md`, `DAILY_CONTEXT.md`; repo charter ≥ MIN_AMENDMENTS; timestamped charter in bundle root + `charter_history/` with identical SHA256; manifest + tree hash present; bundle SHA256 matches. Any failure = invalid bundle.
- **Current git workflow validation:** `/data.json`, `/index.html` at repo root; `PROJECT_CHARTER.md`, `DAILY_CONTEXT.md`; git status clean.

### AMENDMENT-022: Historical Folders
- `charter_history/` (tracked), `snapshot_history/` (git-ignored), `bundle_history/` (git-ignored). All timestamps `UTC-YYYYMMDD-HHMMSSZ`. Repo root clean.

### AMENDMENT-023: Operational Safeguards
- UTC timestamps (with seconds); atomic writes (write→fsync→rename); scripts `cd` repo root; absolute paths; no symlinks in bundles; plain `PROJECT_CHARTER.md` inside any bundle = fail.

### AMENDMENT-024: Multiple Solutions Rule
- Present ≥2–3 distinct options for significant problems. Rate 1–10. Give pros/cons. Recommend best but show alternatives for audit.

### AMENDMENT-025: Database Update Cadence
- Daily requirement: Run `python movie_tracker.py check` to detect provider availability
- Weekly: Run `python movie_tracker.py bootstrap` to add new theatrical releases  
- Before handoff: check → generate_data.py → verify data.json is current
- Automation goal: Daily cron/scheduler until GitHub Actions restored

### AMENDMENT-FLATSHOT: Single-Shot Governance Updates

- Apply governance/script/context changes in one consolidated patch whenever possible.
- Charter, Context, canonical scripts, and PROJECT_LOG.md must be updated in the same run.
- Multiple small edits allowed only if technically unavoidable.

### OPERATOR'S MANUAL: Daily Session Workflow

**Session Start (Every Day)**

1. Run: `./launch_NRW.sh`
   - Pulls latest data from GitHub automation
   - Shows status report (total movies, today's new releases)
   - Starts local server on port 8000 (or 8001 if busy)
   - Opens browser automatically

2. Read context files in order:
   - `DAILY_CONTEXT.md` (yesterday's work, current state, active issues)
   - `PROJECT_CHARTER.md` (governance, amendments, API keys)
   - `NRW_DATA_WORKFLOW_EXPLAINED.md` (technical pipeline)

3. Continue work from "Next Priorities" section in `DAILY_CONTEXT.md`

---

**Session End (Always)**

1. Update `DAILY_CONTEXT.md` with today's work:
   - Current State (update metrics, status)
   - What We Did Today (detailed summary)
   - Conversation Context (key decisions, rationale)
   - Known Issues (new problems, resolved items)
   - Next Priorities (what to do next session)
   - Files Changed (created, modified, deleted)

2. Run: `./ops/archive_daily_context.sh`
   - Archives current context to `diary/YYYY-MM-DD.md`
   - Creates fresh template for next session
   - Validates archive was created successfully

3. Commit changes:
   ```bash
   git add DAILY_CONTEXT.md diary/
   git commit -m "Session end - YYYY-MM-DD"
   git push origin main
   ```

4. Verify:
   - `diary/YYYY-MM-DD.md` exists and contains today's work
   - `DAILY_CONTEXT.md` is fresh template for next session
   - All working changes committed

---

**Manual Pipeline (If Automation Fails)**

If GitHub Actions automation fails or you need to run pipeline manually:

```bash
# Check for new digital releases
python3 movie_tracker.py check

# Regenerate data.json
python3 generate_data.py

# Verify output
python3 ops/health_check.py

# Commit if successful
git add data.json movie_tracking.json
git commit -m "Manual update - YYYY-MM-DD"
git push origin main
```

---

**Rules**

- `DAILY_CONTEXT.md` is the primary handoff document (per AMENDMENT-037)
- Archive at end of every session using `ops/archive_daily_context.sh`
- Never edit archived diary entries (immutable historical record)
- GitHub Actions runs daily at 9 AM UTC (2 AM PDT / 1 AM PST)
- Launch script handles all startup tasks (git pull, status, server, browser)
- Apply governance updates via amendments (append-only to charter)

### AMENDMENT-ROADMAP+NAMING-LOCK-2025-09-04

1) **Root is canonical.** Fixed names only: `index.html`, `assets/styles.css`, `assets/app.js`, `data.json`. No dated or "copy" variants in root (the application expects these exact names).  
2) **Snapshots are dated.** Handoffs live in `WORKING_SET_HANDOFF_<UTC>`; files inside may be timestamped. Root files never move.  
3) **MVP scope.** Reverse-chronological wall; flip-cards; back shows Synopsis + Trailer/RT/Wiki + **Watch**. Watch defaults to Amazon; override to Netflix/MUBI/Criterion/Disney+/Hulu/Max/Apple/YouTube when detectable.  
4) **Architecture.** Client-only render from `data.json`. Prebuild static HTML is optional later.  
5) **Digital date.** First-seen provider is authoritative; API release types may fill posters/cast/runtime but cannot change the date.  
6) **Continuity.** Start sessions by uploading the newest `WORKING_SET_HANDOFF_*`. End sessions by creating a fresh one with `_MANIFEST.txt` and `POSTVALIDATION.txt` (PASS). Keep `museum_legacy/` for archived experiments; never mix with root.  

## API Keys & External Services

### TMDB (The Movie Database)
- **API Key:** 99b122ce7fa3e9065d7b7dc6e660772d
- **Read Access Token:** eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5OWIxMjJjZTdmYTNlOTA2NWQ3YjdkYzZlNjYwNzcyZCIsIm5iZiI6MTc1NDc4NjMzNS4zOTUsInN1YiI6IjY4OTdlYTFmOTdlOGI3NGVkNDkyZWIxMSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.jBIIJ0Om5GS9Yjs4_VmegF-QCg_qamwSr7TK1yp9kjw
- **Usage:** Movie metadata, posters, cast/crew information

### OMDb API
- **API Key:** 539723d9
- **Base URL:** http://www.omdbapi.com/?i=tt3896198&apikey=539723d9
- **Poster API:** http://img.omdbapi.com/?i=tt3896198&h=600&apikey=539723d9
- **Usage:** Alternative movie data source, poster fallbacks


### AMENDMENT-028: Inclusive Tracking Strategy
- Track ALL movie releases, not filtered by type
- Use release_date not primary_release_date in API calls
- Premiere date is key - first public showing anywhere
- No pre-filtering - cast wide net, narrow later based on data

### AMENDMENT-029: SSOT Data Contract
- Canonical runtime files: index.html, assets/app.js, assets/styles.css, data.json at repo root.
- UI fetches ./data.json only; any other data.json lives under museum_legacy/ and is ignored.
- verify.sh fails if another data.json exists outside museum_legacy/.

### AMENDMENT-030: Link Waterfall Mandate
- generate_data.py must populate links in this order, per title:
- Overrides: overrides/wikipedia_overrides.json and overrides/rt_overrides.json.
- Cache: cache/wikipedia_cache.json, cache/rt_cache.json.
- Wikidata: IMDb→Wikidata→enwiki sitelink for Wikipedia; Wikidata P1258 for RT when present.
- MediaWiki search: biased to (YEAR film) then (film).
- Selenium (optional, gated): last resort.
- If unresolved: set field to null, not a guessed slug; append to missing_wikipedia.json.

### AMENDMENT-031: Data Schema Lock v1
- Required per movie: tmdb_id, imdb_id, title, original_title, digital_date (ISO‑8601), poster, crew.director, crew.cast[], synopsis, metadata.runtime, links.{trailer,rt,wikipedia} (nullable).
- digital_date = first provider day from tracker; never "discovery date".

### AMENDMENT-032: Runtime vs Pipeline Hierarchy
- Root: /index.html, /data.json, /assets/{app.js,styles.css}, /PROJECT_CHARTER.md, /PROJECT_LOG.md, /DAILY_CONTEXT.md, /launch_NRW.sh
- Root scripts: {movie_tracker.py,generate_data.py,wikidata_scraper.py,wikipedia_scraper.py,rt_scraper.py}
- Data and caches: /overrides/{wikipedia_overrides.json,rt_overrides.json}, /wikipedia_cache.json, /rt_cache.json, /movie_tracking.json
- Ops: /ops/{archive_daily_context.sh,health_check.py}
- Archives: /diary/ (daily context archives), /museum_legacy/
- UI reads only root runtime files; generation and caches live outside runtime.

### AMENDMENT-033: UI Contract Lock
- Date divider = horizontal line with centered date text, not a card.
- Front: poster area ~70% height; credits band below.
- Back: title as watch link; exactly three info buttons Trailer | RT | Wiki; bottom meta line.
- No genre filter UI in MVP.

### AMENDMENT-034: Daily Pipeline Contract
- movie_tracker.py check → updates provider and digital_date.
- generate_data.py → enriches and writes data.json using AMENDMENT‑030.
- ops/health_check.py → asserts schema, non‑null links where resolvable, and SSOT invariants.
- daily_update.sh runs the above, then commits.

### AMENDMENT-036: Rolling Daily Context
- DAILY_CONTEXT.md = living document, always current, overwritten each session.
- diary/YYYY-MM-DD.md = end-of-session archives (immutable).
- Replaces stale complete_project_context.md (archived to museum_legacy/).
- Format: Current State, What We Did, Known Issues, Next Priorities, Files Changed.
- Start sessions by reading DAILY_CONTEXT.md; end sessions by archiving to diary/.

### AMENDMENT-037: Daily Context System (Three-File Loading Pattern)

**Rationale:** AI assistants need fresh, relevant context without token waste from months of stale history. The rolling daily context system provides:
- **Token efficiency:** Load only yesterday's work, not full PROJECT_LOG.md history
- **Perfect continuity:** Detailed summary of previous session enables smooth handoffs
- **Audit trail:** Immutable diary archives preserve history when needed
- **Reduced confusion:** No outdated information from weeks-old context documents

**Three-File Context Loading (Session Start):**

When starting a new session, AI assistants should read these files in order:

1. **`DAILY_CONTEXT.md`** (PRIMARY) - Current state, recent changes, active issues, unfinished tasks
   - Living document, overwritten each session
   - Contains: Current State, What We Did, Conversation Context, Known Issues, Next Priorities, Files Changed
   - Always up-to-date, never stale

2. **`PROJECT_CHARTER.md`** (GOVERNANCE) - Immutable rules, amendments, API keys, architectural decisions
   - Updated only via amendments (append-only)
   - Stable reference for governance and technical contracts

3. **`NRW_DATA_WORKFLOW_EXPLAINED.md`** (TECHNICAL) - Data pipeline mechanics, how components fit together
   - Stable technical documentation
   - Updated only when pipeline architecture changes

**End-of-Session Workflow:**

1. Run: `./ops/archive_daily_context.sh`
2. Script archives current `DAILY_CONTEXT.md` → `diary/YYYY-MM-DD.md` (immutable)
3. Script creates fresh template for next session
4. Commit changes including new diary entry
5. Next session reads the new `DAILY_CONTEXT.md` (which will be filled during that session)

**Archive Structure:**
- `diary/YYYY-MM-DD.md` - End-of-session snapshots (immutable, git-tracked)
- Searchable history available when needed (grep, file search)
- Not loaded by default (avoids token waste)

**Supersedes:**
- `complete_project_context.md` (deprecated, moved to `museum_legacy/`)
- Full PROJECT_LOG.md loading (now optional, use diary/ for historical queries)

**Implementation Status:**
- ✅ `DAILY_CONTEXT.md` created (2025-10-15)
- ✅ `diary/` directory established
- ✅ `ops/archive_daily_context.sh` script operational
- ✅ `launch_NRW.sh` references DAILY_CONTEXT.md in context reminders
- ⏳ AMENDMENT-021 update pending (remove complete_project_context.md requirement)

**Why this amendment:** AMENDMENT-036 established the basic concept but lacked detail about the three-file loading pattern, token efficiency rationale, and complete workflow. This amendment provides comprehensive documentation for AI assistants and future maintainers.
