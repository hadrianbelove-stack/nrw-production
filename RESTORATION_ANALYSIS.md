# NRW Restoration Analysis - Oct 23 (Working) vs Nov 6 (Current)

**Analysis Date:** 2025-11-06
**Baseline Commit:** 73c6eef3 (Oct 23, 2025 - Last known working state)
**Current Commit:** ef12e3e30b153cd470b841306f8cf30f25612002 (Nov 6, 2025 - After fixes)
**Comparison Range:** 73c6eef3..ef12e3e3 (All analysis scoped to this range)
**Note:** Commit d587dd7 contains documentation-only updates after ef12e3e3
**Outage Period:** Oct 25 - Nov 5 (11 days)
**Status:** System operational as of Nov 6, 09:19 UTC

## Executive Summary

### Key Findings
- **Root Cause:** Branch divergence + data corruption + Playwright CI failures
- **Changes Analyzed:** 5 files, 2000+ lines of diffs
- **Good Changes:** 8 improvements to keep (validation, documentation, enrichment)
- **Problematic Changes:** 3 areas to evaluate for revert (Playwright manager, workflow, selectors)
- **Recommendation:** Surgical reverts, not full rollback

### Quick Decision Matrix
| Component | Status | Action |
|-----------|--------|--------|
| Validation resilience | ✅ KEEP | Critical fix |
| Schema validation | ✅ KEEP | Prevents corruption |
| Enrichment-on-transition | ✅ KEEP | 98% cost reduction |
| PlaywrightManager | ⚠️ EVALUATE | Revert and test |
| Two-branch workflow | ⚠️ EVALUATE | Keep with auto-sync |
| RT selectors | ⚠️ EVALUATE | Compare success rates |

### Impact Assessment
The Oct 25-Nov 5 outage was caused by a **perfect storm** of three issues:
1. **Branch divergence** - Bot ran old code missing critical fixes
2. **Data corruption** - Line 1848 bug corrupted enriched flags
3. **Playwright CI failures** - Scrapers returning null for all movies

The Nov 5-6 fixes addressed the **symptoms** but may not have resolved the **root technical issues**.

---

## Timeline of Changes

### Oct 23, 2025 (Baseline - Working) ✅
- Daily update runtime: ~30 seconds
- Enrichment: Inline Selenium RT scraping
- Workflow: Checkout main, commit to main
- Validation: Basic checks
- **Status:** Operational

### Oct 24, 2025 (Improvements) ✅
- Added enrichment-on-transition pattern (AMENDMENT-025)
- Added discovery/monitoring split
- Reduced API calls from 9,540/month to 150-300/month
- **Status:** Working

### Oct 25, 2025 (Breaking Changes) ❌
- Changed workflow to checkout automation-updates (no auto-sync)
- Introduced two-branch deployment strategy
- **Status:** Automation begins failing

### Oct 26, 2025 (More Breaking Changes) ❌
- Added PlaywrightManager singleton (commit fb271c2)
- Migrated RT scraper to Playwright (rt_scraper_playwright.py)
- Removed Google search fallbacks
- **Status:** Scrapers fail in CI, watch links all null

### Oct 27-Nov 4, 2025 (Failure Period) ❌
- 10 consecutive failed runs
- Branch divergence: automation-updates 22 commits behind main
- Data corruption: Line 1848 bug corrupted enriched flags
- Runtime: 2+ hours (550+ movies re-enriched)
- **Status:** Complete outage

### Nov 5, 2025 (Emergency Fixes) 🟡
- Added automatic branch sync to workflow
- Extended validation window (7→14 days, 30-day fallback)
- Softened content quality checks
- Rebuilt corrupted data
- **Status:** Partially working

### Nov 6, 2025 (Full Recovery) ✅
- Fixed discovery digital_date bug
- Fixed line 1848 data corruption bug
- Added comprehensive schema validation
- Created SYSTEM_ARCHITECTURE.md
- **Status:** Operational (confirmed 09:19 UTC)

---

## File-by-File Analysis

### 3.1: generate_data.py

**Total Changes:** ~1000 lines added/modified

#### Diff Summary (73c6eef3..ef12e3e3)
Key changes from git diff analysis:

**Lines 16-28: New Imports**
```python
+from rt_scraper_playwright import RTScraperPlaywright
+from wikipedia_scraper_playwright import WikipediaScraperPlaywright
+from constants import PLACEHOLDER_ASINS
+try:
+    from streaming_platform_scraper import StreamingPlatformScraper
+except ImportError:
+    StreamingPlatformScraper = None
+
+# Phase 3: Watchmode API with quota management
+from watchmode_api import create_watchmode_client
```

**Lines 78-156: Enhanced Constructor**
- Added logger initialization FIRST before operations
- Environment variable support for TMDB_API_KEY and WATCHMODE_API_KEY
- Watchmode client initialization with quota management
- Added discovery_stats tracking structure
- Lazy initialization for rt_scraper, wikipedia_scraper, platform_scraper

**Lines 287-340: RT Scraper Migration (KEY CHANGE)**
```python
-    def _init_rt_driver(self):
-        """Initialize Selenium WebDriver for RT scraping"""
+    def _init_rt_scraper(self):
+        """Initialize RT scraper with Playwright (lazy initialization)"""
         if self.rt_scraper is not None:
             return self.rt_scraper is not False

         try:
-            from selenium import webdriver
-            # ... Chrome driver setup
+            self.rt_scraper = RTScraperPlaywright(
+                cache_file='rt_cache.json',
+                config=self.config,
+                logger=self.logger
+            )
```

**Lines 1848-1852: Validation Bug Region (CRITICAL FIX)**
The diff shows data loading changed to:
```python
data_movies = json.load(df).get('movies', [])
```
This is the line 1848 bug that caused data corruption - correct restoration uses proper JSON loading.

#### KEEP - Critical Improvements ✅

**1. Discovery/Monitoring Functions** (lines 1513-1814)
- `discover_new_premieres()` - Find new movies via TMDB
- `check_tracking_movies()` - Monitor for digital availability
- **Why keep:** Enables enrichment-on-transition (98% API cost reduction)
- **Evidence:** SYSTEM_ARCHITECTURE.md Section 5 documents this pattern

**2. Enrichment-on-Transition Logic** (lines 2333-2426)
- Only enrich movies when status changes tracking→available
- Uses `enriched` flag and `enrichment_date` timestamp
- **Why keep:** Reduces runtime from 75 min to 30 sec
- **Evidence:** NRW_DATA_WORKFLOW_EXPLAINED.md lines 42-64

**3. Schema Validation** (lines 1921-1990)
- `validate_data_json_schema()` - Validates data.json structure
- `validate_enrichment_consistency()` - Detects corrupted enriched flags
- **Why keep:** Prevents line 1848 bug from recurring
- **Evidence:** Fixed today, prevents data corruption cascade

**4. Google Fallback Removal** (lines 1017, 1110, etc.)
- Changed from Google search URLs to `null`
- Frontend shows "NOT AVAILABLE" instead of fake search
- **Why keep:** Better UX, honest about missing links
- **Evidence:** User confirmed this is good in conversation

**5. Watchmode Quota Management** (lines 27-29, 725-772)
- Added `watchmode_api.py` integration
- Quota tracking and graceful degradation
- **Why keep:** Prevents API quota exhaustion
- **Evidence:** DAILY_UPDATE_DIAGNOSIS.md mentions quota issues

**6. Discovery Digital_Date Fix** (line 2070)
- Sets `digital_date: None` at discovery (not theatrical_date)
- Monitoring sets it when providers detected
- **Why keep:** Fixed Nov 6, prevents incorrect dates
- **Evidence:** Commit ef12e3e "Fix discovery bug"

#### REVERT - Problematic Changes ❌

**1. RT Scraper Migration to Playwright** (lines 287-340)
- Removed inline Selenium RT scraping
- Added RTScraperPlaywright class integration
- **Why revert:** Scrapers failing in CI, worked with Selenium
- **Evidence:** DAILY_UPDATE_DIAGNOSIS.md "Playwright scrapers failing in CI"
- **Revert to:** Oct 23 inline Selenium implementation
- **Keep:** The discovery/monitoring functions (separate concern)

#### EVALUATE - Unclear ⚠️

**1. Placeholder ASIN Detection** (lines 643-663, 1060-1067)
- Added checks for placeholder Amazon ASINs
- Purges cache entries with placeholders
- **Why evaluate:** Might be fixing a real issue or over-engineering
- **Test:** Check if placeholder ASINs are still appearing

**2. Service Exclusion** (lines 692-700)
- Excludes fuboTV and Philo from watch links
- **Why evaluate:** Might be valid (low-quality services) or too restrictive
- **Test:** Check if these services provide valid links

### 3.2: rt_scraper_playwright.py

**Status:** NEW file (didn't exist Oct 23)

#### Diff Summary (73c6eef3..ef12e3e3)
Entirely new file created with 514 lines:

**Lines 1-34: Core Setup**
```python
+from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
+import time
+import json
+import os
+import random
+import re
+from datetime import datetime, timedelta
+from urllib.parse import quote
+from playwright_manager import get_playwright_manager
+
+class RTScraperPlaywright:
+    def __init__(self, cache_file='rt_cache.json', config=None, logger=None):
+        # Shared manager reference
+        self.manager = get_playwright_manager()
+```

**Lines 320-380: Selector Strategy**
```python
+            # Try selector fallbacks for search results
+            search_selectors = [
+                "search-page-media-row a[data-qa='info-name']",  # Primary
+                "a[data-qa='thumbnail-link']",  # Fallback 1
+                "a[href*='/m/'][data-qa='info-name']",  # Fallback 2
+                "search-page-result a[href*='/m/']",  # Fallback 3
+                "a[href*='/m/']"  # Generic movie link
+            ]
+```

**Lines 365-395: Score Extraction**
```python
+            score_selectors = [
+                "rt-text[slot='criticsScore']",  # Primary
+                "score-board",  # Fallback 1
+                "[data-qa='tomatometer']",  # Fallback 2
+                "[data-qa='tomatometer-value']",  # Fallback 3
+                ".tomatometer-score",  # Fallback 4
+                "score-icon-critic"  # Fallback 5
+            ]
+```

#### EVALUATE for Revert ⚠️
- **Purpose:** Playwright-based RT scraper using PlaywrightManager
- **Why it was created:** Replace inline Selenium RT scraping
- **Problem:** Uses `get_playwright_manager()` which may cause CI failures
- **Evidence:** Line 34 `self.manager = get_playwright_manager()`
- **Revert option:** Delete this file, restore inline Selenium in generate_data.py
- **Keep option:** Fix PlaywrightManager CI issues, keep the file

**Decision needed:** Does the Playwright approach provide benefits over Selenium?
- **Pros:** Modern, faster, better selector API
- **Cons:** Failing in CI, added complexity (separate file)
- **Recommendation:** Revert to inline Selenium (Oct 23 approach) until CI issues resolved

### 3.3: playwright_manager.py

**Status:** NEW file (didn't exist Oct 23)

#### Diff Summary (73c6eef3..ef12e3e3)
Entirely new file created with 146 lines:

**Lines 1-47: Singleton Pattern**
```python
+class PlaywrightManager:
+    """Singleton manager for shared Playwright instance"""
+
+    _instance = None
+    _lock = threading.Lock()
+
+    def __new__(cls):
+        if cls._instance is None:
+            with cls._lock:
+                if cls._instance is None:
+                    cls._instance = super().__new__(cls)
+                    cls._instance._initialized = False
+        return cls._instance
+```

**Lines 52-68: Event Loop Detection**
```python
+                # Check for existing event loop
+                import asyncio
+                try:
+                    loop = asyncio.get_running_loop()
+                    print(f"[PlaywrightManager] WARNING: Event loop already running: {loop}")
+                    print(f"[PlaywrightManager] This will cause Playwright sync API to fail!")
+                except RuntimeError:
+                    print("[PlaywrightManager] No event loop detected - safe to proceed")
+```

**Lines 135-146: Global Manager Function**
```python
+def get_playwright_manager():
+    """
+    Get the global PlaywrightManager singleton
+
+    Returns:
+        PlaywrightManager: Global manager instance
+    """
+    global _manager
+    if _manager is None:
+        _manager = PlaywrightManager()
+    return _manager
+```

#### EVALUATE for Revert ⚠️
- **Purpose:** Singleton manager to prevent multiple Playwright event loops
- **Why it was created:** Fix asyncio event loop conflicts
- **Problem:** May not work correctly in CI environment
- **Evidence:** Lines 56-63 check for existing event loop, print warnings
- **Revert option:** Delete this file, use individual sync_playwright().start() in each scraper
- **Keep option:** Fix the CI integration, keep the singleton pattern

**Decision needed:** Is the shared manager necessary?
- **Oct 23 approach:** Each scraper used individual sync_playwright().start()
- **Current approach:** All scrapers share one Playwright instance via manager
- **Evidence from DAILY_UPDATE_DIAGNOSIS.md:** "Playwright worked locally but failed in CI"
- **Recommendation:** Revert to individual instances (Oct 23 approach) - simpler, proven to work

### 3.4: daily-check.yml

#### Diff Summary (73c6eef3..ef12e3e3)
Key workflow changes from git diff analysis:

**Lines 26-38: Checkout Strategy Change**
```yaml
-      - name: Checkout repository
+      - name: Checkout automation-updates branch
         uses: actions/checkout@v4
         with:
-          ref: main
+          ref: automation-updates
+          fetch-depth: 0
+        continue-on-error: true
+        id: checkout-automation
+
+      - name: Checkout main branch fallback
+        if: steps.checkout-automation.outcome == 'failure'
+        uses: actions/checkout@v4
+        with:
+          ref: main
```

**Lines 60-81: Automatic Sync Step (NEW)**
```yaml
+      - name: Sync main → automation-updates
+        id: sync
+        run: |
+          git fetch origin main
+          # Capture HEAD before merge to detect if merge creates new commits
+          BEFORE_MERGE=$(git rev-parse HEAD)
+          git merge origin/main --no-edit || {
+            echo "⚠️ Merge conflict detected - branches have diverged"
+            echo "Manual intervention required to resolve conflicts"
+            echo "Run: git checkout automation-updates && git merge main"
+            git merge --abort
+            exit 1
+          }
+```

**Lines 97-99: Branch Switching Added**
```yaml
+      - name: Switch to automation branch
+        if: steps.changes.outputs.changes == 'true'
+        run: git checkout -B automation-updates
+```

#### KEEP - Critical Fixes ✅
**Automatic sync step** (lines 60-81)
- **Why keep:** Prevents branch divergence (primary root cause)
- **Evidence:** DAILY_UPDATE_DIAGNOSIS.md "Fix #1: Automatic Branch Synchronization"
- **Impact:** Bot now gets latest fixes from main automatically

#### EVALUATE for Revert ⚠️
**Checkout automation-updates** (line 29)
- **Why it was changed:** Two-branch deployment strategy (AMENDMENT-043)
- **Problem:** Caused branch divergence when sync wasn't automatic
- **Now:** Sync is automatic, so two-branch might work
- **Alternative:** Revert to checkout main (simpler)
- **Recommendation:** KEEP with automatic sync OR revert to main (both work now)

**User's subsequent phases suggest:** Revert to checkout main (simplify)
- This would mean: Checkout main → run pipeline → commit to main
- Simpler than: Checkout automation-updates → sync main → run → commit
- **Trade-off:** Lose separation of bot/user work, but gain simplicity

### 3.5: daily_orchestrator.py

#### KEEP - All Changes ✅
1. **Added has_real_watch_link() helper** (lines 15-37)
2. **Extended validation window** (line 186): 7→14 days
3. **Added 30-day fallback** (lines 189-198)
4. **Softened provider coverage** (lines 254-265)
5. **Added phase timings** (lines 45, 72-77, 407-412)
6. **Changed pipeline** (lines 448-464): movie_tracker.py → generate_data.py --discover/--check
7. **Added newsletter generation** (lines 309-379)
8. **Removed hardcoded path** (lines 434-445): ~/Downloads/nrw-production → env var

- ✅ All changes in daily_orchestrator.py are improvements
- ✅ Validation resilience prevents false failures
- ✅ Phase timings help diagnose performance issues
- ✅ Pipeline changes align with discovery/monitoring split
- ✅ Newsletter generation is a feature, not a bug
- ✅ Removed hardcoded path improves portability

**NO REVERTS NEEDED** in daily_orchestrator.py

---

## Change Categories

### KEEP - Proven Improvements (8 items) ✅

| Change | File | Lines | Rationale | Evidence |
|--------|------|-------|-----------|----------|
| Discovery/monitoring split | generate_data.py | 1513-1814 | Enables enrichment-on-transition | 98% API reduction |
| Enrichment-on-transition | generate_data.py | 2333-2426 | Reduces runtime 75min→30s | SYSTEM_ARCHITECTURE.md |
| Schema validation | generate_data.py | 1921-1990 | Prevents data corruption | Fixed line 1848 bug |
| Validation resilience | daily_orchestrator.py | 184-198 | Prevents false failures | Fixed Nov 5 |
| Google fallback removal | generate_data.py | Multiple | Better UX (null > search) | User confirmed |
| has_real_watch_link() | daily_orchestrator.py | 15-37 | Accurate metrics | Fixes stats reporting |
| Automatic branch sync | daily-check.yml | 60-81 | Prevents divergence | Primary fix |
| Documentation | Multiple | N/A | AI assistant guidance | SYSTEM_ARCHITECTURE.md |

### REVERT - Problematic Changes (3 items) ❌

| Change | File | Action | Rationale | Risk |
|--------|------|--------|-----------|------|
| PlaywrightManager integration | rt_scraper_playwright.py, generate_data.py | Delete rt_scraper_playwright.py, restore inline Selenium | Failing in CI | Might reintroduce event loop issues |
| Workflow checkout automation-updates | daily-check.yml | Change line 29 to `ref: main` | Simplify workflow | Might reintroduce merge conflicts |
| RT selector changes | rt_scraper_playwright.py | Revert to Oct 23 selectors | Unknown if broken | Might lose improvements |

### EVALUATE - Needs Testing (4 items) ⚠️

| Change | File | Lines | Question | Test |
|--------|------|-------|----------|------|
| Placeholder ASIN detection | generate_data.py | 643-663 | Still needed? | Check for placeholder ASINs |
| Service exclusion (fuboTV, Philo) | generate_data.py | 692-700 | Valid exclusion? | Test if services work |
| Weekly workflow pattern | weekly-full-regen.yml | 28 | Should match daily? | Already fixed Nov 6 |
| Platform scraper integration | generate_data.py | 1230-1386 | Working in CI? | Check CI logs |

---

## Detailed Revert Plan

### REVERT-1: PlaywrightManager Integration ❌

**Files affected:**
- rt_scraper_playwright.py (DELETE entire file)
- generate_data.py (REVERT lines 287-340 to Oct 23 inline Selenium)
- playwright_manager.py (KEEP but comment out - may be useful later)

**Specific changes in generate_data.py:**
1. Remove import: `from rt_scraper_playwright import RTScraperPlaywright` (line 19)
2. Remove `_init_rt_scraper()` method (lines 290-305)
3. Restore `_init_rt_driver()` method from Oct 23 (Selenium-based)
4. Restore `_rt_rate_limit()` method from Oct 23
5. Restore `_scrape_rt_page()` method from Oct 23 (inline Selenium)
6. Update `scrape_rt_score()` to call `_scrape_rt_page()` directly
7. Restore `_save_rt_cache()` method from Oct 23

**Rationale:**
- Oct 23 inline Selenium approach worked reliably
- Playwright integration failing in CI ("link: None" for all movies)
- Simpler code (no separate file, no manager dependency)
- Can revisit Playwright migration after fixing CI issues

**Risk:**
- Might reintroduce event loop issues (but Oct 23 didn't have them)
- Selenium is older technology (but proven to work)
- Loses Playwright benefits (faster, better API)

**Testing:**
```bash
# After revert
python3 generate_data.py --full
# Check RT scores in data.json
jq '[.movies[] | select(.rt_score != null)] | length' data.json
# Should be >80% coverage
```

### REVERT-2: Workflow Checkout Target ⚠️

**File:** `.github/workflows/daily-check.yml`

**Specific changes:**
1. Line 29: Change `ref: automation-updates` back to `ref: main`
2. Lines 34-39: Remove fallback checkout (not needed if checking out main)
3. Lines 60-81: KEEP the sync step but modify it to sync automation-updates→main (reverse direction)
4. Lines 97-99: Remove "Switch to automation branch" (already on main)
5. Update to: Checkout main → run pipeline → commit to main (simple)

**Rationale:**
- Simpler workflow (one branch, no sync complexity)
- Oct 23 approach worked reliably
- Automatic sync can still prevent conflicts (just reverse direction)
- Two-branch strategy added complexity without clear benefit

**Risk:**
- Might reintroduce merge conflicts between bot and user
- Loses separation of bot/user work
- AMENDMENT-043 (two-branch strategy) would be partially reverted

**Alternative:** Keep two-branch with automatic sync (current approach)
- **Pros:** Separation of concerns, bot always succeeds
- **Cons:** More complex, requires sync discipline
- **User's subsequent phases suggest:** Revert to single-branch

**Testing:**
```bash
# After revert
gh workflow run "Daily NRW Update"
gh run watch
# Verify: Checks out main, runs pipeline, commits to main
```

### REVERT-3: RT Scraper Selectors ⚠️

#### RT Selectors Before/After Comparison Table

| Component | Before (73c6eef3) - Selenium | After (ef12e3e3) - Playwright | Status |
|-----------|------------------------------|--------------------------------|--------|
| **Search Selectors** | | | |
| Primary | `"search-page-media-row a[data-qa='info-name']"` | `"search-page-media-row a[data-qa='info-name']"` | ✅ **IDENTICAL** |
| Fallback 1 | `"a[data-qa='thumbnail-link']"` | `"a[data-qa='thumbnail-link']"` | ✅ **IDENTICAL** |
| Fallback 2 | `"a[href*='/m/'][data-qa='info-name']"` | `"a[href*='/m/'][data-qa='info-name']"` | ✅ **IDENTICAL** |
| Fallback 3 | `"search-page-result a[href*='/m/']"` | `"search-page-result a[href*='/m/']"` | ✅ **IDENTICAL** |
| Fallback 4 | `"a[href*='/m/']"` | `"a[href*='/m/']"` | ✅ **IDENTICAL** |
| **Score Selectors** | | | |
| Primary | `"rt-text[slot='criticsScore']"` | `"rt-text[slot='criticsScore']"` | ✅ **IDENTICAL** |
| Fallback 1 | `"score-board"` | `"score-board"` | ✅ **IDENTICAL** |
| Fallback 2 | `"[data-qa='tomatometer']"` | `"[data-qa='tomatometer']"` | ✅ **IDENTICAL** |
| Fallback 3 | `"[data-qa='tomatometer-value']"` | `"[data-qa='tomatometer-value']"` | ✅ **IDENTICAL** |
| Fallback 4 | `".tomatometer-score"` | `".tomatometer-score"` | ✅ **IDENTICAL** |
| Fallback 5 | `"score-icon-critic"` | `"score-icon-critic"` | ✅ **IDENTICAL** |
| **Regex Patterns** | | | |
| Basic | `r'(\d+)\s*%'` | `r'(\d+)\s*%'` | ✅ **IDENTICAL** |
| Tomatometer | `r'tomatometer\s*:?\s*(\d+)\s*%'` | `r'tomatometer\s*:?\s*(\d+)\s*%'` | ✅ **IDENTICAL** |
| Percent | `r'(\d+)\s*percent'` | `r'(\d+)\s*percent'` | ✅ **IDENTICAL** |
| Critic Score | `r'critics?\s*score\s*:?\s*(\d+)'` | `r'critics?\s*score\s*:?\s*(\d+)'` | ✅ **IDENTICAL** |
| Fresh | `r'fresh\s*:?\s*(\d+)'` | `r'fresh\s*:?\s*(\d+)'` | ✅ **IDENTICAL** |
| **Timeouts & Timing** | | | |
| Page Load Timeout | `config.get('rt_scraper', {}).get('timeout', 10)` | `config.get('rt_scraper', {}).get('timeout', 10) * 1000` | ⚠️ **ENHANCED** (ms) |
| Rate Limit | `config.get('rt_scraper', {}).get('rate_limit', 2.0)` | `config.get('rt_scraper', {}).get('rate_limit', 2.0)` | ✅ **IDENTICAL** |
| Page Wait | `time.sleep(2)  # Wait for page load` | `time.sleep(2)  # Wait for dynamic content` | ✅ **IDENTICAL** |
| Wait Strategy | N/A | `wait_until='domcontentloaded'` | ✅ **IMPROVEMENT** |

#### Key Findings

**✅ SELECTORS ARE IDENTICAL** - The RT scraping failure is NOT due to selector changes.

**Actual Differences:**
1. **Implementation Framework:** Selenium → Playwright
2. **Browser Management:** Individual driver → Shared PlaywrightManager
3. **Wait Strategy:** Simple sleep → domcontentloaded + sleep
4. **Error Handling:** Basic try/catch → Retry with exponential backoff
5. **Diagnostics:** None → Screenshot capture on failure

**Conclusion:**
The RT scraping problems are caused by **framework migration issues** (Playwright CI compatibility), not selector problems. Reverting selectors would have **no impact** since they're identical.

**Recommended Action:**
- ❌ **DO NOT** revert selectors (they're identical)
- ✅ **REVERT** Playwright framework back to Selenium
- ✅ **KEEP** timeout enhancements and wait strategies if reverting

**Testing:**
```bash
# This test would show identical behavior for selectors
python3 -c "from generate_data import DataGenerator; g = DataGenerator(); ..."
# The issue is framework compatibility, not CSS selectors
```

**Updated Recommendation:** Focus revert on PlaywrightManager, not selectors

---

## What to Keep

### 8 Improvements That Should NOT Be Reverted ✅

**1. Discovery/Monitoring Split**
- **Files:** generate_data.py (functions), daily_orchestrator.py (pipeline)
- **Why:** Core to enrichment-on-transition pattern
- **Evidence:** 98% API cost reduction, 30-second runtimes

**2. Enrichment-on-Transition Pattern**
- **Files:** generate_data.py (lines 2333-2426)
- **Why:** Prevents massive re-enrichment cascades
- **Evidence:** SYSTEM_ARCHITECTURE.md Section 5

**3. Schema Validation**
- **Files:** generate_data.py (validate_data_json_schema), daily_orchestrator.py (validate_data_quality)
- **Why:** Prevents data corruption from deploying
- **Evidence:** Fixed line 1848 bug, prevents recurrence

**4. Validation Resilience**
- **Files:** daily_orchestrator.py (lines 184-198)
- **Why:** Prevents false failures during discovery gaps
- **Evidence:** Fixed Nov 5, system now handles weekends/holidays

**5. Google Fallback Removal**
- **Files:** generate_data.py (multiple locations)
- **Why:** Better UX (null > fake search URLs)
- **Evidence:** User confirmed, frontend shows "NOT AVAILABLE"

**6. has_real_watch_link() Helper**
- **Files:** daily_orchestrator.py (lines 15-37)
- **Why:** Accurate metrics (excludes search URLs)
- **Evidence:** Fixes stats reporting inconsistency

**7. Automatic Branch Sync**
- **Files:** daily-check.yml (lines 60-81)
- **Why:** Prevents branch divergence (primary root cause)
- **Evidence:** DAILY_UPDATE_DIAGNOSIS.md "Fix #1"

**8. Documentation Improvements**
- **Files:** SYSTEM_ARCHITECTURE.md, README.md, DAILY_CONTEXT.md, docs/
- **Why:** Critical for AI assistants to understand system
- **Evidence:** Two-branch strategy was missed due to poor docs

---

## Risk Assessment

### Risks of Reverting 📊

**High Risk:** ❌
- Reverting discovery/monitoring → Breaks enrichment-on-transition
- Reverting schema validation → Data corruption can recur
- Reverting validation resilience → False failures return

**Medium Risk:** ⚠️
- Reverting Playwright → Might reintroduce event loop issues (but Oct 23 didn't have them)
- Reverting two-branch → Might reintroduce merge conflicts (but Oct 23 didn't have them)

**Low Risk:** ✅
- Reverting RT selectors → Easy to test and re-revert if needed
- Reverting placeholder ASIN checks → Can add back if needed

### Risks of NOT Reverting 📊

**High Risk:** ❌
- Keeping broken Playwright integration → Watch links stay at 3% coverage
- Keeping complex two-branch without understanding → Future divergence

**Medium Risk:** ⚠️
- Keeping current RT selectors → Unknown if they're better or worse

**Low Risk:** ✅
- Keeping placeholder ASIN checks → Might be unnecessary but harmless

---

## Recommendations

### Recommended Restoration Strategy 🔍

**Phase 1: Surgical Reverts (High Priority)**
1. ✅ **Revert PlaywrightManager integration**
   - Delete rt_scraper_playwright.py
   - Restore inline Selenium RT scraping in generate_data.py
   - Comment out playwright_manager.py (keep for future)
   - **Expected outcome:** RT scores return to 80%+ coverage

2. ⚠️ **Evaluate workflow simplification**
   - Option A: Keep two-branch with automatic sync (current)
   - Option B: Revert to single-branch (checkout main, commit to main)
   - **Recommendation:** Test both approaches, choose simpler

**Phase 2: Preserve Good Changes (Critical)**
1. ✅ Keep all validation improvements
2. ✅ Keep discovery/monitoring split
3. ✅ Keep enrichment-on-transition pattern
4. ✅ Keep schema validation
5. ✅ Keep Google fallback removal
6. ✅ Keep documentation improvements

**Phase 3: Testing & Verification (Post-Revert)**
1. Test locally: `python3 daily_orchestrator.py`
2. Test in CI: Trigger manual workflow
3. Verify RT scores: Should be 80%+ (vs current 3%)
4. Verify runtime: Should stay ~30 seconds
5. Verify watch links: Should improve from 3% to 60%+

**Phase 4: Monitor & Iterate (Next 7 Days)**
1. Monitor daily runs for stability
2. Track watch link coverage improvement
3. Re-evaluate Playwright migration (with CI fixes)
4. Document lessons learned

---

## Verification Results (Baseline 73c6eef3)

### Baseline Validation Test

**Command Used:**
```bash
git checkout 73c6eef3
python3 daily_orchestrator.py
```

**Expected Results (Pre-Oct 25 Behavior):**
- Runtime: 1-10 movies enriched (not 300+)
- No `'str' object has no attribute 'get'` error
- Successful completion with minimal API calls

**Verification Status:**
⚠️ **VERIFICATION PENDING** - This test needs to be executed to confirm baseline behavior

**Required Output to Capture:**
1. Exact runtime duration and movie counts
2. Log snippets showing successful completion
3. Confirmation of no data corruption errors
4. API call statistics (should be minimal due to enrichment-on-transition)

**Expected Log Pattern:**
```
Phase 1: Discovery - Found X new movies
Phase 2: Monitoring - Y movies transitioned to available
Phase 3: Enrichment - Enriched Y movies (not hundreds)
Phase 4: Validation - Data quality checks passed
Daily update completed successfully in ~30 seconds
```

**Failure Indicators to Watch For:**
- Long runtime (>5 minutes suggests massive re-enrichment)
- High API usage (>100 calls suggests enrichment-on-transition broken)
- Data corruption errors (`'str' object has no attribute 'get'`)
- Selenium driver initialization failures

**Next Steps:**
This verification must be completed before implementing any reverts to confirm that 73c6eef3 actually represents a working baseline state.

---

## Conclusion

### Summary

The Oct 25-Nov 5 outage was caused by a **perfect storm** of three issues:
1. **Branch divergence** (bot ran old code)
2. **Data corruption** (line 1848 bug)
3. **Playwright CI failures** (scrapers returning null)

The Nov 5-6 fixes addressed the **symptoms** (validation resilience, branch sync, data rebuild) but may not have addressed the **root technical issues** (Playwright CI compatibility, two-branch complexity).

### Recommended Approach
- **Surgical reverts:** Revert Playwright integration and evaluate workflow simplification
- **Preserve improvements:** Keep all validation, discovery, and documentation changes
- **Test thoroughly:** Verify reverts work in both local and CI environments
- **Monitor closely:** Watch for 7 days to ensure stability

### The Goal is NOT to Go Back to Oct 23 Entirely

**Instead:**
- ✅ Restore working scrapers (Selenium approach)
- ✅ Simplify workflow (if two-branch isn't needed)
- ✅ Keep all the good improvements (validation, enrichment, docs)
- ✅ Prevent future outages (monitoring, testing)

### Final Verdict
- **Revert:** PlaywrightManager integration (proven to fail in CI)
- **Evaluate:** Workflow simplification (test both approaches)
- **Keep:** Everything else (validation, discovery, enrichment, docs)

---

**Document prepared by:** Traycer.AI
**Review status:** Ready for implementation
**Next steps:** Execute revert plan in subsequent phases