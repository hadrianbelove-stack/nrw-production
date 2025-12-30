# Proposed Documentation Updates

Based on Chief Engineer audit, here are the specific updates needed for each core document.

---

## 1. DAILY_CONTEXT.md - COMPLETE REWRITE

**Current State**: 623 lines, mostly October-November content
**Proposed State**: ~100 lines, current December 29 issue focus

**Replace entire file with:**

```markdown
# DAILY_CONTEXT.md

**Date:** 2025-12-29
**Status:** Critical enrichment queue bug identified and fix proposed
**Previous diary entry:** diary/2025-11-06.md

## 🚨 Critical Issue - Enrichment Queue Accumulation

**Discovered:** 2025-12-29
**Status:** Fix proposed, awaiting approval

### The Problem

Enrichment queue has accumulated 594 movies (out of ~600 total available movies):
- **Expected behavior:** 1-10 movies/day
- **Actual behavior:** 594 movies stuck in queue
- **Impact:**
  - 74-minute enrichment runs (should be <5 minutes)
  - 14% success rate (14/100 movies enriched)
  - Queue growing instead of shrinking

### Root Cause Analysis

Three bugs working together:

**1. Catch-up Logic** (pipeline/generator.py:815-833)
- Re-queues movies that became available in last 7 days but weren't enriched
- With empty enrichment_state.json, ALL movies appear "unenriched"
- Adds 100+ movies from last 7 days to queue every run

**2. Queue Merge Logic** (pipeline/generator.py:917-928)
- Merges today's transitions with yesterday's queue
- Designed for persistent retry queue
- No cleanup mechanism removes successfully enriched movies
- Results in infinite accumulation

**3. Empty enrichment_state.json**
- Current: `{}` (2 bytes, empty file)
- Should have: ~485 movies tracked
- Impact: is_enriched() returns False for everything
- Catch-up logic sees ALL movies as needing enrichment

### Proposed Fix

**See:** ENRICHMENT_QUEUE_FIX_PROPOSAL.md for complete proposal

**Summary:**
1. Remove catch-up logic (lines 815-833)
2. Remove queue merge (lines 917-928)
3. Remove enrichment_state.json dependency (unnecessary)
4. Clear polluted queue (start fresh)

**Design principle:** Enrich ONLY on transition day (one attempt), no retries

**Files modified:** 2 files, 18 code changes
**Estimated time:** 2 hours implementation + testing
**Risk:** Low (all changes reversible via git)

---

## Current System Status

**CORE FUNCTIONALITY:** ✅ OPERATIONAL (despite enrichment slowdown)
- **Intake:** Working - discovering new theatrical releases daily
- **Discovery:** Working - detecting digital availability transitions (0-10 movies/day)
- **Enrichment:** Degraded - processing 100 movies instead of 10 (queue accumulation)
- **Display:** Working - data.json updates daily, site functional

**Current Data State:**
- **Tracking:** ~6,000 movies (5,200 tracking, 800 available)
- **Display:** ~600 movies (90-day window)
- **Enrichment Queue:** 594 movies (❌ should be 0-10)

---

## AI Assistant Quick Start

**READ FIRST:** See SYSTEM_ARCHITECTURE.md for system architecture; this file tracks current issues.

**What is this rolling context system?**

This is a **living document** that gets overwritten each session with current information. At the end of each session, we archive it to diary/YYYY-MM-DD.md (immutable historical record).

See [PROJECT_CHARTER.md Amendment 020](PROJECT_CHARTER.md#020-rolling-daily-context) for governance rules.

---

## File Loading Pattern for AI Assistants

**Three-file loading pattern for token-efficient session handoffs:**

1. **DAILY_CONTEXT.md** (this file) - Current state, active issues, priorities
2. **PROJECT_CHARTER.md** - Governance, amendments, core rules
3. **NRW_DATA_WORKFLOW_EXPLAINED.md** - Technical pipeline details

**Session Start:** Read these three files → understand current issue
**Session End:** Update DAILY_CONTEXT.md → archive to diary/

---

## System Architecture Summary

**Charter Governance:**
- Pipeline: Enrichment-on-transition pattern (1-10 movies/day when working)
- Automation: Single-branch workflow, direct commits to main, daily 9 AM UTC
- Admin: Optional editorial review via ./launch_all.sh
- Docs: 7 root MD files (charter-compliant)

**Current Implementation:**
- ✅ Single-branch workflow (no synchronization issues)
- ✅ Modular pipeline services (storage, validation, enrichment)
- ⚠️ Enrichment queue bug (catch-up logic + queue merge = accumulation)
- ✅ Daily automation functional (GitHub Actions running)

**Performance Metrics (When Working Correctly):**
- Runtime: 30-60 seconds per daily run
- API efficiency: 98%+ cache hit rate
- Discovery: 2-5 transitions/day detected
- Enrichment: 1-10 movies/day processed

**Performance Metrics (Current Broken State):**
- Runtime: 74 minutes (timeout at 60 minutes)
- API efficiency: Unknown (batch processing limited to 100 movies)
- Discovery: Working normally (2-5 transitions)
- Enrichment: 100 movies attempted, 14 successful (14% rate)

---

## Next Steps

### Immediate Priority

1. **Review proposal:** ENRICHMENT_QUEUE_FIX_PROPOSAL.md
2. **Approve/modify:** Code changes in ENRICHMENT_QUEUE_FIX_CHANGES.txt
3. **Implement fixes:** Apply 18 code changes
4. **Test locally:** Verify queue size returns to 0-10 movies
5. **Update docs:** Reflect fixes in SYSTEM_ARCHITECTURE.md

### After Fix Implemented

1. Update DAILY_CONTEXT.md with "Issue Resolved" status
2. Update performance metrics in SYSTEM_ARCHITECTURE.md
3. Archive to diary/2025-12-29.md
4. Monitor next day's automation run

---

## Files Changed Today (2025-12-29)

### Investigation Phase
- ENRICHMENT_QUEUE_FIX_PROPOSAL.md (created)
- ENRICHMENT_QUEUE_FIX_CHANGES.txt (created)
- ENRICHMENT_FIX_SUMMARY.md (created)
- CHIEF_ENGINEER_AUDIT.md (created)

### Pending Changes (Awaiting Approval)
- pipeline/generator.py (18 changes proposed)
- metrics/newly_available.json (clear queue)

---

## Archive Instructions

**End-of-session workflow:**

1. Run: `./ops/archive_daily_context.sh`
   - Archives current context to diary/YYYY-MM-DD.md
   - Creates fresh template for next session
   - Use `--dry-run` to preview changes

2. Commit changes:
   ```bash
   git add DAILY_CONTEXT.md diary/2025-12-29.md
   git commit -m "Archive daily context for 2025-12-29"
   ```

3. Next session starts fresh with new DAILY_CONTEXT.md template

---

**Last updated:** 2025-12-29
**Next diary archive:** After enrichment fix tested → diary/2025-12-29.md
**Current phase:** Fix proposed → Awaiting approval → Implementation → Testing
**Estimated completion:** 4-5 hours total
```

---

## 2. SYSTEM_ARCHITECTURE.md - Add Section 5.8

**Location:** After Section 5.7 (line 637)
**Action:** Insert new section

**Add this:**

```markdown
### 5.8 Known Implementation Bugs (December 2025)

⚠️ **CRITICAL BUG IDENTIFIED 2025-12-29**: Enrichment queue accumulation

**The Problem:**

Despite Section 5.2's core principle ("Only enrich on transition"), actual code contains retry mechanisms that violate this design:

1. **Catch-up logic** (lines 815-833): Re-queues movies from last 7 days if not enriched
2. **Persistent queue** (lines 917-928): Merges today's queue with yesterday's
3. **enrichment_state.json dependency**: Empty file makes all movies appear unenriched

**How It Breaks:**

```
Day 1: Discover 5 new movies → Queue: 5
       Enrich 5, fail 4 → enrichment_state remains empty

Day 2: Discover 3 new movies → Catch-up finds 4 from yesterday → Queue: 7
       Merge: yesterday's 4 + today's 3 = 7
       Enrich 7, fail 6 → Queue should clear but doesn't

Day 3+: Accumulation continues...

Week 4: Queue reaches 594 movies (out of ~600 total)
        Runtime: 74 minutes (should be <5 minutes)
        Success rate: 14% (only 14/100 movies enriched)
```

**Impact:**
- Queue size: 594 movies (should be 1-10)
- Runtime: 74 minutes (should be 30-60 seconds)
- Success rate: 14% (normal is 60-80%)
- System attempting to re-enrich already-enriched movies

**Fix Status:**
- **Proposed:** 2025-12-29 (see ENRICHMENT_QUEUE_FIX_PROPOSAL.md)
- **Action:** Remove catch-up logic + queue merge + enrichment_state dependency
- **Design:** Return to pure enrichment-on-transition (one attempt only)

**Design Principle (Restated):**
- Movies get ONE enrichment attempt on transition day
- No retries, no catch-up, no persistent queue
- Manual re-enrichment tool for edge cases (to be built)

**See Also:** DAILY_CONTEXT.md for current status and proposed fix details
```

---

## 3. SYSTEM_ARCHITECTURE.md - Update Section 5.4

**Location:** Section 5.4 (line 534)
**Action:** Replace existing content

**Current:**
```markdown
### 5.4 Flags Used in movie_tracking.json

**`enriched` (boolean)**:
- `true`: Skip enrichment (use cached data)
- `false`: Perform full enrichment
- Set to `false` when movie transitions to "available"

**`enrichment_date` (ISO timestamp)**:
- When movie was last enriched
- Used for cache expiry (90 days)
- Format: "2025-11-05T10:30:00Z"
```

**Replace with:**
```markdown
### 5.4 Enrichment Tracking Systems (As of December 2025)

⚠️ **CONFUSION ALERT**: Two parallel tracking systems exist (causes complexity)

**System 1: movie_tracking.json flags** (Original design)
- **Location:** Inside movie_tracking.json
- **Fields:** `enriched` boolean, `enrichment_date` timestamp
- **Purpose:** Track which movies have been enriched
- **Status:** Still in use

**System 2: enrichment_state.json** (Added November 2025)
- **Location:** Separate file in repo root
- **Purpose:** Track enrichment status independently
- **Rationale:** Prevent race conditions between discovery and enrichment
- **Status:** Currently empty/broken (0 bytes)

**The Problem with Two Systems:**

1. **Dual source of truth**: movie_tracking.json AND enrichment_state.json
2. **Can fail independently**: One can be correct while other is wrong
3. **December 2025 crisis**: enrichment_state.json empty → all movies appear "unenriched"
4. **Complexity**: Catch-up logic checks enrichment_state, not movie_tracking flags

**Proposed Simplification (Dec 2025):**

Remove enrichment_state.json dependency entirely:
- Enrichment happens once on transition day (no tracking needed)
- Success/failure visible in data.json (has rt_score? = enriched)
- Metrics tracked in metrics/enrichment_run.json
- Manual re-enrichment tool for edge cases

**Example JSON (movie_tracking.json):**
```json
{
  "title": "Dune: Part Two",
  "status": "available",
  "enriched": true,
  "enrichment_date": "2025-11-05T10:30:00Z",
  "rt_rating": 93,
  "rt_url": "https://www.rottentomatoes.com/m/dune_part_two"
}
```

**See Section 5.8** for details on current enrichment_state.json bug
```

---

## 4. NRW_DATA_WORKFLOW_EXPLAINED.md - Add Warning Notes

**Location 1:** After line 45
**Action:** Update line and add warning

**Current:**
```markdown
Line 45: "Smart filtering: Only processes movies in state file (1-10 per day)"
```

**Replace with:**
```markdown
- **Smart filtering:** INTENDED to process 1-10 per day from state file
  - ⚠️ **Dec 2025 Bug:** Catch-up logic + queue merge = 594 movies in queue
  - **Fix proposed:** Remove retry mechanisms (ENRICHMENT_QUEUE_FIX_PROPOSAL.md)
```

---

**Location 2:** After line 122
**Action:** Add implementation note

**Current:**
```markdown
3. python3 generate_data.py               # Enrich movies discovered as digitally available from step 2
                                           # → Reads metrics/newly_available.json
```

**Add after this:**
```markdown
   # ⚠️ QUEUE SIZE MONITORING:
   # - Normal: 0-10 movies in queue (jq '.count' metrics/newly_available.json)
   # - Warning: 50+ movies (possible catch-up logic issue)
   # - Critical: 100+ movies (queue accumulation bug confirmed)
   # - Dec 2025: 594 movies (catch-up + merge bug, fix proposed)
```

---

**Location 3:** After line 165 (after automation section)
**Action:** Add new troubleshooting section

**Insert:**
```markdown

---

## 🚨 Known Issues & Troubleshooting (December 2025)

### Issue 1: Enrichment Queue Accumulation

**Symptom:**
- `metrics/newly_available.json` contains 100+ movies
- Enrichment phase takes >10 minutes (should be <5 minutes)
- Low success rate (14% instead of 60-80%)

**Root Cause:**
1. **Catch-up logic** (pipeline/generator.py:815-833) re-queues old movies
2. **Queue merge** (lines 917-928) accumulates across days
3. **Empty enrichment_state.json** makes all movies appear "unenriched"

**Check Status:**
```bash
# Check queue size
jq '.count' metrics/newly_available.json
# Normal: 0-10 | Warning: 50+ | Critical: 100+

# Check enrichment runtime
jq '.enrichment_duration_seconds' metrics/enrichment_run.json
# Normal: <300s | Warning: >600s | Critical: >1800s
```

**Fix Status:** Proposed 2025-12-29 (see ENRICHMENT_QUEUE_FIX_PROPOSAL.md)

---

### Issue 2: Design vs Reality Gap

**Charter Design:**
> "enrichment-on-transition pattern prevents 2+ hour runtimes"
> "Only enrich movies when they transition from tracking to available"

**Actual Implementation:**
- Catch-up logic retries failed enrichments for 7 days
- Persistent queue accumulates movies across days
- Circuit breaker skips after 5 consecutive failures

**Philosophy Mismatch:**
- **User intent:** One attempt on transition day, manual retry if needed
- **Code reality:** Automatic retry for 7 days, persistent queue
- **Result:** Queue accumulation when enrichment_state breaks

**Proposed Alignment:** Remove automatic retry mechanisms entirely

---

### Monitoring Checklist

**Daily Health Check:**
```bash
# 1. Check queue size
jq '.count' metrics/newly_available.json
# Expected: 0-10

# 2. Check last run duration
jq '.enrichment_duration_seconds' metrics/enrichment_run.json
# Expected: <300 seconds

# 3. Check success rate
jq '.movies_enriched, .movies_processed' metrics/enrichment_run.json
# Expected: 60-80% success rate

# 4. Check discovery metrics
jq '.results.transitions' metrics/discovery_run.json
# Expected: 0-10 transitions per day
```

**Red Flags:**
- Queue size >50 movies
- Runtime >600 seconds (10 minutes)
- Success rate <30%
- Batch processing triggered (movies_requested > movies_processed)
```

---

## Summary of All Proposed Updates

**Priority 1: Immediate (Before Code Changes)**
1. ✅ DAILY_CONTEXT.md - Complete rewrite (30 min)
2. ✅ SYSTEM_ARCHITECTURE.md Sec 5.8 - Add bug warning (15 min)
3. ✅ NRW_DATA_WORKFLOW - Add monitoring notes (15 min)

**Priority 2: After Code Changes**
4. ⏳ SYSTEM_ARCHITECTURE.md Sec 5.4 - Update tracking systems (10 min)
5. ⏳ DAILY_CONTEXT.md - Update with "Issue Resolved" (5 min)
6. ⏳ SYSTEM_ARCHITECTURE.md Sec 5.3 - Update performance metrics (5 min)

**Total Time:** ~1.5 hours

**Note:** All updates can be in separate files for review before applying to actual docs.
