# Watch Links Troubleshooting Guide

## Current Architecture (Mar 2026)

**Priority Waterfall** (see `docs/features/WATCH_LINK_ARCHITECTURE.md` for full details):
1. Manual watch links (`movie_tracking.json`) — hand-set by curator
2. Overrides (`overrides/watch_links_overrides.json`) — admin quick-fix
3. Cache (`cache/watch_links_cache.json`) — previous run results
4. **JustWatch API** — PRIMARY: real deep links with prices
5. VOD scraper (Playwright: Amazon + Apple TV) — backup, only if JustWatch fails
6. TMDB provider names with null links — last resort

**Key Files:**
- `pipeline/enrichment.py` - Watch links waterfall logic
- `pipeline/justwatch.py` - JustWatch API (primary deep link source)
- `streaming_platform_scraper.py` - Playwright-based scraper (backup)

---

## Problem: All Watch Links Are Google Search URLs

### Symptoms
- Watch links in `data.json` look like: `https://www.google.com/search?q=Movie%20Title%20watch%20Platform`
- No deep links to Amazon, Apple TV, or other platforms
- Users have to search manually instead of going directly to movie page

### Root Cause (Legacy - Pre Dec 2024)
Previously: Watchmode API quota exhausted. System fell back to Google search URLs.

### Current Cause (Mar 2026)
Check in waterfall order (most common issue first):
1. **JustWatch API** — is it finding the movie? Check enrichment logs for confidence level. Low-confidence matches get rejected (`min_confidence` in config).
2. **Cache stale** — delete entry in `cache/watch_links_cache.json` to force re-lookup
3. **Playwright selectors outdated** — Amazon/Apple TV change HTML periodically. Only matters if JustWatch also failed.
4. Movie may genuinely not be available for digital purchase yet

---

## Understanding Null Streaming Links

### Current Situation (Expected Behavior)

Most streaming service links (Netflix, Hulu, Disney+, Max, etc.) show `link: null` in data.json. This is **EXPECTED BEHAVIOR**, not a bug. The service-based button UI correctly handles this by showing "NOT AVAILABLE" for null links.

### Why Streaming Links Are Null

**Primary Reason: Platform Not Supported by Scraper**
- Playwright scraper currently supports: Amazon Prime Video, Apple TV
- Agent scraper supports: Netflix, Disney+, HBO Max, Hulu
- Other services (Peacock, Paramount+, fuboTV, Criterion, etc.) not supported by any scraper

**Secondary Reason: TMDB Providers Don't Include Links**
- TMDB API returns provider NAMES ("Netflix", "Hulu") but not URLs
- Without a working scraper for that service, system can only show service name with null link
- By design: better to show null than wrong/broken links

**Tertiary Reason: Movie Not Available for Digital Purchase Yet**
- Very new or obscure movies may not be on Amazon/Apple TV yet
- Speculative scraping tries both platforms for ALL movies regardless of TMDB data
- One-shot enrichment means missed movies need `reenrich_watch_link_gaps()` to retry

### What Works Despite Null Streaming Links

✅ **Amazon/Apple Purchase Links:** Platform scraper provides these directly
✅ **Service Names:** Users can see which services have the movie (providers field)
✅ **Graceful Degradation:** System continues working, doesn't break
✅ **Google Search Fallback:** Some movies have Google search links as last resort

### How To Get Missing Links Populated

1. **Run re-enrichment** for ALL movies missing VOD links (uses `reenrich_watch_link_gaps()` — no longer filtered by TMDB providers, processes in batches of 50)
2. **Add manual overrides** via admin panel for high-priority movies
3. **Check scraper selectors** — Amazon/Apple TV change HTML periodically
4. **Speculative scraping** — new movies automatically try Amazon + Apple TV even without TMDB data

### Current Workarounds

**For Users:**
- "NOT AVAILABLE" button is honest (better than broken links)
- Can manually search for the movie on Netflix/Hulu/etc.
- Amazon/Apple purchase buttons still work

**For Admin:**
- Can manually add streaming links via admin panel (overrides/watch_links_overrides.json)
- Manual links have highest priority (Tier 1 in waterfall)
- Useful for high-priority/featured movies

### Technical Implementation

The service-based button implementation (see `buildPlatformButtons()` function in assets/app.js) correctly handles null links:

```javascript
// Check for SVOD streaming
if (watchLinks.streaming?.service && watchLinks.streaming?.link) {
    // Show streaming service button
} else {
    // Don't show streaming button (correct behavior)
}

// Fallback behavior
if (!watchLinks.streaming?.link && !amazonLink && !appleLink) {
    html = '<a href="#" class="watch-btn watch-btn-disabled">NOT AVAILABLE</a>';
}
```

### Long-term Solution

Playwright scrapers for Amazon/Apple TV are free and have no API quotas. Cache prevents redundant scraping. One-shot enrichment means each movie is only scraped once on its digital release date.

---

## Diagnosis

Follow these steps to diagnose the issue:

### 1. Test Playwright Scraper
```bash
/usr/bin/python3 streaming_platform_scraper.py
```
This runs a quick test on a known movie to verify Amazon/Apple TV scraping works.

### 2. Check Logs
```bash
grep -i "scraper\|watch_links" logs/admin.log | tail -20
```
Look for error messages or warnings.

### 3. Check Statistics
Run `python3 generate_data.py` and look for:
```
Watch Links Enrichment:
  Scraper successes: X
  VOD scraper success rate: X%
```

## Solutions

### Option 1: Enable Platform Scraper (Amazon/Apple TV)

**Status:** ✅ Enabled and tested (Playwright-based as of 2025-10-25)

**Configuration:**
```yaml
# config.yaml platform_scraper section
platform_scraper:
  enabled: true
  headless: true
  platforms:
    amazon: true
    apple_tv: false  # User doesn't need Apple TV
```

**Test Results:**
- ✅ Amazon scraper success rate: 100% (validated as of 2025-10-25)
- ✅ Average search time: 6-8 seconds (30-40% faster with Playwright)
- ✅ Selectors verified: 2025-10-25 (Playwright implementation)
- ✅ Selectors updated: Mar 2026 (Prime Video HTML restructure)

**Test Command:**
```bash
python3 streaming_platform_scraper.py  # now uses Playwright
```

**Maintenance:**
- Selectors may need updates every 3-6 months (Playwright selectors are more stable than Selenium)
- Check if success rate drops below 40%
- Update selectors in streaming_platform_scraper.py (Playwright implementation)
- Last update: 2025-10-25 (Playwright migration)

### Scraper Technology

**All scrapers now use Playwright** (migrated October 2025):
- Platform scraper: `streaming_platform_scraper.py` (Amazon, Apple TV)
- Agent scraper: `agent_link_scraper.py` (Netflix, Disney+, HBO Max, Hulu)
- RT scraper: `rt_scraper_playwright.py` (Rotten Tomatoes)
- YouTube scraper: `scripts/youtube_trailer_scraper.py` (YouTube trailers)

**Benefits of Playwright**:
- 30-40% faster than Selenium (WebSocket-based protocol)
- Better auto-waiting (eliminates timing issues)
- More stable selectors (better element detection)
- Improved error handling and diagnostics
- Unified technology stack (easier maintenance)

**Selenium Removed**: Dependencies removed from `requirements.txt`. Backup Selenium versions preserved in `*_selenium_backup.py` files for emergency rollback.

### Option 3: Manual Overrides (Quick Fix)

For high-priority movies, add manual deep links:

**Steps:**
1. Edit `overrides/watch_links_overrides.json`:
   ```json
   {
     "507244": {
       "vod": {
         "service": "Amazon Video",
         "link": "https://www.amazon.com/gp/video/detail/B0XXXXXX"
       }
     }
   }
   ```
2. Regenerate data:
   ```bash
   python3 generate_data.py
   ```

**When to Use:**
- High-priority movies need immediate fixes
- Scraper can't find specific movie
- Platform scraper can't find specific movies
- Manual verification of links is required

## Watch Links System Status (Updated 2025-10-23)

### Three-Tier Strategy Performance

| Tier | Source | Coverage | Status |
|------|--------|----------|--------|
| 1 | Cache | Existing movies | ✅ Working |
| 2 | Amazon Scraper | 100% (validated) | ✅ Working |
| 3 | Apple TV Scraper | Varies | ✅ Working |
| 4 | Manual Overrides | As needed | ✅ Working |

**Last Selector Update:** 2026-03-23 (Prime Video HTML restructure)
**Next Maintenance:** Check quarterly or when success rate drops

## Known Limitations

### Amazon Scraper (Playwright-based)
- Success rate: ~100% (as of 2025-10-25 with Playwright)
- Primary source for Amazon/Apple TV deep links
- Focuses on recent releases
- Some failures expected:
  - Anti-bot detection: No
  - Movies not available on Amazon: No (all test movies found)
  - Selectors may need quarterly updates: Yes
- Performance: 6-8 seconds per search (improved with Playwright, ~48 minutes for full regeneration)

### Manual Overrides (Final Fallback)
- Required for: Movies not on Amazon/Apple TV
- Use Admin Panel to add: http://localhost:5555
- Format: `overrides/watch_links_overrides.json`

## Validation

After applying a fix:

1. **Check data.json for real deep links** (not Google search):
   ```bash
   grep -c "google.com/search" data.json  # Should decrease
   ```

2. **Count success rate:**
   ```bash
   python3 generate_data.py --full
   # Look for "Platform scraper success rate" in output
   ```

3. **Test 3-5 links manually** in a browser:
   - Open `data.json`
   - Find `watch_links` for a few movies
   - Click links to verify they go directly to movie pages (not search results)

4. **Verify they go directly to movie pages** (not search results)

## Monitoring Watch Links Health

### Daily Checks
```bash
# Run full data generation and check statistics
python3 generate_data.py --full

# Look for these metrics in output:
# - Platform scraper link attempts: Link-level attempts
# - Platform scraper success rate: Should be >40%
# - Movies covered: Movie-level coverage
# - Scraper successes: Total successful scrapes
```

### Warning Signs
- ⚠️ Platform scraper success rate drops below 40% → Update selectors
- ⚠️ Many "No Amazon link found" messages → Check anti-bot detection
- ⚠️ Final coverage drops below 80% → Investigate both tiers

### Quick Fixes
```bash
# If Amazon scraper fails (selectors outdated)
# Run with visible browser to inspect HTML:
python3 streaming_platform_scraper.py  # Playwright-based, headless=False in test function

# If specific movies missing links
# Add manual overrides via Admin Panel: http://localhost:5555
```

### Success Criteria
- At least 50% of Amazon/Apple TV movies have real deep links
- Links work (no 404 errors)
- Platform scraper statistics show success rate > 40%

## Related Documentation

- [README.md](README.md) - Quick start and overview
- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) - CRITICAL-003: Watch Links Broken
- `generate_data.py` `get_watch_links()` function - Watch links waterfall logic
- [ADMIN_WORKFLOW.md](../../ADMIN_WORKFLOW.md) - Manual override workflow
- [AMAZON_ASIN_CLEANUP.md](AMAZON_ASIN_CLEANUP.md) - Playwright migration details (Section: Playwright Migration)