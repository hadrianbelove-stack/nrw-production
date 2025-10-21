# NRW Pipeline Test Report
**Date:** [YYYY-MM-DD]
**Tester:** [Your name]
**Test Duration:** [Start time] - [End time]
**Environment:** macOS / Linux / Windows
**Python Version:** [Output of `python3 --version`]

## Executive Summary

**Overall Status:** [✅ PASS / ⚠️ PASS WITH WARNINGS / ❌ FAIL]

**Key Findings:**
- [Bullet point summary of major findings]
- [Include both successes and failures]
- [Highlight any critical issues]

**Recommendation:** [Ready for automation / Needs fixes / Requires investigation]

---

## Test Environment

**Repository Location:** `/Users/hadrianbelove/Downloads/nrw-production`

**Dependencies Verified:**
```
Flask: [version]
requests: [version]
selenium: [version]
playwright: [version]
beautifulsoup4: [version]
PyYAML: [version]
```

**Configuration:**
- TMDB API Key: [Present/Missing]
- Agent Scraper: [Enabled/Disabled] (Expected: Disabled per config.yaml line 21)
- RT Scraper: [Enabled/Disabled] (Expected: Enabled per config.yaml line 35)
- Display Window: [N] days (Expected: 90 days per config.yaml line 7)

**Baseline Metrics (Before Test):**
- Movies in data.json: [N]
- Movies in movie_tracking.json: [N]
- Last tracking update: [timestamp]
- data.json file size: [size]

---

## Phase 1: Discovery & Monitoring Test

**Command Executed:** `python3 movie_tracker.py daily`

**Execution Time:** [MM:SS]

**Exit Code:** [0 = success, non-zero = failure]

**Output Summary:**
```
[Paste relevant output here]
```

**Results:**
- New premieres discovered: [N]
- Newly digital: [N]
- Total tracking: [N]
- Total available: [N]
- movie_tracking.json updated: [Yes/No]
- Last update timestamp: [timestamp]

**Status:** [✅ PASS / ❌ FAIL]

**Issues Found:**
- [List any errors, warnings, or unexpected behavior]
- [Or write "None" if everything worked]

**Notes:**
- [Any observations about performance, API responses, etc.]

---

## Phase 2: Data Enrichment Test

**Command Executed:** `python3 generate_data.py`

**Execution Time:** [MM:SS]

**Exit Code:** [0 = success, non-zero = failure]

**Output Summary:**
```
[Paste relevant output here]
```

**Results:**
- Movies processed: [N]
- Wikidata queries: [N]
- Watchmode API hits: [N]
- RT scrapes: [N]
- Admin overrides applied: [N] hidden, [N] featured
- Watch links validation: [N] passed, [N] warnings
- Final movie count in data.json: [N]
- data.json updated: [Yes/No]
- Generation timestamp: [timestamp]

**Status:** [✅ PASS / ❌ FAIL]

**Issues Found:**
- [List any errors, warnings, or unexpected behavior]
- [Note any scraper failures, API timeouts, validation warnings]

**Notes:**
- [Observations about link resolution success rates]
- [RT scraper performance]
- [Any cache hits/misses]

---

## Phase 3: Data Quality Validation

### Health Check Test

**Command Executed:** `python3 ops/health_check.py`

**Exit Code:** [0 = healthy, 1 = critical failure]

**Output:**
```
[Paste output here]
```

**Status:** [✅ PASS / ⚠️ WARNINGS / ❌ FAIL]

**Issues Found:**
- [List any critical failures (❌) or warnings (⚠️)]

### Manual Data Quality Inspection

**Movie Count Verification:**
- Total movies in data.json: [N]
- Expected minimum: 200
- Status: [✅ PASS / ❌ FAIL]

**Recent Movies Verification (Last 7 Days):**
- Recent movies found: [N]
- Expected minimum: 1
- Status: [✅ PASS / ❌ FAIL]

**Required Fields Verification (Sample of 5 movies):**
- All have title: [Yes/No]
- All have digital_date: [Yes/No]
- All have poster: [Yes/No]
- Status: [✅ PASS / ❌ FAIL]

**Link Coverage Analysis:**

| Link Type | Count | Percentage | Status |
|-----------|-------|------------|--------|
| Watch Links (any) | [N] | [%] | [✅/⚠️/❌] |
| RT Scores | [N] | [%] | [✅/⚠️/❌] |
| Wikipedia Links | [N] | [%] | [✅/⚠️/❌] |
| Trailer Links | [N] | [%] | [✅/⚠️/❌] |

**Expected Coverage:**
- Watch Links: Variable (depends on Watchmode API coverage)
- RT Scores: 30-50% (RT scraper enabled but not all movies have reviews)
- Wikipedia Links: 70-90% (REST API is reliable)
- Trailer Links: 80-95% (TMDB provides most trailers)

**Overall Data Quality Status:** [✅ PASS / ⚠️ ACCEPTABLE / ❌ FAIL]

**Issues Found:**
- [List any data quality concerns]
- [Note any unexpectedly low coverage percentages]

---

## Phase 4: Admin Panel Testing

**Command Executed:** `python3 admin.py`

**Flask Startup:** [✅ Success / ❌ Failed]

**Port:** 5555

**Authentication Test:**
- Correct credentials (admin/changeme): [✅ Success / ❌ Failed]
- Incorrect credentials: [✅ Properly rejected / ❌ Allowed access]

**UI Features Tested:**

| Feature | Tested | Status | Notes |
|---------|--------|--------|-------|
| Movie cards render | [Yes/No] | [✅/❌] | |
| Statistics display | [Yes/No] | [✅/❌] | |
| Missing data detection | [Yes/No] | [✅/❌] | |
| Inline editing | [Yes/No] | [✅/❌] | |
| Hide/Show toggle | [Yes/No] | [✅/❌] | |
| Feature toggle | [Yes/No] | [✅/❌] | |
| Regenerate button | [Yes/No] | [✅/❌] | |

**Inline Editing Test Details:**
- Movie edited: [Title]
- Field edited: [e.g., RT Score]
- Value entered: [e.g., 75]
- Save successful: [Yes/No]
- movie_tracking.json updated: [Yes/No]
- Manual flag set: [Yes/No] (Check for `manual_rt_score: true`)

**Hide/Show Toggle Test Details:**
- Movie hidden: [Title]
- admin/hidden_movies.json updated: [Yes/No]
- Movie ID added to array: [Yes/No]

**Feature Toggle Test Details:**
- Movie featured: [Title]
- admin/featured_movies.json updated: [Yes/No]
- Movie ID added to array: [Yes/No]

**Regenerate Button Test Details:**
- Button clicked: [Yes/No]
- Subprocess started: [Yes/No]
- Execution time: [seconds]
- Success message shown: [Yes/No]
- data.json timestamp updated: [Yes/No]

**Overall Admin Panel Status:** [✅ PASS / ❌ FAIL]

**Issues Found:**
- [List any UI bugs, functionality issues, or errors]

---

## Phase 5: Complete Pipeline Test (Optional)

**Command Executed:** `python3 daily_orchestrator.py`

**Execution Time:** [MM:SS]

**Exit Code:** [0 = success, non-zero = failure]

**Pipeline Steps:**

| Step | Status | Duration | Notes |
|------|--------|----------|-------|
| Discovery & Monitoring | [✅/❌] | [seconds] | |
| Data Enrichment | [✅/❌] | [seconds] | |
| RT Data Validation | [✅/⚠️/❌] | [seconds] | |
| Data Quality Validation | [✅/❌] | [seconds] | |

**Validation Results:**
- RT validation: [N]/[N] movies have RT data
- Quality check: [N] total movies, [N] recent
- Data coverage: [N] with watch links, [N] with RT scores
- Additional links: [N] Wikipedia, [N] trailers

**Summary Statistics:**
- Total tracked: [N]
- Still tracking: [N]
- Now digital: [N]
- Movies in data.json: [N]
- Watch links coverage: [N] ([%])
- RT scores coverage: [N] ([%])
- Wikipedia coverage: [N] ([%])
- Trailers coverage: [N] ([%])

**Overall Pipeline Status:** [✅ PASS / ❌ FAIL]

**Issues Found:**
- [List any pipeline failures or validation errors]

---

## Post-Test Analysis

**Before/After Comparison:**

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Movies in data.json | [N] | [N] | [+/-N] |
| Movies in tracking DB | [N] | [N] | [+/-N] |
| data.json file size | [size] | [size] | [+/-size] |
| Last tracking update | [time] | [time] | [duration] |

**New Files Created:**
- [List any new cache files, screenshots, or logs]

**Files Modified:**
- movie_tracking.json: [Yes/No]
- data.json: [Yes/No]
- rt_cache.json: [Yes/No]
- wikipedia_cache.json: [Yes/No]
- Admin override files: [Yes/No]

**Cache Performance:**
- RT cache hits: [N] / [N] lookups ([%])
- Wikipedia cache hits: [N] / [N] lookups ([%])
- Watchmode cache hits: [N] / [N] lookups ([%])

---

## Critical Issues Summary

**Blocking Issues (Must Fix Before Automation):**
1. [Issue description]
   - Impact: [How it affects the pipeline]
   - Root cause: [If known]
   - Recommended fix: [Suggested solution]

**Non-Blocking Issues (Can Deploy with Workarounds):**
1. [Issue description]
   - Impact: [How it affects the pipeline]
   - Workaround: [Temporary solution]
   - Recommended fix: [Long-term solution]

**Warnings (Monitor but Not Critical):**
1. [Issue description]
   - Impact: [Minor effects]
   - Action: [What to watch for]

---

## Performance Analysis

**Execution Times:**
- movie_tracker.py daily: [MM:SS]
- generate_data.py: [MM:SS]
- ops/health_check.py: [MM:SS]
- daily_orchestrator.py (if tested): [MM:SS]

**Bottlenecks Identified:**
- [e.g., RT scraping takes 2 seconds per movie due to rate limiting]
- [e.g., Wikipedia REST API occasionally times out]

**Optimization Opportunities:**
- [Suggestions for improving performance]

---

## Configuration Review

**Current Configuration (config.yaml):**
- Agent scraper enabled: [true/false] (Expected: false)
- RT scraper enabled: [true/false] (Expected: true)
- Display days back: [N] (Expected: 90)
- RT rate limit: [N] seconds (Expected: 2.0)
- RT cache TTL: [N] days (Expected: 90)

**Configuration Issues:**
- [List any misconfigurations or recommended changes]

**Recommended Changes:**
- [Suggest any config.yaml updates]

---

## Recommendations

**Immediate Actions:**
1. [Action item with priority]
2. [Action item with priority]

**Before Enabling Automation:**
1. [Prerequisite for GitHub Actions]
2. [Prerequisite for GitHub Actions]

**Future Improvements:**
1. [Enhancement suggestion]
2. [Enhancement suggestion]

---

## Conclusion

**Pipeline Readiness:** [✅ Ready for automation / ⚠️ Ready with caveats / ❌ Not ready]

**Summary:**
[2-3 paragraph summary of test results, key findings, and overall assessment]

**Next Steps:**
1. [Immediate next action]
2. [Follow-up action]
3. [Long-term action]

**Sign-off:**
- Tester: [Name]
- Date: [YYYY-MM-DD]
- Approved for automation: [Yes/No]

---

## Appendix: Raw Output Logs

### movie_tracker.py Output
```
[Paste full output here]
```

### generate_data.py Output
```
[Paste full output here]
```

### ops/health_check.py Output
```
[Paste full output here]
```

### daily_orchestrator.py Output (if tested)
```
[Paste full output here]
```

### Admin Panel Screenshots
[Attach screenshots of admin panel UI, if available]

---

**Reference Documentation:**
- `TEST_EXECUTION_PLAN.md` - Detailed test procedures
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Pipeline architecture
- `PROJECT_CHARTER.md` - Governance and specifications
- `daily_orchestrator.py` lines 92-138 - Data quality validation logic
- `ops/health_check.py` - System health checks
- `config.yaml` - Configuration settings