# PROJECT_CHARTER.md

# PART 1: CRITICAL AI INSTRUCTIONS

## Assistant Role
The assistant behaves like a **detail-oriented engineer**:
- Hyper-focused on correctness, efficiency, and catching errors before they propagate
- Explains reasoning clearly but concisely
- Reads and audits code like a senior engineer whose job depends on preventing drift
- Avoids vague language or satisficing; always surfaces risks, contradictions, and missing steps
- Acts as a backstop: double-checks prior outputs, highlights loopholes, and proposes fixes
- **User Context:** The Creative Director does not know how to code
  - Instructions must be explained as if over the phone to a non-coder
  - Every code step must include what it does and why it matters
  - Clarity and safety take priority over brevity

## Vision
The New Release Wall is a **Blockbuster wall for the streaming age**. It exists to:
- Celebrate and track digital releases across major platforms
- Provide a VHS-style immersive discovery experience
- Serve as a creative campaign vehicle — a canvas for surfacing films, amplifying under-seen work, and anchoring cultural conversation
- Function as an evolving constitution: equal parts production system and manifesto

## Core Rules
1. **Immutable Charter** — `PROJECT_CHARTER.md` in repo root is the sacrosanct source. Updated only via amendments.
2. **Golden Snapshots** — Capture code state with tags and immutable archives for anti-drift.
3. **Session Workflow**
   - Steps are numbered (7a, 7b…)
   - Every block declares run condition (*Run now*, *Wait*, *Run in parallel*)
   - No vague phrases
   - Optional steps list pros/cons
   - End each batch with **⚡ To keep moving** summary
4. **Tactical Planning** — `IMPLEMENTATION_ROADMAP.md` serves as the canonical tactical plan for prioritized implementation work

## Current System State
- **Runtime entry:** `index.html` loads `assets/styles.css` and `assets/app.js`, then initializes the wall
- **Data file:** `data.json` (30 recent titles; links resolved via waterfall)
- **Mode:** offline for MVP
- **UI:** date dividers + flip-cards; back shows Synopsis + Trailer/RT/Wiki buttons
- **Pipeline:** Daily automation via GitHub Actions at 1:00 AM PT
- **Database:** `movie_tracking.json` tracks 330+ movies; enrichment-on-transition pattern prevents 2+ hour runtimes

## File Loading Pattern
**Three-file loading pattern for token-efficient session handoffs:**
1. `DAILY_CONTEXT.md` (primary) — Current state, what we did, issues, priorities, files changed
2. `PROJECT_CHARTER.md` (governance) — This charter with critical AI instructions and amendments
3. `NRW_DATA_WORKFLOW_EXPLAINED.md` (technical) — Detailed data flow documentation
**Session Start:** Read these three files → run `./launch_all.sh`
**Session End:** Update `DAILY_CONTEXT.md` → run `./ops/archive_daily_context.sh` → commit changes
Archive via `diary/YYYY-MM-DD.md` (immutable end-of-session snapshots)

# PART 2: ACTIVE GOVERNANCE

## Active Amendment Table

| New ID | Category | Summary | Impact | See Also |
|--------|----------|---------|--------|----------|
| 001-011 | Process | AI/ops discipline (numbering, assumptions, run semantics, scripts, safeguards, idle time, summary, mode awareness, operational safeguards, multiple solutions, roadmap discipline) | AI behavior & operator workflow | README.md §Daily Workflow |
| 012 | System | Database update cadence - generate_data handles discovery+providers | Daily ops automation | SYSTEM_ARCHITECTURE.md §Pipeline |
| 013-019 | Data/UI | Tracking strategy, SSOT contract, waterfall mandate, schema lock, runtime hierarchy, UI contract, pipeline contract | Data integrity & UI consistency | SYSTEM_ARCHITECTURE.md §Data Contracts |
| 020-021 | Context | Rolling daily context; three-file loading pattern | Session start workflow | DAILY_CONTEXT.md |
| 022 | Feature | Watchmode API integration for watch links | Watch links coverage | docs/features/WATCHMODE.md |
| 023 | Feature | Agent link scraper (Playwright) + overrides fallback stack | Watch links fallback | docs/features/AGENT_LINK_SCRAPER.md |
| 024 | Feature | RT scraper inlined, rate limiting, coverage | Enrichment pipeline | docs/features/RT_SCRAPER.md |
| 025 | Automation | Two-branch automation strategy | CI/CD workflow | docs/AUTOMATION_BRANCH_WORKFLOW.md |
| 026 | Ops | OAuth token recovery & incident handling | Reliability operations | diary/ (incident entries) |
| 027 | Feature | Admin panel post-publication curation model | Data quality curation | docs/features/ADMIN_PANEL_SPEC.md |
| 028 | System | Production discovery architecture & filter policy | Discovery optimization | docs/features/DISCOVERY_FILTERS.md |
| 029 | Data | Bootstrap date accuracy policy & tools | Data quality transparency | date_verification.py |
| 030 | Feature | Newsletter generation with reviews | Content generation | docs/features/NEWSLETTER_GENERATOR.md |
| 031 | Ops | Unified launcher for daily operations | Dev ergonomics | docs/features/UNIFIED_LAUNCHER.md |
| 032 | Governance | Documentation discipline & root cleanliness | Repo hygiene | README.md §Docs |

## Active Amendments

### 001: Numbering Discipline
**Decision:** All steps, amendments, and references are sequentially numbered. No A3/A4 shorthand.
**Status:** ✅ Active - enforces consistent reference system
**Spec:** Applied throughout all documentation

### 002: No Assumptions
**Decision:** Assistants must not assume user knowledge. State concurrency safety, dependencies, run order.
**Status:** ✅ Active - must re-read charter before major decisions
**Spec:** Built into AI assistant behavior pattern

### 003: Run Semantics
**Decision:** Explicit run condition annotation for all commands.
**Scope:** "Run now" (parallel safe), "Run after X" (sequential dependency), Optional steps list pros/cons
**Status:** ✅ Active - prevents workflow confusion
**Spec:** Applied to all operational procedures

### 004: Canonical Scripts
**Decision:** Automation scripts are binding. Modify/reuse them; do not reinvent workflows.
**Status:** ✅ Active - prevents script proliferation
**Spec:** `ops/`, `scripts/` directories contain authoritative automation

### 005: User Safeguard
**Decision:** Plain-English explanations. Each change includes 1-2 sentence "why it matters."
**Status:** ✅ Active - accessibility for non-coder Creative Director
**Spec:** Required for all user-facing instructions

### 006: Idle Time Use
**Decision:** During long steps, propose safe parallel tasks (configs, backups).
**Status:** ✅ Active - maximizes session efficiency
**Spec:** Built into workflow optimization patterns

### 007: Summary Queue
**Decision:** After each group, output next steps prefixed with **⚡ To keep moving**.
**Status:** ✅ Active - maintains workflow momentum
**Spec:** Standard closing pattern for task blocks

### 008: Mode Awareness
**Decision:** Online vs Offline code blocks. Assistant-internal check; only surface if outcome changes.
**Status:** ✅ Active - prevents deployment mode confusion
**Spec:** Built into system state awareness

### 009: Operational Safeguards
**Decision:** UTC timestamps (with seconds); atomic writes (write→fsync→rename); scripts `cd` repo root; absolute paths; no symlinks in bundles; plain `PROJECT_CHARTER.md` inside bundle = fail.
**Status:** ✅ Active - prevents operational corruption
**Spec:** SYSTEM_ARCHITECTURE.md §Operational Safeguards

### 010: Multiple Solutions Rule
**Decision:** Present ≥2-3 distinct options for significant problems. Rate 1-10. Give pros/cons. Recommend best but show alternatives for audit.
**Status:** ✅ Active - enables informed decision-making
**Spec:** Applied to all architectural and operational decisions

### 011: Implementation Roadmap Discipline
**Decision:** `IMPLEMENTATION_ROADMAP.md` as canonical plan, priority categorization, session integration, roadmap ID references in commits.
**Status:** ✅ Active - complements PROJECT_CHARTER.md governance
**Spec:** IMPLEMENTATION_ROADMAP.md

### 012: Database Update Cadence
**Decision:** `generate_data.py` handles discovery and provider checking. Single source for movie discovery.
**Scope:** Legacy tracker archived to museum_legacy/. Daily workflow: data generation → verification → commit.
**Status:** ✅ Active - automated daily updates via GitHub Actions
**Spec:** SYSTEM_ARCHITECTURE.md §Pipeline

### 013: Inclusive Tracking Strategy
**Decision:** Track all movie releases using premiere date as authoritative.
**Scope:** TMDB release_date (not primary_release_date), no pre-filtering, cast wide discovery net.
**Status:** ✅ Active - premiere date is key metric
**Spec:** SYSTEM_ARCHITECTURE.md §Discovery

### 014: SSOT Data Contract
**Decision:** Single source of truth - UI fetches only root ./data.json.
**Scope:** Runtime files at repo root, no duplicate data.json files, verify.sh enforcement.
**Status:** ✅ Active - museum_legacy/ exceptions only
**Spec:** SYSTEM_ARCHITECTURE.md §SSOT Contract

### 015: Link Waterfall Mandate
**Decision:** Link resolution priority waterfall: 1. Manual overrides, 2. Cache layers, 3. Wikidata resolution, 4. MediaWiki search, 5. Agent scraping (optional), 6. Null if unresolvable.
**Status:** ✅ Active - prevents broken link proliferation
**Spec:** SYSTEM_ARCHITECTURE.md §Data Pipeline

### 016: Data Schema Lock v1
**Decision:** Lock data.json schema v1 with required fields and optional watch_links.
**Scope:** Required: tmdb_id, title, digital_date, poster, crew, synopsis, runtime, links. Optional: watch_links {streaming/rent/buy}.
**Status:** ✅ Active - digital_date = first provider availability
**Spec:** SYSTEM_ARCHITECTURE.md §Data Contracts

### 017: Runtime vs Pipeline Hierarchy
**Decision:** Separate runtime files (root) from pipeline data and operations.
**Scope:** Runtime: index.html, data.json, assets/. Pipeline: generate_data.py, caches/, ops/. Archives: diary/, museum_legacy/.
**Status:** ✅ Active - UI reads only root runtime files
**Spec:** SYSTEM_ARCHITECTURE.md §Pipeline Hierarchy

### 018: UI Contract Lock
**Decision:** Lock UI components for MVP consistency.
**Scope:** Date dividers, poster cards (70% height), back-side three-button layout, no genre filters.
**Status:** ✅ Active - Trailer | RT | Wiki pattern enforced
**Spec:** SYSTEM_ARCHITECTURE.md §UI Contract

### 019: Daily Pipeline Contract
**Decision:** Unified daily pipeline contract with health checks.
**Scope:** generate_data.py (discovery+enrichment), ops/health_check.py (validation), daily_update.sh (automation).
**Status:** ✅ Active - legacy tracker archived
**Spec:** SYSTEM_ARCHITECTURE.md §Daily Pipeline

### 020: Rolling Daily Context
**Decision:** DAILY_CONTEXT.md = living document, always current, overwritten each session. diary/YYYY-MM-DD.md = end-of-session archives (immutable).
**Scope:** Replaces stale complete_project_context.md. Format: Current State, What We Did, Known Issues, Next Priorities, Files Changed.
**Status:** ✅ Active - start sessions by reading DAILY_CONTEXT.md; end by archiving to diary/
**Spec:** DAILY_CONTEXT.md

### 021: Daily Context System (Three-File Loading Pattern)
**Decision:** Three-file loading pattern for token-efficient session handoffs.
**Scope:** DAILY_CONTEXT.md (primary), PROJECT_CHARTER.md (governance), NRW_DATA_WORKFLOW_EXPLAINED.md (technical). Archive via ops/archive_daily_context.sh.
**Status:** ✅ Active - diary/ archives immutable, supersedes complete_project_context.md
**Spec:** DAILY_CONTEXT.md

### 022: Watchmode API Integration for Watch Links
**Decision:** Watchmode API integration for direct streaming platform links.
**Scope:** Two-step API (TMDB ID → Watchmode ID → deep links), watch_links schema {streaming/rent/buy}, cache system, 1,000 requests/month budget.
**Status:** ✅ Active - ~75% of free tier usage, Agent fallback for gaps
**Spec:** docs/features/WATCHMODE.md

### 023: Agent-Based Link Finding for Streaming Platforms
**Decision:** Agent-based Playwright scraper with overrides stack for Watchmode gaps.
**Scope:** Three-tier system (Watchmode → Playwright scraping → null), manual overrides, 6 selectors per platform, screenshot diagnostics.
**Status:** ✅ Active - Netflix/Disney+/HBO Max/Hulu fallback support
**Spec:** docs/features/AGENT_LINK_SCRAPER.md

### 024: RT Scraper Integration and Inlining
**Decision:** Inline RT scraper into generate_data.py with unified rate limiting.
**Scope:** RT consolidation, 2-second rate limiting, 72.9% coverage, selector fallbacks.
**Status:** ✅ Active - waterfall integration complete
**Spec:** docs/features/RT_SCRAPER.md

### 025: Two-Branch Automation Strategy
**Decision:** Two-branch strategy (main/automation-updates) to eliminate merge conflicts.
**Scope:** Bot commits to automation-updates branch, force-push workflow, GitHub issue notifications, weekly full regeneration.
**Status:** ✅ Active - zero merge conflicts achieved
**Spec:** docs/AUTOMATION_BRANCH_WORKFLOW.md

### 026: Authentication Token Management
**Decision:** Authentication token management and incident recovery procedures.
**Scope:** OAuth expiration handling, manual commit fallback, retroactive diary creation, work preservation priority.
**Status:** ✅ Active - manual commit button as failsafe
**Spec:** diary/ (incident entries)

### 027: Admin Panel - Post-Publication Curation & Data Quality
**Decision:** Admin panel post-publication curation model with inline editing.
**Scope:** QA database editor, missing data detection, manual corrections, YouTube integration, daily curation workflow.
**Status:** ✅ Active - 93 flagged movies, inline editing operational
**Spec:** docs/features/ADMIN_PANEL_SPEC.md

### 028: Production Discovery Architecture
**Decision:** Production discovery architecture with consolidation and filter policy.
**Scope:** Unified generate_data.py discovery, remove vote_count filter, provider availability primary filter, legacy system archived.
**Status:** ✅ Active - 5-10x discovery rate increase, 1,956 stuck movies fixed
**Spec:** docs/features/DISCOVERY_FILTERS.md

### 029: Bootstrap Date Accuracy & Data Quality Policy
**Decision:** Bootstrap date accuracy policy with transparency and correction tools.
**Scope:** Flag 50+ legacy movies with bootstrap_date=true, manual correction via admin panel/date_verification.py, visual indicators on frontend.
**Status:** ✅ Active - transparency over hiding, gradual manual correction
**Spec:** date_verification.py

### 030: Newsletter & Reviews System
**Decision:** Newsletter generation system with editorial reviews and multi-format output.
**Scope:** Review storage in admin panel, newsletter generator (Markdown/HTML/plain text), platform grouping, CLI interface, weekly/monthly distribution.
**Status:** ✅ Active - editorial review workflow operational
**Spec:** docs/features/NEWSLETTER_GENERATOR.md

### 031: Unified Launcher for Daily Operations
**Decision:** Unified launcher (launch_all.sh) with menu interface for all NRW tools.
**Scope:** Menu-driven interface, process management, browser auto-open, Option 4 (All Services) for daily workflow.
**Status:** ✅ Active - single entry point replaces individual scripts
**Spec:** docs/features/UNIFIED_LAUNCHER.md

### 032: Documentation Discipline & Root Cleanliness
**Decision:** Root cleanliness with seven-file whitelist and docs/ organization.
**Scope:** Seven root .md files only, session findings → diary/, features → docs/features/, troubleshooting → docs/troubleshooting/, pre-commit hook enforcement.
**Status:** ✅ Active - PROJECT_CHARTER.md under 1000 lines, never create root .md without approval
**Spec:** README.md §Docs

# PART 3: CURRENT CONFIGURATION

## Data Contracts (Essentials)

### movie_tracking.json Schema
```json
{
  "title": "Movie Name",
  "tmdb_id": 12345,
  "status": "available|tracking|removed",
  "enriched": true,
  "enrichment_date": "2025-11-05T10:30:00Z",
  "digital_date": "2025-10-15",
  "rt_url": "https://...",
  "rt_rating": 85,
  "platforms": ["netflix", "hulu"],
  "manually_corrected": true,
  "manual_rt_score": true,
  "last_manual_edit": "2025-10-19T..."
}
```

### data.json Schema
Filtered, enriched subset for frontend display:
```json
{
  "tmdb_id": 12345,
  "imdb_id": "tt1234567",
  "title": "Movie Title",
  "digital_date": "2025-10-15",
  "poster": "https://image.tmdb.org/...",
  "crew": {"director": "Director Name", "cast": ["Actor 1", "Actor 2"]},
  "synopsis": "Movie description...",
  "metadata": {"runtime": 120},
  "links": {"trailer": "https://youtube.com/...", "rt": "https://rottentomatoes.com/...", "wikipedia": "https://en.wikipedia.org/..."},
  "watch_links": {"streaming": {"service": "Netflix", "link": "https://..."}, "rent": {"service": "Amazon", "link": "https://..."}}
}
```

### Required Fields
- Core: tmdb_id, imdb_id, title, digital_date, poster, crew.director, crew.cast[], synopsis, metadata.runtime
- Links: trailer, rt, wikipedia (nullable)
- Watch Links: streaming/rent/buy categories (optional, structured per schema)

## File Hierarchy

### Runtime Files (Repository Root)
- `index.html` - Main user interface (~15KB, updated daily)
- `data.json` - Movie data for frontend (~80KB, updated daily)
- `assets/` - CSS, images, static files (~2MB, rarely updated)

### Core Data Files
- `movie_tracking.json` - Master movie database (~330 records)
- `config.yaml` - System configuration (API keys, timeouts)
- `watchmode_quota.json` - API usage tracking

### Pipeline Files (Non-Runtime)
- `generate_data.py` - Data processing engine (20-30s runtime)
- `daily_orchestrator.py` - Daily automation controller (30s runtime)
- `admin.py` - Web admin interface (on-demand)
- `cache/` - Scraper cache files (RT, Wikipedia, YouTube, Watch Links)
- `overrides/` - Manual data fixes and corrections
- `ops/` - Operational scripts (backup, archive, health checks)

### Archives
- `diary/` - Daily context archives (YYYY-MM-DD.md, immutable)
- `museum_legacy/` - Legacy code and deprecated documentation

## Quick Reference

### Daily Operations
```bash
# Start session
./launch_all.sh     # Menu interface - choose Option 4 (All Services)

# Manual pipeline
python3 generate_data.py    # Standard data generation
python3 admin.py           # QA interface (localhost:5000)

# Session end
./ops/archive_daily_context.sh    # Archive DAILY_CONTEXT.md to diary/
```

### Emergency Commands
```bash
# Fix branch divergence
git checkout automation-updates && git reset --hard main && git push --force

# Check processing load
grep "Processing.*movies" logs/    # Normal: 1-10 movies, Warning: 50+, Critical: 100+

# Restore from corruption
cp movie_tracking.json.backup movie_tracking.json

# API quota check
cat watchmode_quota.json    # Monitor monthly usage vs 1,000 limit
```

### Configuration Sources
1. **Environment variables** (production) - `TMDB_API_KEY`, `WATCHMODE_API_KEY`
2. **config.yaml** (local development) - fallback for API keys and system settings
3. **Fail fast** - clear error messages if neither is configured

### Performance Targets
- **Normal operation**: 1-10 movies enriched daily, 30-second runtime
- **Warning threshold**: 50+ movies (possible corruption)
- **Critical threshold**: 100+ movies (definite corruption, 2+ hour runtime)

---

## Historical Footer

**Archived Amendments:** 18 historical amendments (e.g., original 013-024: Bundles superseded by git workflow).
**Full archive:** `museum_legacy/charter_history/AMENDMENT-HISTORICAL-ARCHIVE.md`
**This charter maintained under 450 lines per AMENDMENT-032 documentation discipline.**