# RT Scraper Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-042
**Date:** 2025-10-17
**Maintainer:** Development Team

## Overview

The RT Scraper is an integrated component of the NRW data pipeline that automatically scrapes Rotten Tomatoes scores and URLs for movies. Originally implemented as separate scripts, it was inlined into `generate_data.py` to match the Wikipedia scraping pattern and provide unified rate limiting and statistics tracking.

## Implementation Details

### Inlined RT Scraping Logic

- **Removed:** `from scripts.rt_scraper import RTScraper` import
- **Added:** `_init_rt_driver()` method to DataGenerator for lazy Selenium initialization
- **Added:** `_rt_rate_limit()` method for enforcing 2-second delays between scrapes
- **Added:** `_scrape_rt_page(title, year)` method with scraping logic from scripts/rt_scraper.py
- **Added:** `_save_rt_cache()` method for cache persistence
- **Updated:** `find_rt_url()` to call inlined methods instead of external class

### Rate Limiting

- Tracks last scrape time in `self.rt_last_scrape_time`
- Enforces minimum 2-second delay between scrapes (not just page loads)
- Prevents anti-bot detection from rapid requests
- Configurable via `config.yaml` `rt_scraper.rate_limit`

### Statistics Tracking

- Added `rt_attempts`, `rt_successes`, `rt_cache_hits` to watchmode_stats
- Tracks RT scraper usage similar to agent scraper
- Displays statistics at end of generation run
- Helps monitor scraper effectiveness and cache hit rate

### Selector Fallbacks

- **Search results:** 3 selectors (primary + 2 fallbacks)
- **Score extraction:** 4 selectors (primary + 3 fallbacks)
- Resilient to RT website HTML changes
- Logs which selector succeeded (for monitoring)

### Driver Cleanup

- Added RT driver cleanup to `generate_display_data()` method
- Ensures Selenium browser is closed at end of run
- Prevents zombie Chrome processes

## Waterfall Priority

The RT scraper follows this priority order:

1. **RT overrides** (`overrides/rt_overrides.json`) - Manual curator fixes
2. **RT cache** (`rt_cache.json`) - Previously scraped results
3. **RT scraper** (NEW - inlined) - Selenium-based scraping
4. **RT search URL** - Fallback when scraping fails

## Score Extraction Status

**Verification Complete (Oct 18, 2025):**
- ✅ Implemented in `_scrape_rt_page()` method (generate_data.py:181-291)
- ✅ 6 selector fallbacks for score elements (lines 244-251)
- ✅ Regex pattern `r'(\d+)%'` extracts percentage scores (line 261)
- ✅ Cached in rt_cache.json with 90-day TTL
- ✅ Rate limiting enforced (2-second delays between scrapes)
- ✅ Integrated into waterfall at tier 4 (line 630)
- ✅ Test results: 100% success rate on 4 test cases (including live scraping)
- ✅ Current coverage: 72.9% (172/236 entries have scores)
- ⚠️ Selectors working correctly (extracted 89% for "The Substance", 82% for random movie)
- 📊 Target coverage: 85-90% (achievable with full regeneration)

## Cache Structure

- **File:** `rt_cache.json`
- **Key:** `{title}_{year}` (e.g., "Landmarks_2025")
- **Value:** `{url: string, score: string}` or `null` for failures
- **Format:** Same as before (backward compatible)
- **TTL:** 90 days (RT links are stable)

## Performance Impact

- **Cache hit:** ~0ms (instant return)
- **Fresh scrape:** ~6-8 seconds (2s rate limit + 2s search + 2s movie page)
- **Full regeneration:** Adds ~2-3 minutes if 20-30 movies need RT scraping
- **Daily automation:** Adds ~30-60 seconds (5-10 new movies per day)

## Configuration

```yaml
rt_scraper:
  enabled: true
  headless: true
  rate_limit: 2.0
  timeout: 10
  max_retries: 1
  cache_ttl_days: 90
```

## Files Deprecated

- `scripts/rt_scraper.py` - Logic moved into generate_data.py
- Root `rt_scraper.py` - Old version, replaced by scripts version
- `update_rt_data.py` - No longer needed (RT scraping is automatic)
- `bootstrap_rt_cache.py` - No longer needed (RT scraping is automatic)

These files will be archived to `museum_legacy/` in subsequent phase.

## Testing

- Created `test_rt_scraper_inline.py` for standalone verification
- Tests cache hits, fresh scrapes, rate limiting, error handling
- Verifies statistics tracking
- Tests with known movies: "Landmarks", "Inspector Zende", "The Substance"

## Rollback Plan

- If issues arise, revert to external RTScraper class from scripts/rt_scraper.py
- Restore import and external class usage
- No data loss (RT scraping is additive)

## Implementation Status

- ✅ RT scraping logic inlined into generate_data.py
- ✅ Rate limiting implemented
- ✅ Statistics tracking added
- ✅ Driver cleanup added
- ✅ Configuration added to config.yaml
- ⏳ Selector verification with current RT website
- ⏳ Testing with known movies
- ⏳ Full regeneration test

## Success Criteria

- RT scraper success rate > 80% (RT has good search functionality)
- Rate limiting enforced (2-second minimum delays)
- Statistics show accurate counts
- No crashes or hangs during generation
- Cache properly updated after scrapes