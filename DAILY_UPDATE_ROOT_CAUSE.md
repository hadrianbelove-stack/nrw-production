# Daily Update Root Cause Analysis

**Date:** 2025-11-03
**Status:** ROOT CAUSE IDENTIFIED

---

## Timeline

- **Oct 26, 09:27 UTC:** ✅ Last successful daily update
  - 14/90 movies had real watch links
  - Scrapers working normally

- **Oct 26, 16:53 PST:** Deployed Playwright async fix (commit fb271c2)
  - Created PlaywrightManager singleton
  - Updated all 5 scrapers to use shared manager

- **Oct 27, 09:21 UTC:** ❌ First failure
  - Only 1/90 movies had real watch links
  - Error: "Provider coverage too low: 1 < 5"

- **Oct 27-Nov 3:** ❌ Continued failures every day
  - Oct 27-29: Provider coverage failures (1 < 5 or 0 < 5)
  - Nov 1-3: "No recent movies found" (cascading failure from old data)

---

## Root Cause

### The Smoking Gun

Oct 27 logs show:
```
- Mirreyes contra Godínez: Las Vegas: {'streaming': {'service': 'VIX ', 'link': None}}
- Regretting You: {'buy': {'service': 'Fandango', 'link': None}}
- Leslie Jones: Life Part 2: {'streaming': {'service': 'Peacock', 'link': None}}
- LEGO Frozen: Operation Puffins: {'streaming': {'service': 'Disney+', 'link': None}}
- A House of Dynamite: {'streaming': {'service': 'Netflix', 'link': None}}
```

**All movies have:**
- ✅ Service name (from Watchmode API)
- ❌ `link: None` (Playwright scrapers failing)

### What's Happening

1. **Watchmode API works:** Provides service names (VIX, Netflix, Disney+, etc.)
2. **Playwright scrapers fail silently:** Return None instead of deep links
3. **Validation fails:** Only movies with BOTH service AND link count as "real watch links"
4. **Daily update aborts:** Provider coverage < 5 → workflow fails

### Why It Started Oct 27

The **Playwright async fix** (fb271c2) was deployed Oct 26 and broke the scrapers in the CI environment:

**Possible causes:**
1. PlaywrightManager not properly initialized in CI
2. Browser/Playwright version mismatch in GitHub Actions
3. Permissions issue with shared manager in CI
4. Timing issue - scrapers not waiting for manager initialization
5. Silent exceptions being swallowed

---

## Evidence

### Last Successful Run (Oct 26)

On automation-updates branch:
```json
{
  "generated_at": "2025-10-26T09:27:55.719595",
  "movies": 325,
  "sample_movie": {
    "title": "Taken at a Truck Stop",
    "watch_links": {
      "streaming": {
        "service": "Tubi",
        "link": "https://tubitv.com/movies/123456"  // ✅ Actual link
      }
    }
  }
}
```

### First Failed Run (Oct 27)

```json
{
  "sample_movie": {
    "title": "Mirreyes contra Godínez",
    "watch_links": {
      "streaming": {
        "service": "VIX ",  // ✅ Service found
        "link": null        // ❌ Scraper failed
      }
    }
  }
}
```

---

## Why Oct 26 Data Shows Links on automation-updates

The Oct 26 data was generated BEFORE the Playwright fix was deployed:
- Morning run (09:27 UTC): ✅ Used old working scrapers
- Evening commit (16:53 PST): Deployed Playwright fix
- Next day (Oct 27): ❌ New code breaks scrapers

---

## The Real Issues (Not What We Thought)

### ❌ NOT the threshold
- Changing MIN_PROVIDER_COVERAGE won't help
- The scrapers genuinely aren't working
- Even threshold=0 would just hide the problem

### ❌ NOT stale data causing validation failures
- Stale data is a SYMPTOM, not the cause
- Validation is working correctly
- Data is stale BECAUSE daily updates keep failing

### ✅ Playwright scrapers broke in CI after async fix
- Local testing might work fine
- CI environment has different conditions
- Needs investigation of PlaywrightManager in GitHub Actions

---

## Next Steps to Fix

### 1. Investigate PlaywrightManager in CI

Check the Oct 27 full logs:
```bash
gh run view 18835938557 --log > oct27_full.log
grep -i "playwright\|browser\|manager" oct27_full.log
```

Look for:
- Playwright initialization errors
- Browser launch failures
- Manager singleton issues
- Silent exceptions

### 2. Add Diagnostic Logging

Update scrapers to log failures:
```python
try:
    link = self._scrape_amazon(title, year)
except Exception as e:
    self.logger.error(f"Amazon scrape failed: {e}")
    return None
```

### 3. Test Locally vs CI

Compare behavior:
```bash
# Local (probably works)
python3 generate_data.py

# CI environment simulation
docker run --rm -it ubuntu:22.04
apt-get update && apt-get install -y python3 python3-pip
pip3 install playwright
playwright install chromium --with-deps
# Try running scrapers
```

### 4. Rollback Option

If fix takes too long, temporarily revert Playwright fix:
```bash
git revert fb271c2
# Test if scrapers work again
# Then re-apply fix properly
```

### 5. Quick Workaround

Lower the validation or make it a warning:
```python
# In daily_orchestrator.py
if coverage_count < min_coverage:
    print(f"⚠️ WARNING: Low coverage {coverage_count}/{len(recent_movies)}")
    # Don't fail, just warn
```

---

## Recommended Immediate Action

**Run generate_data.py locally to break the cycle:**
```bash
# This will use your local working Playwright setup
python3 generate_data.py --full

# Commit the results
git add data.json movie_tracking.json
git commit -m "Manual data generation to restore service"
git push origin automation-updates

# This gives you working data while you fix CI
```

Then investigate why CI Playwright scrapers fail while local ones work.

---

**Last Updated:** 2025-11-03 16:45 PST
**Status:** Root cause identified - Playwright scrapers failing in CI after async fix
**Next:** Investigate CI environment Playwright initialization
