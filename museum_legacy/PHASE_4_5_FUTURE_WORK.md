# Phases 4 & 5: Future Work - Scraper Improvements & Validation

**Date:** 2025-10-24
**Status:** DEFERRED (LOW PRIORITY)
**Recommendation:** Monitor system performance first, implement only if needed

---

## Executive Summary

Phases 4 and 5 are **optional enhancements** that can be deferred until there's clear evidence they're needed. With Phases 1-3 complete, the system is:
- ✅ **Cost-optimized**: 98% reduction in API/scraping costs
- ✅ **Quota-protected**: Automatic monitoring and fallback
- ✅ **Functionally complete**: All core features working

**Recommendation:** **DEFER Phases 4-5 for now.** Monitor the system for 30 days first to gather data on:
- Apple TV scraper coverage (just enabled)
- Scraper failure rates
- Link quality/staleness
- Performance bottlenecks

If issues arise, revisit this plan.

---

## Phase 4: Scraper Improvements (DEFERRED)

**Priority:** Low
**Estimated Effort:** 1-2 weeks
**Current Status:** Selenium scrapers working, Apple TV just enabled

### 4.1 Upgrade Selenium → Playwright

**Why upgrade?**
- Playwright is faster (~30% speed improvement)
- More reliable (better error handling)
- Consistent with agent_link_scraper.py (already uses Playwright)
- Better maintained (Selenium declining)

**Why NOT upgrade now?**
- Current Selenium scrapers working well (90% Amazon success rate)
- No performance complaints
- Risk of breaking working system
- Effort not justified without proven need

**Implementation Plan (IF you decide to do it):**

#### Step 1: Install Playwright browsers
```bash
playwright install chromium
```

#### Step 2: Create Playwright version
**File:** `streaming_platform_scraper_playwright.py` (new)

**Key changes from Selenium:**
```python
# OLD (Selenium)
from selenium import webdriver
driver = webdriver.Chrome(options=options)
element = driver.find_element(By.CSS_SELECTOR, selector)

# NEW (Playwright)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    element = page.locator(selector)
```

**Full conversion checklist:**
- [  ] Replace webdriver imports with playwright imports
- [  ] Convert initialization (WebDriver → Browser/Page)
- [  ] Convert wait logic (WebDriverWait → page.wait_for_selector)
- [  ] Convert element selection (find_element → locator)
- [  ] Convert attribute access (get_attribute → get_attribute)
- [  ] Convert text access (element.text → element.text_content())
- [  ] Update error handling (TimeoutException → TimeoutError)
- [  ] Test parity with Selenium version

#### Step 3: A/B Testing
**Before switching:**
1. Run both scrapers side-by-side for 100 movies
2. Compare success rates
3. Compare speed (Playwright should be 30% faster)
4. Compare link quality (both should return same URLs)

**Acceptance criteria:**
- Playwright success rate >= Selenium success rate
- Playwright faster than Selenium
- No regressions in link quality

#### Step 4: Gradual Rollout
1. **Week 1:** Playwright for 10% of movies
2. **Week 2:** Playwright for 50% of movies
3. **Week 3:** Playwright for 100% of movies
4. **Week 4:** Remove Selenium code if no issues

### 4.2 Improve Apple TV Scraper Coverage

**Current status:**
- Apple TV scraper enabled 2025-10-24
- Only 2 real Apple TV links in current dataset
- Amazon scraper: 266 links (90% coverage)

**Why improve?**
- Apple TV is major streaming service
- Low coverage (2 vs 266 Amazon)
- Competitor to Amazon (users want options)

**Why wait?**
- **Just enabled today** - no data yet on performance!
- Need baseline data before optimization
- May be working fine, just needs time

**Recommended approach:**
1. **Monitor for 7 days** (Oct 24 - Oct 31)
2. **Collect metrics:**
   - Apple TV scraper success rate
   - Number of Apple TV links found
   - Failure patterns (errors, timeouts, selector failures)
3. **Analyze results:**
   - If success rate < 50%: Investigate and improve
   - If success rate >= 80%: No action needed
4. **Improve if needed:**
   - Update CSS selectors
   - Increase wait times for React rendering
   - Add more fallback selectors

**Improvement options (if needed):**
```python
# Option 1: Longer wait for React rendering
time.sleep(5)  # Currently 3 seconds

# Option 2: More robust selectors
selectors = [
    "a[href*='/movie/'][href*='umc.cmc']",  # Current
    "[data-metrics-loc*='movie'] a",         # NEW: Metrics-based
    ".product-header a[href*='umc.cmc']",   # NEW: Product header
    "a.we-lockup__link[href*='movie']"      # NEW: Lockup link
]

# Option 3: Retry logic
for attempt in range(3):
    result = find_apple_tv_link(title, year)
    if result:
        return result
    time.sleep(2)  # Wait before retry
```

### 4.3 Add Link Validation

**Purpose:** Prevent caching broken/404 links

**Current behavior:**
- Scraper returns URL without validation
- URL cached for 90 days
- User clicks, may get 404

**Proposed improvement:**
```python
import requests

def validate_watch_link(url, timeout=5):
    """Validate that a watch link is still working"""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)

        # Check for common error patterns
        if response.status_code == 404:
            return False
        if response.status_code >= 500:
            return False  # Server error
        if 'error' in response.url.lower() or 'notfound' in response.url.lower():
            return False

        return response.status_code == 200
    except Exception as e:
        print(f"⚠️  Link validation failed for {url}: {e}")
        return False  # Assume broken if can't validate

# Usage in scraper
amazon_link = scraper.find_amazon_link(title, year)
if amazon_link and validate_watch_link(amazon_link):
    movie['watch_links']['amazon'] = amazon_link
else:
    print(f"⚠️  Invalid Amazon link for {title}: {amazon_link}")
```

**Trade-offs:**
- **Pros:** Prevents caching broken links, better user experience
- **Cons:** Extra HTTP request per link (~1 second overhead)

**Recommendation:**
- Add validation only for stale links (>30 days old) during re-enrichment
- Skip validation for fresh links to avoid overhead

---

## Phase 5: Testing & Validation (DEFERRED)

**Priority:** Medium (after Phase 4)
**Estimated Effort:** Ongoing

### 5.1 Enhanced Validation Script

**Extend existing:** `ops/validate_discovery.py`

**Add new checks:**
```python
def validate_enrichment_efficiency():
    """Validate Phase 2.1 optimization is working"""
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)

    available = [m for m in db['movies'].values() if m['status'] == 'available']
    enriched = [m for m in available if m.get('enriched')]
    unenriched = [m for m in available if not m.get('enriched')]

    # Alert if too many unenriched
    if len(unenriched) > 50:
        print(f"⚠️  WARNING: {len(unenriched)} movies need enrichment!")
        return False

    # Alert if enrichment rate too low
    enrichment_rate = len(enriched) / len(available) * 100
    if enrichment_rate < 80:
        print(f"⚠️  WARNING: Only {enrichment_rate:.1f}% of available movies enriched!")
        return False

    print(f"✅ Enrichment efficiency: {enrichment_rate:.1f}% ({len(enriched)}/{len(available)})")
    return True

def validate_watch_links_quality():
    """Validate watch links aren't broken"""
    with open('data.json', 'r') as f:
        data = json.load(f)

    broken_links = []

    for movie in data['movies'][:10]:  # Sample 10 movies
        for category in ['streaming', 'rent', 'buy']:
            link_obj = movie['links'].get(category)
            if link_obj and link_obj.get('link'):
                url = link_obj['link']
                if not validate_watch_link(url):
                    broken_links.append((movie['title'], category, url))

    if broken_links:
        print(f"⚠️  WARNING: Found {len(broken_links)} broken links in sample:")
        for title, category, url in broken_links:
            print(f"  - {title} ({category}): {url}")
        return False

    print(f"✅ All sampled links valid")
    return True

def validate_quota_usage():
    """Validate Watchmode quota is within limits"""
    if not os.path.exists('watchmode_quota.json'):
        print(f"⚠️  No quota tracker found")
        return True

    with open('watchmode_quota.json', 'r') as f:
        tracker = json.load(f)

    calls = tracker['calls_this_month']
    limit = tracker['quota_limit']
    percentage = calls / limit * 100

    if percentage >= 90:
        print(f"⚠️  WARNING: Watchmode quota at {percentage:.1f}% ({calls}/{limit})")
        return False
    elif percentage >= 75:
        print(f"⚠️  NOTICE: Watchmode quota at {percentage:.1f}% ({calls}/{limit})")
    else:
        print(f"✅ Watchmode quota healthy: {percentage:.1f}% ({calls}/{limit})")

    return True
```

### 5.2 Daily Health Checks

**Add to daily_orchestrator.py:**
```python
# After all phases complete
print("\n🔍 Running health checks...")

checks = [
    validate_enrichment_efficiency(),
    validate_watch_links_quality(),
    validate_quota_usage()
]

if all(checks):
    print("\n✅ All health checks passed")
else:
    print("\n⚠️  Some health checks failed - review warnings above")
```

### 5.3 Monitoring Dashboard (Future)

**Admin panel enhancements:**
- Enrichment efficiency chart
- Quota usage trends graph
- Scraper success rates over time
- Link validation reports
- Alert system for failures

---

## Decision Matrix: When to Implement

### Implement Phase 4.1 (Playwright) if:
- [ ] Selenium scraper success rate drops below 70%
- [ ] Selenium maintenance becomes burdensome
- [ ] Performance becomes a bottleneck (>2 min/movie)
- [ ] Selenium deprecated or security issues

### Implement Phase 4.2 (Apple TV improvements) if:
- [ ] Apple TV scraper success rate < 50% (after 7-day monitoring)
- [ ] User complaints about missing Apple TV links
- [ ] Apple TV becomes primary provider (market shift)

### Implement Phase 4.3 (Link validation) if:
- [ ] User reports of broken links > 10%
- [ ] Staleness issues detected in validation runs
- [ ] Re-enrichment strategy needs validation

### Implement Phase 5 (Enhanced validation) if:
- [ ] System growing complex (>1000 movies)
- [ ] Multiple contributors need health checks
- [ ] Production deployment requires CI/CD
- [ ] Debugging failures becomes frequent

---

## Cost-Benefit Analysis

### Phase 4 (Scraper Improvements)

**Costs:**
- Developer time: 1-2 weeks
- Testing and validation: 3-5 days
- Risk of breaking working system
- Maintenance of new codebase

**Benefits:**
- 30% faster scraping (Playwright)
- More reliable error handling
- Better Apple TV coverage (maybe)
- Consistent tech stack

**Verdict:** **DEFER** - costs outweigh benefits at current scale

### Phase 5 (Enhanced Validation)

**Costs:**
- Developer time: 2-3 days
- Ongoing maintenance of checks
- CI/CD setup time

**Benefits:**
- Early detection of issues
- Confidence in system health
- Better debugging capability
- Professional quality assurance

**Verdict:** **DEFER** - implement basic checks only when needed

---

## Recommended Timeline (IF you decide to implement)

**Month 1 (November 2025):**
- Monitor current system performance
- Collect baseline metrics
- Identify pain points
- No code changes

**Month 2 (December 2025):**
- Review monitoring data
- Decide which (if any) Phase 4/5 features needed
- Prioritize based on actual issues found

**Month 3 (January 2026):**
- Implement highest-priority items only
- Test thoroughly before deployment
- Monitor impact

**Beyond:**
- Continuous monitoring
- Incremental improvements based on data
- Avoid premature optimization

---

## Current System Status (Phases 1-3 Complete)

### What's Working

**Discovery & Monitoring:**
- ✅ Provider monitoring restored (Phase 1.1)
- ✅ 11 newly digital movies found from backlog
- ✅ Daily pipeline monitors 1,900 tracking movies

**Enrichment Optimization:**
- ✅ Phase 2.1: 98% reduction in API/scraping costs
- ✅ Only enriches newly available movies
- ✅ Stale link re-enrichment (90-day batches)
- ✅ Free tier sustainable indefinitely

**Quota Management:**
- ✅ Phase 3: Quota monitoring active
- ✅ 429 error detection working
- ✅ Graceful degradation to scrapers
- ✅ Monthly auto-reset (Nov 1st)

**Scraping:**
- ✅ Amazon scraper: 90% success rate (266 links)
- ✅ Apple TV scraper: Enabled (needs baseline data)
- ✅ Selenium working reliably

### Current Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Monthly API calls | 150 estimated | ✅ Well within 1000 limit |
| Watchmode quota | Exhausted until Nov 1 | ⚠️  Expected, fallback active |
| Amazon coverage | 266/297 movies (90%) | ✅ Excellent |
| Apple TV coverage | 2/297 movies (0.7%) | ⏸️  Just enabled, monitoring |
| Enrichment efficiency | 99.7% (317/318 cached) | ✅ Optimization working |
| Data generation time | ~30 seconds | ✅ 96% faster than before |

---

## Conclusion

**Phases 4 and 5 are OPTIONAL and DEFERRED.**

The system is production-ready and performant after Phases 1-3. Before investing 1-2 weeks in scraper improvements:

1. **Monitor for 30 days** (Oct 24 - Nov 24)
2. **Collect data** on Apple TV coverage, scraper failures, quota usage
3. **Decide based on evidence**, not speculation
4. **Avoid premature optimization** - the current system works well

**If you never implement Phases 4-5, that's perfectly fine.** The core optimization (98% cost reduction) is complete and delivering value.

---

**Status:** Documented for future reference
**Recommendation:** Close Phases 4-5 as "deferred pending monitoring data"
**Next action:** Monitor system performance for 30 days, revisit if issues arise

---

**Document created by:** Claude Code
**Date:** 2025-10-24
**Plan reference:** [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md)
