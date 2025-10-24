# PROJECT_LOG.md

## 2025-08-26 — Session Summary

### Actions Completed
- **Charter Amendments Approved**
  - A3: Numbered step labels (7a, 7b, etc.) locked as standard.
  - A4: No assumptions — every step explicitly requires confirmation before proceeding.
  - A6: All code blocks must state run condition (`run now` vs `wait`).
  - A7: Removed vague phrases ("after it prints") — replaced with explicit sequencing.
  - A8: Optional steps must include pros/cons for decision-making.
  - A9: Every instruction batch includes a **⚡ To keep moving** summary.

- **System Configuration**
  - Port **3001** hard-locked for local server.
  - Offline mode set (`offline: true`, `fetch_tmdb/rt/trailers: false`).
  - Cache skeleton built with `.cache/rt/`, `.cache/tmdb/`, `.cache/trailers/`.
  - TMDB poster cache populated (~95% coverage, w500 image URLs).
  - RT cache and trailers cache initialized but not yet populated.

- **Renderer / Frontend**
  - Rebuilt `render_approved.js` with global guard, poster resolver, provider chips, RT badges, date filtering, and idempotent rendering.
  - Template cleanup: single `#cards` container, assets normalized.
  - Styling updated: VHS flip-card CSS preserved + modern overrides (grid, fixed 220x330px cards, provider chip styles).

### Issues / Observations
- Posters still not displaying in UI despite valid TMDB poster URLs.
- Duplicate `div` containers and script tags cleaned.
- Header consistent: **"The New Release Wall"**.
- Potential mismatch between Aug 20 baseline template and current JS-only renderer.

### Next Focus
1. Compare **Aug 20 site.html** vs current index.html.
2. Decide patch forward vs rebuild baseline.
3. Debug poster pipeline (`resolvePoster`, CSS sizing, container injection).
4. Validate renderer execution (cards counted, posters missing).

---

⚡ **To keep moving next session:**
- Upload latest sync (`NRW_SYNC_*.zip`).
- Compare Aug 20 baseline vs current index.
- Choose patch/rebuild strategy.
- Focus on poster rendering + layout polish.

## 2025-08-27 13:36
- RULE-010 enforced; preflight checks integrated.
- Structured rules (RULE-011..017) appended.
- Cache infra confirmed; offline mode acceptable for now (TMDB creds in config.yaml).
- Renderer and CSS stabilized; JS-only rendering is canonical.
- End-of-session bundling policy active.
- 20250827-1346: Handoff complete → tag golden-20250827-1346 (zip: NRW_SINGLE_HANDOFF_20250827-134640.zip)

## 2025-08-27 14:14
- Repo history rewritten to remove bundles and snapshots
- Pre-push guard installed (blocks NRW_SYNC and >50MB)
- Canonical branch: main (cleaned)
- 20250827-231948: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-231948.txt
- 20250827-232849: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-232849.txt
- 20250827-233050: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10352
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-233050.txt
- 20250827-233200: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10352
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-233200.txt
- 20250828-034817: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250828-034817.txt
- 20250828-035944: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250828-035944.txt
- 20250828-191116: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=2, data_core.json=2, index.html=10073
  Data: items=0; dups=0; bad_dates=0
  Report: output/nrw_audit_20250828-191116.txt
- 20250829-210506: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=2, data_core.json=2, index.html=9794
  Data: items=0; dups=0; bad_dates=0
  Report: output/nrw_audit_20250829-210506.txt
- 20250830-222116Z: Added AMENDMENT-WS (Unified Working Set Rule); archived pre-WS charter.
- 20250830-230320: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=26252, data_core.json=2, index.html=9515
  Data: items=20; dups=0; bad_dates=0
  Report: output/nrw_audit_20250830-230320.txt
- 20250830-231237: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=26252, data_core.json=2, index.html=9515
  Data: items=20; dups=0; bad_dates=0
  Report: output/nrw_audit_20250830-231237.txt
- 20250831-000751: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=26253, data_core.json=2, index.html=271602
  Data: items=20; dups=0; bad_dates=0
  Report: output/nrw_audit_20250831-000751.txt
- 20250831-001031Z: Added AMENDMENT-IFTHEN (Conditional & Parallel Command Flow)
- 20250831-004650Z: Context updated — unified Working Set handoff; legacy NRW_SYNC deprecated
- 20250831-005853Z: Retired legacy NRW_SYNC; moved to bundle_history; Working Set only
- : Charter updated — flat handoff checklist finalized
- 20250831-065647Z: Context patched — Flat Handoff canonical; NRW_SYNC deprecated
- 20250831-070929Z: Flat handoff canonical; AMENDMENT-FLATSHOT added; scripts locked to FLAT_HANDOFF_ONLY
- 20250831-070929Z: Context updated with Flat Handoff section
- 20250831-075104Z: Operator's Manual appended to Charter

## 2025-09-06 - Repository Migration & Bootstrap

### Major Changes
- **Repository Migration:** Moved from new-release-wall to nrw-production
- **GitHub Actions Issue:** Account flagged, preventing workflow execution
- **Bootstrap Complete:** 180 movies tracked, 107 marked digital on discovery
- **Support Ticket:** Filed for GitHub account reinstatement

### Data Pipeline Status
- movie_tracker.py: Functional, tracking 180 movies
- generate_data.py: Functional, showing 30 most recent
- daily_update.sh: Created with canonical workflow
- GitHub Actions: Blocked pending reinstatement

### Issues Identified
- All bootstrap movies show Sept 5 (discovery date, not digital date)
- No way to retroactively determine actual digital dates
- GitHub Actions blocked at account level
- Design issues: small date markers, no hover states

### Amendments Added
- AMENDMENT-025: Database Update Cadence
- AMENDMENT-026: Repository Migration Record
- AMENDMENT-027: Bootstrap Data Integrity
- AMENDMENT-008: Canonical Daily Update Script

### Next Session Focus
- Await GitHub reinstatement decision
- Fix design issues with current data
- Implement bootstrap movie filtering if needed

## 2025-10-14 - Comprehensive Analysis & Roadmap Creation

### Session Summary
Conducted thorough codebase exploration and created structured implementation roadmap for prioritized system improvements. Focused on agent scraper failures, discovery pipeline optimization, and tactical planning discipline.

### Analysis Completed
- **Agent Scraper Investigation:** Identified 0% success rate with 41 failed attempts in cache
- **Discovery Pipeline Review:** Found vote_count filter blocking new releases with 0 votes
- **Daily Automation Analysis:** Discovered git conflict issues and incremental mode limitations
- **Code Architecture Assessment:** Evaluated RT scraper integration and frontend schema alignment
- **Configuration Review:** Identified incomplete config loading and missing dependencies

### Problems Identified (12 items grouped by priority)

**Critical Issues:**
- CRIT-001: Agent scraper 0% success rate (Netflix/Disney+/Hulu links all null)
- CRIT-002: Incremental mode skips existing 235 movies (never get agent links)
- CRIT-003: Cache directory not persistent (.gitignore excludes cache/)

**High Priority Issues:**
- HIGH-001: Config not fully loaded (only api section read)
- HIGH-002: Missing Selenium dependencies in requirements.txt
- HIGH-003: Daily automation git conflicts (bot and user both commit to main)
- HIGH-004: No execution evidence (no logs, cache files, or statistics)

**Medium Priority Issues:**
- MED-001: RT scraper not integrated into main generation pipeline
- MED-002: Discovery rate too low (only 2 movies in 3 days)
- MED-003: Frontend three-button UI missing (still uses old free/paid schema)

**Low Priority Issues:**
- LOW-001: Manual override system needed for watch links
- LOW-002: Admin panel enhancement for inline editing

### Documents Created
- **IMPLEMENTATION_ROADMAP.md:** Canonical tactical plan with 12 prioritized issues, implementation sequence, and decision log
- **AMENDMENT-036:** Implementation Roadmap Discipline establishing tactical planning rules

### Decisions Made
- **Prioritize agent scraper fixes:** Major user experience impact with 90% of movies having null watch_links
- **Migrate Selenium to Playwright:** More reliable with better error messages and modern API
- **Weekly full regeneration:** Required to populate existing movies with retroactive improvements
- **Separate branch automation:** Eliminate git conflicts between bot and user commits
- **Remove discovery filters:** Allow movies with 0 votes to improve discovery rate

### User Requirements Captured
- Direct deep links to streaming platforms (not search URLs)
- Reliable daily automation without manual conflict resolution
- Quality assurance workflow for data validation
- Systematic approach to technical debt and enhancement priorities

### Next Session Focus
**Phase 1 Implementation (Critical Issues):**
1. Add cache/.gitkeep for persistence
2. Fix dependencies in requirements.txt
3. Update config loading to read full structure
4. Add comprehensive debug logging
5. Migrate agent scraper to Playwright
6. Implement weekly full regeneration

**Reference:** See [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) for complete tactical plan and implementation sequence.

### Notes
- Session documented creation of systematic approach to technical debt
- All implementation decisions cross-referenced with roadmap IDs
- User communication emphasized regarding breaking changes and new features
- Rollback plans established for major changes (Playwright migration)
