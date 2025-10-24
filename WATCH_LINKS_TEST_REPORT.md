# Watch Links System Test Report

## Test Overview
- **Date**: 2025-10-23
- **Objective**: Verify three-tier watch links strategy (Watchmode API → Amazon scraper → Manual overrides)
- **Components Tested**: Watchmode API, Amazon scraper, integration pipeline, data.json output
- **Success Criteria**: 85-90% coverage with acceptable failure rate for scraper

## Phase 1: Watchmode API Testing (Primary Source)

### Test Commands
```bash
# Set environment variables
export TMDB_API_KEY="99b122ce7fa3e9065d7b7dc6e660772d"
export WATCHMODE_API_KEY="bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp"

# Run full data generation
python3 generate_data.py --full
```

### Expected Output Indicators
- No error messages about missing WATCHMODE_API_KEY
- Statistics section shows: `Watchmode API Statistics:`
- `watchmode_successes` should be > 0 (target: 150-200 out of 251 movies)
- `Watchmode success rate` should be 60-80%

### Results to Document
- [ ] Watchmode API calls made: ___
- [ ] Watchmode successes: ___
- [ ] Watchmode success rate: ___%
- [ ] Cache hits: ___
- [ ] Movies with Watchmode links: ___/251
- [ ] Identified gaps (movies without links): List titles of 5-10 examples

### Validation Steps
1. Check console output for Watchmode statistics
2. Verify no API key errors
3. Identify which movies are missing links (likely recent 2025 releases)
4. Sample 3-5 movies in `data.json` to verify real streaming links (not Google search URLs)

### Gap Analysis
Document which types of movies Watchmode misses:
- [ ] Recent 2025 releases: Yes/No
- [ ] Independent films: Yes/No
- [ ] International films: Yes/No
- [ ] Specific platforms missing: List platforms

---

## Phase 2: Amazon Scraper Standalone Testing (Backup Source)

### Test Commands
```bash
# Run standalone scraper test with visible browser
python3 streaming_platform_scraper.py
```

### Test Movies (Recent 2025 Releases)
The test function will attempt to find Amazon links for:
1. Afterburn (2025)
2. Pet Shop Days (2025)
3. The Eichmann Trial (2025)
4. Little Brother (2025)

### Expected Behavior
- Chrome browser opens visibly (headless=False)
- Navigates to Amazon Prime Video search for each movie
- Tries multiple CSS selectors in priority order
- Prints detailed logging for each selector attempt
- Pauses between movies for manual inspection
- Reports success/failure for each movie

### Results to Document
- [ ] Test 1 - Afterburn: Link found? ___ | URL: ___
- [ ] Test 2 - Pet Shop Days: Link found? ___ | URL: ___
- [ ] Test 3 - The Eichmann Trial: Link found? ___ | URL: ___
- [ ] Test 4 - Little Brother: Link found? ___ | URL: ___
- [ ] Success rate: ___/4 (___%)
- [ ] Average time per search: ___ seconds

### Selector Analysis
For each successful find, document which selector worked:
- [ ] High-confidence selectors (lines 96-100): Used? Which one?
- [ ] Fallback selectors (lines 103-123): Used? Which one?
- [ ] Validation keywords found: List keywords (e.g., "prime video", "stream", "rent")

### Failure Pattern Analysis
For each failure, document why:
- [ ] No search results found: Yes/No
- [ ] Results found but no video links: Yes/No
- [ ] Selectors outdated (elements not found): Yes/No
- [ ] Anti-bot detection (CAPTCHA, blocking): Yes/No
- [ ] Movie not available on Amazon: Yes/No

### Manual Validation
For each successful link:
1. Copy the URL from test output
2. Open in browser
3. Verify it goes directly to movie page (not search results)
4. Verify movie title matches
5. Verify rent/buy options are available

### Selector Update Recommendations
If success rate < 50%:
- [ ] Document which selectors failed consistently
- [ ] Inspect Amazon HTML manually during test
- [ ] Identify new selector patterns to add
- [ ] Note: This is acceptable - manual overrides will handle failures

---

## Phase 3: Full Integration Testing (End-to-End Pipeline)

### Test Commands
```bash
# Ensure environment variables are set
export TMDB_API_KEY="99b122ce7fa3e9065d7b7dc6e660772d"
export WATCHMODE_API_KEY="bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp"

# Run full data generation with platform scraper enabled
python3 generate_data.py --full
```

### Expected Pipeline Behavior
For each movie:
1. Check manual tracking data (movie_tracking.json)
2. Check manual overrides (overrides/watch_links_overrides.json)
3. Check admin overrides (admin/watch_link_overrides.json)
4. Check cache (cache/watch_links_cache.json)
5. **Try Watchmode API** ← Primary source
6. If Watchmode fails and movie has Amazon provider:
   - **Initialize platform scraper** (lazy, first time only)
   - **Try Amazon scraper** ← Backup source
7. If scraper fails, fall back to Google search URL

### Console Output to Monitor
Look for these log messages:
- `Initializing platform scraper for {movie_title}...` (first Amazon attempt)
- `Platform scraper initialized (headless=True, timeout=10s)`
- `Trying platform scraper for {title} {type} on Amazon...`
- `✓ Platform scraper found {type} link for {title} on Amazon`
- `✗ No Amazon link found for {title}`
- `Rate limiting: sleeping X.Xs before platform scraper`

### Statistics to Document
From the final output:

**Watchmode API Statistics:**
- [ ] Search calls: ___
- [ ] Source calls: ___
- [ ] Cache hits: ___
- [ ] Watchmode successes: ___
- [ ] Success rate: ___%

**Platform Scraper Statistics (Amazon/Apple TV):**
- [ ] Platform scraper enabled: ___
- [ ] Platform scraper initialized: ___
- [ ] Amazon enabled: ___
- [ ] Apple TV enabled: ___
- [ ] Platform scraper attempts: ___
- [ ] Platform scraper successes: ___
- [ ] Platform scraper failures: ___
- [ ] Success rate: ___%
- [ ] Success rate vs Watchmode API: ___ (higher/lower than ___%)
- [ ] Last selector update: ___
- [ ] Expected update frequency: ___

### Integration Validation
- [ ] Platform scraper only attempted for movies with Amazon providers: Yes/No
- [ ] Platform scraper only attempted when Watchmode had no data: Yes/No
- [ ] Rate limiting enforced (2 seconds between scrapes): Yes/No
- [ ] Statistics tracking worked correctly: Yes/No
- [ ] No crashes or errors: Yes/No

### Cache Validation
```bash
# Check if cache was created and populated
ls -lh cache/watch_links_cache.json

# Inspect cache contents (sample)
cat cache/watch_links_cache.json | python3 -m json.tool | head -50
```

- [ ] Cache file exists: Yes/No
- [ ] Cache contains entries with `"source": "platform_scraper"`: Yes/No
- [ ] Cache entries have correct schema (streaming/rent/buy): Yes/No

### Performance Metrics
- [ ] Total execution time: ___ minutes
- [ ] Time added by platform scraper: ~___ minutes (estimate)
- [ ] Acceptable for daily automation: Yes/No

---

## Phase 4: Data Validation (Output Quality)

### Link Type Analysis
```bash
# Count Google search fallbacks (should decrease from baseline)
grep -c "google.com/search" data.json

# Count Amazon deep links (should increase)
grep -c "amazon.com/gp/video" data.json
grep -c "amazon.com/dp" data.json

# Count total Amazon links
grep -o '"amazon.com/[^"]*"' data.json | wc -l
```

### Results to Document
- [ ] Google search URLs: ___ (baseline: ~251, target: <100)
- [ ] Amazon /gp/video/ links: ___ (baseline: 0, target: >20)
- [ ] Amazon /dp/ links: ___ (baseline: 0, target: >10)
- [ ] Total Amazon deep links: ___ (target: >30)
- [ ] Improvement: Reduced Google search by ___ URLs

### Sample Movie Inspection
Inspect specific movies mentioned by user:

```bash
# Check Afterburn
jq '.movies[] | select(.title == "Afterburn") | .watch_links' data.json

# Check Pet Shop Days
jq '.movies[] | select(.title == "Pet Shop Days") | .watch_links' data.json

# Check The Eichmann Trial
jq '.movies[] | select(.title == "The Eichmann Trial") | .watch_links' data.json

# Check Little Brother
jq '.movies[] | select(.title == "Little Brother") | .watch_links' data.json
```

### Expected Structure (Success)
```json
{
  "rent": {
    "service": "Amazon Video",
    "link": "https://www.amazon.com/gp/video/detail/B0XXXXXX"
  },
  "buy": {
    "service": "Amazon Video",
    "link": "https://www.amazon.com/gp/video/detail/B0XXXXXX"
  }
}
```

### Expected Structure (Failure/Fallback)
```json
{
  "rent": {
    "service": "Amazon Video",
    "link": "https://www.google.com/search?q=Afterburn+2025+watch+Amazon+Video"
  }
}
```

### Document Results
- [ ] Afterburn: Has deep link? ___ | Link type: ___
- [ ] Pet Shop Days: Has deep link? ___ | Link type: ___
- [ ] The Eichmann Trial: Has deep link? ___ | Link type: ___
- [ ] Little Brother: Has deep link? ___ | Link type: ___

### Manual Link Testing
Test 3-5 deep links in browser:

```bash
# Extract sample Amazon deep links
jq -r '.movies[] | select(.watch_links.rent.link | contains("amazon.com/gp")) | .watch_links.rent.link' data.json | head -5
```

For each link:
1. [ ] Link 1: Opens? ___ | Goes to movie page? ___ | Title matches? ___ | 404 error? ___
2. [ ] Link 2: Opens? ___ | Goes to movie page? ___ | Title matches? ___ | 404 error? ___
3. [ ] Link 3: Opens? ___ | Goes to movie page? ___ | Title matches? ___ | 404 error? ___
4. [ ] Link 4: Opens? ___ | Goes to movie page? ___ | Title matches? ___ | 404 error? ___
5. [ ] Link 5: Opens? ___ | Goes to movie page? ___ | Title matches? ___ | 404 error? ___

### Coverage Calculation
```bash
# Total movies
jq '.movies | length' data.json

# Movies with Amazon providers
jq '[.movies[] | select(.providers.rent[]? | contains("Amazon")) or select(.providers.buy[]? | contains("Amazon"))] | length' data.json

# Movies with Amazon deep links (not Google search)
jq '[.movies[] | select(.watch_links.rent.service == "Amazon Video" and (.watch_links.rent.link | contains("amazon.com/gp") or contains("amazon.com/dp")))] | length' data.json
```

### Final Coverage Metrics
- [ ] Total movies: ___
- [ ] Movies with Amazon providers: ___
- [ ] Movies with Watchmode links: ___ (___%)
- [ ] Movies with Amazon scraper links: ___ (___%)
- [ ] Movies with deep links (Watchmode + Scraper): ___ (___%)
- [ ] Movies still using Google search: ___ (___%)
- [ ] **Final coverage: ___%** (target: 85-90%)

---

## Phase 5: Results Documentation & Recommendations

### Summary Report

**Three-Tier Strategy Performance:**

| Tier | Source | Coverage | Success Rate | Notes |
|------|--------|----------|--------------|-------|
| 1 | Watchmode API | ___% | ___% | Primary source, works well for most movies |
| 2 | Amazon Scraper | ___% | ___% | Backup for recent releases, acceptable failure rate |
| 3 | Manual Overrides | ___% | 100% | Final fallback, admin tool |
| **Total** | **Combined** | **___%** | **N/A** | **Target: 85-90%** |

**Success Criteria Assessment:**
- [ ] ✅/❌ Watchmode API returns links for 70-80% of movies
- [ ] ✅/❌ Amazon scraper finds links for 50%+ of movies Watchmode misses
- [ ] ✅/❌ Final coverage is 85-90%
- [ ] ✅/❌ No crashes or errors in pipeline
- [ ] ✅/❌ Caching works correctly
- [ ] ✅/❌ Links are valid and go to correct movie pages

### Known Limitations
Document observed limitations:

**Watchmode API:**
- Misses recent 2025 releases: Yes/No
- Misses independent films: Yes/No
- Misses international films: Yes/No
- Over quota issues: Yes/No

**Amazon Scraper:**
- Anti-bot detection encountered: Yes/No
- Selectors need updates: Yes/No (which ones?)
- Movies not available on Amazon: Yes/No
- Performance impact acceptable: Yes/No

**Overall System:**
- Acceptable failure rate: Yes/No
- Manual overrides needed for: ___ movies (___%)
- System ready for production: Yes/No

### Maintenance Recommendations

**Immediate Actions:**
- [ ] Update `config.yaml` line 57 with today's date: `last_selector_update: "2025-10-23"`
- [ ] Document selector update in `IMPLEMENTATION_ROADMAP.md`
- [ ] Add failing movies to manual override list if needed

**Quarterly Maintenance (Every 3 months):**
- [ ] Re-run standalone Amazon scraper test
- [ ] Check if selectors still work
- [ ] Update selectors if success rate drops below 40%
- [ ] Update `last_selector_update` date in config

**Monitoring:**
- [ ] Track platform scraper success rate in daily runs
- [ ] Alert if success rate drops below 30% (indicates selector issues)
- [ ] Review manual override list monthly

### Next Steps

**If Tests Pass (85-90% coverage):**
1. ✅ Mark CRITICAL-003 as RESOLVED in `IMPLEMENTATION_ROADMAP.md`
2. ✅ Update `README.md` troubleshooting section with test results
3. ✅ Commit changes with message: "Fix: Configure Watchmode API and Amazon scraper for watch links"
4. ✅ Deploy to production
5. ✅ Monitor daily runs for 3 days

**If Tests Partially Pass (70-84% coverage):**
1. ⚠️ Mark CRITICAL-003 as PARTIAL in `IMPLEMENTATION_ROADMAP.md`
2. ⚠️ Document gaps and limitations
3. ⚠️ Create manual override list for failing movies
4. ⚠️ Consider selector updates if Amazon scraper success rate < 40%
5. ⚠️ Deploy with known limitations

**If Tests Fail (<70% coverage):**
1. ❌ Debug Watchmode API (check API key, quota, network)
2. ❌ Debug Amazon scraper (update selectors, check anti-bot)
3. ❌ Review integration logic in `generate_data.py`
4. ❌ Re-run tests after fixes
5. ❌ Do not deploy until coverage improves

### Files to Update After Testing

1. **`config.yaml` line 57:**
   - Update `last_selector_update` to today's date

2. **`IMPLEMENTATION_ROADMAP.md` CRITICAL-003 section:**
   - Update status to RESOLVED/PARTIAL/IN PROGRESS
   - Add test results summary
   - Document coverage metrics
   - Add decision log entry with test date and results

3. **`README.md` troubleshooting section:**
   - Update with actual success rates
   - Document known limitations
   - Add maintenance schedule

4. **`admin/watch_link_overrides.json` (if needed):**
   - Add manual overrides for movies that failed both Watchmode and scraper
   - Format: `{"movie_id": {"rent": {"service": "Amazon Video", "link": "https://..."}}}`

---

## Test Execution Checklist

### Pre-Test Setup
- [ ] Backup current `data.json`: `cp data.json data.json.backup`
- [ ] Backup current cache: `cp -r cache cache.backup` (if exists)
- [ ] Ensure Chrome browser is installed
- [ ] Ensure ChromeDriver is installed: `pip3 install webdriver-manager`
- [ ] Set environment variables (TMDB_API_KEY, WATCHMODE_API_KEY)

### Phase Execution
- [ ] Phase 1: Test Watchmode API (15-20 minutes)
- [ ] Phase 2: Test Amazon Scraper Standalone (10-15 minutes)
- [ ] Phase 3: Test Full Integration (15-20 minutes)
- [ ] Phase 4: Validate Data Output (10-15 minutes)
- [ ] Phase 5: Document Results (15-20 minutes)

### Total Estimated Time
- **1-1.5 hours** for complete testing and documentation

### Post-Test Actions
- [ ] Review all documented results
- [ ] Calculate final coverage percentage
- [ ] Assess against success criteria
- [ ] Update configuration files
- [ ] Update documentation files
- [ ] Commit changes if tests pass
- [ ] Create manual override list if needed

---

## Appendix: Useful Commands

### Environment Setup
```bash
# Set API keys (add to ~/.zshrc or ~/.bashrc for persistence)
export TMDB_API_KEY="99b122ce7fa3e9065d7b7dc6e660772d"
export WATCHMODE_API_KEY="bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp"

# Verify environment variables
echo $TMDB_API_KEY
echo $WATCHMODE_API_KEY
```

### Data Analysis
```bash
# Count movies by watch link type
jq '[.movies[].watch_links | to_entries[] | .value.link] | group_by(. | contains("google.com")) | map({type: (if .[0] | contains("google.com") then "google_search" else "deep_link" end), count: length})' data.json

# List movies without any watch links
jq -r '.movies[] | select(.watch_links == null or .watch_links == {}) | .title' data.json

# List movies with Amazon providers but Google search links
jq -r '.movies[] | select(.providers.rent[]? | contains("Amazon")) | select(.watch_links.rent.link | contains("google.com")) | .title' data.json

# Extract all unique streaming services
jq -r '[.movies[].watch_links | to_entries[] | .value.service] | unique | .[]' data.json
```

### Cache Inspection
```bash
# View cache structure
cat cache/watch_links_cache.json | python3 -m json.tool | less

# Count cache entries by source
jq '[.[] | .source] | group_by(.) | map({source: .[0], count: length})' cache/watch_links_cache.json

# Find platform scraper cache entries
jq 'to_entries[] | select(.value.source == "platform_scraper")' cache/watch_links_cache.json
```

### Log Analysis
```bash
# View recent logs
tail -100 logs/admin.log

# Search for platform scraper activity
grep -i "platform scraper" logs/admin.log

# Search for errors
grep -i "error" logs/admin.log | tail -20
```

### Quick Validation
```bash
# Test a single movie's watch links
jq '.movies[] | select(.title == "MOVIE_TITLE") | {title, watch_links, providers}' data.json

# Compare before/after data.json
diff <(jq '.movies[].watch_links' data.json.backup) <(jq '.movies[].watch_links' data.json) | head -50
```