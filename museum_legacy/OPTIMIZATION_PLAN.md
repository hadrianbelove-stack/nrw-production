# NRW System Optimization Plan
**Created:** 2025-10-24
**Status:** Ready for Implementation

## Executive Summary

This plan addresses critical inefficiencies in the NRW movie discovery system discovered during investigation of "no new movies appearing" bug. The primary issue: **wasting API calls and scraping energy on movies that will never appear on the website** by enriching ALL movies instead of only newly available ones.

**Key Metrics:**
- 1,956 movies stuck in 'tracking' status (now fixed with provider monitoring)
- Watchmode API quota exhausted (1000 free calls/month exceeded)
- Current workflow: ~500 API calls per run enriching all movies
- Optimized workflow: ~10-20 API calls per run enriching only new arrivals
- **Estimated savings: 95% reduction in API/scraping costs**

---

## Phase 1: Immediate Fixes ✅ COMPLETED

**Timeline:** Completed 2025-10-24
**Status:** All done, systems operational

### 1.1 Restore Provider Monitoring ✅
**Problem:** 1,956 movies stuck in 'tracking', never transitioning to 'available'
**Root Cause:** Oct 23 migration forgot to port check_tracking_movies()

**Solution Implemented:**
- Ported `check_tracking_movies()` from legacy tracker to [generate_data.py:1724-1907](generate_data.py#L1724-L1907)
- Added `--check` flag to argument parser
- Integrated into [daily_orchestrator.py](daily_orchestrator.py) as Phase 1.5
- Updated [AMENDMENT-047](PROJECT_CHARTER.md#amendment-047) documentation

**Results:**
- ✅ 11 newly digital movies found from initial check
- ✅ Daily pipeline now monitors tracking movies
- ✅ Bug documented in PROJECT_CHARTER.md

### 1.2 Enable Apple TV Scraper ✅
**Problem:** Only 2 real Apple TV links in data.json (vs 266 Amazon links)
**Solution:** Changed `apple_tv: true` in [config.yaml](config.yaml)

**Next:** Test on next full data generation run

### 1.3 Document Watchmode Quota Issue ✅
**Problem:** API quota exhausted, all movies showing `source: "unknown"`
**Status:** Documented, waiting for Nov 1st reset (likely)

---

## Phase 2: Critical Workflow Optimization ✅ COMPLETE

**Timeline:** 1-2 days → Completed 2025-10-24
**Impact:** 95% reduction in API/scraping costs → **Achieved 98%+ reduction**
**Status:** Implemented, tested, and validated
**Details:** See [PHASE_2_1_COMPLETE.md](PHASE_2_1_COMPLETE.md)

### Problem Statement

**Current (Wasteful) Workflow:**
```
Daily Run:
├─ Generate data.json for 251 movies
├─ Call Watchmode API for ALL 251 movies
├─ Scrape Amazon for ALL 251 movies
├─ Scrape Apple TV for ALL 251 movies
└─ Result: ~500 API calls, most wasted on movies already enriched
```

**Optimized Workflow:**
```
Daily Run:
├─ Discovery: Find 5-10 new theatrical releases
├─ Provider Check: Find 3-5 newly digital movies (tracking → available)
├─ Enrich ONLY the 8-15 newly available movies
│   ├─ Watchmode API (8-15 calls instead of 251)
│   ├─ Amazon scraper (8-15 scrapes instead of 251)
│   └─ Apple TV scraper (8-15 scrapes instead of 251)
└─ Generate data.json with cached + newly enriched data
```

### 2.1 Implement Enrichment-on-Transition Logic

**File:** [generate_data.py](generate_data.py)
**Approach:** Add `newly_available_ids` tracking to avoid redundant enrichment

**Implementation Steps:**

1. **Track enrichment state in movie_tracking.json:**
```python
# Add to each movie object:
{
    "status": "available",
    "enriched": true,  # NEW FLAG
    "enrichment_date": "2025-10-24",  # NEW FIELD
    "watch_links": {  # Cache enriched links here
        "amazon": "...",
        "apple_tv": "...",
        "watchmode_data": {...}
    }
}
```

2. **Modify check_tracking_movies() to flag newly available:**
```python
def check_tracking_movies(self):
    newly_digital = []

    for movie_id, movie in tracking_movies:
        if has_providers and movie['status'] == 'tracking':
            movie['status'] = 'available'
            movie['enriched'] = False  # Mark for enrichment
            movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')
            newly_digital.append(movie_id)

    return newly_digital  # Return IDs of movies needing enrichment
```

3. **Modify main data generation to enrich only unenriched movies:**
```python
def generate_data_json(self):
    # Load tracking database
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)

    # Get available movies
    available_movies = [m for m in db['movies'].values() if m['status'] == 'available']

    # Split into enriched vs needs enrichment
    needs_enrichment = [m for m in available_movies if not m.get('enriched', False)]
    already_enriched = [m for m in available_movies if m.get('enriched', False)]

    print(f"📊 Available movies: {len(available_movies)}")
    print(f"   ✅ Already enriched: {len(already_enriched)}")
    print(f"   🆕 Need enrichment: {len(needs_enrichment)}")

    # Enrich ONLY the newly available movies
    for movie in needs_enrichment:
        # Call Watchmode API
        watchmode_data = self.get_watchmode_links(movie)

        # Scrape Amazon
        amazon_link = self.scrape_amazon(movie)

        # Scrape Apple TV
        apple_tv_link = self.scrape_apple_tv(movie)

        # Cache results
        movie['watch_links'] = {
            'amazon': amazon_link,
            'apple_tv': apple_tv_link,
            'watchmode_data': watchmode_data
        }
        movie['enriched'] = True
        movie['enrichment_date'] = datetime.now().strftime('%Y-%m-%d')

    # Save updated tracking database with cached links
    with open('movie_tracking.json', 'w') as f:
        json.dump(db, f, indent=2)

    # Generate data.json from ALL available movies (using cached + newly enriched)
    data = {
        'movies': [],
        'generated_at': datetime.now().isoformat()
    }

    for movie in available_movies:
        data['movies'].append({
            'title': movie['title'],
            'watch_links': movie.get('watch_links', {}),
            # ... other fields ...
        })

    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)
```

**Expected Impact:**
- Watchmode API calls: 251 → 8-15 per day (95% reduction)
- Amazon scrapes: 251 → 8-15 per day (95% reduction)
- Apple TV scrapes: 251 → 8-15 per day (95% reduction)
- Free tier sustainability: ~30 days quota → ~2000 days quota (5.5 years!)

### 2.2 Add Re-enrichment Strategy for Stale Links

**Problem:** Links can go stale (platforms remove movies, change URLs)

**Solution:** Add periodic re-enrichment for old movies
```python
def needs_re_enrichment(movie, max_age_days=90):
    """Check if movie's enrichment is stale and needs refresh"""
    if not movie.get('enriched'):
        return True

    enrichment_date = movie.get('enrichment_date')
    if not enrichment_date:
        return True

    age_days = (datetime.now() - datetime.fromisoformat(enrichment_date)).days
    return age_days > max_age_days

# In generate_data_json():
needs_enrichment = [m for m in available_movies
                    if needs_re_enrichment(m, max_age_days=90)]
```

**Strategy:**
- Fresh movies (< 90 days old): Never re-enrich unless manually flagged
- Old movies (> 90 days): Re-enrich in batches (10 per day max) to keep links fresh
- Manual override: Admin can flag any movie for re-enrichment

**Files to Modify:**
- [generate_data.py](generate_data.py): Core enrichment logic
- [movie_tracking.json](movie_tracking.json): Schema update (add enriched flag)
- [admin.py](admin.py): Add "Force Re-enrich" button for manual override

---

## Phase 3: Watchmode API Management ✅ COMPLETE

**Timeline:** 2-3 hours → Completed 2025-10-24
**Impact:** Quota monitoring, graceful degradation, automatic monthly reset
**Status:** Implemented, tested, and validated
**Details:** See [PHASE_3_COMPLETE.md](PHASE_3_COMPLETE.md)

### 3.1 Implement Quota Monitoring

**File:** [watchmode_api.py](watchmode_api.py) (create new module)

```python
class WatchmodeAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.quota_tracker = self.load_quota_tracker()

    def load_quota_tracker(self):
        """Track API usage to avoid exceeding quota"""
        if os.path.exists('watchmode_quota.json'):
            with open('watchmode_quota.json', 'r') as f:
                return json.load(f)
        return {
            'calls_this_month': 0,
            'quota_limit': 1000,  # Free tier
            'reset_date': self.get_next_month_start(),
            'call_history': []
        }

    def check_quota_before_call(self):
        """Prevent calls if over quota"""
        if self.quota_tracker['calls_this_month'] >= self.quota_tracker['quota_limit']:
            print(f"⚠️  Watchmode quota exhausted ({self.quota_tracker['calls_this_month']}/{self.quota_tracker['quota_limit']})")
            print(f"   Resets on: {self.quota_tracker['reset_date']}")
            return False
        return True

    def get_watch_links(self, title, tmdb_id):
        """Get watch links with quota checking"""
        if not self.check_quota_before_call():
            return None  # Fallback to scraping

        # Make API call
        response = requests.get(...)

        # Track usage
        self.quota_tracker['calls_this_month'] += 1
        self.quota_tracker['call_history'].append({
            'timestamp': datetime.now().isoformat(),
            'title': title,
            'tmdb_id': tmdb_id
        })
        self.save_quota_tracker()

        return response.json()
```

### 3.2 Implement Graceful Degradation

**Strategy:** If Watchmode quota exhausted, fall back to scraping without breaking

```python
# In generate_data.py:
def enrich_movie(self, movie):
    """Enrich movie with watch links using tiered approach"""

    # Tier 1: Admin overrides (always prioritized)
    if movie.get('admin_override_links'):
        return movie['admin_override_links']

    # Tier 2: Watchmode API (if quota available)
    watchmode_links = None
    if self.watchmode_api.check_quota_before_call():
        watchmode_links = self.watchmode_api.get_watch_links(movie['title'], movie['tmdb_id'])
        if watchmode_links:
            return watchmode_links
    else:
        print(f"⚠️  Watchmode quota exhausted, falling back to scraping for {movie['title']}")

    # Tier 3: Platform scrapers (Amazon, Apple TV)
    scraped_links = {
        'amazon': self.scrape_amazon(movie),
        'apple_tv': self.scrape_apple_tv(movie)
    }

    # Tier 4: TMDB providers (if scrapers fail)
    if not any(scraped_links.values()):
        scraped_links = self.get_tmdb_providers(movie)

    # Tier 5: Google search fallback
    if not any(scraped_links.values()):
        scraped_links = self.google_search_fallback(movie)

    return scraped_links
```

### 3.3 Cost Analysis & Upgrade Decision

**Current Situation:**
- Free tier: 1000 calls/month (exhausted)
- Paid tier: $249/month (Startup plan)

**With Optimization (Phase 2 implemented):**
- Expected usage: 8-15 calls/day = 240-450 calls/month
- Free tier: SUFFICIENT (within 1000 limit)
- Recommendation: **Stay on free tier, upgrade only if discovery rate increases**

**Upgrade Triggers:**
- If daily new arrivals exceed 33 movies/day (unlikely)
- If we want to re-enrich entire catalog monthly (not recommended)
- If we add more features requiring Watchmode data

---

## Phase 4: Scraper Improvements ⏸️ DEFERRED

**Timeline:** 1 week → Deferred pending monitoring data
**Status:** Documented for future reference
**Details:** See [PHASE_4_5_FUTURE_WORK.md](PHASE_4_5_FUTURE_WORK.md)
**Recommendation:** Monitor system for 30 days first, implement only if needed

### 4.1 Upgrade Selenium → Playwright

**File:** [streaming_platform_scraper.py](streaming_platform_scraper.py)

**Rationale:**
- [agent_link_scraper.py](agent_link_scraper.py) already uses Playwright
- Playwright is faster, more reliable, better maintained
- Consistent tech stack across project

**Migration Steps:**
1. Install Playwright: `pip3 install playwright && playwright install`
2. Rewrite Amazon scraper using Playwright
3. Rewrite Apple TV scraper using Playwright
4. Test against current Selenium version (validate parity)
5. Switch over once validated
6. Remove Selenium dependency

**Expected Impact:**
- Faster scraping (Playwright ~30% faster than Selenium)
- More reliable (better error handling)
- Easier maintenance (single scraping framework)

### 4.2 Improve Apple TV Scraper Coverage

**Current Status:**
- Enabled but untested after recent activation
- Only 2 real Apple TV links vs 266 Amazon links

**Improvement Plan:**
1. Test current scraper on next full run
2. Analyze failure cases
3. Improve selector robustness
4. Add retry logic for transient failures
5. Target: 80%+ coverage (similar to Amazon's 90%)

### 4.3 Add Link Validation

**Problem:** Scraped links can be broken or redirect to error pages

**Solution:** Validate links before caching
```python
def validate_watch_link(url, timeout=5):
    """Validate that a watch link is still working"""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        # Check for common error patterns
        if response.status_code == 404:
            return False
        if 'error' in response.url.lower() or 'notfound' in response.url.lower():
            return False
        return response.status_code == 200
    except:
        return False

# In enrichment flow:
amazon_link = self.scrape_amazon(movie)
if amazon_link and validate_watch_link(amazon_link):
    movie['watch_links']['amazon'] = amazon_link
else:
    print(f"⚠️  Invalid Amazon link for {movie['title']}: {amazon_link}")
```

---

## Phase 5: Testing & Validation ⏸️ DEFERRED

**Status:** Basic validation complete, advanced features deferred
**Details:** See [PHASE_4_5_FUTURE_WORK.md](PHASE_4_5_FUTURE_WORK.md)
**Current:** Manual testing sufficient, automated tests when system grows

**Timeline:** Continuous
**Priority:** Critical for each phase

### 5.1 Validation Checklist

**After Phase 2 Implementation:**
- [ ] Run `python3 generate_data.py --discover` (should find 5-10 new releases)
- [ ] Run `python3 generate_data.py --check` (should find 3-5 newly digital)
- [ ] Run `python3 generate_data.py` (should enrich ONLY the 8-15 newly available)
- [ ] Verify watchmode_quota.json shows reduced usage
- [ ] Verify movie_tracking.json has `enriched: true` flags
- [ ] Verify data.json has watch links for newly enriched movies
- [ ] Check logs for "Already enriched: X, Need enrichment: Y" message

**After Phase 3 Implementation:**
- [ ] Verify quota monitoring prevents over-usage
- [ ] Test graceful degradation (manually exhaust quota, verify scraping fallback)
- [ ] Verify quota resets on 1st of month

**After Phase 4 Implementation:**
- [ ] Compare Playwright vs Selenium scraping success rates
- [ ] Verify Apple TV coverage improves
- [ ] Validate all links are working (not 404s)

### 5.2 Regression Testing

**File:** [ops/validate_discovery.py](ops/validate_discovery.py) (already exists)

**Enhancement:** Add enrichment validation
```python
def validate_enrichment_efficiency():
    """Validate that we're only enriching newly available movies"""
    with open('movie_tracking.json', 'r') as f:
        db = json.load(f)

    available = [m for m in db['movies'].values() if m['status'] == 'available']
    enriched = [m for m in available if m.get('enriched')]
    unenriched = [m for m in available if not m.get('enriched')]

    print(f"📊 Enrichment Efficiency Report:")
    print(f"   Total available: {len(available)}")
    print(f"   Enriched: {len(enriched)} ({len(enriched)/len(available)*100:.1f}%)")
    print(f"   Needs enrichment: {len(unenriched)}")

    # Alert if too many unenriched (indicates enrichment not running)
    if len(unenriched) > 50:
        print(f"⚠️  WARNING: {len(unenriched)} movies need enrichment!")
        return False

    return True
```

---

## Phase 6: Long-term Improvements 🚀 FUTURE

**Timeline:** 2-4 weeks
**Priority:** Nice-to-have, after critical issues resolved

### 6.1 Smart Re-enrichment

**Feature:** Automatically detect stale links and re-enrich
- Monitor 404 errors from user link clicks (if we add analytics)
- Periodically validate cached links
- Re-enrich only movies with broken links

### 6.2 Alternative Link Sources

**Research:** Find additional free/cheap link aggregators
- JustWatch API (if they have one)
- TMDB "external IDs" field (links to IMDb, which has streaming info)
- Reelgood (similar to Watchmode)

### 6.3 Admin Panel Enhancements

**Features:**
- Dashboard showing API quota usage
- Manual re-enrichment button for individual movies
- Link validation reports
- Enrichment efficiency metrics

### 6.4 Caching Layer Improvements

**Optimization:** Separate cache for different data types
```
cache/
  ├─ tmdb_metadata/      # Movie metadata (rarely changes)
  ├─ watch_links/        # Watch links (change frequently)
  ├─ provider_status/    # Provider availability (check daily)
  └─ enrichment_state/   # Enrichment flags (update on transition)
```

---

## Success Metrics

### Phase 1 (Completed) ✅
- ✅ Provider monitoring restored
- ✅ 11 newly digital movies found
- ✅ Apple TV scraper enabled

### Phase 2 (Critical)
- **API call reduction:** 500 → 10-20 per day (95% reduction)
- **Watchmode sustainability:** Stay within free tier (1000 calls/month)
- **No broken functionality:** All movies still have watch links
- **Performance:** Data generation completes in < 5 minutes (vs current ~15 min)

### Phase 3 (Medium)
- **Quota monitoring:** Never exceed quota unexpectedly
- **Graceful degradation:** System works even if Watchmode unavailable
- **Cost control:** Avoid $249/month upgrade (stay on free tier)

### Phase 4 (Low)
- **Apple TV coverage:** 2 links → 200+ links (80% coverage)
- **Scraping speed:** 30% faster with Playwright
- **Link quality:** < 5% broken links (validated before caching)

---

## Implementation Order

**Week 1: Critical Foundation**
1. ✅ Phase 1 (completed)
2. Phase 2.1: Implement enrichment-on-transition logic
3. Phase 2.2: Add re-enrichment strategy
4. Phase 5.1: Test and validate

**Week 2: API Management**
5. Phase 3.1: Implement quota monitoring
6. Phase 3.2: Implement graceful degradation
7. Phase 5.1: Test quota management

**Week 3-4: Scraper Improvements (Optional)**
8. Phase 4.1: Upgrade to Playwright
9. Phase 4.2: Improve Apple TV scraper
10. Phase 4.3: Add link validation
11. Phase 5.2: Regression testing

**Future: Long-term Enhancements**
12. Phase 6: Implement as needed based on user feedback

---

## Risk Mitigation

### Risk 1: Breaking Existing Functionality
**Mitigation:**
- Keep old enrichment code as fallback
- Test on copy of movie_tracking.json first
- Validate data.json structure before overwriting
- Git commit before each major change

### Risk 2: Watchmode Quota Doesn't Reset
**Mitigation:**
- Have scraping fallback ready (Tier 3)
- Contact Watchmode support to confirm reset date
- Prepare for potential upgrade if quota doesn't reset

### Risk 3: Scrapers Break (Platform UI Changes)
**Mitigation:**
- Have multi-tier fallback system (Watchmode → Scraping → TMDB → Google)
- Add link validation to detect broken scrapers early
- Set up alerts for scraping failure rate > 50%

### Risk 4: Performance Degradation
**Mitigation:**
- Profile code before/after changes
- Set timeout limits on all external calls
- Add caching at every layer
- Monitor data generation time

---

## Rollback Plan

If Phase 2 optimization causes issues:

1. **Immediate Rollback:**
```bash
git revert HEAD  # Undo last commit
python3 generate_data.py  # Regenerate with old logic
```

2. **Restore movie_tracking.json:**
```bash
cp movie_tracking.json.backup movie_tracking.json
```

3. **Fallback to Full Enrichment:**
```python
# In generate_data.py, comment out optimization:
# needs_enrichment = [m for m in available_movies if not m.get('enriched')]
needs_enrichment = available_movies  # Enrich all (old behavior)
```

---

## Next Actions

**Immediate (Start Now):**
1. Review this plan with user for approval
2. Create backup: `cp movie_tracking.json movie_tracking.json.backup`
3. Implement Phase 2.1 (enrichment-on-transition logic)
4. Test on subset of movies first (10-20 movies)
5. Validate before rolling out to full catalog

**This Week:**
- Complete Phase 2 (critical optimization)
- Test thoroughly with Phase 5.1 validation
- Monitor results for 2-3 days

**Next Week:**
- Implement Phase 3 (quota management)
- Wait for Watchmode quota reset (Nov 1st likely)
- Re-test with fresh quota

**Future:**
- Phase 4 (scraper improvements) as time permits
- Phase 6 (long-term enhancements) based on user needs

---

## Questions for User

1. **Phase 2 Priority:** Approve immediate implementation of enrichment optimization?
2. **Watchmode Strategy:** Wait for Nov 1st quota reset, or implement without Watchmode first?
3. **Testing Approach:** Test on subset first (conservative) or full rollout (aggressive)?
4. **Phase 4 Priority:** How important is Apple TV scraper improvement vs other priorities?

---

**Document Status:** Ready for review and approval
**Next Step:** User approval to begin Phase 2 implementation
