# Agent Link Scraper Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-039, AMENDMENT-040, AMENDMENT-041
**Date:** 2025-10-16 (Created), 2025-10-17 (Debugging), 2025-10-17 (Playwright Migration)
**Maintainer:** Development Team

## Overview

The Agent Link Scraper provides automated discovery of streaming platform watch links. It uses Playwright browser automation to search platforms directly and extract deep links to watch pages.

## Problem Statement

Some streaming platforms (Netflix, Disney+, HBO Max, Hulu) don't have predictable URL patterns that can be constructed programmatically. Users need direct links to these platforms, not search URLs or null links.

## Solution Architecture

The agent scraper is part of a multi-tier system (see `docs/features/WATCH_LINK_ARCHITECTURE.md`):
1. **Tier 1:** Manual watch links (`movie_tracking.json`)
2. **Tier 2:** Overrides (`overrides/watch_links_overrides.json`)
3. **Tier 3:** Cache (`cache/watch_links_cache.json`)
4. **Tier 4:** JustWatch API — primary source for rent/buy deep links
5. **Tier 5:** VOD scraper (Playwright: Amazon/Apple TV) — backup when JustWatch fails
6. **Tier 6:** TMDB provider names with null links (last resort)

## Technical Implementation

### Technology Migration

**Original Implementation (Oct 16):** Selenium-based with 0% success rate
**Current Implementation (Oct 17):** Playwright-based with enhanced reliability

### Playwright Advantages

- Faster page loads (WebSocket protocol vs HTTP)
- Built-in auto-wait (reduces timing-related failures)
- Better error messages (shows what was found vs expected)
- Modern API with better selector handling
- Trace viewer for debugging (can replay exact browser state)

### Platform Support

**Supported Platforms:**
- **Netflix** - `https://www.netflix.com/title/{id}`
- **Disney+** - `https://www.disneyplus.com/movies/{slug}/{id}`
- **HBO Max/Max** - `https://www.max.com/movies/{slug}/{id}`
- **Hulu** - `https://www.hulu.com/movie/{slug}/{id}`

**Handled by Platform Scraper (`streaming_platform_scraper.py`) instead:**
- Amazon Prime Video
- Apple TV+

### Selector Fallback Strategy

Each platform has 4-6 selector fallbacks (ordered by reliability):
- Try selectors sequentially until one matches
- Track which selector succeeded (for monitoring)
- Example: Netflix tries `.title-card a`, `[data-uia='title-card'] a`, `.search-result a`, `a[href*='/title/']`, etc.

### Integration Point

The scraper integrates into the enrichment pipeline `get_watch_links()` method:
- After cache lookup returns no streaming links
- Before returning `{service: X, link: None}`
- Only for supported platforms: Netflix, Disney+, HBO Max, Hulu

## Cache System

**File:** `cache/agent_links_cache.json`
**Structure:**
```json
{
  "movies": {
    "movie_id": {
      "streaming": {
        "service": "Netflix",
        "link": "https://..."
      },
      "scraped_at": "2025-10-17T...",
      "source": "agent_search",
      "success": true,
      "retry_count": 1,
      "last_error": null,
      "screenshot": "/path/to/screenshot.png",
      "selector_used": ".title-card a"
    }
  }
}
```

**Features:**
- Cache-first approach: check cache before launching browser
- Enhanced schema with retry tracking and error details
- Expires after 30 days (configurable)
- Backward compatible with old cache entries
- No automatic invalidation (links are stable)

## Rate Limiting and Reliability

### Rate Limiting
- Minimum 2-second delay between scrapes
- Prevents anti-bot detection
- Backoff to 5 seconds on errors

### Exponential Backoff Retry
- Retry failed scrapes up to 3 times (configurable)
- Delays: 0.5s, 1s, 2s (exponential with jitter)
- Handles transient network issues and page load delays
- Jitter prevents thundering herd in CI

### Screenshot Capture on Failure
- Saves screenshot + HTML when scraping fails
- Location: `cache/screenshots/{movie_id}_{service}_{timestamp}.png`
- Provides visual proof of what page looked like
- Auto-delete after 7 days (configurable)
- Can be disabled in CI via config

## Error Handling

### Graceful Degradation
- Agent failures return `null` (not fake URLs)
- Browser crashes disable agent for remainder of run
- Timeouts (10 seconds per page load)
- All errors logged but don't crash generation

### Statistics Tracking
- `agent_attempts`: Number of times agent scraper was called
- `agent_successes`: Number of successful link extractions
- `agent_cache_hits`: Number of cache hits (no scraping needed)
- Displayed after each `generate_data.py` run

## Performance Impact

- **First run:** Adds 2-3 seconds per scraped movie (~5-10 minutes for full regeneration)
- **Cached runs:** No performance impact (cache hits)
- **Daily automation:** Only scrapes new movies (~5-10 per day, ~30 seconds added)
- **Browser reuse:** Single Playwright instance reused across all movies (saves 5-10 seconds per movie)

## Configuration

```yaml
agent_scraper:
  enabled: true
  headless: true
  rate_limit: 2.0
  timeout: 10
  max_retries: 3
  cache_ttl_days: 30
  screenshots_enabled: true
  screenshot_retention_days: 7
  exponential_backoff:
    base_delay: 0.5
    max_delay: 5.0
    jitter_ratio: 0.2
```

## Dependencies

- Added `playwright` to `requirements.txt`
- Installation: `pip install playwright && playwright install chromium`
- Chromium browser binary: ~100MB download
- Keep Selenium temporarily for other scrapers (YouTube, RT, Wikipedia)

## CI/CD Integration

**GitHub Actions:**
- Added step: `playwright install chromium --with-deps`
- Updated dependencies: Added `playwright` to pip install
- Keep Chrome setup for Selenium-based scrapers

## Debugging and Maintenance

### Historical Issues (Oct 17, 2025)

**Root Causes Identified:**
1. **Cache Directory Gitignored:** `.gitignore` excluded `cache/` directory
2. **Incremental Mode Skips Existing Movies:** Only processes NEW movies
3. **Config Not Read:** Only read `api` section, ignored `agent_scraper` settings
4. **Missing Dependencies:** `requirements.txt` lacked selenium and webdriver-manager
5. **No Execution Evidence:** No cache files or log messages

**Fixes Implemented:**
1. **Enhanced Debug Logging:** Comprehensive logging throughout all methods
2. **Cache Directory Persistence:** Created `cache/.gitkeep` to track directory in git
3. **Config Reading:** Updated `load_config()` to load entire config.yaml
4. **Dependencies:** Added selenium, webdriver-manager, beautifulsoup4, lxml to requirements.txt
5. **Testing Infrastructure:** Created `test_agent_scraper.py` for standalone testing

### Selector Maintenance

- Selectors documented in code with last-verified dates
- Test script (`test_agent_scraper.py`) provides quick verification
- `--debug-selectors` flag shows which selectors matched
- Screenshots provide visual evidence when selectors break
- Expected maintenance: Update selectors every 3-6 months as platforms change HTML

## Terms of Service Considerations

Web scraping may violate platform Terms of Service. This feature:
- Is **optional** (can be disabled by not initializing agent)
- Uses **low volume** (5-10 scrapes per day)
- Is **non-commercial** (personal project)
- Uses **respectful delays** (2+ seconds between requests)
- **Does not bypass paywalls** (only finds public watch page URLs)

Users should be aware of potential ToS violations and use responsibly.

## Rollback Plan

If agent scraping causes issues:
1. Disable in config.yaml: `streaming_scraper.enabled: false`
2. System falls back to cache + TMDB providers only
3. No data loss (agent is additive)

## Implementation Status

- ✅ `agent_link_scraper.py` module created
- ✅ Integration into `generate_data.py`
- ✅ Cache system operational
- ✅ Rate limiting implemented
- ✅ Error handling and graceful degradation
- ✅ Statistics tracking
- ✅ Playwright migration completed
- ✅ Selector arrays implemented (6 selectors per platform)
- ✅ Exponential backoff implemented
- ✅ Screenshot capture implemented
- ✅ Cache schema enhanced
- ✅ Testing infrastructure updated
- ✅ CI workflow updated
- ⏳ Awaiting selector discovery via manual platform inspection
- ⏳ Awaiting full regeneration test

## Success Criteria

- Agent scraper success rate > 70% (currently 0%)
- Netflix links found for majority of Netflix movies
- Screenshots captured for all failures
- Cache entries have expiration dates
- No crashes or hangs during generation
- CI workflow completes successfully with Playwright

## Future Enhancements

- Proxy support for IP rotation (if rate limiting becomes issue)
- Parallel scraping with multiple browser instances
- Machine learning to predict URL patterns
- Alternative APIs as they become available

## Reference Implementation

- **File:** `agent_link_scraper.py` (Playwright-based rewrite)
- **Integration:** `generate_data.py` lines 197-402 (modified)
- **Cache:** `cache/agent_links_cache.json`
- **Statistics:** `generate_data.py` lines 629-640 (extended)
- **Config:** `config.yaml` lines 20-39 (enhanced settings)
- **Test:** `test_agent_scraper.py` (adapted for Playwright)
- **Screenshots:** `cache/screenshots/` (failure diagnostics)