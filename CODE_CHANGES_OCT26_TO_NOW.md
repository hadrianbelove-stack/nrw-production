# Code Changes Analysis: Oct 26 (Working) → Nov 5 (Broken)

**Baseline:** Commit `1eebb28` - Oct 26, 2025 - Daily update working
**Current:** Commit `7fa9ea9` - Nov 5, 2025 - Daily update broken since Oct 27

---

## ROOT CAUSE IDENTIFIED

**The Breaking Change:** Discovery code sets `digital_date` immediately instead of `None`
- **File:** `generate_data.py` line 2080
- **When:** Part of "Discovery System Consolidation" (commit d2e1162, Oct 23)
- **Impact:** 181 movies stuck in `status='tracking'` with `digital_date` set but `providers={}` empty

---

## DETAILED FILE CHANGES

### 1. **generate_data.py** ⚠️ CRITICAL

**Changes that BROKE monitoring:**
- Discovery was refactored into `_run_discovery_pass()` method
- Line 2075-2080: Discovery now sets `digital_date` from TMDB's `release_date`/`primary_release_date`
  ```python
  # BROKEN (current):
  'digital_date': digital_date,  # ← Sets theatrical release date!

  # CORRECT (should be):
  'digital_date': None,  # ← Wait for monitoring to set it
  ```

**Changes that are GOOD:**
- Wikipedia scraper migrated to Playwright (better reliability)
- RT scraper improvements
- Agent scraper cache improvements
- Validation improvements (schema checking, corrupted file handling)

**Discovery Structure Change:**
- Oct 26: Used standalone discovery logic
- Now: Uses `_run_discovery_pass()` with Pass A (digital) and Pass B (theatrical)
- Creates movies with fields: `title`, `status`, `first_seen`, `digital_date`, `providers`, `discovery_pass`

**Line Count:**
- Added: ~400 lines (new methods, validation, Wikipedia scraper)
- Removed: ~200 lines (inline Wikipedia REST API logic)

---

### 2. **daily_orchestrator.py** ✅ IMPROVED

**All changes are GOOD:**
- Softened fatal validation checks (Nov 5, commit 7fa9ea9)
  - Provider coverage: Fatal → Warning
  - Minimum movie count: Fatal (< 200) → Warning (< 50)
  - No recent movies: Fatal → Warning
  - Missing digital_date: Fatal → Warning
- Extended recent movies window: 7 days → 14 days
- Added schema validation for data.json
- Better error handling for corrupted data

**These changes FIXED validation issues but didn't fix discovery bug**

---

### 3. **agent_link_scraper.py** ✅ NO BREAKING CHANGES

**Changes:**
- Cache schema changed to per-service structure (commit 98eac06, Nov 1)
  ```python
  # Old: streaming: {link, service}
  # New: streaming: {netflix: {link, ...}, disney: {link, ...}}
  ```
- Backward compatibility migration added
- Better error handling
- No functional breakage

**Scraper Status:** Working perfectly (98.8% success rate on Oct 26, unchanged since)

---

### 4. **streaming_platform_scraper.py** ✅ MINOR FIXES

**Changes:**
- Removed redundant `self.manager = get_playwright_manager()` in cleanup (Nov 5)
- No breaking changes

---

### 5. **tests/test_agent_scraper_improvements.py** ✅ TEST FIXES (archived)

**Changes:**
- Fixed `find_watch_link()` calls to include `movie_id` parameter (Nov 5)
- Test-only changes, no production impact

---

### 6. **youtube_playlist_manager.py** ⚠️ AUTH FIX

**Changes:**
- Auth command now actually calls `_ensure_client()` to trigger OAuth (Nov 5)
- RT score comparison bug fix (Oct 27)
- No impact on daily pipeline

---

### 7. **movie_tracking.json** 📊 DATA CHANGES

**Status:**
- Oct 26: ~1,400 movies with proper structure
- Now: ~3,000 movies total
  - 2,664 in `status='tracking'`
  - 330 in `status='available'`
  - **181 with `digital_date` set but `providers={}` empty** ← THE PROBLEM

---

### 8. **data.json** 📊 OUTPUT DATA

**Status:**
- Oct 26: ~320 movies (all properly enriched)
- Now: 169 movies (stuck with old data from Oct 26)
- **No new movies added since Oct 26** because they're stuck in `status='tracking'`

---

### 9. **Workflow Files** ✅ IMPROVEMENTS

**.github/workflows/daily-check.yml:**
- Added enrichment pre-flight checks
- Better error handling
- More descriptive failure messages

**.github/workflows/youtube-playlists.yml:**
- Disabled due to Google account suspension (unrelated)

---

### 10. **New Files Added** 📁

**Documentation:**
- `CURRENT_WORKFLOW_STATUS.md` - Status tracking
- `YOUTUBE_WORKFLOW_DISABLED.md` - YouTube workflow docs
- `docs/AUTOMATION_BRANCH_WORKFLOW.md` - Branch workflow docs
- Multiple `museum_legacy/*.md` - Session summaries and analyses

**Scripts:**
- `scripts/encode_youtube_token.sh` - YouTube token helper
- `launch_site.sh` - Local development helper
- `close_issues.sh` - GitHub issue management
- `analyze_wiki_cache.py` - Cache analysis

**Tests:**
- `tests/test_agent_scraper_improvements.py` - Agent scraper tests (archived)
- `tests/test_amazon_scraper_fix.py` - Amazon scraper tests (archived)
- `tests/test_*.py` - Multiple archived debugging tests (see tests/README.md)

**Core Files:**
- `wikipedia_scraper_playwright.py` - NEW Playwright-based Wikipedia scraper
- `playwright_manager.py` - Shared Playwright singleton (fixes asyncio conflicts)

---

## COMMITS THAT MATTER

### Commits That Broke Things:
1. **d2e1162** (Oct 23) - "Discovery System Consolidation"
   - Introduced `digital_date` bug in discovery

### Commits That Fixed Other Issues:
1. **fb271c2** (Oct 26) - Playwright asyncio fix (singleton manager)
2. **50fa7c7** (Oct 26) - Async fix verification (98.8% scraper success)
3. **7fa9ea9** (Nov 5) - Softened fatal validations (allows pipeline to complete)
4. **98eac06** (Nov 1) - Agent scraper cache schema fix
5. **61d54ea** (Oct 28) - YouTube token corruption fix

### Commits That Are Just Documentation:
- 8bbf161, 1f8df72, 21ddb8c, a781a97 - Workflow documentation
- 7b1c6c3 - Root cause documentation (incomplete diagnosis)

---

## THE FIX

**One line change needed in generate_data.py line 2080:**

```python
# BEFORE (broken):
discovered_movies[movie_id] = {
    'title': title,
    'status': 'tracking',
    'first_seen': datetime.now().strftime('%Y-%m-%d'),
    'digital_date': digital_date,  # ← WRONG
    'providers': {},
    'discovery_pass': pass_name
}

# AFTER (fixed):
discovered_movies[movie_id] = {
    'title': title,
    'status': 'tracking',
    'first_seen': datetime.now().strftime('%Y-%m-%d'),
    'digital_date': None,  # ← CORRECT
    'providers': {},
    'discovery_pass': pass_name
}
```

**Why this fixes it:**
1. Discovery finds new movies → sets `digital_date=None`, `status='tracking'`
2. Monitoring (`--check`) checks TMDB daily for providers
3. When providers found → sets `digital_date=today`, `status='available'`
4. Enrichment runs on `status='available'` movies (line 2343)
5. Scrapers get called, watch links fetched

**Current broken flow:**
1. Discovery finds new movies → sets `digital_date=2025-10-24` (theatrical date), `status='tracking'`
2. Monitoring checks but movie already has `digital_date`, doesn't change anything
3. Movie stays `status='tracking'` forever because `providers={}` is still empty
4. Enrichment never runs (requires `status='available'`)
5. Scrapers never called

---

## SHOULD WE ROLL BACK?

**NO - Most changes are improvements. Only fix the one-line bug.**

**Keep these good changes:**
- Wikipedia Playwright scraper (more reliable)
- Validation improvements (better error handling)
- Agent scraper cache schema (prevents collisions)
- PlaywrightManager singleton (fixes asyncio)
- Softened validations (allows partial data)

**Fix only:**
- Line 2080 in generate_data.py: `'digital_date': digital_date,` → `'digital_date': None,`

---

## ADDITIONAL FIXES NEEDED

**After fixing line 2080, also need to:**

1. **Clear bad data from tracking DB** - 181 movies with wrong `digital_date`
   ```bash
   # These movies need digital_date reset to None
   # So monitoring can properly detect when they go live
   ```

2. **Verify monitoring runs daily** - Confirm `--check` is called by orchestrator

3. **Monitor for provider detection** - After fix, should see movies transition to `status='available'`

---

## STATISTICS

- **Total commits since Oct 26:** 31
- **Files changed:** 49
- **Lines added:** 32,206
- **Lines removed:** 13,685
- **Breaking changes:** 1 (the `digital_date` line)
- **Good improvements:** ~25 commits
- **Documentation:** ~5 commits
- **Time broken:** 10 days (Oct 27 - Nov 5)
- **Movies affected:** 181 stuck in limbo
- **Old movies in data.json:** 169 (stale since Oct 26)
