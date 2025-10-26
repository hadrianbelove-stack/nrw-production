# DAILY_CONTEXT.md
**Date:** [YYYY-MM-DD]
**Previous diary entry:** diary/2025-10-26.md

---

## AI Assistant Quick Start

**READ THESE FILES FIRST WHEN STARTING A NEW SESSION:**

1. **This file (DAILY_CONTEXT.md)** - Current state, recent changes, active issues
2. **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance rules, amendments, API keys, architectural decisions
3. **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline mechanics, how everything fits together

**What is this rolling context system?**

This is a **living document** that gets overwritten each session with current information. At the end of each session, we archive it to  (immutable historical record). This approach:
- **Avoids token waste** from loading months of PROJECT_LOG.md history
- **Provides fresh context** without stale information
- **Maintains audit trail** in the diary/ folder
- **Reduces AI confusion** by keeping focus on current state

See [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context) and [AMENDMENT-037](PROJECT_CHARTER.md#amendment-037-daily-context-system-three-file-loading-pattern) for governance rules.

---

## Current State

### What's Working
[Fill in during session - describe operational systems and their status]

### Architecture
[Fill in during session - describe runtime components and data flow]

---

## What We Did Today ([YYYY-MM-DD])

[Fill in during session - document major changes, commits, and implementations]

---

## Conversation Context (Key Decisions)

[Fill in during session - record important decisions and their rationale]

---

## Known Issues

[Fill in during session - document current problems and their status]

---

## Next Priorities

### Immediate (This Session)
[Fill in during session - list current tasks and their completion status]

### Next Phase
[Fill in during session - list upcoming tasks for next session]

### Subsequent Phase
[Fill in during session - list future improvements]

### Short-term (Next Few Days)
[Fill in during session - list near-term tasks]

### Long-term (Ongoing)
[Fill in during session - list ongoing maintenance tasks]

---

## Archive Instructions

**End-of-session workflow (automated via 🚀 Daily Context Archive Script
===============================

📋 Validating prerequisites...
[0;32m✅ Prerequisites validated[0m

📅 Archive date: 2025-10-26 (UTC)

📂 Checking diary directory...
[0;34m📁 diary/ directory already exists[0m

📦 Preparing to archive...
[1;33m⚠️ Archive already exists: diary/2025-10-26.md[0m
[0;31m❌ Error: Non-interactive environment detected and archive exists.[0m
   Use --force to overwrite existing archive: diary/2025-10-26.md):**

1. Run archive script: 🚀 Daily Context Archive Script
===============================

📋 Validating prerequisites...
[0;32m✅ Prerequisites validated[0m

📅 Archive date: 2025-10-26 (UTC)

📂 Checking diary directory...
[0;34m📁 diary/ directory already exists[0m

📦 Preparing to archive...
[1;33m⚠️ Archive already exists: diary/2025-10-26.md[0m
[0;31m❌ Error: Non-interactive environment detected and archive exists.[0m
   Use --force to overwrite existing archive: diary/2025-10-26.md
   - Archives current context to 
   - Creates fresh template for next session
   - Use  to preview changes without executing

2. **Testing:** 🚀 Daily Context Archive Script
===============================

📋 Validating prerequisites...
[0;32m✅ Prerequisites validated[0m

📅 Archive date: 2025-10-26 (UTC)

📂 Checking diary directory...
[0;34m📁 diary/ directory already exists[0m

📦 Preparing to archive...
[1;33m⚠️ Archive already exists: diary/2025-10-26.md[0m
[0;34m📁 [DRY RUN] Would overwrite existing archive[0m
[0;34m📁 [DRY RUN] Would create archive with metadata header at diary/2025-10-26.md[0m

📄 Creating fresh template...
[0;34m📁 [DRY RUN] Would create fresh DAILY_CONTEXT.md template[0m

🎉 Archive Complete!
===================

📋 DRY RUN SUMMARY:
   📦 Would archive: DAILY_CONTEXT.md → diary/2025-10-26.md
   📄 Would create: Fresh DAILY_CONTEXT.md template

   Run without --dry-run to execute these changes.

✨ Ready for next development session! shows what would happen

3. **Troubleshooting:**
   - Permission error: 
   - Missing file error: Ensure you're in repo root
   - Directory issues: Script creates  automatically

4. **Next session starts fresh:**
   - AI reads new DAILY_CONTEXT.md template
   - Historical context available in  if needed
   - No token waste from stale information

**Current status:** Archive script created and ready to use

---

## Files Changed Today

### Created
[Fill in during session - list new files]

### Modified
[Fill in during session - list changed files with brief descriptions]

### Archived
[Fill in during session - list files moved to museum_legacy/]

---

## Quick Reference

### Daily Workflow
🎬 NEW RELEASE WALL - Daily Startup
====================================

🔍 Step 0: Checking dependencies...
   ✅ All dependencies available

📥 Step 1: Pulling latest data from automation...
   ✅ Data is current

📊 Step 2: Quick Status Report
   Total movies on wall: 314
   Tracked: 2438 / Displayed: 314
   New today (Oct 26): 10
   New yesterday (Oct 25): 0
   Last generated: 2025-10-26T11:16:39

📋 Step 3: Context Files for AI Assistants
   When working with AI assistants, read these files in order:
   1. DAILY_CONTEXT.md (current state, recent changes, active issues) ⭐ PRIMARY
   2. PROJECT_CHARTER.md (governance & amendments)
   3. NRW_DATA_WORKFLOW_EXPLAINED.md (technical pipeline)

🚀 Step 4: Starting local server...
   ⚠️ Port 8000 in use, trying 8001...
   ❌ Ports 8000 and 8001 both in use. Stop other servers first.
   Try: lsof -ti:8000 | xargs kill

### Manual Pipeline (if needed)
❌ DEPRECATED: movie_tracker.py is no longer supported

The movie tracking functionality has been integrated into the production discovery system.
Please use the following commands instead:

  For daily discovery:
    python3 generate_data.py --discover

  For full data generation:
    python3 generate_data.py

  For the complete daily pipeline:
    python3 daily_orchestrator.py

The legacy implementation is available at:
    museum_legacy/legacy_movie_tracker.py

For more information, see README.md and DAILY_CONTEXT.md
📂 Found 314 existing movies in data.json

🔍 Validating enrichment consistency...
  🔍 Enrichment consistency: 330/330 valid, 0 corrected

📊 Phase 2.1 Enrichment Optimization:
   Total available movies (last 90 days): 330
   ✅ Already enriched (cached): 328
   🆕 Need enrichment: 2
   ⏰ Stale (>90 days, will re-enrich): 0

🎬 Processing 2 movies (enrichment phase)...
   API savings: 328 movies skipped (95% cost reduction)

💾 Enrichment tracking saved: 0 movies marked as enriched

📋 Using 314 cached movies + 0 newly enriched = 314 total
📝 Admin overrides applied:
  Hidden movies: 0
  Featured movies: 0
✅ Generated data.json with 314 movies
Wikipedia links found: 314
Direct trailers found: 306
RT scores cached: 49
Movies with reviews: 1

📊 Wikidata Usage:
  Wikidata attempts: 0
  Wikidata successes: 0
  Wikipedia links recovered via Wikidata: 0

📊 Watchmode API Usage:
  Search calls: 0
  Source calls: 0
  Cache hits: 0
  Cache hit rate: 0.0%
  Watchmode success rate: 0.0%

📊 Watchmode API Quota Report:
   Calls used: 1000/1000
   Remaining: 0
   Usage: 100.0%
   Reset date: 2025-11-01T00:00:00
   ⚠️  STATUS: EXHAUSTED (falling back to scrapers)

   Recent calls (last 5):
     ✗ 2025-10-24 20:52 - The Matrix (search)

📊 Agent Scraper Usage:
  Agent enabled: True
  Agent initialized: False
  Agent attempts: 0
  Agent successes: 0
  Agent cache hits: 0
  ⚠️  Agent scraper was never called (check if movies have Netflix/Disney+/Hulu providers)

📊 Platform Scraper Statistics (Amazon/Apple TV):
  Platform scraper enabled: True
  Platform scraper initialized: False
  Amazon enabled: True
  Apple TV enabled: True
  Platform scraper attempts: 0
  Platform scraper successes: 0
  Platform scraper failures: 0
  ⚠️  Platform scraper was never called (check if movies have Amazon/Apple TV providers)
  Last selector update: 2025-10-25
  Expected update frequency: quarterly

📊 RT Scraper Usage:
  RT attempts: 0
  RT successes: 0
  RT cache hits: 0

📊 Admin Override Usage:
  Manual tracking hits: 0
  Override hits: 0

🔍 Schema Validation:
  Validation passes: 628
  Validation warnings: 0
  Validation pass rate: 100.0%
❌ DEPRECATED: movie_tracker.py is no longer supported

The movie tracking functionality has been integrated into the production discovery system.
Please use the following commands instead:

  For daily discovery:
    python3 generate_data.py --discover

  For full data generation:
    python3 generate_data.py

  For the complete daily pipeline:
    python3 daily_orchestrator.py

The legacy implementation is available at:
    museum_legacy/legacy_movie_tracker.py

For more information, see README.md and DAILY_CONTEXT.md

### Context Files (Read These First)
- **Daily:** This file (DAILY_CONTEXT.md) - Current state and recent changes
- **Governance:** [PROJECT_CHARTER.md](PROJECT_CHARTER.md) - Rules, amendments, API keys
- **Pipeline:** [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md) - How data flows
- **History:**  - End-of-session archives (when needed)

---

**Last updated:** [End of session]
**Next diary archive:** End of session -> `diary/[YYYY-MM-DD].md`
