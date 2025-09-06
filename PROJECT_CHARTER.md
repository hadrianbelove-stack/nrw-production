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
- **Data file:** `data.json` (126 titles; blanks allowed; renderer supplies search fallbacks).  
- **Mode:** offline for MVP.  
- **UI:** date cards + flip-cards; back shows Synopsis + Trailer/RT/Wiki + Watch.

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

### AMENDMENT-004: Ordered Execution
- `movie_tracker.py` → `generate_from_tracker.py` → `generate_site.py`; then handoff: smoke tests → verify outputs → package sync. Parallel only after pipeline completes.

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

### AMENDMENT-021: Post-Validation Gate
- Validate before success: `output/data.json`, `output/site/index.html`, `PROJECT_LOG.md`, `complete_project_context.md`; repo charter ≥ MIN_AMENDMENTS; timestamped charter in bundle root + `charter_history/` with identical SHA256; manifest + tree hash present; bundle SHA256 matches. Any failure = invalid bundle.

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

**End of Session (always one shot)**

1. Run:
   ./nrw-handoff.sh

2. This will:
   - Build a flat handoff folder: WORKING_SET_HANDOFF_<UTC>/ (files only).
   - Write required files: index.handoff.html, index.html, _ASSET_MAP.txt, _MANIFEST.txt,
     PROJECT_CHARTER_<timestamp>.md, PROJECT_LOG.md, complete_project_context.md,
     sources/scripts/data JSONs, _WHY.txt, POSTVALIDATION.txt.
   - Validate the set (POSTVALIDATION.txt records results).
   - Write an optional archival zip to bundle_history/ (for audit only).

3. Check:
   - No directories inside handoff.
   - index.handoff.html opens locally.
   - POSTVALIDATION.txt ends with PASS.

---

**Next Session (resync)**

1. Open the latest WORKING_SET_HANDOFF_<UTC>/ folder.
2. Select all files (⌘A / Ctrl+A).
3. Upload them into the assistant.
4. Reference the golden tag (from PROJECT_LOG.md) if needed.
5. Do not upload folders or zips.

---

**Rules**

- Only the flat handoff folder is canonical.
- Uploads must be all files from WORKING_SET_HANDOFF_<UTC>/.
- Zips and legacy NRW_SYNC artifacts are retired.
- Apply governance/script/context updates in one consolidated patch whenever possible (AMENDMENT-FLATSHOT).

## File Structure

```
Root Structure:
├── index.html          # Entry point
├── data.json          # Movie database  
├── assets/
│   ├── app.js         # Client-side renderer
│   ├── styles.css     # All styling
│   └── no-poster.jpg  # Fallback image
└── museum_legacy/     # Archived experiments
```

### File Rules

- One JS file for client display (app.js)
- One CSS file for all styles (styles.css)
- One data file for movies (data.json)
- No framework dependencies for MVP
- All paths relative from root

### AMENDMENT-ROADMAP+NAMING-LOCK-2025-09-04

1) **Root is canonical.** Fixed names only: `index.html`, `assets/styles.css`, `assets/app.js`, `data.json`. No dated or "copy" variants in root (the application expects these exact names).  
2) **Snapshots are dated.** Handoffs live in `WORKING_SET_HANDOFF_<UTC>`; files inside may be timestamped. Root files never move.  
3) **MVP scope.** Reverse-chronological wall; flip-cards; back shows Synopsis + Trailer/RT/Wiki + **Watch**. Watch defaults to Amazon; override to Netflix/MUBI/Criterion/Disney+/Hulu/Max/Apple/YouTube when detectable.  
4) **Architecture.** Client-only render from `data.json`. Prebuild static HTML is optional later.  
5) **Digital date.** First-seen provider is authoritative; API release types may fill posters/cast/runtime but cannot change the date.  
6) **Continuity.** Start sessions by uploading the newest `WORKING_SET_HANDOFF_*`. End sessions by creating a fresh one with `_MANIFEST.txt` and `POSTVALIDATION.txt` (PASS). Keep `museum_legacy/` for archived experiments; never mix with root.  
7) **Operator guide.** `ALLCODE.md` travels with handoffs and explains the four live files, the Watch rule, and museum policy.

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

### AMENDMENT-008: Canonical Daily Update Script
- `daily_update.sh` is the binding daily workflow
- Executes: check → generate → summary → git commit
- Run manually or via cron until GitHub Actions restored
- Located in repo root, not Downloads folder

### AMENDMENT-026: Repository Migration Record
- Migrated from new-release-wall to nrw-production on 2025-09-05
- Due to GitHub Actions account flag on original repo
- All future work in nrw-production repository
- GitHub support ticket filed for account reinstatement

### AMENDMENT-027: Bootstrap Data Integrity
- Bootstrap movies (discovered already-digital) marked with bootstrap_digital flag
- Only show movies caught transitioning in real-time for pure tracking
- Filter option in generate_data.py to exclude bootstrap batch
- Integrity over appearance: no fake dates
