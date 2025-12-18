# RT Scraper Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-042
**Date:** 2025-10-17
**Last Updated:** 2025-12-18 (Enhanced with direct page scraping)
**Maintainer:** Development Team

## Overview

The RT Scraper is an integrated component of the NRW data pipeline that automatically scrapes Rotten Tomatoes scores and URLs for movies. Implemented as an external module `rt_scraper_playwright.py`, it provides a `RTScraperPlaywright` class that is instantiated by `DataGenerator` to handle all RT scraping operations with unified rate limiting and statistics tracking.

**Major Enhancement (2025-12-18):** The RT scraper now uses a two-stage approach: Google search for RT URL discovery followed by direct RT page score extraction for authoritative scoring, replacing unreliable Google snippet parsing.

## Implementation Details

### External RT Scraping Module

- **File:** `rt_scraper_playwright.py` (external module)
- **Class:** `RTScraperPlaywright` - Handles all RT scraping operations
- **Integration:** Instantiated by `DataGenerator` class via `self.rt_scraper = RTScraperPlaywright()`
- **Responsibilities:**
  - Browser initialization and management (Playwright Chromium context with stealth configuration)
  - Rate limiting enforcement (configurable delays between scrapes, default 1.0s)
  - Two-stage scraping: Google search for URL discovery + direct RT page score extraction
  - Stealth automation features to avoid detection (hidden webdriver signals, fake plugins)
  - Cache persistence and retrieval
  - Statistics tracking (attempts, successes, cache hits)
- **Methods:**
  - `scrape_rt_score(title, year)` - Main entry point called by `DataGenerator.find_rt_url()`, returns `{url, score}`
  - `_extract_score_from_rt_page(rt_url)` - Direct RT page scraping for authoritative scores

### Rate Limiting

- Managed by `RTScraperPlaywright` class internally
- Configurable delay between scrapes (default 1.0s, previously 2.0s)
- Prevents anti-bot detection from rapid requests
- Configurable via `config.yaml` `rt_scraper.rate_limit`
- Enhanced stealth mode helps reduce detection risk, allowing faster scraping

### Statistics Tracking

- `RTScraperPlaywright` class tracks `rt_attempts`, `rt_successes`, `rt_cache_hits`
- Statistics accessible via class properties
- `DataGenerator` aggregates RT scraper stats with other enrichment metrics
- Displays statistics at end of generation run
- Helps monitor scraper effectiveness and cache hit rate

### Selector Fallbacks

- **Google search results:** 3 selectors for RT URL discovery (primary + 2 fallbacks)
- **RT page score extraction:** 8+ selectors across multiple RT score formats (primary + 7+ fallbacks)
- Resilient to both Google and RT website HTML changes
- Direct page scraping provides more reliable score extraction than snippet parsing
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

**Enhanced Implementation (Dec 18, 2025):**
- ✅ Two-stage scraping: Google search for URL discovery + direct RT page score extraction
- ✅ Implemented `_extract_score_from_rt_page()` method for authoritative scoring
- ✅ 8+ selector fallbacks for RT score elements across multiple page formats
- ✅ Stealth automation features (hidden webdriver signals, fake plugins/chrome.runtime)
- ✅ Regex pattern `r'(\d+)%'` extracts percentage scores from actual RT pages
- ✅ Cached in cache/rt_cache.json with 90-day TTL
- ✅ Rate limiting configurable (default 1.0s, improved from 2.0s)
- ✅ Integrated into `DataGenerator.find_rt_url()` waterfall at tier 3
- ✅ Enhanced test coverage with direct page scraping verification
- ✅ Score extraction success rate: ~90% when RT URL is known
- ⚠️ Google search detection remains a challenge (automation blocking)
- 📊 Architectural improvement: Authoritative scores from RT pages vs unreliable snippets

## Cache Structure

- **File:** `cache/rt_cache.json`
- **Key:** `{title}_{year}` (e.g., "Landmarks_2025")
- **Value:** `{url: string, score: string, title: string, scraped_at: string}` or `null` for failures
- **Format:** Includes `scraped_at` ISO timestamp field for TTL calculation
- **TTL:** 90 days (RT links are stable), TTL depends on `scraped_at` timestamp

## Performance Impact

- **Cache hit:** ~0ms (instant return)
- **Fresh scrape:** ~3-5 seconds (1s rate limit + dual page navigation: Google + RT page)
- **Two-stage process:** Google search for URL discovery + RT page for score extraction
- **Full regeneration:** Adds ~2-3 minutes if 20-30 movies need RT scraping (improved timing)
- **Daily automation:** Adds ~30-60 seconds (5-10 new movies per day)
- **Stealth features:** May require additional wait times to avoid detection

## Configuration

```yaml
rt_scraper:
  enabled: true
  headless: true
  rate_limit: 1.0  # Improved from 2.0s with stealth features
  timeout: 10
  max_retries: 1
  cache_ttl_days: 90
  stealth_mode: true  # Enhanced automation hiding
```

## Files Deprecated

- `museum_legacy/scripts_rt_scraper.py` - Superseded by `rt_scraper_playwright.py` (Playwright migration)
- `museum_legacy/scripts/rt_scrape.py` - Old scripts version, archived
- `museum_legacy/rt_scraper.py` - Root Selenium version, replaced by Playwright version
- `update_rt_data.py` - No longer needed (RT scraping is automatic)
- `bootstrap_rt_cache.py` - No longer needed (RT scraping is automatic)

These files have been archived to `museum_legacy/`.

## Testing

- **Enhanced test suite:** `tests/test_rt_scraper_playwright.py`
- **Test improvements (2025-12-18):** Fixed import paths and rate limit expectations
- **Success rate testing:** `tests/test_rt_success_rate.py` with partial/full success tracking
- **Coverage:** Tests cache hits, fresh scrapes, rate limiting, error handling, stealth features
- **Statistics verification:** Tracks RT attempts, successes, and cache hits
- **Test movies:** "Landmarks", "Inspector Zende", "The Substance", "No Time to Die"
- **Two-stage testing:** Verifies both URL discovery and score extraction phases
- **Integration testing:** Via `DataGenerator` class in generate_data.py

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

- **URL discovery phase:** Google search successfully finds RT URLs
- **Score extraction phase:** Direct RT page scraping achieves >90% success rate when URLs are known
- **Overall success:** RT scraper success rate >80% (depends on Google search effectiveness)
- **Rate limiting:** Configurable delays enforced (default 1.0s minimum)
- **Stealth operation:** Browser automation signals properly hidden
- **Statistics accuracy:** Precise tracking of attempts, successes, cache hits
- **Stability:** No crashes or hangs during generation
- **Cache consistency:** Proper updates after fresh scrapes with 90-day TTL