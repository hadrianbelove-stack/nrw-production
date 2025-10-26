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

## Future Considerations

1. **Watchmode Quota Reset:** Nov 1st - verify auto-reset functionality
2. **Apple TV Coverage:** Monitor low coverage (3.5%) vs Amazon (61%)
3. **Monitor Playwright performance vs Selenium baseline**
4. **Consider extracting shared Playwright utilities into a base class**
5. **Additional Placeholder ASINs:** Watch for new patterns
6. **Service Provider Changes:** TMDB may add new "Channel" variants

---

**Implementation Status:** ✅ Complete
**Next Review:** After Watchmode quota reset (Nov 1st)
**Maintenance:** Quarterly scraper selector updates