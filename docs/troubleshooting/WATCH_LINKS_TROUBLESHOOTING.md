# Watch Links Troubleshooting Guide

> **Note (Dec 2024):** Watch links now use **JustWatch API** as the primary source.
> Watchmode API was deprecated due to quota/cost issues. Most of this doc refers to
> the legacy Watchmode system and is kept for historical reference.

## Current Architecture (Dec 2024+)

**Priority Waterfall:**
1. Manual overrides (`overrides/watch_links_overrides.json`)
2. Cache (`cache/watch_links_cache.json`)
3. **JustWatch API** (primary - free, reliable)
4. Agent scraper (Netflix, Disney+, HBO Max, Hulu fallback)
5. TMDB provider names with null links

**Key Files:**
- `justwatch_client.py` - JustWatch GraphQL API client
- `pipeline/enrichment.py` - Watch links waterfall logic

---

## Problem: All Watch Links Are Google Search URLs

### Symptoms
- Watch links in `data.json` look like: `https://www.google.com/search?q=Movie%20Title%20watch%20Platform`
- No deep links to Amazon, Apple TV, or other platforms
- Users have to search manually instead of going directly to movie page

### Root Cause (Legacy - Pre Dec 2024)
Previously: Watchmode API quota exhausted. System fell back to Google search URLs.

### Current Cause (Dec 2024+)
JustWatch API couldn't find the movie. Check that:
1. Movie title and year are correct in movie_tracking.json
2. JustWatch API is accessible (test with `justwatch_client.py`)
3. Cache isn't stale (delete entry in `cache/watch_links_cache.json` to force refresh)

---

## Understanding Null Streaming Links

### Current Situation (Expected Behavior)

Most streaming service links (Netflix, Hulu, Disney+, Max, etc.) show `link: null` in data.json. This is **EXPECTED BEHAVIOR**, not a bug. The service-based button UI correctly handles this by showing "NOT AVAILABLE" for null links.

### Why Streaming Links Are Null

**Primary Reason: Watchmode API Quota Exhausted**
- Watchmode API is the primary source for streaming service deep links
- Free tier quota: 1000 calls/month
- Current status: Exhausted (over quota)
- Quota resets: November 1st, 2025 (automatic)
- Graceful degradation: System falls back to other sources when Watchmode unavailable

**Secondary Reason: Agent Scraper Limited Support**
- Agent scraper (agent_link_scraper.py) only supports: Netflix, Disney+, HBO Max, Hulu
- Other services (Peacock, Paramount+, fuboTV, Criterion, etc.) not supported
- When Watchmode unavailable AND agent scraper doesn't support the service → null link

**Tertiary Reason: TMDB Providers Don't Include Links**
- TMDB API returns provider NAMES ("Netflix", "Hulu") but not URLs
- Without Watchmode or agent scraper, system can only show service name with null link
- By design: better to show null than wrong/broken links

### What Works Despite Null Streaming Links

✅ **Amazon/Apple Purchase Links:** Platform scraper provides these directly
✅ **Service Names:** Users can see which services have the movie (providers field)
✅ **Graceful Degradation:** System continues working, doesn't break
✅ **Google Search Fallback:** Some movies have Google search links as last resort

### When Will Streaming Links Be Populated

**November 1st, 2025 (Expected)**
- Watchmode API quota resets to 0/1000
- System automatically detects reset (see `_check_monthly_reset()` function in watchmode_api.py)
- Next data generation run will use Watchmode API again
- Streaming links will be populated with real deep links

**How the auto-reset works:**
- The watchmode_api.py module checks reset_date on every run
- If current date >= reset_date, quota counter resets to 0
- System resumes calling Watchmode API automatically
- No manual intervention required

### Current Workarounds

**For Users:**
- "NOT AVAILABLE" button is honest (better than broken links)
- Can manually search for the movie on Netflix/Hulu/etc.
- Amazon/Apple purchase buttons still work

**For Admin:**
- Can manually add streaming links via admin panel (admin/watch_link_overrides.json)
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

With Phase 2.1 optimization (enrichment-on-transition), the system now uses only 150-300 Watchmode calls/month instead of 9,540. This means:
- Free tier (1000 calls/month) is sustainable indefinitely
- No need to upgrade to $249/month paid plan
- Quota exhaustion should not happen again after Nov 1st reset

---

## Diagnosis

Follow these steps to diagnose the issue:

### 1. Test API Key
```bash
curl "https://api.watchmode.com/v1/search/?apiKey=YOUR_KEY&search_field=tmdb_movie_id&search_value=507244"
```

**Expected Results:**
- 200 OK with data → API works
- 401 Unauthorized → API key invalid
- 429 Too Many Requests → Rate limit exceeded

### 2. Check Logs
```bash
grep -i watchmode logs/generate_data.log
```
Look for error messages or warnings.

### 3. Check Statistics
Run `python3 generate_data.py` and look for:
```
Watchmode API Statistics:
  Watchmode successes: 0  ← Problem if zero
```

## Solutions

### Option 1: Get New API Key (Recommended)

**Steps:**
1. Sign up at https://api.watchmode.com/ (free tier: 1000 calls/month)
2. Copy your new API key
3. Set environment variable:
   ```bash
   export WATCHMODE_API_KEY="YOUR_NEW_API_KEY"
   ```
   **Note:** You can also set the key in `config.yaml` but environment variables are preferred for security
4. Regenerate data:
   ```bash
   python3 generate_data.py --full
   ```

**Why This Works:**
- Environment variables override config.yaml settings
- Fresh API key resets quota and resolves authentication issues
- Full regeneration ensures all movies get new watch links

### Option 2: Enable Platform Scraper (Amazon/Apple TV)

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
- ❌ Watchmode API: Not tested (TMDB API key missing)
- ⚠️ Overall coverage: Invalid test - re-run required
- Known issues: Configuration error - TMDB API key not set in config.yaml

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
- Watchmode API is down temporarily
- Platform scraper can't find specific movies
- Manual verification of links is required

## Watch Links System Status (Updated 2025-10-23)

### Three-Tier Strategy Performance

| Tier | Source | Coverage | Status |
|------|--------|----------|--------|
| 1 | Watchmode API | ⚠️ Not Tested | 🔴 Test Invalid |
| 2 | Amazon Scraper | 100% (validated) | ✅ Working |
| 3 | Manual Overrides | TBD (pending re-test) | ⏳ Pending |
| **Total** | **Combined** | **⚠️ Invalid Test** | **🔴 Re-test Required** |

### Test Invalidation Notice (2025-10-24)

⚠️ The validation test failed due to missing TMDB API key configuration. The script crashed before testing Watchmode API. Only Amazon scraper results are valid.

**Action Required:** Fix config.yaml (add TMDB API key) and re-run validation test.

See `IMPLEMENTATION_ROADMAP.md` (CRITICAL-003) for detailed re-test checklist.

**Last Tested:** 2025-10-24 (INVALID - configuration error)
**Last Selector Update:** 2025-10-23
**Next Maintenance:** 2026-01-23 (quarterly)

## Known Limitations

### Watchmode API
- Tends to miss recent 2025 releases: ⚠️ Not tested (configuration error)
- Coverage: ⚠️ Not tested (re-test required)
- Free tier: 1,000 requests/month (sufficient for daily automation)
- **Status:** Configuration error prevented testing - add TMDB API key to config.yaml

### Amazon Scraper (Playwright-based)
- Success rate: ~100% (as of 2025-10-25 with Playwright)
- Only runs when Watchmode has no data
- Focuses on recent releases
- Some failures expected:
  - Anti-bot detection: No
  - Movies not available on Amazon: No (all test movies found)
  - Selectors may need quarterly updates: Yes
- Performance: 6-8 seconds per search (improved with Playwright, ~48 minutes for full regeneration)

### Manual Overrides (Final Fallback)
- Required for: ~132 movies (53.4% as of 2025-10-24 invalid test)
- Use Admin Panel to add: http://localhost:5555
- Format: `admin/watch_link_overrides.json`

## Validation

After applying a fix:

1. **Check data.json for real deep links** (not Google search):
   ```bash
   grep -c "google.com/search" data.json  # Should decrease
   ```

2. **Count success rate:**
   ```bash
   python3 generate_data.py --full
   # Look for "Watchmode success rate" and "Platform scraper success rate" in output
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
# - Watchmode success rate: Currently 0% (needs investigation)
# - Platform scraper link attempts: Link-level attempts (e.g., 266 attempts)
# - Platform scraper success rate: Currently 100% (excellent)
# - Movies covered: Movie-level coverage (e.g., 115 movies with links)
# - Final coverage: Currently 46.6% (below 85-90% target)
```

### Warning Signs
- ⚠️ Watchmode success rate drops below 50% → Check API quota
- ⚠️ Platform scraper success rate drops below 40% → Update selectors
- ⚠️ Many "No Amazon link found" messages → Check anti-bot detection
- ⚠️ Final coverage drops below 80% → Investigate both tiers

### Quick Fixes
```bash
# If Watchmode API fails (quota exceeded)
# Wait for quota reset or get new API key from https://api.watchmode.com/

# If Amazon scraper fails (selectors outdated)
# Run with visible browser to inspect HTML:
python3 streaming_platform_scraper.py  # Playwright-based, headless=False in test function

# If specific movies missing links
# Add manual overrides via Admin Panel: http://localhost:5555
```

### Success Criteria
- At least 50% of Amazon/Apple TV movies have real deep links (Watchmode API handles most)
- Links work (no 404 errors)
- Platform scraper statistics show success rate > 40%
- Watchmode API should handle majority of movies

## Related Documentation

- [README.md](README.md) - Quick start and overview
- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) - CRITICAL-003: Watch Links Broken
- `generate_data.py` `get_watch_links()` function - Watch links waterfall logic
- [ADMIN_WORKFLOW.md](../../ADMIN_WORKFLOW.md) - Manual override workflow
- [AMAZON_ASIN_CLEANUP.md](AMAZON_ASIN_CLEANUP.md) - Playwright migration details (Section: Playwright Migration)