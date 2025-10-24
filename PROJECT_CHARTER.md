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
4. **Tactical Planning** — `IMPLEMENTATION_ROADMAP.md` serves as the canonical tactical plan for prioritized implementation work.

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
- Daily automation: `generate_data.py` handles both discovery and provider checking
- Discovery source: `generate_data.py` is the single system for movie discovery
- Legacy: `museum_legacy/legacy_movie_tracker.py` is for historical reference only
- Before handoff: generate_data.py → verify data.json is current
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
python3 generate_data.py  # Now handles discovery + provider checking

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

## Configuration

The system expects configuration to be provided via `config.yaml` in the repository root and/or environment variables.

### config.yaml Structure
```yaml
api:
  tmdb_api_key: ""  # TMDB API key (can be set via TMDB_API_KEY env var)
  tmdb_rate_limit: 0.1  # Seconds between API calls
  max_retries: 3

workflow:
  daily_check_time: "02:00"  # 2 AM PST
  weekly_bootstrap_day: "sunday"

display:
  days_back: 90  # Show movies from last N days
  min_movies: 20  # Minimum movies to display
  max_movies: 100  # Maximum movies to display

tracking:
  bootstrap_days: 7  # Look back N days for new releases
  check_interval_hours: 24  # How often to check
```

### Environment Variables
- **TMDB_API_KEY**: TMDB API key (takes precedence over config.yaml)

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

### Watchmode API
- **API Key:** bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp
- **Base URL:** https://api.watchmode.com/v1/
- **Documentation:** https://api.watchmode.com/docs/
- **Free Tier:** 1,000 requests/month (no credit card required)
- **Usage:** Deep links to streaming platforms (Netflix, Amazon, HBO Max, etc.)
- **Endpoints used:**
  - Search: https://api.watchmode.com/v1/search/ (search by TMDB ID)
  - Details: https://api.watchmode.com/v1/title/{watchmode_id}/details/ (get streaming sources)
- **Authentication:** Pass `apiKey` as query parameter
- **Coverage:** 200+ streaming services in 50+ countries (US data on free tier)
- **Features:** Web links, iOS/Android deep links, episode-level links

### Agent-Based Link Finding (No API Key Required)
- **Purpose:** Scrape direct watch links from streaming platforms when Watchmode API has no data
- **Platforms:** Netflix, Disney+, HBO Max, Hulu
- **Technology:** Selenium WebDriver with headless Chrome
- **Rate Limiting:** 2-second minimum delay between scrapes
- **Cache:** `cache/agent_links_cache.json`
- **Usage:** Automatic fallback when Watchmode API returns no data
- **Optional:** Can be disabled by not initializing agent in `generate_data.py`
- **Terms of Service:** Web scraping may violate platform ToS; use responsibly

### Canonical Watch Links Schema

**Official Structure (as of AMENDMENT-038):**

The `watch_links` field in `data.json` uses a **three-category structure** representing different access methods:

```json
{
  "watch_links": {
    "streaming": {
      "service": "Netflix",
      "link": "https://www.netflix.com/title/12345"
    },
    "rent": {
      "service": "Amazon Video",
      "link": "https://www.amazon.com/..."
    },
    "buy": {
      "service": "Apple TV",
      "link": "https://tv.apple.com/..."
    }
  }
}
```

**Category Definitions:**
- **`streaming`**: Subscription-based services (Netflix, Prime, Disney+, HBO Max, Hulu, MUBI, Criterion)
- **`rent`**: Rental options (Amazon Video, Apple TV, Google Play, Vudu)
- **`buy`**: Purchase options (Amazon Video, Apple TV, Google Play, Microsoft Store)

**Schema Rules:**
1. **Optional categories**: Only present when available for the movie (sparse structure)
2. **Required fields per category**: `service` (string, provider name) and `link` (string URL or null)
3. **Null links allowed**: `link: null` indicates service is available but URL not found (frontend shows error state)
4. **No search URLs**: System returns `null` instead of Google/Amazon search fallbacks (curator can add overrides)
5. **Service priority**: Best service selected per category (Netflix > Disney+ for streaming, Amazon > Apple TV for rent/buy)

**Why `streaming/rent/buy` (not `free/paid`):**
- More semantic clarity - users understand "streaming" vs "rent" better than "free" vs "paid"
- Aligns with industry terminology (Watchmode API, TMDB, streaming platforms)
- Three categories provide finer granularity (rent vs buy are different user intents)
- "Free" is ambiguous (subscription services aren't truly free)

**Legacy Migration:**
- Early implementation used `free/paid` categories (Oct 16, 2025)
- Automatic migration function in `generate_data.py` (lines 1021-1072) converts old cache entries
- All production code now uses `streaming/rent/buy` exclusively
- Migration is transparent (no user action required)

**Validation:**
- Schema validation function in `generate_data.py` enforces structure (see `validate_watch_links_schema()`)
- Invalid categories rejected (only streaming/rent/buy allowed)
- Invalid structure logged as warning (graceful degradation)


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
- Required per movie: tmdb_id, imdb_id, title, original_title, digital_date (ISO‑8601), poster, crew.director, crew.cast[], synopsis, metadata.runtime, links.{trailer,rt,wikipedia} (nullable), watch_links (optional).
- watch_links (optional): object whose optional keys are `streaming`, `rent`, `buy`, each containing `{service: string, link: string}`. Categories are present only when available for the title. See "Canonical Watch Links Schema" section and AMENDMENT-038 for full details and fallback logic.
- digital_date = first provider day from tracker; never "discovery date".

### AMENDMENT-032: Runtime vs Pipeline Hierarchy
- Root: /index.html, /data.json, /assets/{app.js,styles.css}, /PROJECT_CHARTER.md, /PROJECT_LOG.md, /DAILY_CONTEXT.md, /launch_NRW.sh
- Root scripts: {generate_data.py} (primary), {museum_legacy/legacy_movie_tracker.py} (historical reference)
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
- generate_data.py → handles discovery, provider checking, and enrichment, writes data.json using AMENDMENT‑030.
- Legacy: museum_legacy/legacy_movie_tracker.py → historical reference only.
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
- Archive dates use UTC timezone to align with GitHub Actions automation timeline
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

### AMENDMENT-038: Watchmode API Integration for Watch Links

**Rationale:**

The project needed direct links to streaming platforms rather than Google searches for movie watch options. TMDB provides provider names ("Netflix", "Amazon Video") but not deep links to actual watch pages. Users need clickable links that take them directly to streaming platforms, not search results.

**Problem evaluation:**
- **TMDB limitation:** Provides provider metadata (service names) but no deep links
- **User need:** Direct links to streaming platforms for immediate viewing
- **Solution evaluation:** Tested multiple APIs for streaming link coverage
  - Streaming Availability API (RapidAPI): 100 requests/day free tier
  - Watchmode API: 1,000 requests/month free tier
- **Winner:** Watchmode API had superior coverage for new releases (October 2025 movies)
- **Example:** "The Long Walk" (Oct 2025) - Watchmode returned 6 sources with Amazon deep links, while Streaming Availability API had no data

**Technical Implementation:**

1. **Two-step API process:**
   - Step 1: Search by TMDB ID to get Watchmode internal ID
   - Step 2: Fetch streaming sources for that Watchmode ID
   - Endpoints: `https://api.watchmode.com/v1/search/` and `https://api.watchmode.com/v1/title/{id}/details/`
   - Implementation: `get_watch_links()` method in `generate_data.py` (lines 197-400)

2. **Watch links schema (canonical structure):**
   ```
   watch_links: {
     'streaming': {'service': 'Netflix', 'link': 'https://...'},  // subscription streaming
     'rent': {'service': 'Amazon', 'link': 'https://...'},        // rental
     'buy': {'service': 'Apple TV', 'link': 'https://...'}        // purchase
   }
   ```
   - Each category contains: `service` (platform name) and `link` (URL or null)
   - When Watchmode API has no data, `link` is set to `null` while `service` name is preserved for UI display
   - Links are either Watchmode deep links or `null` (no search URLs generated)
   - Categories are optional - only present if movie has that availability type

3. **Service priority hierarchies:**
   - **Streaming priority:** Netflix > Disney+ > HBO Max > Hulu > Amazon Prime > MUBI > Shudder > Criterion Channel
   - **Paid priority:** Amazon Video > Apple TV > Vudu > Google Play > Microsoft Store
   - **Rationale:** Prioritizes platforms with largest user bases for better UX
   - **Implementation:** `select_best_service()` function (lines 246-253)

**Link Failure Handling:**
- When Watchmode API returns no data for a service, the system returns `{service: 'ServiceName', link: null}`
- This preserves service information for UI display while making link failures explicit
- No search URLs are generated as fallbacks (per user requirement)
- Frontend can display disabled/error state for buttons with null links
- Admin panel can be used to manually add override links for null entries

4. **Link failure handling (two-tier system):**
   - **Tier 1:** Watchmode API deep links (e.g., `https://watch.amazon.com/detail?gti=...`)
   - **Tier 2:** Service name with `null` link (when Watchmode has no data)
   - **No fallback links:** All search URLs removed - returns null instead
   - **No direct links:** Netflix, Disney+, HBO Max (return null)
   - **UI handling:** Frontend can display disabled/error state for buttons with null links

5. **Cache strategy:**
   - **Location:** `cache/watch_links_cache.json`
   - **Key:** TMDB ID (string)
   - **Value:** `{links: {...}, cached_at: ISO-8601, source: 'watchmode_api'|'tmdb_providers'}`
   - **Purpose:** Prevents redundant API calls (saves 13,380 calls/month)
   - **Effectiveness:** With cache, monthly usage is ~300 calls (new movies only); without cache, would be 13,680 calls (exceeds free tier)
   - **Migration support:** Automatically migrates legacy `free/paid` format to canonical `streaming/rent/buy` schema
   - **Schema enforcement:** See "Canonical Watch Links Schema" section for official structure definition
   - **Validation:** `validate_watch_links_schema()` function enforces schema correctness during generation

6. **API usage tracking:**
   - **Statistics:** search_calls, source_calls, cache_hits, watchmode_successes
   - **Reporting:** Displayed after each `generate_data.py` run
   - **Metrics:** Cache hit rate, Watchmode success rate
   - **Purpose:** Monitor API usage to ensure staying within free tier limits

**API limits and sustainability:**
- **Free tier:** 1,000 requests/month
- **Full regeneration:** 456 API calls (228 movies × 2 calls each) = 45.6% of limit
- **Daily automation:** ~10 calls/day for new movies = ~300 calls/month
- **Total monthly usage:** ~756 calls (75.6% of limit) with 244-request buffer
- **Sustainability:** ✅ Well under free tier limit with cache in place

**Implementation status:**
- ✅ Backend integration complete (`generate_data.py` lines 197-400)
- ✅ Cache system operational
- ✅ Statistics tracking implemented
- ✅ Fallback hierarchy working
- ✅ `argparse` support for `--full` flag testing
- ✅ Search fallbacks removed - hard links only (2025-10-17)
- ⏳ Frontend three-button UI (STREAM/RENT/BUY)
- ✅ Agent-based link finding for null links (AMENDMENT-039)

**Reference implementation:**
- File: `generate_data.py`
- Method: `get_watch_links()` (lines 197-400)
- Cache handling: `load_cache()` and `save_cache()` (lines 60-69)
- Statistics: `watchmode_stats` dictionary (lines 27-33)
- Migration: `_migrate_legacy_cache_format()` (lines 407-424)

### AMENDMENT-039: Agent-Based Link Finding for Streaming Platforms

**Rationale:**

Watchmode API provides excellent coverage for most streaming platforms, but has gaps for certain services (Netflix, Disney+, HBO Max, Hulu) where it returns no data. These platforms don't have predictable URL patterns that can be constructed programmatically. Users need direct links to these platforms, not search URLs or null links.

**Problem:**
- Watchmode API returns no data for ~10-20% of movies on Netflix, Disney+, HBO Max, Hulu
- These platforms require internal IDs that can't be predicted from TMDB data
- Current fallback returns `link: null`, forcing users to manually search
- User experience is degraded for popular streaming services

**Solution:**

Implement agent-based scraping as a third tier in the watch links system:
1. **Tier 1:** Watchmode API deep links (primary, fastest)
2. **Tier 2:** Agent scraping for Netflix/Disney+/HBO Max/Hulu (fallback, slower)
3. **Tier 3:** Return `null` if both fail (last resort)

**Technical Implementation:**

1. **New module:** `agent_link_scraper.py`
   - `AgentLinkScraper` class manages Selenium browser lifecycle
   - Platform-specific scrapers: `NetflixScraper`, `DisneyPlusScraper`, `HBOMaxScraper`, `HuluScraper`
   - Each scraper navigates to platform search, finds movie, extracts watch page URL
   - Headless Chrome with user-agent spoofing to avoid bot detection

2. **Integration point:** `generate_data.py` `get_watch_links()` method
   - After Watchmode API fails for streaming category
   - Before returning `{service: X, link: None}`
   - Only for supported platforms: Netflix, Disney+, HBO Max, Hulu
   - Does NOT scrape rent/buy categories (Watchmode has good coverage)

3. **Cache system:** `cache/agent_links_cache.json`
   - Structure: `{movies: {movie_id: {streaming: {service, link}, scraped_at, source, success}}}`
   - Separate from `watch_links_cache.json` to avoid mixing sources
   - Cache-first approach: check cache before launching browser
   - No automatic invalidation (links are stable)

4. **Rate limiting:**
   - Minimum 2-second delay between scrapes
   - Prevents anti-bot detection
   - Backoff to 5 seconds on errors

5. **Error handling:**
   - Graceful degradation: agent failures return `null` (not fake URLs)
   - Browser crashes disable agent for remainder of run
   - Timeouts (10 seconds per page load)
   - All errors logged but don't crash generation

**Performance Impact:**

- **First run:** Adds 2-3 seconds per scraped movie (~5-10 minutes for full regeneration)
- **Cached runs:** No performance impact (cache hits)
- **Daily automation:** Only scrapes new movies (~5-10 per day, ~30 seconds added)
- **Browser reuse:** Single Selenium instance reused across all movies (saves 5-10 seconds per movie)

**API Usage:**

- **No API calls:** Agent scraping doesn't use external APIs
- **Selenium only:** Uses headless Chrome to navigate public websites
- **Low volume:** ~5-10 scrapes per day (new movies only)
- **Respectful:** 2-second delays, realistic user-agent, no aggressive scraping

**Supported Platforms:**

- **Netflix** - `https://www.netflix.com/title/{id}`
- **Disney+** - `https://www.disneyplus.com/movies/{slug}/{id}`
- **HBO Max/Max** - `https://www.max.com/movies/{slug}/{id}`
- **Hulu** - `https://www.hulu.com/movie/{slug}/{id}`

**Not Supported (Watchmode has good coverage):**
- Amazon Prime Video (predictable URLs)
- Apple TV+ (predictable URLs)
- Paramount+, Peacock, MUBI, etc. (Watchmode coverage sufficient)

**Statistics Tracking:**

- `agent_attempts`: Number of times agent scraper was called
- `agent_successes`: Number of successful link extractions
- `agent_cache_hits`: Number of cache hits (no scraping needed)
- Displayed after each `generate_data.py` run

**Implementation Status:**

- ✅ `agent_link_scraper.py` module created
- ✅ Integration into `generate_data.py`
- ✅ Cache system operational
- ✅ Rate limiting implemented
- ✅ Error handling and graceful degradation
- ✅ Statistics tracking
- ⏳ Testing in production environment
- ⏳ Monitoring for anti-scraping issues

**Future Enhancements:**

- Proxy support for IP rotation (if rate limiting becomes issue)
- Parallel scraping with multiple browser instances
- Machine learning to predict URL patterns
- Alternative APIs as they become available

**Terms of Service Considerations:**

Web scraping may violate platform Terms of Service. This feature:
- Is **optional** (can be disabled by not initializing agent)
- Uses **low volume** (5-10 scrapes per day)
- Is **non-commercial** (personal project)
- Uses **respectful delays** (2+ seconds between requests)
- **Does not bypass paywalls** (only finds public watch page URLs)

Users should be aware of potential ToS violations and use responsibly.

**Rollback Plan:**

If agent scraping causes issues:
1. Comment out agent initialization in `generate_data.py`
2. System falls back to Watchmode-only behavior
3. No data loss (agent is additive)

**Reference Implementation:**

- File: `agent_link_scraper.py`
- Integration: `generate_data.py` lines 197-402 (modified)
- Cache: `cache/agent_links_cache.json`
- Statistics: `generate_data.py` lines 629-640 (extended)

### AMENDMENT-040: Agent Scraper Debugging and Fixes (Oct 17, 2025)

**Problem Discovered:**

Agent scraper was integrated on Oct 16 but never successfully executed. All Netflix/Disney+/Hulu links in data.json remain null despite integration.

**Root Causes Identified:**

1. **Cache Directory Gitignored:**
   - `.gitignore` line 7 excludes `cache/` directory
   - Cache created on Oct 16 but lost when pulling from GitHub
   - Agent scraper can't save results without cache directory
   - Solution: Add `cache/.gitkeep` to track directory structure in git

2. **Incremental Mode Skips Existing Movies:**
   - Daily automation runs `python3 generate_data.py` (incremental mode)
   - Incremental mode only processes NEW movies (lines 706-708)
   - All 236 existing movies have null watch_links from before agent scraper existed
   - Agent scraper never called for existing movies
   - Solution: Run `python3 generate_data.py --full` to reprocess all movies

3. **Config Not Read:**
   - `config.yaml` has `agent_scraper` section with enabled flag and settings
   - `generate_data.py` `load_config()` only reads `api` section (line 55-56)
   - Agent scraper settings (enabled, headless, rate_limit) are ignored
   - Solution: Update `load_config()` to load entire config.yaml structure

4. **Missing Dependencies:**
   - `requirements.txt` lacks selenium and webdriver-manager
   - GitHub Actions installs them manually (line 26 of workflow)
   - Local development fails with ImportError
   - Solution: Add selenium, webdriver-manager to requirements.txt

5. **No Execution Evidence:**
   - No `cache/agent_links_cache.json` file exists
   - No log messages indicating agent scraper ran
   - No statistics showing agent attempts
   - Conclusion: Agent scraper never successfully executed

**Fixes Implemented:**

1. **Enhanced Debug Logging:**
   - Added comprehensive logging to `agent_link_scraper.py` throughout all methods
   - Added logging to `generate_data.py` `_init_agent_scraper()` and `_try_agent_scraper()`
   - Added `--debug` flag to enable verbose output
   - Helps trace execution path and identify failure points

2. **Cache Directory Persistence:**
   - Created `cache/.gitkeep` to track directory in git
   - Cache JSON files remain gitignored (correct behavior)
   - Directory now persists across git pull operations

3. **Config Reading:**
   - Updated `load_config()` to load entire config.yaml (not just api section)
   - Updated `_init_agent_scraper()` to respect `agent_scraper.enabled` flag
   - Added check for selenium availability before initialization
   - Added full stack trace on initialization failure

4. **Dependencies:**
   - Added selenium, webdriver-manager, beautifulsoup4, lxml to requirements.txt
   - Matches GitHub Actions dependency list
   - Enables local development without manual dependency installation

5. **Testing Infrastructure:**
   - Created `test_agent_scraper.py` for standalone testing
   - Tests each platform scraper in isolation
   - Provides clear success/failure summary
   - Can run in visible mode (--headless flag) for debugging

**Next Steps:**

1. **Test standalone:** Run `python3 test_agent_scraper.py` to verify Selenium works
2. **Fix selectors:** Update CSS selectors if platforms changed their HTML
3. **Full regeneration:** Run `python3 generate_data.py --full` to process all movies
4. **Verify results:** Check data.json for non-null Netflix/Disney+/Hulu links
5. **Monitor cache:** Verify `cache/agent_links_cache.json` is created and populated

**Performance Impact:**

- **First full run:** ~10-15 minutes (2-3 seconds per movie × ~50 Netflix/Disney+/Hulu movies)
- **Subsequent runs:** ~2-3 minutes (cache hits, no scraping)
- **Daily automation:** ~30 seconds (only new movies, ~5-10 per day)

**Monitoring:**

- Agent statistics now show enabled/initialized status
- Debug logging traces complete execution path
- Standalone test provides quick verification

**Status:**

- ⏳ Debug logging added
- ⏳ Dependencies fixed
- ⏳ Cache directory persistence fixed
- ⏳ Config reading fixed
- ⏳ Testing infrastructure created
- ⏳ Awaiting full regeneration test
- ⏳ Awaiting Selenium selector verification

### AMENDMENT-041: Playwright Migration for Agent Scraper (Oct 17, 2025)

**Problem:**

Selenium-based agent scraper had 0% success rate despite being properly integrated. Analysis of `cache/agent_links_cache.json` showed 41 scraping attempts, all failed with `"success": false`. Root cause: CSS selectors are outdated and don't match current Netflix/Disney+/HBO Max/Hulu HTML structures.

**Solution:**

Migrate agent scraper from Selenium to Playwright with enhanced reliability features:

1. **Playwright Advantages:**
   - Faster page loads (WebSocket protocol vs HTTP)
   - Built-in auto-wait (reduces timing-related failures)
   - Better error messages (shows what was found vs expected)
   - Modern API with better selector handling
   - Trace viewer for debugging (can replay exact browser state)

2. **Selector Fallback Strategy:**
   - Each platform has 4-6 selector fallbacks (ordered by reliability)
   - Try selectors sequentially until one matches
   - Track which selector succeeded (for monitoring)
   - Example: Netflix tries `.title-card a`, `[data-uia='title-card'] a`, `.search-result a`, `a[href*='/title/']`, etc.

3. **Exponential Backoff Retry:**
   - Retry failed scrapes up to 3 times (configurable)
   - Delays: 0.5s, 1s, 2s (exponential with jitter)
   - Handles transient network issues and page load delays
   - Jitter prevents thundering herd in CI

4. **Screenshot Capture on Failure:**
   - Saves screenshot + HTML when scraping fails
   - Location: `cache/screenshots/{movie_id}_{service}_{timestamp}.png`
   - Provides visual proof of what page looked like
   - Auto-delete after 7 days (configurable)
   - Can be disabled in CI via config

5. **Enhanced Cache Schema:**
   - Added `expires_at`: Cache entries expire after 30 days
   - Added `retry_count`: Tracks number of retry attempts
   - Added `last_error`: Error message from final attempt
   - Added `screenshot`: Path to failure screenshot
   - Added `selector_used`: Which selector succeeded (for monitoring)
   - Backward compatible: Old cache entries remain valid

**Technical Implementation:**

1. **Dependencies:**
   - Added `playwright` to `requirements.txt`
   - Installation: `pip install playwright && playwright install chromium`
   - Chromium browser binary: ~100MB download
   - Keep Selenium temporarily for other scrapers (YouTube, RT, Wikipedia)

2. **Code changes:**
   - Complete rewrite of `agent_link_scraper.py` (Selenium → Playwright sync API)
   - Updated `generate_data.py` to check for Playwright instead of Selenium
   - Pass full config dict to AgentLinkScraper (not just headless flag)
   - Updated `test_agent_scraper.py` dependency checks

3. **Configuration (config.yaml):**
   ```yaml
   agent_scraper:
     enabled: true
     headless: true
     rate_limit: 2.0
     timeout: 10
     max_retries: 3  # Increased from 1
     cache_ttl_days: 30  # NEW
     screenshots_enabled: true  # NEW
     screenshot_retention_days: 7  # NEW
     exponential_backoff:  # NEW
       base_delay: 0.5
       max_delay: 5.0
       jitter_ratio: 0.2
   ```

4. **CI/CD (GitHub Actions):**
   - Added step: `playwright install chromium --with-deps`
   - Updated dependencies: Added `playwright` to pip install
   - Keep Chrome setup for Selenium-based scrapers

**Performance Impact:**

- **Selenium (before):** ~20s per movie, 0% success rate
- **Playwright (after):** Expected ~10-15s per movie, 70-80% success rate
- **With cache:** ~0.1s per movie (cache hit)
- **First full run:** ~10-15 minutes (scraping ~50 Netflix/Disney+/Hulu movies)
- **Daily automation:** ~30 seconds (only new movies, ~5-10 per day)

**Selector Maintenance:**

- Selectors documented in code with last-verified dates
- Test script (`test_agent_scraper.py`) provides quick verification
- `--debug-selectors` flag shows which selectors matched
- Screenshots provide visual evidence when selectors break
- Expected maintenance: Update selectors every 3-6 months as platforms change HTML

**Rollback Plan:**

1. **Keep Selenium version:** Rename current `agent_link_scraper.py` to `agent_link_scraper_selenium.py` before migration
2. **Disable agent scraper:** Set `agent_scraper.enabled: false` in config.yaml
3. **Revert dependencies:** Remove `playwright` from requirements.txt and CI workflow
4. **No data loss:** Cache format is backward compatible

**Implementation Status:**

- ✅ Playwright migration completed
- ✅ Selector arrays implemented (6 selectors per platform)
- ✅ Exponential backoff implemented
- ✅ Screenshot capture implemented
- ✅ Cache schema enhanced
- ✅ Testing infrastructure updated
- ✅ CI workflow updated
- ⏳ Awaiting selector discovery via manual platform inspection
- ⏳ Awaiting full regeneration test

**Success Criteria:**

- Agent scraper success rate > 70% (currently 0%)
- Netflix links found for majority of Netflix movies
- Screenshots captured for all failures
- Cache entries have expiration dates
- No crashes or hangs during generation
- CI workflow completes successfully with Playwright

**Reference:**

- File: `agent_link_scraper.py` (Playwright-based rewrite)
- Config: `config.yaml` lines 20-39 (enhanced settings)
- Test: `test_agent_scraper.py` (adapted for Playwright)
- Cache: `cache/agent_links_cache.json` (enhanced schema)
- Screenshots: `cache/screenshots/` (failure diagnostics)

### AMENDMENT-042: RT Scraper Integration and Inlining (Oct 17, 2025)

**Background:**

RT scraper existed in two versions:
1. Root `rt_scraper.py` (old, 129 lines) - No cache management, used by standalone scripts
2. `scripts/rt_scraper.py` (new, 183 lines) - Cache management, lazy init, already integrated into generate_data.py

The scripts version was already integrated (line 17 import, lines 318-323 usage) but existed as a separate class. This amendment inlines the logic into DataGenerator to match the Wikipedia scraping pattern.

**Changes Implemented:**

1. **Inlined RT Scraping Logic:**
   - Removed `from scripts.rt_scraper import RTScraper` import
   - Added `_init_rt_driver()` method to DataGenerator for lazy Selenium initialization
   - Added `_rt_rate_limit()` method for enforcing 2-second delays between scrapes
   - Added `_scrape_rt_page(title, year)` method with scraping logic from scripts/rt_scraper.py
   - Added `_save_rt_cache()` method for cache persistence
   - Updated `find_rt_url()` to call inlined methods instead of external class

2. **Rate Limiting:**
   - Tracks last scrape time in `self.rt_last_scrape_time`
   - Enforces minimum 2-second delay between scrapes (not just page loads)
   - Prevents anti-bot detection from rapid requests
   - Configurable via `config.yaml` `rt_scraper.rate_limit`

3. **Statistics Tracking:**
   - Added `rt_attempts`, `rt_successes`, `rt_cache_hits` to watchmode_stats
   - Tracks RT scraper usage similar to agent scraper
   - Displays statistics at end of generation run
   - Helps monitor scraper effectiveness and cache hit rate

4. **Selector Fallbacks:**
   - Search results: 3 selectors (primary + 2 fallbacks)
   - Score extraction: 4 selectors (primary + 3 fallbacks)
   - Resilient to RT website HTML changes
   - Logs which selector succeeded (for monitoring)

5. **Driver Cleanup:**
   - Added RT driver cleanup to `generate_display_data()` method
   - Ensures Selenium browser is closed at end of run
   - Prevents zombie Chrome processes

**Waterfall Priority (Unchanged):**

1. RT overrides (`overrides/rt_overrides.json`) - Manual curator fixes
2. RT cache (`rt_cache.json`) - Previously scraped results
3. RT scraper (NEW - inlined) - Selenium-based scraping
4. RT search URL - Fallback when scraping fails

**Score Extraction Status (Oct 18, 2025 - Verification Complete):**
- ✅ Implemented in `_scrape_rt_page()` method (generate_data.py:181-291)
- ✅ 6 selector fallbacks for score elements (lines 244-251)
- ✅ Regex pattern `r'(\d+)%'` extracts percentage scores (line 261)
- ✅ Cached in rt_cache.json with 90-day TTL
- ✅ Rate limiting enforced (2-second delays between scrapes)
- ✅ Integrated into waterfall at tier 4 (line 630)
- ✅ Test results: 100% success rate on 4 test cases (including live scraping)
- ✅ Current coverage: 72.9% (172/236 entries have scores)
- ⚠️ Selectors working correctly (extracted 89% for "The Substance", 82% for random movie)
- 📊 Target coverage: 85-90% (achievable with full regeneration)

**Cache Structure:**

- **File:** `rt_cache.json`
- **Key:** `{title}_{year}` (e.g., "Landmarks_2025")
- **Value:** `{url: string, score: string}` or `null` for failures
- **Format:** Same as before (backward compatible)
- **TTL:** 90 days (RT links are stable)

**Performance Impact:**

- **Cache hit:** ~0ms (instant return)
- **Fresh scrape:** ~6-8 seconds (2s rate limit + 2s search + 2s movie page)
- **Full regeneration:** Adds ~2-3 minutes if 20-30 movies need RT scraping
- **Daily automation:** Adds ~30-60 seconds (5-10 new movies per day)

**Configuration (config.yaml):**

```yaml
rt_scraper:
  enabled: true
  headless: true
  rate_limit: 2.0
  timeout: 10
  max_retries: 1
  cache_ttl_days: 90
```

**Files Deprecated:**

- `scripts/rt_scraper.py` - Logic moved into generate_data.py
- Root `rt_scraper.py` - Old version, replaced by scripts version
- `update_rt_data.py` - No longer needed (RT scraping is automatic)
- `bootstrap_rt_cache.py` - No longer needed (RT scraping is automatic)

These files will be archived to `museum_legacy/` in subsequent phase.

**Testing:**

- Created `test_rt_scraper_inline.py` for standalone verification
- Tests cache hits, fresh scrapes, rate limiting, error handling
- Verifies statistics tracking
- Tests with known movies: "Landmarks", "Inspector Zende", "The Substance"

**Rollback Plan:**

- If issues arise, revert to external RTScraper class from scripts/rt_scraper.py
- Restore import and external class usage
- No data loss (RT scraping is additive)

**Implementation Status:**

- ✅ RT scraping logic inlined into generate_data.py
- ✅ Rate limiting implemented
- ✅ Statistics tracking added
- ✅ Driver cleanup added
- ✅ Configuration added to config.yaml
- ⏳ Selector verification with current RT website
- ⏳ Testing with known movies
- ⏳ Full regeneration test

**Success Criteria:**

- RT scraper success rate > 80% (RT has good search functionality)
- Rate limiting enforced (2-second minimum delays)
- Statistics show accurate counts
- No crashes or hangs during generation
- Cache properly updated after scrapes

### AMENDMENT-043: Bulletproof Daily Automation with Separate Branch Strategy (Oct 17, 2025)

**Problem:**

Daily automation was causing merge conflicts when user worked locally during the day:
- Bot and user both commit to `main` branch
- Git conflicts occur when both modify `data.json` or `movie_tracking.json`
- User must manually resolve conflicts every morning
- `git push` can fail silently in GitHub Actions (workflow shows green but push failed)
- Incremental mode only processes NEW movies (existing 235 movies never get agent scraper links)

**Solution:**

Implement separate branch strategy where bot and user never write to same branch simultaneously:

**Architecture:**
- **main branch:** User works here (commits, pushes, pulls)
- **automation-updates branch:** Bot force-pushes here (always succeeds, never conflicts)
- **Sync mechanism:** User runs `./sync_daily_updates.sh` to merge automation data when ready
- **Weekly full regen:** Sunday full regeneration ensures all movies get retroactive improvements

**Implementation:**

1. **Daily Automation (.github/workflows/daily-check.yml):**
   - Checkout main branch (start from user's latest work)
   - Run pipeline: movie_tracker.py daily → generate_data.py (incremental)
   - Validate data quality (minimum 200 movies check)
   - Create/switch to automation-updates branch: `git checkout -B automation-updates`
   - Force-push to automation-updates: `git push --force origin automation-updates`
   - On failure: Create GitHub issue with workflow run URL

2. **Weekly Full Regeneration (.github/workflows/weekly-full-regen.yml):**
   - Trigger: Sunday at 10 AM UTC (2 AM PDT)
   - Checkout main branch
   - Run: `python3 generate_data.py --full` (reprocess ALL movies)
   - Validate data quality
   - Force-push to automation-updates branch
   - On failure: Create GitHub issue

3. **User Sync Script (sync_daily_updates.sh):**
   - Fetch automation-updates branch
   - Show what changed (git diff --stat)
   - Merge into main branch
   - Show latest movies added
   - Handle merge conflicts gracefully

4. **Data Quality Validation (daily_orchestrator.py):**
   - Check data.json exists and is valid JSON
   - Verify minimum 200 movies (prevents data loss)
   - Verify at least 1 movie from last 7 days (ensures discovery working)
   - Sample movies for required fields (title, digital_date, poster)
   - Check watch links coverage (some movies should have links)

**Benefits:**

- ✅ **No merge conflicts:** Bot and user never write to same branch
- ✅ **Bot always succeeds:** Force-push never fails
- ✅ **User control:** Merge automation data when ready (not forced)
- ✅ **Data quality:** Validation prevents committing broken data
- ✅ **Failure visibility:** GitHub issues created automatically
- ✅ **Retroactive improvements:** Weekly full regen populates agent scraper links for all movies
- ✅ **Easy rollback:** Don't merge automation-updates if something looks wrong

**Workflow:**

**Daily (Automated):**
1. 9 AM UTC: GitHub Actions runs daily automation
2. Bot: Discovers new movies, updates tracking database
3. Bot: Generates data.json (incremental mode - only new movies)
4. Bot: Validates data quality (minimum 200 movies)
5. Bot: Force-pushes to automation-updates branch
6. Bot: Creates GitHub issue if any step fails

**Daily (User):**
1. Morning: Run `./sync_daily_updates.sh` to merge automation data
2. Review: Check what changed (git diff output)
3. Merge: Automation data merged into main
4. Work: Make changes, test locally
5. Commit: Push changes to main
6. Next day: Repeat

**Weekly (Automated):**
1. Sunday 10 AM UTC: GitHub Actions runs weekly full regeneration
2. Bot: Reprocesses ALL 235 movies (not just new ones)
3. Bot: Agent scraper populates Netflix/Disney+/Hulu links for existing movies
4. Bot: RT scraper updates scores for movies that got reviews
5. Bot: Validates data quality
6. Bot: Force-pushes to automation-updates branch (overwrites daily incremental)
7. User: Merges weekly regen on Monday morning (preferred over daily incremental)

**Performance Impact:**

- **Daily automation:** 3-5 minutes (incremental mode, only new movies)
- **Weekly full regen:** 15-20 minutes (first run with agent scraper), 5-10 minutes (subsequent runs with cache)
- **User sync:** <1 second (just git merge)

**Failure Handling:**

- **Validation failure:** Workflow stops, no commit/push, GitHub issue created
- **Scraper failure:** Graceful degradation (returns null links), workflow continues
- **Git push failure:** Impossible (force-push always succeeds)
- **Merge conflict:** User runs `git merge --abort` and regenerates data.json

**Configuration:**

No new configuration needed. Uses existing:
- `config.yaml` for agent_scraper and rt_scraper settings
- Environment variables for API keys
- GitHub Actions secrets (none needed - uses default GITHUB_TOKEN)

**Testing:**

1. **Test daily automation:**
   - Trigger workflow manually
   - Verify automation-updates branch created
   - Verify force-push succeeded
   - Verify data quality validation passed

2. **Test weekly full regen:**
   - Trigger workflow manually
   - Verify --full flag is used
   - Verify all movies reprocessed
   - Verify agent scraper links populated

3. **Test sync script:**
   - Run `./sync_daily_updates.sh`
   - Verify merge succeeds
   - Verify latest movies shown

4. **Test failure notification:**
   - Temporarily break generate_data.py
   - Trigger workflow
   - Verify GitHub issue created
   - Fix and verify issue can be closed

**Rollback Plan:**

- If separate branch strategy causes issues:
  1. Revert daily-check.yml to push to main (remove force-push)
  2. Delete automation-updates branch
  3. Delete sync_daily_updates.sh
  4. Keep data quality validation (still useful)
  5. Accept merge conflicts (original problem returns)

**Implementation Status:**

- ✅ Daily automation modified for automation-updates branch
- ✅ Weekly full regeneration workflow created
- ✅ User sync script created
- ✅ Data quality validation added
- ✅ Failure notifications implemented
- ✅ Workflows deployed to .github/workflows/
- ⏳ Awaiting first automated run to verify functionality

**Success Criteria:**

- Zero merge conflicts for user
- Bot automation succeeds 100% of time (force-push)
- Data quality maintained (minimum 200 movies)
- Failures are visible (GitHub issues)
- Weekly full regen populates agent scraper links
- User can review automation changes before merging

---

### AMENDMENT-044: Authentication Token Management

**Date:** October 19, 2025
**Author:** Assistant (reconstruction session)
**Category:** Operational / Incident Management

**Context:**

OAuth token expiration during Oct 17 session prevented normal end-of-session workflow. This amendment documents the incident and establishes best practices for handling authentication failures.

**Incident Details:**

- **Error:** "API Error: 401 authentication_error - OAuth token has expired"
- **Impact:** Unable to commit changes through normal Claude Code workflow
- **Resolution:** User manually hit "commit changes" button and restarted extensions
- **Outcome:** Work was successfully committed (commit `0d7f978`), but documentation workflow was interrupted

**Lessons Learned:**

1. Authentication errors can interrupt end-of-session workflows
2. Manual commit button can serve as fallback when API fails
3. Diary archives may need retroactive creation after incidents
4. Work preservation takes priority over documentation completeness

**Best Practices Going Forward:**

1. **Monitor for authentication warnings** before end-of-session
2. **Refresh OAuth tokens proactively** (before expiration) when possible
3. **If authentication fails:** Use manual commit button as fallback
4. **Document incidents** in next session's diary
5. **Retroactive diary creation** is acceptable per AMENDMENT-036 (immutable historical record)

**Recovery Procedure:**

When authentication incident occurs:

1. **Check git log** to verify work was committed:
   ```bash
   git log --oneline -10
   ```

2. **Review git status** for uncommitted changes:
   ```bash
   git status
   ```

3. **Reconstruct diary entries** from DAILY_CONTEXT.md and commit messages

4. **Update DAILY_CONTEXT.md** to reflect actual state

5. **Create missing diary archives** retroactively with session-end notes

6. **Document incident** as amendment for future reference

**Key Principle:**

Work preservation takes priority. If authentication fails:
- FIRST: Save work via any available method (manual commit button)
- THEN: Reconstruct documentation in next session
- FINALLY: Update procedures to prevent recurrence

This amendment ensures future authentication incidents can be handled systematically without losing work or context.

## AMENDMENT-045: Admin Panel - Post-Publication Curation & Data Quality
**Date:** October 19-20, 2025
**Context:** Admin panel redesigned from basic editorial tool to comprehensive QA database editor

### Admin Panel Role - Post-Publication Curation

The admin panel is used for **post-publication curation** where movies are refined after they appear on the public site. Movies are **automatically visible** when discovered by automation unless explicitly hidden. The admin panel allows curators to hide unwanted movies, feature important releases, and fix incomplete data.

**Data Flow with Post-Publication Curation:**
```
Daily Scraper → movie_tracking.json → data.json → Public Site
                (all discovered)      (filtered)   (visitors)
                                         ↓
                                   ADMIN PANEL (post-publication curation)
                                   - Hide unwanted movies
                                   - Feature important releases
                                   - Fix incomplete data
```

### Default Visibility Model

Movies are **visible by default** (no approval required). The `apply_admin_overrides()` method in `generate_data.py` (lines 2197-2228) filters out movies in `admin/hidden_movies.json` during data generation. Admin uses "🚫 Hide" button to remove unwanted movies from public display and "⭐ Feature" button to highlight important releases.

**Rationale:** Publish-first model reduces friction, allows rapid discovery, and trusts automation with manual refinement.

### Inline Database Editing Capabilities

All movie fields are directly editable in the UI:
- **Digital release date** (date picker)
- **RT score** (0-100 number input)
- **RT link** (URL with test button 🔗)
- **Trailer link** (URL with play button ▶️)
- **Director** (text input)
- **Country** (text input)
- **Synopsis** (textarea)
- **Poster URL** (URL with TMDB button 🎬)
- **Watch links** - streaming/rent/buy (service + URL pairs)

**Save Mechanism:**
- Single "💾 Save All Changes" button per movie card
- Changes save directly to `movie_tracking.json` with `manual_*` flags
- Auto-regenerates `data.json` after save

### Missing Data Detection System

**"⚠️ Missing Data" Filter:**
- Shows all incomplete movies at once
- Badge displays count of movies needing attention (e.g., "93")
- Incomplete movies have:
  * Red left border
  * "⚠️ INCOMPLETE" badge in top-right corner
  * Red background on missing fields
  * Pink box listing exactly what's missing (RT Score, Trailer, Poster, Director, Country)
- Allows rapid quality control: click filter → scan flagged movies → fix or hide

### Manual Correction Tracking

All edits saved to `movie_tracking.json` with flags:
- `manually_corrected: true` (overall flag)
- `manual_rt_score: true`, `manual_rt_link: true`, etc. (field-specific flags)
- `last_manual_edit: "2025-10-19T..."` (timestamp)

**Protection:** Flags protect manual edits from being overwritten by daily scraper. Separate from UI preferences (hidden/featured stay in admin/*.json files).

### YouTube Playlist Integration

**"📺 Create YouTube Playlist" Feature:**
- Button in admin panel header
- Custom date parameters: "Last X Days" OR "From Date → To Date"
- Manual control (no automation) with dry-run preview mode
- Privacy settings (public/unlisted/private)
- Calls `youtube_playlist_manager.py` with custom parameters
- See `YOUTUBE_PLAYLIST_SETUP.md` for OAuth setup instructions

### Implementation Details

**File:** `admin.py` (Flask application on port 5555)

**Routes:**
- `/` - Main admin panel with inline editing UI
- `/update-movie-fields` - Saves all editable fields to movie_tracking.json
- `/create-youtube-playlist` - Creates YouTube playlists with custom dates
- `/toggle-hidden`, `/toggle-featured` - UI preference toggles
- `/regenerate` - Manual data.json regeneration trigger

**Authentication:** HTTP Basic Auth (default: admin/changeme)

**Frontend:** Embedded JavaScript with fetch API for AJAX operations

### Daily Curation Workflow

**Morning Routine:**
1. Open http://localhost:5555 (after automation has run)
2. Review new movies on public site to identify candidates for hiding/featuring
3. Click "⚠️ Missing Data (93)" to see incomplete movies
4. For each flagged movie:
   - Missing RT score only? → Wait (reviews coming)
   - Missing trailer/poster? → Check TMDB → Fix or Hide
   - Wrong director/country? → Edit field → Save
5. All fixed movies turn from RED to normal
6. Hidden movies removed from public site via regeneration

### Rationale

- **Scrapers are imperfect** - APIs have gaps, platforms change, data is incomplete
- **Post-publication curation** - Admin refines display after automation, rather than blocking publication
- **Publish-first model** - Reduces manual bottleneck, allows rapid discovery of new releases
- **Manual QA ensures quality** - Quality control through post-publication refinement
- **Inline editing efficiency** - Faster than editing JSON files manually
- **Visual indicators** - Red borders, badges make quality control efficient
- **Single save button** - Reduces cognitive load
- **Protected corrections** - Prevents automation from overwriting manual fixes

**Reference Files:**
- Implementation: `admin.py` (lines 1-1987)
- YouTube integration: `youtube_playlist_manager.py` (lines 573-662 for custom playlists)
- Setup guide: `YOUTUBE_PLAYLIST_SETUP.md`
- Related amendments: AMENDMENT-038 (Watchmode API), AMENDMENT-044 (Auth token management)

For detailed curation workflow and best practices, see `ADMIN_WORKFLOW.md`.

### AMENDMENT-046: Remove TMDB vote_count Filter for Discovery

**Date:** 2025-10-21

**Context:**
Discovery rate was too low (2 movies in 3 days). Analysis revealed the `vote_count.gte: 1` filter in `movie_tracker.py` was blocking brand-new releases with 0 TMDB votes.

**Decision:**
Remove the vote_count filter from both `discover_new_premieres` and `bootstrap` methods to allow discovery of movies with 0 votes.

**Rationale:**
1. **Vote count is unreliable for new releases:** Movies often have 0 votes for 1-3 days after premiere
2. **Provider availability is the real filter:** Movies without distribution deals never get providers, so they never appear on the wall
3. **90-day window is based on digital_date:** Long premiere-to-provider gaps don't cause movies to be missed
4. **Empirical approach:** Start wider, narrow later if needed based on actual results

**Implementation:**
- Modified: `movie_tracker.py` line 50 (discover_new_premieres method)
- Modified: `movie_tracker.py` line 97 (bootstrap method)
- Kept: `sort_by: 'primary_release_date.desc'` (chronological order)
- Kept: All other filters unchanged (date range, pagination)

**Expected impact:**
- Discovery rate: 10-20 movies/day (5-10x increase)
- Movies becoming digital: 2-5/day (unchanged)
- Total tracking: 600-900 movies after 1 month
- Movies on wall: 250-350 (unchanged, limited by 90-day window)

**Testing plan:**
- Day 1: Run discovery, document new movie count
- Day 2-3: Monitor discovery rates
- Day 4: Calculate 3-day average, assess quality
- Decision point: Keep filter removed or add alternative filters

**Alternative filters considered (rejected for now):**
- `popularity.desc` sorting - User prefers chronological
- `region: 'US'` filter - Would reduce results (user wants wider discovery)
- `with_release_type: '2|3'` - Would reduce results (user wants wider discovery)

**Monitoring criteria:**
- If spam/fake movies appear: Consider adding `vote_average.gte: 4.0` or popularity threshold
- If too many irrelevant movies: Consider adding region or release_type filters
- If discovery rate is still low: Investigate TMDB API parameters or date range

**Success criteria:**
- 3-day average discovery: 10-20 movies/day
- Quality maintained: No spam movies appearing on wall
- Provider filtering working: Only movies with distribution deals appear on wall

**Supersedes:** None (new amendment)

**Status:** ✅ Implemented, ⏳ Testing in progress

### AMENDMENT-047: Production Discovery Architecture

**Date:** 2025-10-22
**Severity:** Critical

**Problem:** Discovery system was fragmented between legacy `movie_tracker.py` and `generate_data.py`, leading to inconsistent behavior and maintenance complexity.

**Solution:** Complete consolidation to production discovery architecture.

**Production Flow (MANDATORY):**
```
daily_orchestrator.py
  ↓
generate_data.py --discover  (with bounded timeouts, retry logic, structured diagnostics)
  ↓
generate_data.py  (enrichment phase)
```

**Legacy System Status:**
- `movie_tracker.py` → **ARCHIVED** to `museum_legacy/legacy_movie_tracker.py`
- Use ONLY for historical reference and debugging
- **NEVER use in production pipeline**

**Discovery Features (Implemented):**
- Bounded timeouts: (10s connect, 30s read) with 3 retries
- Exponential backoff with jitter for rate limiting
- Structured diagnostics: per-page counts, duplicate tracking, sample titles
- Configuration-driven: Uses `config.yaml` `discovery` section only
- Daily metrics: Saves to `metrics/daily.jsonl` for 3-day baselining
- Debug mode: `--debug` flag for detailed logging

**Configuration:**
- Discovery settings: `config.yaml` → `discovery` section
- Deprecated: `api.max_pages_daily` (use `discovery.max_pages`)
- TLS fix: `urllib3<2` pinned in `requirements.txt`

**Baseline Monitoring:**
- Target: 3-day average discovery rate of 10-20 movies/day
- Metrics script: `scripts/baseline_metrics.py`
- Daily tracking: discovery count, newly-digital count, total tracking/available

**Testing:**
- Discovery: `python3 generate_data.py --discover --debug`
- Metrics: `python3 scripts/baseline_metrics.py`
- Full pipeline: `python3 daily_orchestrator.py`

**Supersedes:** AMENDMENT-046 (adds production implementation)

**Status:** ✅ Implemented and documented

### AMENDMENT-036: Implementation Roadmap Discipline (2025-10-14)

**Rationale:** The project requires disciplined tactical planning to systematically address prioritized issues and maintain implementation continuity across sessions.

**Rules Established:**

1. **Canonical Tactical Plan:** `IMPLEMENTATION_ROADMAP.md` serves as the single source of truth for all planned implementation work, complementing `PROJECT_CHARTER.md` (governance) and `PROJECT_LOG.md` (historical record).

2. **Update Requirements:** The roadmap must be updated:
   - When new issues are identified and prioritized
   - When implementation decisions are made
   - When status changes occur (Not Started → In Progress → Completed)
   - When dependencies or priorities shift

3. **Relationship to PROJECT_LOG.md:** The roadmap focuses on future work (what to do next), while PROJECT_LOG.md records completed work (what was done). Both reference each other for continuity.

4. **Priority Discipline:** Issues must be categorized by impact and urgency (Critical, High, Medium, Low, Future) with clear criteria for each level.

5. **Session Integration:** Each session should:
   - Review roadmap status at start
   - Update roadmap with new decisions and progress
   - Reference specific roadmap IDs in commit messages and log entries

This amendment aligns with AMENDMENT-001 (numbering discipline), AMENDMENT-006 (user safeguards), AMENDMENT-007 (session documentation), and FLATSHOT (consolidated governance updates).

### AMENDMENT-048: Watch Links Agent Search and Manual Override System

**Date:** 2025-10-22
**Severity:** Enhancement

**Problem:** Watchmode API has coverage gaps for very new releases (~30-50% of October 2025 movies), resulting in Google search fallbacks instead of direct deep links.

**Solution:** Two-tier enhancement: manual overrides + optional agent search.

**Manual Override System (Tier 1 - IMPLEMENTED):**
- **File:** `overrides/watch_links_overrides.json`
- **Structure:** `{"tmdb_id": {"streaming": {...}, "rent": {...}, "buy": {...}}}`
- **Priority:** Highest (checked before cache and Watchmode API)
- **Use Case:** High-priority movies, Watchmode gaps, platform-specific corrections
- **Workflow:** Manually find deep link → Add to overrides → Regenerate data.json
- **Integration:** Admin panel can edit this file (future enhancement)

**Agent Search System (Tier 2 - OPTIONAL):**
- **File:** `streaming_platform_scraper.py`
- **Class:** `StreamingPlatformScraper`
- **Platforms Supported:** Amazon Prime Video, Apple TV (Netflix/Disney+ skipped due to anti-bot)
- **Trigger:** When Watchmode API returns no data AND provider is Amazon/Apple TV
- **Process:** Search platform → Extract deep link → Cache with `source: 'agent_search'`
- **Performance:** ~5-10 seconds per movie, ~5-6 minutes for full regeneration
- **Maintenance:** Requires selector updates when platforms change UI (~1-2 hours/month)

**Complete Fallback Hierarchy:**
1. Manual watch links from `movie_tracking.json` - Highest priority
2. Manual overrides (`overrides/watch_links_overrides.json`) - Second priority
3. Admin overrides (`admin/watch_link_overrides.json`) - Backward compatibility
4. Cache (`cache/watch_links_cache.json`) - Third priority
5. Watchmode API - Fourth priority
6. Agent search (Amazon/Apple TV only) - Fifth priority (optional)
7. Platform search URLs - Sixth priority (fallback)
8. Amazon search - Ultimate fallback (default)

**Platform Deep Link Formats:**
- **Amazon:** `https://www.amazon.com/gp/video/detail/{ASIN}` or `https://watch.amazon.com/detail?gti=amzn1.dv.gti.{id}`
- **Apple TV:** `https://tv.apple.com/us/movie/{slug}/umc.cmc.{id}`
- **Netflix:** `https://www.netflix.com/title/{netflix_id}` (agent search not supported)

**Cache Source Types:**
- `manual_tracking`: Deep link from movie_tracking.json manual entry
- `manual_override`: Deep link from overrides/watch_links_overrides.json
- `watchmode_api`: Deep link from Watchmode API
- `agent_search`: Deep link from Selenium scraping (if implemented)
- `tmdb_fallback`: Platform search URL built from TMDB provider data

**Implementation Status:**
- ✅ Manual override system (simple, reliable)
- ✅ Agent search infrastructure (`streaming_platform_scraper.py`)
- ✅ Integration into fallback hierarchy
- ⏳ Admin panel integration (future enhancement)

**Usage Guidelines:**

**For Manual Overrides:**
- Add ~5-10 entries per day for movies lacking Watchmode data
- Verify links work before adding to overrides
- Use for high-priority releases or platform-specific corrections

**For Agent Search (if enabled):**
- Runs automatically during `generate_data.py`
- Only for Amazon and Apple TV (reliable platforms)
- Results are cached (no re-scraping)
- Graceful degradation if Selenium unavailable

**Configuration:**
- Agent search is optional (import handled gracefully)
- No configuration required for manual overrides
- Chrome WebDriver required for agent search functionality

**Supersedes:** No previous amendment (new functionality)

**Status:** ✅ Implemented and documented

## AMENDMENT-049: Bootstrap Date Accuracy & Data Quality Policy (2025-10-22)

**Context:** On 2025-09-06, the legacy movie tracker bootstrap process marked 50+ movies as "available" with `digital_date: 2025-09-06` (discovery date) instead of their actual digital release dates. This occurred because the legacy system set `digital_date = datetime.now()` when providers were first detected.

**Problem:** Movies with premiere dates in August 2025 showing September 6 digital dates are clearly inaccurate. This affects timeline accuracy and user trust.

**Solution Implemented:**

1. **Metadata Flagging:**
   - All bootstrap movies marked with `bootstrap_date: true` flag in `movie_tracking.json`
   - Flag propagated to `data.json` for frontend display
   - Visual indicator ("~" prefix or tooltip) shown on website
   - Admin panel highlights bootstrap movies for review

2. **Manual Correction Tools:**
   - Admin panel `/update-date` endpoint sets `manually_corrected: true`
   - `date_verification.py` provides interactive and batch correction tools
   - CSV import for bulk corrections after manual research
   - Corrected movies lose `bootstrap_date` flag

3. **Prevention:**
   - Current discovery system (integrated into `generate_data.py`) uses TMDB's `release_date` field
   - No longer sets `digital_date = today` when providers detected
   - Future movies will have accurate dates from TMDB

**Data Quality Policy:**

- **Transparency:** Bootstrap dates are flagged, not hidden
- **Gradual Correction:** High-profile titles corrected manually over time
- **Acceptable Uncertainty:** Low-profile titles may retain approximate dates
- **Audit Trail:** `manually_corrected` flag tracks admin interventions
- **Future Accuracy:** Prevention measures ensure new data is accurate

**Files Modified:**
- `movie_tracking.json` - Added `bootstrap_date` flag to affected movies
- `generate_data.py` - Propagates bootstrap metadata to display data
- `assets/app.js` - Displays visual indicator for bootstrap dates
- `assets/styles.css` - Styles bootstrap date indicator
- `admin.py` - Shows bootstrap movies in admin panel
- `date_verification.py` - Implements manual correction tools
- `scripts/flag_bootstrap_dates.py` - One-time flagging script

**Rationale:** Automated retroactive correction (via Reelgood scraping) proved unreliable. Manual correction of high-value titles is more practical than hiding 50+ movies or attempting fragile web scraping. Transparency about data quality builds user trust.

**Related:** See AMENDMENT-027 (Bootstrap Data Integrity) for original bootstrap documentation.

**Status:** ✅ Implemented and documented

## AMENDMENT-050: Review System for Newsletter Content (2025-10-22)

**Context:** Newsletter generation requires editorial content - custom reviews written by the curator to highlight notable releases and provide context beyond metadata.

**Implementation:**

1. **Review Storage:**
   - Reviews stored in `admin/movie_reviews.json`
   - Schema: `{movie_id: {review, author, rating, featured_in_newsletter, added_date, last_modified}}`
   - Follows admin override pattern (similar to hidden/featured movies)

2. **Admin Panel UI:**
   - Review section added to each movie card in admin panel
   - Fields: review text (textarea), author, rating (0-5), featured flag
   - Separate "Save Review" and "Delete Review" buttons
   - Review statistics in header (count of reviewed movies)
   - Filter button to show only reviewed movies

3. **Backend Routes:**
   - `/update-review` - POST endpoint to create/update reviews
   - `/delete-review` - POST endpoint to delete reviews
   - Atomic writes with backup management
   - Triggers data.json regeneration after changes

4. **Data Integration:**
   - `generate_data.py` loads reviews at initialization
   - Reviews included in `data.json` for each movie
   - Newsletter generator can access review data

5. **Review Workflow:**
   - Curator writes reviews in admin panel
   - Reviews saved to `admin/movie_reviews.json`
   - Data regeneration includes reviews in `data.json`
   - Newsletter generator features reviewed movies prominently
   - "Featured in newsletter" flag highlights top picks

**Schema Example:**
```json
{
  "1234567": {
    "review": "A haunting meditation on memory and loss...",
    "author": "Hadrian Belove",
    "rating": 4.5,
    "featured_in_newsletter": true,
    "added_date": "2025-10-22T14:30:00Z",
    "last_modified": "2025-10-22T14:30:00Z"
  }
}
```

**Files Modified:**
- `admin/movie_reviews.json` - Review storage (new file)
- `admin.py` - Review CRUD routes
- `admin/templates/index.html` - Review UI
- `admin/static/js/admin.js` - Review JavaScript handlers
- `generate_data.py` - Review data integration

**Rationale:** Editorial content is essential for newsletter value proposition. Reviews provide context, recommendations, and personality that distinguish the newsletter from automated aggregators. The inline admin UI keeps the workflow simple - curators can write reviews while browsing the movie list.

**Related:** Unblocks HIGH-002 (Newsletter Export) in `IMPLEMENTATION_ROADMAP.md`.

## AMENDMENT-051: Multi-Format Newsletter Generator (2025-10-22)

**Context:** With the review system in place (AMENDMENT-050), the project needs a newsletter generator to distribute weekly updates to subscribers. The generator must support multiple output formats for different distribution channels (Substack, email, social media).

**Implementation:**

1. **Script: `generate_newsletter.py`**
   - Standalone Python script (no external dependencies)
   - Reads `data.json` and `admin/movie_reviews.json`
   - Filters movies by configurable date range (default 7 days)
   - Groups movies by streaming platform (not genre)
   - Features reviewed movies prominently

2. **Output Formats:**
   - **Markdown** (`newsletter_YYYY-MM-DD.md`): Substack/blog-ready format
   - **HTML** (`newsletter_YYYY-MM-DD.html`): Email-friendly with inline styles
   - **Plain Text** (`newsletter_YYYY-MM-DD.txt`): Simple list for quick sharing

3. **Newsletter Sections:**
   - **Hero Review**: Featured movie with full review (first movie with `featured_in_newsletter: true`)
   - **This Week's Highlights**: 3-5 reviewed movies with excerpts
   - **By Platform**: Movies grouped by streaming service (Netflix, Amazon, Apple TV+, Disney+, Hulu, Max, etc.)
   - **Quick List**: Alphabetical reference of all movies with RT scores

4. **CLI Interface:**
   ```bash
   python3 generate_newsletter.py [--days N] [--format FORMAT] [--output-dir DIR]
   ```
   - `--days`: Number of days to look back (default 7)
   - `--format`: Output format (markdown, html, text, all)
   - `--output-dir`: Output directory (default current directory)

5. **Platform Grouping Logic:**
   - Extracts platforms from movie `providers` object (streaming, rent, buy)
   - Normalizes platform names ("Amazon Video" → "Amazon Prime Video")
   - Sorts platforms by movie count (most popular first)
   - Limits to top 10 movies per platform for readability

6. **Review Integration:**
   - Loads reviews from `admin/movie_reviews.json`
   - Matches reviews to movies by ID
   - Prioritizes movies with `featured_in_newsletter: true` for Hero Review
   - Includes review text, author, rating in all formats
   - Gracefully handles missing reviews (newsletter works without them)

7. **Error Handling:**
   - Fatal error if `data.json` missing (can't generate without data)
   - Warning if `admin/movie_reviews.json` missing (continues without reviews)
   - Skips movies with malformed dates (logs warning)
   - Uses defaults for missing fields ("Unknown Director", "No synopsis")
   - Prints helpful message if no movies in date range

**Design Decisions:**

- **New script vs. modifying existing:** Created new `generate_newsletter.py` instead of modifying `substack_newsletter_generator.py` because requirements differ significantly (platform grouping vs. genre, review integration, multiple formats)
- **Platform grouping vs. genre:** Aligns with user's "where to watch" focus and streaming-first audience
- **Three formats:** Supports different distribution channels (Substack, email, social media)
- **Hero Review section:** Showcases editorial content and incentivizes review writing
- **No external dependencies:** Uses only Python standard library for easy deployment

**Workflow Integration:**

1. Curator writes reviews in admin panel (`python3 admin.py`)
2. Marks top pick as "featured in newsletter"
3. Runs `python3 generate_newsletter.py` to generate all formats
4. Copies markdown to Substack or HTML to email client
5. Distributes to subscribers

**Files Created:**
- `generate_newsletter.py` - Newsletter generator script (~600-800 lines)

**Files Modified:**
- `README.md` - Added newsletter generation documentation
- `IMPLEMENTATION_ROADMAP.md` - Updated HIGH-002 status to resolved

**Rationale:** Multi-format output supports different distribution channels without requiring multiple tools. Platform grouping helps users find movies on their preferred services. Review integration provides editorial value beyond automated aggregation. Configurable date range enables both weekly and monthly newsletters.

**Related:** Completes HIGH-002 (Newsletter Export) in `IMPLEMENTATION_ROADMAP.md`. Depends on AMENDMENT-050 (Review System).

**Status:** ✅ Implemented and documented

## AMENDMENT-052: Unified Launcher for Daily Operations (2025-10-23)

**Context:** Users previously needed to remember three separate commands to launch different NRW tools: `./launch_NRW.sh` for the public site, `python3 admin.py` for the admin panel, and `python3 youtube_playlist_manager.py [args]` for YouTube management. This created friction for daily operations and onboarding new users to the project.

**Decision:** Create `launch_all.sh` as unified launcher with menu-driven interface. The launcher provides four menu options: (1) Public Site, (2) Admin Panel, (3) YouTube Manager, (4) All Services. Browser auto-open for web interfaces (site and admin), process management with graceful cleanup on Ctrl+C, and authentication reminder for admin panel access.

**Implementation:**

1. **Script: `launch_all.sh`**
   - Menu-driven interface with 5 options (1-4 plus Exit)
   - Reuses browser detection and port checking logic from `launch_NRW.sh`
   - Tracks PIDs for all launched processes with cleanup function
   - Registered cleanup with `trap` for EXIT, INT, TERM signals
   - YouTube manager integrated as interactive CLI (not background service)

2. **Menu Options:**
   - **Option 1: Public Site** - HTTP server on port 8000/8001, auto-open browser
   - **Option 2: Admin Panel** - Flask server on port 5555, auth reminder, auto-open browser
   - **Option 3: YouTube Manager** - Interactive CLI with common commands listed
   - **Option 4: All Services** - Launch site + admin simultaneously, both auto-open
   - **Option 5: Exit** - Clean shutdown

3. **Process Management:**
   - Global variables: `SITE_PID`, `ADMIN_PID`, `YOUTUBE_PID`
   - Cleanup function checks if PIDs exist and running with `kill -0`
   - Graceful shutdown with `kill $PID` for each service
   - Automatic cleanup on script exit or Ctrl+C

4. **Authentication Reminder:**
   - Displays credentials box when launching admin panel (options 2 or 4)
   - Shows default username/password and reference to `PROJECT_CHARTER.md`
   - Security note about changing defaults in production

5. **Browser Integration:**
   - Detects `open` (macOS) or `xdg-open` (Linux)
   - Auto-opens URLs for web interfaces, displays URLs if no opener available
   - Staggered browser opens for option 4 (site first, admin after 1 second)

6. **Error Handling:**
   - Port availability checking using `lsof`
   - Dependency validation (python3, git required)
   - Graceful fallbacks for missing tools (`lsof`, browser opener)
   - Clear error messages for port conflicts

**Design Decisions:**

- **Menu-driven vs. command-line flags:** Menu interface is more discoverable for new users and reduces cognitive load
- **Process management:** Track all PIDs to ensure complete cleanup and prevent orphaned processes
- **Staggered launches:** 2-second delay between services to avoid port conflicts and startup races
- **YouTube CLI integration:** Interactive prompt for commands rather than background service (matches its CLI nature)
- **Browser auto-open:** Automatic for web interfaces, manual for CLI tools
- **Authentication prominence:** Large box display for admin credentials to reduce login friction
- **Backward compatibility:** Original scripts (`launch_NRW.sh`, `admin.py`) remain unchanged and supported

**Files Created:**
- `launch_all.sh` - Unified launcher script (~430 lines)

**Files Modified:**
- `README.md` - Updated Quick Start section, added comprehensive Unified Launcher documentation
- `DAILY_CONTEXT.md` - Added launcher to Quick Reference section, updated admin panel instructions
- `PROJECT_CHARTER.md` - This amendment

**Usage:**

Primary command: `./launch_all.sh`
Recommended for daily work: Select option 4 (All Services)
YouTube manager: Select option 3 for interactive CLI
Direct launches still supported for automation/scripting

**Related Files:**
- `launch_all.sh` - Unified launcher (new)
- `launch_NRW.sh` - Public site launcher (existing, still supported)
- `admin.py` - Admin panel (existing, still supported)
- `youtube_playlist_manager.py` - YouTube CLI (existing, still supported)

**Rationale:** Improved user experience with single entry point for all tools eliminates need to remember multiple commands. Menu interface aids discovery and onboarding. Option 4 (All Services) optimizes daily workflow by launching both site and admin simultaneously. Process management prevents orphaned processes. Authentication reminder reduces admin panel friction. Maintains backward compatibility for automation and scripting use cases.

**Status:** ✅ Implemented and documented
