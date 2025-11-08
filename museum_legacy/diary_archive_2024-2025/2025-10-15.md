# DAILY_CONTEXT.md
**Date:** 2025-10-15
**Previous diary entry:** None (first daily context)

---

## 🤖 AI Assistant Quick Start

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

See [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context) for governance rules.

---

## Current State

### What's Working
- **GitHub Actions automation:** ✅ Fully operational
  - Daily cron job runs at 9 AM UTC (1 AM PST / 2 AM PDT)
  - `daily_orchestrator.py` handles check → generate → commit pipeline
  - Automated commits: "Daily update - YYYY-MM-DD [automated]"
  - Two successful runs today (commits `7657abc` and `7d4c219`)
  - Manual trigger available via `workflow_dispatch` for testing

- **Data pipeline:** ✅ Production-ready
  - Tracking: 1,168 movies total (229 with digital dates, 939 still tracking)
  - Display: 228 movies on wall (generated 2025-10-15T12:48:18)
  - Date range: 2025-10-15 (newest) → 2025-09-06 (oldest)
  - Pipeline: `movie_tracker.py check` → `generate_data.py` → `data.json`

- **Launch workflow:** ✅ One-command startup
  - `./launch_NRW.sh` pulls latest data, shows status, starts server at localhost:8000
  - Consolidated git pull, Python status report, and browser launch
  - Created 2025-10-15 as canonical daily startup script
  - **Recent improvements:** Added error handling, port conflict detection (8000→8001 fallback), clean Ctrl+C shutdown via trap handler, dependency validation, and updated context reminders to reference DAILY_CONTEXT.md first

### Architecture
- **Runtime:** `index.html` → `assets/app.js` + `assets/styles.css` → `data.json`
- **Generation:** `movie_tracking.json` → `generate_data.py` → `data.json` (228 movies)
- **Automation:** GitHub Actions → `daily_orchestrator.py` → pipeline → auto-commit
- **API keys:** TMDB and OMDb API keys are configured in scripts

---

## What We Did Today (2025-10-15)

### 1. Fixed GitHub Actions Automation
**Commits:** `b5dc672` "Fix automation: correct API params and eliminate confusing language"

**Historical context:** On Sept 6, we discovered an account flag issue that was preventing the automation from running correctly. The initial implementation had incorrect API parameters and confusing error messages that made debugging difficult.

**What we built:**
- Created `.github/workflows/daily-check.yml` with cron schedule `0 9 * * *` (9 AM UTC daily)
- Workflow triggers `daily_orchestrator.py` which runs the full pipeline:
  1. `movie_tracker.py check` - Updates provider availability and digital dates
  2. `generate_data.py` - Enriches data and writes `data.json`
  3. Git commit with message pattern: "Daily update - YYYY-MM-DD [automated]"
- Added `workflow_dispatch` trigger for manual testing without waiting for cron
- Fixed API parameters in data fetching scripts
- Removed confusing language from error messages and logs

**Results:** Two successful automated runs today (commits `7657abc` and `7d4c219`). The wall now updates automatically every day without manual intervention. The system pulls new releases, checks provider availability, and commits updated data to the repo.

**Technical details:**
- Runner: `ubuntu-latest`
- Python: 3.10
- Dependencies: `requests`, `pyyaml`, `beautifulsoup4`, `lxml`, `selenium`
- Git config: `action@github.com` / "NRW Daily Bot"
- Only commits if there are staged changes (avoids empty commits)

### 2. Created Launch Script (`launch_NRW.sh`)
**Created:** 2025-10-15

**Purpose:** Single-command daily startup for viewing the wall

**What it does:**
1. Pulls latest data from GitHub automation (`git pull origin main`)
2. Shows quick status: total movies, today's new releases, yesterday's count
3. Reminds about key context files (PROJECT_CHARTER.md, NRW_DATA_WORKFLOW_EXPLAINED.md)
4. Starts local server on port 8000 and opens browser

**Usage:** `./launch_NRW.sh` (one command, handles everything)

**Strengths:**
- Convenience: One command to get up and running
- Auto-sync: Pulls latest data before starting
- Status visibility: Shows what's new today
- Context reminders: Prompts reading governance docs

**Known weaknesses:**
- No error handling for git pull failures
- No port conflict detection (fails silently if 8000 is busy)
- Poor Ctrl+C cleanup (leaves Python server running)
- No validation that data.json exists before starting

**Decision:** Script stays in root for convenience (not moved to ops/) despite being operational. User accessibility trumps folder organization for daily-use tools.

### 3. Established AMENDMENT-036: Rolling Daily Context
**Added to:** [PROJECT_CHARTER.md](PROJECT_CHARTER.md#amendment-036-rolling-daily-context)

**New governance rule:**
- `DAILY_CONTEXT.md` = living document, always current, overwritten each session
- `diary/YYYY-MM-DD.md` = end-of-session archives (immutable)
- Replaces stale `complete_project_context.md` (moved to museum_legacy/)
- Format: Current State, What We Did, Known Issues, Next Priorities, Files Changed

**Why it matters:** Context documents were getting stale and confusing. The old `complete_project_context.md` was last updated Sept 6 and had become irrelevant. The new system ensures fresh context at session start, with historical archive for audit.

**Implementation:**
- Created `DAILY_CONTEXT.md` (this file)
- Created `diary/` directory for archives
- Archived old `complete_project_context.md` to `museum_legacy/`
- Added AMENDMENT-036 to PROJECT_CHARTER.md

### 4. Enhanced Launch Script Error Handling
**Modified:** `launch_NRW.sh` (lines 1-73 → expanded with improvements)

**Problem:** Script had five documented weaknesses (see lines 202-209): no trap handler, no port detection, no error handling, no dependency checks, outdated context reminders.

**Solution implemented:**
1. **Trap handler** - Added SIGINT/SIGTERM handler to cleanly kill server on Ctrl+C
2. **Port conflict detection** - Checks if 8000 is busy, falls back to 8001, errors if both occupied
3. **Dependency validation** - Checks for python3, git, and browser opener before execution
4. **Git error handling** - Graceful degradation for offline mode (warns but continues with stale data)
5. **data.json validation** - Verifies file exists and is readable before status report
6. **Context reminder update** - Now references DAILY_CONTEXT.md as primary file per AMENDMENT-036

**Result:** Script is now production-grade with comprehensive error handling while maintaining simple one-command user experience. Addresses all issues documented in "Known Issues" section.

**Technical details:**
- Trap pattern: `trap "kill $SERVER_PID 2>/dev/null" INT TERM`
- Port detection: `lsof -Pi :$PORT -sTCP:LISTEN -t`
- Dependency checks: `command -v python3 >/dev/null`
- Graceful git failures: Continues with warning rather than exiting
- Clear error messages with remediation steps

---

## Conversation Context (Key Decisions)

### Decision: Rolling Daily Context vs Full PROJECT_LOG.md
**Problem:** Loading full project history wastes tokens and creates confusion with outdated context.

**Solution:** AMENDMENT-036 creates a rolling daily context system:
- `DAILY_CONTEXT.md` is rewritten each session with current state
- End-of-session archive to `diary/YYYY-MM-DD.md` preserves history
- Next session starts fresh by reading new DAILY_CONTEXT.md

**Why:** Token efficiency + clarity. AI assistants get relevant recent context without months of stale history. Immutable diary archives provide audit trail when needed.

### Decision: Launch Script Location and Limitations
**Analysis of `launch_NRW.sh`:**

**Strengths:**
- One-command startup (`./launch_NRW.sh`)
- Auto git pull (always syncs latest data)
- Status report (shows new releases today)
- Context reminders (prompts reading docs)

**Previous weaknesses (now resolved):**
- No error handling (git pull failures go unnoticed)
- Port conflicts (doesn't check if 8000 is busy)
- Poor Ctrl+C cleanup (leaves server running as zombie process)
- No validation (doesn't verify data.json exists)

**Current capabilities:**
- Comprehensive error handling with graceful degradation
- Port conflict detection (8000→8001 fallback)
- Clean shutdown via trap handler
- Dependency validation and helpful error messages

**Decision:** Keep script in root despite being operational code. Rationale: Daily-use tools should be maximally convenient. User accessibility > folder organization for frequently-used scripts.

### Decision: Archive Automation
**Plan:** Create `ops/archive_daily_context.sh` script for end-of-session workflow:
1. Copy `DAILY_CONTEXT.md` → `diary/YYYY-MM-DD.md`
2. Create fresh template for next session
3. Next session reads new DAILY_CONTEXT.md (which was today's work)

**Why scripted:** Ensures consistent archiving, prevents manual errors, creates clean handoff between sessions.

### Decision: AMENDMENT-021 Update Needed
**Current issue:** AMENDMENT-021 references `complete_project_context.md` which no longer exists.

**Action needed:** Update AMENDMENT-021 to reference `DAILY_CONTEXT.md` instead (subsequent phase after archive script is working).

---

## Known Issues

### 1. Bootstrap Date Clustering
- **Symptom:** Many movies show Sept 5-6 digital dates (discovery date, not true digital date)
- **Root cause:** Initial bootstrap captured "first seen with providers" as digital date
- **Impact:** Historical accuracy compromised for ~100 movies from first bootstrap
- **Mitigation:** Daily checks will gradually improve data quality for new releases
- **Status:** Accepted limitation; focus is on forward accuracy

### 2. Git Status Shows Uncommitted Changes
- **Current status:**
  ```
  M NRW_DATA_WORKFLOW_EXPLAINED.md
  MM data.json
  M generate_data.py
  M missing_wikipedia.json
  ?? launch_NRW.sh
  ```
- **Why:** Working changes from today's fixes and launch script creation
- **Action needed:** Review and commit after DAILY_CONTEXT.md enhancements are finalized

### 3. Missing Wikipedia Links
- **Symptom:** Some movies have `null` wikipedia links
- **Tracking:** `missing_wikipedia.json` contains unresolved titles
- **Pipeline:** Waterfall checks overrides → cache → Wikidata → MediaWiki search
- **Status:** Known limitation; ongoing manual override additions as needed

### 4. Launch Script Improvements (Completed)
- **Previous issues:** Script didn't handle errors gracefully
- **✅ Implemented:**
  - Trap handler for clean Ctrl+C shutdown (kills server process)
  - Port conflict detection with 8001 fallback
  - Dependency checks (python3, git, browser opener)
  - Git pull error handling (graceful degradation for offline mode)
  - data.json validation before status report
  - Updated context reminders to prioritize DAILY_CONTEXT.md
- **Status:** ✅ Implemented - addresses all issues from lines 202-209

---

## Next Priorities

### Immediate (This Session)
1. ✅ Create rolling daily context system (DAILY_CONTEXT.md + diary/)
2. ✅ Enhance DAILY_CONTEXT.md with AI handoff improvements
3. ⏳ Commit working changes (data.json, generate_data.py, launch script, DAILY_CONTEXT.md, etc.)
4. ⏳ Test one full cycle: launch script → view wall → verify data freshness

### Next Phase (Archiving Automation)
1. ✅ **Create `ops/archive_daily_context.sh`** - Script to automate end-of-session workflow:
   - ✅ Copy `DAILY_CONTEXT.md` → `diary/YYYY-MM-DD.md`
   - ✅ Create fresh template for next session
   - ✅ Validate archive was created successfully
   - ✅ Template updated to match current DAILY_CONTEXT.md structure
2. ⏳ **Test archive script with first real end-of-session run** - Verify it handles edge cases (existing archives, missing diary/, etc.)
3. ⏳ **Verify diary/ archives are being committed to git properly** - Ensure archived contexts are tracked in version control

### Subsequent Phase (Polish & Updates)
1. **✅ Improve `launch_NRW.sh` error handling:**
   - ✅ Check if port 8000 is busy before starting server
   - ✅ Validate data.json exists and is valid JSON
   - ✅ Handle git pull failures gracefully
   - ✅ Add proper Ctrl+C cleanup (trap SIGINT, kill server process)
   - ✅ Show helpful error messages with remediation steps

2. **Update AMENDMENT-021** - Remove `complete_project_context.md` requirement, reference `DAILY_CONTEXT.md` instead

3. **Monitor GitHub Actions** - Verify daily updates capture new releases correctly over next few days

### Short-term (Next Few Days)
1. Verify daily updates are capturing new releases correctly
2. Add Wikipedia overrides for high-profile missing links
3. Consider UI improvements (hover states, date marker sizing per AMENDMENT-033)

### Long-term (Ongoing)
1. Improve data quality: reduce bootstrap date artifacts over time
2. Expand tracking: add more theatrical releases weekly (`movie_tracker.py bootstrap`)
3. Platform detection: enhance Watch button provider detection
4. Performance: optimize `generate_data.py` for larger datasets

---

## Archive Instructions

**End-of-session workflow (automated via `ops/archive_daily_context.sh`):**

1. Run archive script: `./ops/archive_daily_context.sh`
   - Archives current context to `diary/YYYY-MM-DD.md`
   - Creates fresh template for next session
   - Use `--dry-run` to preview changes without executing

2. **Testing:** `./ops/archive_daily_context.sh --dry-run` shows what would happen

3. **Troubleshooting:**
   - Permission error: `chmod +x ops/archive_daily_context.sh`
   - Missing file error: Ensure you're in repo root
   - Directory issues: Script creates `diary/` automatically
   - If `diary/` folder is missing: `mkdir -p diary` before running `cp` command

4. **Next session starts fresh:**
   - AI reads new DAILY_CONTEXT.md template
   - Historical context available in `diary/` if needed
   - No token waste from stale information

**Current status:** Archive script created and ready to use

---

## Files Changed Today

### Created
- `launch_NRW.sh` - One-command daily startup script (stays in root for convenience)
- `DAILY_CONTEXT.md` - This file (rolling daily context, enhanced for AI handoff)
- `diary/` - Directory for context archives (contains .gitkeep placeholder)

### Modified
- `PROJECT_CHARTER.md` - Added AMENDMENT-036 (rolling daily context) at lines 247-252
- `.github/workflows/daily-check.yml` - Fixed automation parameters (commit `b5dc672`)
- `generate_data.py` - API parameter corrections
- `data.json` - Generated output (228 movies, 2025-10-15T12:48:18)
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Documentation updates
- `missing_wikipedia.json` - Updated during generation
- `ops/archive_daily_context.sh` - Updated template to match current DAILY_CONTEXT.md structure
- `DAILY_CONTEXT.md` - Updated Next Priorities section to mark archive script as completed
- `launch_NRW.sh` - Enhanced with error handling, port conflict detection, trap handler, dependency checks, and updated context reminders (addresses issues from lines 202-209)

### Archived
- `complete_project_context.md` → `museum_legacy/` (stale, superseded by DAILY_CONTEXT.md)

---

## Quick Reference

### Daily Workflow
```bash
# Morning: View the wall
./launch_NRW.sh

# Automation runs automatically at 9 AM UTC
# (No manual intervention needed)
```

### Manual Pipeline (if needed)
```bash
# Check for new digital releases
python3 movie_tracker.py check

# Regenerate data.json
python3 generate_data.py

# Add new theatrical releases (weekly)
python3 movie_tracker.py bootstrap
```

### Context Files (Read These First)
- **Daily:** This file (DAILY_CONTEXT.md) - Current state and recent changes
- **Governance:** [PROJECT_CHARTER.md](PROJECT_CHARTER.md) - Rules, amendments, API keys
- **Pipeline:** [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md) - How data flows
- **History:** `diary/YYYY-MM-DD.md` - End-of-session archives (when needed)

---

**Last updated:** 2025-10-15T12:55:00 (enhanced with AI handoff improvements)
**Next diary archive:** End of session → `diary/2025-10-15.md` (manual until archive script created)
