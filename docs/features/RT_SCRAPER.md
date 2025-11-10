# RT Scraper Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-042
**Date:** 2025-10-17
**Maintainer:** Development Team

## Overview

The RT Scraper is an integrated component of the NRW data pipeline that automatically scrapes Rotten Tomatoes scores and URLs for movies. Implemented as an external module `rt_scraper_playwright.py`, it provides a `RTScraperPlaywright` class that is instantiated by `DataGenerator` to handle all RT scraping operations with unified rate limiting and statistics tracking.

## Implementation Details

### External RT Scraping Module

- **File:** `rt_scraper_playwright.py` (external module)
- **Class:** `RTScraperPlaywright` - Handles all RT scraping operations
- **Integration:** Instantiated by `DataGenerator` class via `self.rt_scraper = RTScraperPlaywright()`
- **Responsibilities:**
  - Browser initialization and management (Playwright Chromium context)
  - Rate limiting enforcement (2-second delays between scrapes)
  - Page scraping with selector fallbacks
  - Cache persistence and retrieval
  - Statistics tracking (attempts, successes, cache hits)
- **Methods:** `scrape_rt_score(title, year)` - Main entry point called by `DataGenerator.find_rt_url()`, returns `{url, score}`

### Rate Limiting

- Managed by `RTScraperPlaywright` class internally
- Enforces minimum 2-second delay between scrapes (not just page loads)
- Prevents anti-bot detection from rapid requests
- Configurable via `config.yaml` `rt_scraper.rate_limit`

### Statistics Tracking

- `RTScraperPlaywright` class tracks `rt_attempts`, `rt_successes`, `rt_cache_hits`
- Statistics accessible via class properties
- `DataGenerator` aggregates RT scraper stats with other enrichment metrics
- Displays statistics at end of generation run
- Helps monitor scraper effectiveness and cache hit rate

### Selector Fallbacks

- **Search results:** 3 selectors (primary + 2 fallbacks)
- **Score extraction:** 4 selectors (primary + 3 fallbacks)
- Resilient to RT website HTML changes
- Logs which selector succeeded (for monitoring)

### Driver Cleanup

- `RTScraperPlaywright` class manages browser lifecycle
- Provides `close()` method to cleanly shutdown Playwright browser
- Called by `DataGenerator.generate_display_data()` at end of run
- Prevents zombie Chromium processes

## Waterfall Priority

The RT scraper follows this priority order:

1. **RT overrides** (`overrides/rt_overrides.json`) - Manual curator fixes
2. **RT cache** (`cache/rt_cache.json`) - Previously scraped results
3. **RT scraper** (`rt_scraper_playwright.py`) - Playwright-based scraping via `RTScraperPlaywright` class
4. **RT search URL** - Fallback when scraping fails

## Score Extraction Status

**Verification Complete (Oct 18, 2025):**
- ✅ Implemented in `RTScraperPlaywright.scrape_rt_url()` method (rt_scraper_playwright.py)
- ✅ 6 selector fallbacks for score elements
- ✅ Regex pattern `r'(\d+)%'` extracts percentage scores
- ✅ Cached in cache/rt_cache.json with 90-day TTL
- ✅ Rate limiting enforced (2-second delays between scrapes)
- ✅ Integrated into `DataGenerator.find_rt_url()` waterfall at tier 3
- ✅ Test results: 100% success rate on 4 test cases (including live scraping)
- ✅ Current coverage: 72.9% (172/236 entries have scores)
- ⚠️ Selectors working correctly (extracted 89% for "The Substance", 82% for random movie)
- 📊 Target coverage: 85-90% (achievable with full regeneration)

## Cache Structure

- **File:** `cache/rt_cache.json`
- **Key:** `{title}_{year}` (e.g., "Landmarks_2025")
- **Value:** `{url: string, score: string, title: string, scraped_at: string}` or `null` for failures
- **Format:** Includes `scraped_at` ISO timestamp field for TTL calculation
- **TTL:** 90 days (RT links are stable), TTL depends on `scraped_at` timestamp

## Performance Impact

- **Cache hit:** ~0ms (instant return)
- **Fresh scrape:** ~4-6 seconds (2s rate limit + Playwright auto-waiting + page navigation)
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

- `museum_legacy/scripts_rt_scraper.py` - Superseded by `rt_scraper_playwright.py` (Playwright migration)
- `museum_legacy/scripts/rt_scrape.py` - Old scripts version, archived
- `museum_legacy/rt_scraper.py` - Root Selenium version, replaced by Playwright version
- `update_rt_data.py` - No longer needed (RT scraping is automatic)
- `bootstrap_rt_cache.py` - No longer needed (RT scraping is automatic)

These files have been archived to `museum_legacy/`.

## Testing

- Standalone tests available in `tests/test_rt_scraper_playwright.py`
- Tests cache hits, fresh scrapes, rate limiting, error handling
- Verifies statistics tracking
- Tests with known movies: "Landmarks", "Inspector Zende", "The Substance"
- Integration testing via `DataGenerator` class in generate_data.py

## Rollback Plan

- If issues arise, emergency Selenium backup available as `rt_scraper_selenium_backup.py`
- Restore old import and class instantiation
- No data loss (RT scraping is additive, cache format unchanged)

## Implementation Status

- ✅ RT scraping logic in external `rt_scraper_playwright.py` module
- ✅ `RTScraperPlaywright` class manages all RT operations
- ✅ Rate limiting implemented
- ✅ Statistics tracking added
- ✅ Driver cleanup added
- ✅ Configuration added to config.yaml
- ✅ Selector verification with current RT website
- ✅ Testing with known movies
- ✅ Full regeneration tested

## Success Criteria

- RT scraper success rate > 80% (RT has good search functionality)
- Rate limiting enforced (2-second minimum delays)
- Statistics show accurate counts
- No crashes or hangs during generation
- Cache properly updated after scrapes