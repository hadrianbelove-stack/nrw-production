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
2. **No Unauthorized Coding** — Assistant must never write, modify, or create code without explicit user approval. All unspecified changes must be presented as suggestions with clear explanations of what the code does and why it's needed. User approval required before any implementation.
3. **Tactical Planning** — `IMPLEMENTATION_ROADMAP.md` serves as the canonical tactical plan for prioritized implementation work

## Current System State
- **Runtime entry:** `index.html` loads `assets/styles.css` and `assets/app.js`, then initializes the wall
- **Data file:** `data.json` (30 recent titles; links resolved via waterfall)
- **Mode:** offline for MVP
- **UI:** date dividers + flip-cards; back shows Synopsis + Trailer/RT/Wiki buttons
- **Pipeline:** Daily automation via GitHub Actions at 1:00 AM PT
- **Database:** `movie_tracking.json` tracks 330+ movies; enrichment-on-transition pattern prevents 2+ hour runtimes

## Documentation Loading Pattern
**Two-file loading pattern for AI assistant context:**
1. `PROJECT_CHARTER.md` (governance) — This charter with critical AI instructions and core rules
2. `NRW_DATA_WORKFLOW_EXPLAINED.md` (technical) — Detailed data flow and pipeline documentation

**Session Start:** Read PROJECT_CHARTER.md → Read NRW_DATA_WORKFLOW_EXPLAINED.md → Begin work
**Current Status:** Check recent git commits and metrics files for current system state
**Session End:** Commit changes with clear commit messages

# PART 2: ACTIVE GOVERNANCE

## Active Amendment Table

| ID | Category | Summary | Impact | See Also |
|--------|----------|---------|--------|----------|
| 001-011 | Process | AI/ops discipline (numbering, assumptions, run semantics, scripts, safeguards, idle time, summary, mode awareness, operational safeguards, multiple solutions, roadmap discipline) | AI behavior & operator workflow | Ops: README.md §Daily Workflow |
| 014 | Governance | Documentation discipline & root cleanliness | Repo hygiene | Ops: README.md §Docs |
| 015 | Process | Minimal implementation principle | Prevents scope creep | Applied to all changes |
| 016 | Process | Source first discipline | Prevents assumption mistakes | Applied to all references |
| 017 | Governance | Charter vs implementation separation | Keeps charter clean | PROJECT_CHARTER.md vs IMPLEMENTATION_ROADMAP.md |

**Note:** Former tactical amendments (022-031) moved to IMPLEMENTATION_ROADMAP.md as completed implementation decisions, not governance principles.

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
**Spec:** SYSTEM_ARCHITECTURE.md §4 (Configuration & Secrets)

### 010: Multiple Solutions Rule
**Decision:** Present ≥2-3 distinct options for significant problems. Rate 1-10. Give pros/cons. Recommend best but show alternatives for audit.
**Status:** ✅ Active - enables informed decision-making
**Spec:** Applied to all architectural and operational decisions

### 011: Implementation Roadmap Discipline
**Decision:** `IMPLEMENTATION_ROADMAP.md` as canonical plan, priority categorization, session integration, roadmap ID references in commits.
**Status:** ✅ Active - complements PROJECT_CHARTER.md governance
**Spec:** IMPLEMENTATION_ROADMAP.md

### 012: Database Update Cadence
**Decision:** `generate_data.py` handles both `intake` (new premiere ingestion from TMDB) and `discovery` (provider availability detection for tracked titles). Single source of truth for both which titles are tracked and when they become digitally available.
**Scope:** Legacy tracker archived to museum_legacy/. Daily workflow: data generation → verification → commit.
**Status:** ✅ Active - automated daily updates via GitHub Actions
**Spec:** SYSTEM_ARCHITECTURE.md §Daily Pipeline Phases

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
**Scope:** Required: tmdb_id, title, digital_date, poster, crew, synopsis, runtime, links. Optional: watch_links {streaming/vod}.
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

### 020: Append-Only data.json Architecture
**Decision:** data.json is append-only. Movies are added during discovery and NEVER deleted.
**Scope:**
- Discovery phase immediately writes minimal movie entry to data.json
- Enrichment phase overlays additional data onto existing entries
- No "wipe and regenerate" behavior - data accumulates
- Each movie gets ONE enrichment attempt on transition day (no retries)
- Queue resets daily - no accumulation across days
**Status:** ✅ Active - implemented 2025-12-29
**Spec:** SYSTEM_ARCHITECTURE.md §1.1 Core Data Model

### 021: Documentation Discipline & Root Cleanliness
**Decision:** Root cleanliness with seven-file whitelist and docs/ organization.
**Scope:** Seven root .md files only, session findings → diary/, features → docs/features/, troubleshooting → docs/troubleshooting/, pre-commit hook enforcement.
**Status:** ✅ Active - PROJECT_CHARTER.md under 1000 lines, never create root .md without approval
**Spec:** README.md §Docs

### 015: Minimal Implementation Principle
**Decision:** Implement only what is explicitly requested. No feature additions, improvements, or anticipatory work without explicit approval.
**Scope:** Covers both code changes and file creation. Default to simplest possible implementation.
**Status:** ✅ Active - prevents over-engineering and scope creep
**Spec:** Applied to all implementation decisions

### 016: Source First Discipline
**Decision:** Never reference or implement based on documents, requirements, or specifications without reading them first using available tools.
**Scope:** Applies to amendments, configs, existing code, and external requirements.
**Status:** ✅ Active - prevents building wrong solutions based on assumptions
**Spec:** Must use Read tool before claiming what documents say

### 017: Charter vs Implementation Separation
**Decision:** Charter contains only timeless governance principles. All tactical decisions belong in IMPLEMENTATION_ROADMAP.md.
**Scope:** Test: "Is this how to work (charter) or what to build (roadmap)?"
**Status:** ✅ Active - keeps charter focused on governance
**Spec:** PROJECT_CHARTER.md vs IMPLEMENTATION_ROADMAP.md

# PART 3: CURRENT CONFIGURATION

## Data Contracts (Essentials)

### What NRW Does
NRW tracks when theatrical movies become available for digital streaming/rental. Since no API provides "when" a movie became available (only "what" is currently available), we poll daily to detect transitions and record them.

### Core Data Invariants
- **movie_tracking.json**: Master tracking database (~6,700 records), status = "tracking" or "available"
- **data.json**: Frontend display data (~230 records), **append-only** - movies added on discovery, never deleted
- **metrics/newly_available.json**: Today's enrichment queue - contains IDs of movies that transitioned today
- **Required fields**: tmdb_id, title, digital_date, poster, crew, synopsis, runtime, links
- **Data flow**: Intake → Discovery (writes to data.json) → Enrichment (overlays data) → Display

### File Hierarchy

#### Runtime (Repository Root)
- `index.html`, `data.json`, `assets/` - User-facing interface
- **Size**: ~2MB total, updated daily via automation

#### Pipeline (Non-Runtime)
- `movie_tracking.json`, `config.yaml` - Core data and configuration
- `generate_data.py`, `daily_orchestrator.py`, `admin.py` - Processing engines
- `cache/`, `overrides/`, `ops/` - Support infrastructure

#### Archives
- `diary/` - Session snapshots (immutable), `museum_legacy/` - Deprecated code

## Configuration Sources

**Configuration priorities**: Environment variables (production) → config.yaml (development) → fail fast
For full details, see `SYSTEM_ARCHITECTURE.md §4 (Configuration & Secrets)`.

## Quick Reference


### Configuration & Performance
- **Config sources**: Environment variables (production) → config.yaml (development) → fail fast
- **Normal operation**: 1-10 movies/day, 30s runtime
- **Critical thresholds**: 50+ movies (warning), 100+ movies (corruption), 2+ hour runtime

**Detailed specifications**: SYSTEM_ARCHITECTURE.md §4 (Configuration & Secrets)
**Daily operations**: README.md §Daily Workflow

---

## Historical Footer

**Archived Amendments:** See museum_legacy/charter_history/AMENDMENT-HISTORICAL-ARCHIVE.md
**Historical Archives:**
- [Pre-compression charter](museum_legacy/charter_history/PROJECT_CHARTER_20251107-PRE-COMPRESSION.md) - Full charter before compression
- [Amendment archives](museum_legacy/charter_history/AMENDMENT-HISTORICAL-ARCHIVE.md) - Historical amendment versions
**This charter maintained under 400 lines per 032: Documentation discipline.**