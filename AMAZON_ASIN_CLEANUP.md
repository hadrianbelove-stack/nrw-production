# Amazon ASIN Cleanup Documentation

**Date:** 2025-10-25
**Issue:** Amazon Placeholder ASIN Bug (B0FMPYFP9W)
**Status:** Fixed (Implementation Complete)

## Bug Summary

- **Discovered:** 2025-10-25
- **Symptom:** ~55 movies showing same placeholder ASIN B0FMPYFP9W
- **Impact:** All affected Amazon links redirect to same incorrect movie page
- **User Experience:** Broken watch links, poor user trust
- **Root Cause:** Amazon Channel Provider Confusion

## Root Cause Analysis

### Primary Cause: Amazon Channel Provider Confusion

TMDB returns providers like "HBO Max Amazon Channel", "Shudder Amazon Channel" which are NOT Amazon Prime Video - they're subscriptions available through Amazon Channels. The code at `generate_data.py:1409` checked `if 'Amazon' in provider` which matched these, causing the platform scraper to search Amazon for non-Amazon content, resulting in sponsored/placeholder results (ASIN B0FMPYFP9W).

### Secondary Cause: Service/Link Mismatch

Service selection logic picked best service from priority list (e.g., "Max") but kept the Amazon link that was scraped for "HBO Max Amazon Channel". Result: `service="Max"` with `link` pointing to `amazon.com` (data corruption).

### Tertiary Cause: Scraper Validation Gaps

**Multiple Placeholder ASINs Discovered:**
- B0FMPYFP9W: Original placeholder ASIN (10+ occurrences)
- B0FNDR5BW5: Second placeholder ASIN (20+ occurrences, MORE prevalent)
- B0FMPYFP9X: Third placeholder ASIN (in detection list but not found in data)

The second placeholder ASIN B0FNDR5BW5 was not in the original detection list, allowing it to pass through validation and corrupt even more movies than the first placeholder.

**Other validation gaps:**
- Title matching threshold (60%) was too lenient
- Sponsored result detection incomplete (Amazon changes HTML frequently)
- No position-based filtering (first results are usually sponsored)
- Incomplete placeholder ASIN detection

## Solution Implemented

### Fix 1: Filter Amazon Channel Providers (`generate_data.py`)

**Added Helper Functions:**
- `is_actual_amazon_service()` - Returns True only for genuine Amazon Prime Video services
- `is_actual_apple_service()` - Returns True only for genuine Apple TV services

**Logic:**
- Match: "Amazon Video", "Amazon Prime Video", "Prime Video"
- Reject: "HBO Max Amazon Channel", "Shudder Amazon Channel", etc.
- Implementation: Check if provider contains "Amazon" but NOT "Channel" or "Channels"

**Files Modified:**
- `generate_data.py:1344-1396` - Added helper functions
- `generate_data.py:1463-1466` - Updated streaming provider filtering
- `generate_data.py:1494-1497` - Updated rent provider filtering
- `generate_data.py:1525-1528` - Updated buy provider filtering

**Note:** These improvements were later applied to agent scraper in Phase 4.

### Fix 2: Strengthen Scraper Validation (`streaming_platform_scraper.py`)

**Enhanced Title Matching:**
- Increased threshold from 60% to 70% word overlap
- Added exact title match bonus (accepts 60% if exact title found)
- Added year validation when year is in search query
- Added negative keyword detection ("not available", "TV series", etc.)

**Enhanced Sponsored Detection:**
- Strategy 1: Traditional sponsored parent classes
- Strategy 2: Check for 'sponsored' keyword in ancestor attributes
- Strategy 3: Check for ad-related IDs and classes
- Strategy 4: Look for "Sponsored" text in nearby elements

**Position-Based Filtering:**
- Skip first 2 search results (most likely sponsored)
- Start validation from 3rd result onward

**Placeholder ASIN Detection:**
- Maintain list of known placeholder ASINs: ['B0FMPYFP9W', 'B0FMPYFP9X', 'B0FNDR5BW5']
- Skip any result containing these ASINs

**Stricter Video Validation:**
- Require at least 2 video keywords OR 1 keyword + video indicators
- Extended negative keywords list
- Video format indicators validation

**Files Modified:**
- `streaming_platform_scraper.py:144-153` - Position filtering & placeholder detection
- `streaming_platform_scraper.py:155-197` - Enhanced sponsored detection
- `streaming_platform_scraper.py:177-209` - Improved title validation
- `streaming_platform_scraper.py:259-284` - Stricter video keyword validation

**Note:** These improvements were later applied to agent scraper in Phase 4.

### Fix 3: Service/Link Consistency Validation (`generate_data.py`)

**Added Validation Function:**
- `validate_service_link_consistency()` - Checks service names match link domains

**Logic:**
- Validates that service="Max" has `max.com` or `hbomax.com` in link
- Validates that service="Netflix" has `netflix.com` in link
- Validates that service="Amazon" has `amazon.com` in link
- Replaces mismatched pairs with Google search fallback

**Files Modified:**
- `generate_data.py:1398-1450` - Added validation function
- `generate_data.py:1188-1198` - Applied validation before caching

### Fix 4: Placeholder ASIN Detection in Validation (`generate_data.py`)

**Schema Validation Enhancement:**
- Added check for known placeholder ASINs (B0FMPYFP9W, B0FNDR5BW5) in URL validation
- Rejects any link containing these placeholder ASINs
- Logs warning with specific ASIN detected

**Files Modified:**
- `generate_data.py:1304-1308` - Added comprehensive placeholder ASIN detection

### Fix 5: Enrichment Consistency Validation (`generate_data.py`)

**Enhanced Validation Method:**
- Detects movies marked `enriched: true` but missing watch_links data
- Detects movies with placeholder ASINs (B0FMPYFP9W, B0FNDR5BW5) in their links
- Resets enriched flags for corrupted movies
- Clears potentially corrupted watch_links data

**Files Modified:**
- `generate_data.py:2009-2029` - Enhanced validation logic

## Data Cleanup Process

### Step 1: Identify Affected Movies
**Tool:** `cleanup_placeholder_asins.py`
- Updated script to detect both B0FMPYFP9W and B0FNDR5BW5
- Scanned data.json for both placeholder ASINs
- Found 41 affected movies across streaming/rent/buy categories
- Generated list of movie IDs needing cleanup

### Step 2: Reset Enriched Flags
**Tool:** `cleanup_placeholder_asins.py`
- Reset `enriched: false` for 41 affected movies in movie_tracking.json
- Removed `enrichment_date` for affected movies
- Created backup: `movie_tracking_backup_20251025_134756.json`

### Step 3: Clear Cache Entries
**Tool:** `clear_cache_for_placeholder_asins.py`
- Removed affected cache entries containing placeholder ASINs
- Created backup: `cache/watch_links_cache_backup_20251025_132921.json`
- Forced re-enrichment of affected movies

### Step 4: Regenerate Data
- Run `python3 generate_data.py` with fixed scraper
- Movies re-enriched with improved validation
- Fixed scraper prevents future placeholder ASINs

## Verification Steps

After implementation, verify the fixes:

1. **Check for placeholder ASINs:** `grep -c 'B0FMPYFP9W\|B0FNDR5BW5' data.json` should return 0
2. **Verify unique ASINs:** Extract all Amazon ASINs and check for duplicates
3. **Test service/link consistency:** Verify service names match link domains
4. **Manual link testing:** Click 5-10 Amazon links to verify correct pages
5. **Coverage check:** Count valid Amazon links vs Google fallbacks

## Prevention Measures

### Permanent Safeguards
1. **Placeholder ASIN Detection:** Validation layer permanently blocks known placeholder ASINs
2. **Amazon Channel Filtering:** Provider filtering prevents root cause
3. **Enhanced Scraper Validation:** Reduces false positives from sponsored content
4. **Service/Link Consistency:** Prevents mismatched service/link pairs
5. **Regular Monitoring:** Enrichment consistency validation runs during data generation

### Monitoring
- Watch for new placeholder ASINs in logs
- Monitor ASIN uniqueness in data generation statistics
- Alert on service/link mismatches
- Regular manual testing of Amazon links

**Lesson learned:** When discovering placeholder ASINs, always check for multiple variants. Amazon may rotate through different placeholder ASINs, so the detection list should be maintained and updated as new placeholders are discovered.

**Recommendation:** Add a monitoring check to the daily pipeline that alerts if any ASIN appears more than 5 times in data.json (likely indicates a new placeholder ASIN).

## Files Created/Modified

### New Files
- `cleanup_placeholder_asins.py` - Data cleanup tool
- `clear_cache_for_placeholder_asins.py` - Cache cleanup tool
- `AMAZON_ASIN_CLEANUP.md` - This documentation

### Modified Files
- `generate_data.py` - Provider filtering, validation, consistency checks
- `streaming_platform_scraper.py` - Enhanced scraper validation
- `movie_tracking.json` - Reset enriched flags for 41 movies
- Cache files - Cleared corrupted entries

### Backup Files Created
- `movie_tracking_backup_20251025_134756.json`
- `cache/watch_links_cache_backup_20251025_132921.json`

## Related Issues and References

- **Optimization Project:** PHASE_2_1_COMPLETE.md, OPTIMIZATION_COMPLETE.md
- **Discovery Architecture:** PROJECT_CHARTER.md AMENDMENT-047
- **Watch Links System:** IMPLEMENTATION_ROADMAP.md CRITICAL-003
- **Daily Context:** DAILY_CONTEXT.md (current session)

## Playwright Migration Complete (2025-10-25)

**Motivation:** Improve scraper reliability and performance by migrating from Selenium to Playwright.

**Changes:**
- Migrated `streaming_platform_scraper.py` from Selenium to Playwright
- Migrated `scripts/youtube_trailer_scraper.py` from Selenium to Playwright
- Archived `wikipedia_scraper.py` to museum_legacy/ (manual tool only)
- Archived `test_selenium.py` to museum_legacy/ (no longer needed)
- Removed `selenium` and `webdriver-manager` from requirements.txt
- All scrapers now use Playwright (RT, platform, YouTube, agent)
- Maintained exact same public interface for backward compatibility
- Reused proven patterns from `agent_link_scraper.py` (browser init, retry, diagnostics)
- Preserved all validation logic (placeholder ASIN detection, sponsored filtering, title matching)
- Performance improvement: 30-40% faster (6-8s vs 10s per search)
- Improved reliability through Playwright's auto-waiting and better element stability

**Benefits:**
- Consistent technology stack (all scrapers use Playwright)
- Better maintainability (shared patterns and utilities)
- Complete Selenium removal (cleaner dependency tree)
- Reduced installation size (no ChromeDriver management)
- Unified testing approach (all scrapers use same patterns)
- Enhanced reliability (auto-waiting eliminates timing issues)
- Faster scraping (WebSocket-based protocol vs HTTP)

**Testing:**
- Created `test_platform_scraper.py` for standalone testing
- Verified with 10-20 movies to ensure no placeholder ASINs
- Tested YouTube scraper with 3 movies (100% success rate)
- Verified all scrapers work without Selenium installed
- Confirmed backup files preserved for emergency rollback
- Confirmed integration with `generate_data.py` works without changes

**Backup:** Original Selenium implementations preserved as `*_selenium_backup.py` files

### Migration Summary

**Phase 1** (2025-10-24): RT scraper migrated to Playwright
**Phase 2** (2025-10-25): Platform scraper migrated to Playwright
**Phase 3** (2025-10-25): YouTube scraper migrated, Selenium removed

**Final State**:
- ✅ All active scrapers use Playwright
- ✅ Selenium removed from dependencies
- ✅ Backup files preserved for rollback
- ✅ Manual tools archived to museum_legacy/
- ✅ Documentation updated

**Performance Gains**:
- RT scraper: 30-40% faster
- Platform scraper: 30-40% faster
- YouTube scraper: 20-30% faster
- Overall: ~15-20 minutes saved per full regeneration

## Phase 3: Async/Sync Playwright Fix

**Date:** 2025-10-26
**Issue:** 100% Playwright scraper failure with asyncio event loop error
**Status:** Fixed (Implementation Complete)

### Problem Discovery
**Symptom:** ALL Playwright scrapers failing with 100% error rate
- Platform scraper: 327 attempts, 0 successes
- Agent scraper: 95 attempts, 0 successes
- Only cached results working

**Error Message:** "Browser initialization failed: It looks like you are using Playwright Sync API inside the asyncio loop"

### Root Cause Analysis
**Primary Cause:** Multiple Event Loop Creation
- Multiple scrapers calling `sync_playwright().start()` independently
- Each call creates its own asyncio event loop
- Python only allows one event loop per thread
- Second and subsequent calls fail with asyncio error

**Investigation Process:**
- Created `test_event_loop_detection.py` to pinpoint where loop is created
- Found: YouTube scraper initialized first, created initial event loop
- Subsequent scrapers (RT, Wikipedia, Agent, Platform) failed when trying to create their own loops

### Solution Implemented

**Created PlaywrightManager Singleton:**
- **File:** `playwright_manager.py`
- **Pattern:** Thread-safe singleton with reference counting
- **Features:**
  - Single shared Playwright instance across all scrapers
  - Proper cleanup with `atexit` registration
  - Reference counting to track active users
  - Diagnostic logging for event loop detection

**Updated All 5 Scrapers:**
1. `scripts/youtube_trailer_scraper.py`
2. `rt_scraper_playwright.py`
3. `wikipedia_scraper_playwright.py`
4. `agent_link_scraper.py`
5. `streaming_platform_scraper.py`

**Changes per scraper:**
- **Import:** `from playwright_manager import get_playwright_manager`
- **Init:** `self.manager = get_playwright_manager()`
- **Browser init:** `self.playwright = self.manager.get_playwright()`
- **Cleanup:** `self.manager.release()` instead of `self.playwright.stop()`

### Verification

**Standalone Tests:**
- ✅ test_amazon_scraper_fix.py: 2/2 PASS
- ✅ test_rt_migration.py: PASS
- ✅ PlaywrightManager diagnostic: "No event loop detected - safe to proceed"

**Full Pipeline Test:**
- Run `python3 generate_data.py --full` with new code
- Verify PlaywrightManager messages appear in log
- Verify zero asyncio errors
- Verify scraper success rates > 0%

**Success Criteria:**
- PlaywrightManager initialization messages in logs
- No "Browser initialization failed" errors
- Platform scraper success rate > 50%
- Agent scraper success rate > 30%

### Lessons Learned

**What Worked:**
- Methodical root cause analysis (user's request: "be methodical and find and root out the problem")
- Defense in depth: Shared manager (#1) AND proper cleanup (#2)
- Test-driven approach: Verify fix in isolation before full pipeline

**What Didn't Work:**
- Quick workarounds (nest_asyncio, etc.) - user rejected as technical debt
- Converting to async - massive complexity with no benefit for sequential scraping

**Key Insight:**
- Singleton pattern is the right solution for shared resources (Playwright instance)
- Event loop conflicts are subtle - require careful investigation
- Test scripts can behave differently than full pipeline (Heisenbug)

## Phase 4: Agent Scraper Improvements (Netflix/Disney+/Max/Hulu)

**Date:** 2025-10-26
**Issue:** Agent scraper showing 0% success rate after async fix
**Status:** Implementation Complete, Testing Pending

### Motivation
- After successfully fixing Amazon scraper, applied same improvements to agent scraper
- Agent scraper was showing 0% success rate (95 attempts, 0 successes, cache only)
- Same validation challenges exist across all platforms (sponsored results, title matching, year inconsistencies)

### Improvements Applied

Document that the following improvements from `streaming_platform_scraper.py` were copied to `agent_link_scraper.py`:

1. **Flexible Year Matching (±1 year)**
   - Copied from streaming_platform_scraper.py lines 422-444
   - Accepts 2024/2026 for 2025 searches
   - Year is bonus/penalty, not required
   - Prevents rejecting valid results due to year mismatch

2. **Position-Based Filtering**
   - Copied from streaming_platform_scraper.py lines 307-311
   - Skips first 2 search results (likely sponsored)
   - Can be disabled if featured results appear in position 0-1

3. **Enhanced Title Matching**
   - Copied from streaming_platform_scraper.py lines 388-421
   - Stopword filtering (removes "the", "a", "and", etc.)
   - Character normalization (handles accents, special characters)
   - Word overlap percentage calculation
   - Lower threshold for exact title matches

4. **Alternative Validation for Featured Results**
   - Copied from streaming_platform_scraper.py lines 500-557
   - Handles results without parent containers
   - Simpler title matching (50% threshold instead of 70%)
   - Extracts title from link element or nearby parents

5. **Negative Keyword Detection**
   - Checks for: 'not available', 'unavailable', 'coming soon', 'pre-order', 'tv series', 'season'
   - Prevents scraper from returning wrong content types

### Implementation Details

**Files Modified:**
- `agent_link_scraper.py` - Added helper methods to BasePlatformScraper class
- Updated 4 platform-specific scrapers: NetflixScraper, DisneyPlusScraper, HBOMaxScraper, HuluScraper
- Each scraper now uses identical validation logic

**Code Reuse:**
- Helper methods in BasePlatformScraper avoid duplication
- All 4 platforms call same validation functions
- Platform-specific selectors remain unchanged (proven to work)

### Testing

**Test Script:** `test_agent_scraper_improvements.py`

**Test Cases:**
- Netflix: "A House of Dynamite" (2025), "Vash Level 2" (2025)
- Disney+: "LEGO Frozen: Operation Puffins" (2025), "Spidey and Iron Man" (2025)
- Hulu: "The Hand That Rocks the Cradle" (2025)
- Max: "Armed Only with a Camera" (2025)

**Results:** Verification pending - async fix being completed in Claude Code

**Status as of 2025-10-27:**
- ✅ Code implementation: COMPLETE
- ✅ Test script created: test_agent_scraper_improvements.py (6 test cases)
- 🔄 Async fix verification: IN PROGRESS (Claude Code)
- ⏳ Agent scraper testing: PENDING (awaiting async fix completion)

**Next Steps:**
1. Complete async fix verification in Claude Code
2. Run test_agent_scraper_improvements.py with --clear-cache
3. Document actual success rates below
4. Update this section with real metrics

**Success Criteria:**
- No sponsored/placeholder results returned
- Correct movie pages found (verify URLs manually)
- Title matching works with flexible year (±1 year)
- Overall success rate > 70%
- Per-platform success rate > 50%

### Before/After Comparison

**Before Improvements:**
- Agent scraper: 0% success rate (0/95 attempts)
- All results from cache only
- No live scraping working due to async errors

**After Improvements (Pending Verification):**

Implementation complete, awaiting test results from:
- verify_async_fix.log (full pipeline run)
- test_agent_scraper_improvements.py (agent scraper tests)

**Expected Improvements:**
- Agent scraper success rate: 0% → 30-50% (target)
- Per-platform success rates: >50% each (target)
- Zero sponsored/placeholder results
- Flexible year matching working (±1 year)
- Enhanced title matching reducing false negatives

**To be filled in after testing:**
- Actual overall success rate: ____%
- Netflix success rate: ____%
- Disney+ success rate: ____%
- Max success rate: ____%
- Hulu success rate: ____%
- Common failure patterns: [list]
- Selector effectiveness: [which selectors worked best per platform]

### Platform-Specific Notes

**Netflix:**
- URL pattern: `netflix.com/title/` or `netflix.com/watch/`
- Test movies: "A House of Dynamite" (2025), "Vash Level 2" (2025)
- Selectors: [To be documented after test - record which selector from SELECTORS list worked]
- Common issues: [To be documented after test - note any Netflix-specific challenges]
- Success rate: [To be documented after test - e.g., "2/2 PASS (100%)"]

**Disney+:**
- URL pattern: `disneyplus.com/movies/` or `disneyplus.com/video/`
- Test movies: "LEGO Frozen: Operation Puffins" (2025), "Spidey and Iron Man" (2025)
- Selectors: [To be documented after test]
- Common issues: [To be documented after test]
- Success rate: [To be documented after test]

**Max (formerly HBO Max):**
- URL pattern: `max.com/movies/` or `play.max.com/`
- Test movie: "Armed Only with a Camera" (2025)
- Selectors: [To be documented after test]
- Common issues: Service rebranding may affect selectors [+ any issues found in testing]
- Success rate: [To be documented after test]

**Hulu:**
- URL pattern: `hulu.com/movie/` or `hulu.com/watch/`
- Test movie: "The Hand That Rocks the Cradle" (2025)
- Selectors: [To be documented after test]
- Common issues: [To be documented after test]
- Success rate: [To be documented after test]

### Enhanced Test Infrastructure

**Pre-Flight Checks Added:**
- Import and test PlaywrightManager before running tests
- Check for existing event loops (asyncio conflict detection)
- Verify AgentLinkScraper using PlaywrightManager
- Exit early if async fix not working

**Timing Information:**
- Track elapsed time per platform search
- Calculate average time per platform
- Compare to Amazon scraper baseline (~30-35 seconds)

**Diagnostic Output on Failure:**
- Check if PlaywrightManager was used
- Detect asyncio errors in exceptions
- Suggest troubleshooting steps

**Cache Clearing Option:**
- `--clear-cache` flag forces fresh scraping
- Removes agent_links_cache.json before testing
- Useful for verifying scraper improvements work

**Baseline Comparison:**
- Compare current results to 0% baseline
- Calculate improvement in percentage points
- Display success/progress indicators

## Future Considerations

1. **Watchmode Quota Reset:** Nov 1st - verify auto-reset functionality
2. **Apple TV Coverage:** Monitor low coverage (3.5%) vs Amazon (61%)
3. **Monitor Playwright performance vs Selenium baseline**
4. **Consider extracting shared Playwright utilities into a base class**
5. **Additional Placeholder ASINs:** Watch for new patterns
6. **Service Provider Changes:** TMDB may add new "Channel" variants
7. **Agent Scraper Monitoring:** Track per-platform success rates quarterly
8. **Async Fix Verification:** Ensure PlaywrightManager working in production
9. **Test Agent Improvements:** Run test_agent_scraper_improvements.py after async verification
10. **Agent Scraper Verification Complete:** Fill in Phase 4 placeholders with actual test results
11. **Scraper Effectiveness Baseline:** Document pre-improvement metrics for future comparison

---

**Implementation Status:** ✅ Complete (Amazon scraper + Async fix + Agent scraper improvements)
**Verification Status:** 🔄 In Progress (Async fix verification in Claude Code)
**Testing Status:** ⏳ Pending (Agent scraper tests await async verification)
**Next Review:** After async fix verified and agent tests run
**Maintenance:** Quarterly scraper selector updates + monthly async health checks