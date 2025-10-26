# DAILY_CONTEXT.md
**Date:** [YYYY-MM-DD]
**Previous diary entry:** diary/2025-10-24.md

---

## AI Assistant Quick Start

**READ THESE FILES FIRST WHEN STARTING A NEW SESSION:**

1. **This file (DAILY_CONTEXT.md)** - Current state, recent changes, active issues
2. **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance rules, amendments, API keys, architectural decisions
3. **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline mechanics, how everything fits together

**What is this rolling context system?**

This is a **living document** that gets overwritten each session with current information. At the end of each session, we archive it to `diary/YYYY-MM-DD.md` (immutable historical record). This approach:
- **Avoids token waste** from loading months of PROJECT_LOG.md history
- **Provides fresh context** without stale information
- **Maintains audit trail** in the diary/ folder
- **Reduces AI confusion** by keeping focus on current state

See [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context) and [AMENDMENT-037](PROJECT_CHARTER.md#amendment-037-daily-context-system-three-file-loading-pattern) for governance rules.

---

## Current State

### What's Working
- **Provider monitoring:** Restored and operational (checks 1,889 tracking movies daily)
- **Enrichment optimization:** 99.4% cache efficiency (318/320 movies cached)
- **Quota management:** Watchmode quota tracking active, auto-resets Nov 1st
- **Watch links:** 100% coverage (318/318 movies have at least one link)
- **Performance:** Data generation in 30 seconds (96% faster than before)
- **System stability:** Graceful degradation when Watchmode quota exhausted

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

- **Amazon ASIN placeholder bug:** Same ASIN (B0FMPYFP9W) appearing for multiple movies ✅ FIXED
- **Watchmode quota:** Exhausted until Nov 1st reset (graceful degradation to scrapers active)
- **Apple TV coverage:** Only 11 links (3.5%), needs monitoring after recent enablement

---

## Next Priorities

### Immediate (This Session)
- ✅ Fix Amazon scraper title validation (placeholder ASIN bug)
- ✅ Redesign watch buttons (service-based layout per user requirements)
- ⏳ Monitor Apple TV scraper performance (just enabled)
- ⏳ Wait for Watchmode quota reset (Nov 1st)

### Next Phase
- Monitor Apple TV scraper coverage improvements
- Test new watch button UI design with users
- Review enrichment consistency validation effectiveness

### Subsequent Phase
- Consider additional streaming platform scrapers (if needed)
- Optimize scraper performance and reliability
- Implement advanced watch link validation

### Short-term (Next Few Days)
- Monitor system performance with new optimizations
- Track Watchmode quota reset on Nov 1st
- Validate Amazon ASIN fix effectiveness

### Long-term (Ongoing)
[Fill in during session - list ongoing maintenance tasks]

---

## Archive Instructions

**End-of-session workflow:**

1. **Run archive script:** `./ops/archive_daily_context.sh`
   - Archives current context to `diary/YYYY-MM-DD.md` (immutable historical record)
   - Creates fresh DAILY_CONTEXT.md template for next session
   - Automatically uses UTC date for consistency

2. **Preview changes (dry-run):** `./ops/archive_daily_context.sh --dry-run`
   - Shows what would happen without executing
   - Useful for verifying before archiving

3. **Force overwrite existing archive:** `./ops/archive_daily_context.sh --force`
   - Use when archive already exists for today
   - Overwrites existing diary entry (use with caution)

4. **Troubleshooting:**
   - **Permission error:** Run `chmod +x ops/archive_daily_context.sh`
   - **Missing file error:** Ensure you're in repository root directory
   - **Directory issues:** Script creates `diary/` automatically if missing

5. **Next session starts fresh:**
   - AI assistants read new DAILY_CONTEXT.md template
   - Historical context available in `diary/YYYY-MM-DD.md` if needed
   - No token waste from loading stale information

**See also:** [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context) and [AMENDMENT-037](PROJECT_CHARTER.md#amendment-037-daily-context-system-three-file-loading-pattern) for governance rules.

**Current status:** Archive script created and ready to use

---

## Files Changed Today

### Created
- `watchmode_api.py` - New quota management module
- `OPTIMIZATION_PLAN.md` - Initial optimization planning
- `PHASE_2_1_COMPLETE.md` - Enrichment optimization documentation
- `PHASE_3_COMPLETE.md` - Quota management implementation
- `PHASE_4_5_FUTURE_WORK.md` - Future optimization roadmap
- `OPTIMIZATION_COMPLETE.md` - Overall completion summary

### Modified
- `generate_data.py` - Added enrichment-on-transition optimization
- `daily_orchestrator.py` - Updated with new workflow
- `PROJECT_CHARTER.md` - Updated governance for optimization
- `config.yaml` - Configuration updates for new features
- `movie_tracking.json` - Enhanced with enrichment state tracking
- `streaming_platform_scraper.py` - Fixed Amazon ASIN placeholder bug with title validation
- `assets/app.js` - Redesigned watch buttons for service-based layout
- `assets/styles.css` - Added side-by-side button layout styles
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Documented Phase 2.1 optimization
- `IMPLEMENTATION_ROADMAP.md` - Marked CRITICAL-003 as resolved
- `DAILY_CONTEXT.md` - Updated with optimization completion status

### Archived
- `itunes_search_api.py` - Deleted dead code (iTunes API non-functional for movies)

---

## Quick Reference

### Daily Workflow
🎬 NEW RELEASE WALL - Daily Startup
====================================

🔍 Step 0: Checking dependencies...
   ✅ All dependencies available

📥 Step 1: Pulling latest data from automation...
   ✅ Data is current

📊 Step 2: Quick Status Report (as of [YYYY-MM-DD])
   Total movies on wall: [N]
   Tracked: [N] / Displayed: [N]
   New today ([MM-DD]): [N]
   New yesterday ([MM-DD]): [N]
   Last generated: [YYYY-MM-DDTHH:MM:SS]

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

### Context Files (Read These First)
- **Daily:** This file (DAILY_CONTEXT.md) - Current state and recent changes
- **Governance:** [PROJECT_CHARTER.md](PROJECT_CHARTER.md) - Rules, amendments, API keys
- **Pipeline:** [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md) - How data flows
- **History:** [diary/](diary/) – End-of-session archives

---

**Last updated:** [End of session]
**Next diary archive:** End of session -> `diary/[YYYY-MM-DD].md`
