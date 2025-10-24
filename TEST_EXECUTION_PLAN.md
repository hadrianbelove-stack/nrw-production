# Manual Pipeline Test Execution Plan
**Date:** [Current date]
**Tester:** [Your name]
**Purpose:** Verify complete NRW data pipeline functionality before relying on automation

## Pre-Test Checklist

**Environment Verification:**
- [ ] Confirm in repository root: `/Users/hadrianbelove/Downloads/nrw-production`
- [ ] Check Python version: `python3 --version` (should be 3.11+)
- [ ] Verify dependencies installed: `pip3 list | grep -E "(Flask|requests|selenium|playwright|beautifulsoup4)"`
- [ ] Check config.yaml exists and has TMDB API key
- [ ] Verify movie_tracking.json exists (master database)
- [ ] Verify data.json exists (current display data)

**Baseline Metrics (Before Test):**
- [ ] Record current movie count in data.json: `jq '.count' data.json`
- [ ] Record last update timestamp in movie_tracking.json: `jq '.last_update' movie_tracking.json`
- [ ] Record current data.json file size: `ls -lh data.json`
- [ ] Create backup: `cp data.json data.json.backup && cp movie_tracking.json movie_tracking.json.backup`

## Phase 1: Discovery & Monitoring Test

**Command (DEPRECATED):** `python3 movie_tracker.py daily`
**Production Command:** `python3 generate_data.py --discover`

⚠️ **IMPORTANT:** The legacy `movie_tracker.py` has been moved to `museum_legacy/legacy_movie_tracker.py`. The production system now uses `generate_data.py --discover` for discovery.

**Expected Behavior (Production):**
- Prints "🔍 Running discovery for new premieres..."
- Uses config.yaml discovery settings (days_back: 7, max_pages: 10)
- Implements bounded timeouts and retry logic for TMDB API calls
- Provides structured diagnostics with per-page logging
- Shows discovery statistics (pages fetched, total results, new movies added, duplicates skipped)
- Updates movie_tracking.json with new data
- Prints "✅ Discovery complete: [N] new movies added"
- Execution time: 30 seconds to 2 minutes depending on API responses

**Verification Steps:**
- [ ] Command completes without errors (exit code 0)
- [ ] Output shows "New premieres discovered: [N]" (may be 0 if no new releases)
- [ ] Output shows "Newly digital: [N]" (may be 0 if no status changes)
- [ ] Output shows "Total tracking: [N]" and "Total available: [N]"
- [ ] Check movie_tracking.json was updated: `jq '.last_update' movie_tracking.json` (should be current timestamp)
- [ ] Verify new movies added: `jq '.movies | length' movie_tracking.json`

**Success Criteria:**
- Script completes without Python exceptions
- movie_tracking.json timestamp is updated
- Summary statistics are reasonable (tracking + available = total movies)

**Failure Scenarios:**
- TMDB API errors (check API key in config.yaml)
- Network connectivity issues
- JSON parsing errors (corrupted database)
- Rate limiting (too many API calls)

**Document:**
- New premieres count: _______
- Newly digital count: _______
- Total tracking: _______
- Total available: _______
- Execution time: _______
- Any errors/warnings: _______

## Phase 2: Data Enrichment Test

**Command:** `python3 generate_data.py`

**Expected Behavior:**
- Runs in incremental mode (default) - only processes NEW movies not in data.json
- Loads configuration from config.yaml
- Initializes RT scraper (Selenium WebDriver)
- Processes movies with digital_date within last 90 days
- Resolves Wikipedia links via REST API
- Resolves trailer links from TMDB or YouTube scraper cache
- Resolves RT links and scores via scraper (with 2-second rate limiting)
- Resolves watch links via Watchmode API cache (agent scraper disabled per config.yaml)
- Applies admin overrides from admin/hidden_movies.json and admin/featured_movies.json
- Validates watch links schema
- Saves enriched data to data.json
- Prints detailed statistics (Wikidata queries, Watchmode API hits, RT scrapes, admin overrides)
- Execution time: 30 seconds to 5 minutes depending on new movies count

**Verification Steps:**
- [ ] Command completes without errors (exit code 0)
- [ ] Output shows "Loading configuration from config.yaml"
- [ ] Output shows "Initializing RT scraper" (if RT scraping enabled)
- [ ] Output shows "🎬 Processing NEW/ALL movies that went digital in last [N] days..."
- [ ] Output shows statistics: "Wikidata queries: [N]", "Watchmode API hits: [N]", "RT scrapes: [N]"
- [ ] Output shows "📝 Admin overrides applied:" with "Hidden movies: [N]" and "Featured movies: [N]"
- [ ] Output shows "🔍 Schema Validation:" with "Validation passes: [N]" and "Validation warnings: [N]"
- [ ] Output shows "Validation pass rate: [X]%" (if validations > 0)
- [ ] May show "⚠️ WARNING: High validation failure rate" alert (if warnings > 5%)
- [ ] Check data.json was updated: `ls -l data.json` (timestamp should be current)
- [ ] Verify movie count: `jq '.count' data.json` (should be 200+)
- [ ] Check generation timestamp: `jq '.generated_at' data.json`

**Success Criteria:**
- Script completes without Python exceptions
- data.json is updated with current timestamp
- Movie count is at least 200 (per validation threshold)
- Watch links schema validation passes for most movies
- RT scraper completes without excessive failures

**Failure Scenarios:**
- Selenium WebDriver not found (RT scraper initialization fails)
- Watchmode API cache missing (first run may have no cached links)
- Wikipedia REST API timeouts
- RT scraping blocked by anti-bot measures
- JSON schema validation failures (malformed watch links)

**Document:**
- Movies processed: _______
- Wikidata queries: _______
- Watchmode API hits: _______
- RT scrapes: _______
- Admin overrides (hidden/featured): _______
- Watch links validation (passed/warnings): _______
- Final movie count in data.json: _______
- Execution time: _______
- Any errors/warnings: _______

## Phase 3: Data Quality Validation

**Command 1:** `python3 ops/health_check.py`

**Expected Behavior:**
- Checks movie_tracking.json exists and is recent (updated within 2 days)
- Checks data.json exists and has at least 10 movies
- Checks cache/ directory exists
- Validates watch links schema in data.json (checks for malformed URLs, missing fields)
- Prints "✅ System healthy" if all checks pass
- Prints specific issues if problems found ("❌" for critical, "⚠️" for warnings)
- Exits with code 0 if healthy, code 1 if critical failures

**Verification Steps:**
- [ ] Command completes (check exit code: `echo $?`)
- [ ] Output shows "✅ System healthy" OR lists specific issues
- [ ] If issues found, review each one:
  - "❌ No tracking database found" - Critical: movie_tracking.json missing
  - "⚠️ Database stale: last updated [date]" - Warning: tracker hasn't run recently
  - "❌ No display data found" - Critical: data.json missing
  - "⚠️ Only [N] movies in display" - Warning: fewer than 10 movies
  - "❌ Cache directory missing" - Critical: cache/ directory not found
  - "❌ High validation failure rate: [%]" - Critical: >5% of movies have malformed watch links
  - "⚠️ Validation warnings: [%]" - Warning: Some movies have watch link issues

**Success Criteria:**
- Exit code 0 (healthy)
- All checks pass with "✅ System healthy"
- OR only warnings ("⚠️"), no critical failures ("❌")

**Command 2: Manual Data Quality Inspection**

**Verify Movie Count:**
```bash
jq '.count' data.json
```
Expected: 200+ movies (per daily_orchestrator.py validation threshold)

**Verify Recent Movies (Last 7 Days):**
```bash
jq --arg cutoff "$(date -v-7d +%Y-%m-%d)" '[.movies[] | select(.digital_date >= $cutoff)] | length' data.json
```
Expected: At least 1 movie (ensures discovery is working)

**Verify Required Fields (Sample Check):**
```bash
jq '.movies[0:5] | .[] | {title, digital_date, poster, rt_score, watch_links}' data.json
```
Expected: All movies have title, digital_date, poster; rt_score and watch_links may be null

**Verify Watch Links Coverage:**
```bash
jq '[.movies[] | select(.watch_links.streaming.link != null or .watch_links.rent.link != null or .watch_links.buy.link != null)] | length' data.json
```
Expected: Significant percentage have at least one watch link (exact % depends on Watchmode API coverage)

**Verify RT Scores Coverage:**
```bash
jq '[.movies[] | select(.rt_score != null)] | length' data.json
```
Expected: Some movies have RT scores (RT scraper is enabled per config.yaml)

**Verify Wikipedia Links Coverage:**
```bash
jq '[.movies[] | select(.wikipedia_link != null)] | length' data.json
```
Expected: High percentage have Wikipedia links (REST API is reliable)

**Verify Trailer Links Coverage:**
```bash
jq '[.movies[] | select(.trailer_link != null)] | length' data.json
```
Expected: High percentage have trailer links (TMDB provides trailers)

**Document:**
- Health check exit code: _______
- Health check output: _______
- Total movies: _______
- Recent movies (last 7 days): _______
- Movies with watch links: _______ (____%)
- Movies with RT scores: _______ (____%)
- Movies with Wikipedia links: _______ (____%)
- Movies with trailer links: _______ (____%)
- Any data quality issues: _______

## Phase 4: Admin Panel Testing

**Command:** `python3 admin.py`

**Expected Behavior:**
- Flask app starts on port 5555
- Prints startup info: "Running on http://127.0.0.1:5555"
- Prints "Press CTRL+C to quit"
- Requires HTTP Basic Auth (username: `admin`, password: `changeme`)
- Serves admin panel UI with movie cards, inline editing, hide/show/feature controls

**Verification Steps:**

**1. Start Admin Panel:**
- [ ] Run `python3 admin.py` in terminal
- [ ] Verify output shows "Running on http://127.0.0.1:5555"
- [ ] Keep terminal open (Flask runs in foreground)

**2. Access Admin Panel:**
- [ ] Open browser to `http://localhost:5555`
- [ ] Verify HTTP Basic Auth prompt appears
- [ ] Enter username: `admin`, password: `changeme`
- [ ] Verify authentication succeeds and admin panel loads

**3. Test UI Features:**
- [ ] **Movie Display:** Verify movie cards render with posters, titles, dates
- [ ] **Statistics:** Check header shows total movies count
- [ ] **Missing Data Detection:** Click "⚠️ Missing Data" button (if present)
  - Verify incomplete movies are highlighted with red borders
  - Verify "⚠️ INCOMPLETE" badges appear
  - Verify pink boxes list missing fields (RT Score, Trailer, Poster, Director, Country)
- [ ] **Inline Editing:** Test editing a movie field:
  - Find a movie with missing RT score
  - Enter a test value (e.g., 75)
  - Click "💾 Save All Changes" button
  - Verify success message appears
  - Verify movie_tracking.json is updated with `manual_rt_score: true` flag
- [ ] **Hide/Show Toggle:** Test hiding a movie:
  - Click "Hide" button on a movie card
  - Verify button changes to "Show"
  - Verify admin/hidden_movies.json is updated
- [ ] **Feature Toggle:** Test featuring a movie:
  - Click "Feature" button on a movie card
  - Verify button state changes
  - Verify admin/featured_movies.json is updated
- [ ] **Regenerate Button:** Click "🔄 Regenerate data.json" button
  - Verify subprocess starts (may take 30-60 seconds)
  - Verify success/error message appears
  - Verify data.json timestamp is updated

**4. Test Authentication:**
- [ ] Open new incognito/private browser window
- [ ] Navigate to `http://localhost:5555`
- [ ] Try wrong password - verify access denied
- [ ] Try correct credentials - verify access granted

**5. Stop Admin Panel:**
- [ ] Return to terminal running Flask
- [ ] Press CTRL+C to stop server
- [ ] Verify clean shutdown

**Success Criteria:**
- Flask app starts without errors
- Authentication works correctly
- All UI features render properly
- Inline editing saves to movie_tracking.json
- Hide/show/feature toggles update admin JSON files
- Regenerate button triggers generate_data.py successfully

**Failure Scenarios:**
- Port 5555 already in use (another process running)
- Flask import errors (dependencies not installed)
- Authentication fails (environment variables override default credentials)
- File permission errors (can't write to admin/ directory)
- Regenerate subprocess fails (generate_data.py errors)

**Document:**
- Admin panel started successfully: Yes/No
- Authentication tested: Yes/No
- UI features tested: _______
- Inline editing tested: Yes/No
- Hide/show toggle tested: Yes/No
- Feature toggle tested: Yes/No
- Regenerate button tested: Yes/No
- Any errors/issues: _______

## Phase 5: Complete Pipeline Test (Optional)

**Purpose:** Verify the complete end-to-end workflow as it runs in automation

**Command:** `python3 daily_orchestrator.py`

**Expected Behavior:**
- Runs production pipeline: generate_data.py --discover → generate_data.py → validation
- Prints "🚀 NRW Daily Update - [timestamp]"
- Executes each step with progress indicators
- Validates RT data (checks sample of movies for RT scores)
- Validates data quality (minimum 200 movies, recent movies check, required fields)
- Prints comprehensive summary with statistics
- Does NOT commit/push (git operations only in CI environment)
- Execution time: 3-10 minutes

**Verification Steps:**
- [ ] Command completes without errors
- [ ] Output shows "📍 Discover new premieres using production discovery..."
- [ ] Output shows "✅ Discover new premieres using production discovery complete"
- [ ] Output shows "📍 Generate data.json for website..."
- [ ] Output shows "✅ Generate data.json for website complete"
- [ ] Output shows "🔍 Validating RT data..."
- [ ] Output shows "✅ RT validation: [N]/[N] movies have RT data" OR "⚠️ Warning: No RT data found"
- [ ] Output shows "🔍 Validating data quality..."
- [ ] Output shows "✅ Quality check passed: [N] total, [N] recent"
- [ ] Output shows data coverage statistics (watch links, RT scores, Wikipedia, trailers)
- [ ] Output shows "📊 SUMMARY" with final statistics
- [ ] Output shows "✨ Daily update complete!"

**Success Criteria:**
- Orchestrator completes without exceptions
- All pipeline steps succeed (✅)
- Data quality validation passes
- Summary shows reasonable statistics

**Document:**
- Orchestrator completed: Yes/No
- New premieres discovered: _______
- Newly digital: _______
- Movies processed by generate_data.py: _______
- Data quality validation: Pass/Fail
- Final statistics: _______
- Execution time: _______
- Any errors/warnings: _______

## Post-Test Analysis

**Compare Before/After Metrics:**
- [ ] Movie count change: Before _______ → After _______
- [ ] movie_tracking.json last_update: Before _______ → After _______
- [ ] data.json file size: Before _______ → After _______
- [ ] New movies added to tracking: _______
- [ ] Movies transitioned to digital: _______

**Review Generated Files:**
- [ ] Check if any new cache files created in cache/ directory
- [ ] Check if rt_cache.json was updated (if RT scraping ran)
- [ ] Check if wikipedia_cache.json was updated
- [ ] Check if admin override files were modified

**Restore Backups (If Needed):**
If test caused issues and you want to revert:
```bash
cp data.json.backup data.json
cp movie_tracking.json.backup movie_tracking.json
```

## Test Report Summary

**Overall Status:** ✅ Pass / ⚠️ Pass with Warnings / ❌ Fail

**Phase Results:**
- Phase 1 (Discovery & Monitoring): _______
- Phase 2 (Data Enrichment): _______
- Phase 3 (Quality Validation): _______
- Phase 4 (Admin Panel): _______
- Phase 5 (Complete Pipeline): _______

**Critical Issues Found:** _______

**Warnings/Minor Issues:** _______

**Recommendations:** _______

**Next Steps:** _______

Reference files:
- `generate_data.py` - Production discovery, data enrichment and link resolution
- `daily_orchestrator.py` - Pipeline coordinator with validation
- `museum_legacy/legacy_movie_tracker.py` - ARCHIVED legacy discovery system (historical reference only)
- `ops/health_check.py` - System health validator
- `admin.py` - QA panel on port 5555
- `config.yaml` - Configuration (discovery section, agent scraper disabled, RT scraper enabled)
- `metrics/daily.jsonl` - Daily discovery and newly-digital metrics
- `scripts/baseline_metrics.py` - 3-day baseline computation
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Complete workflow documentation