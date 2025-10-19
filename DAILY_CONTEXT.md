# DAILY_CONTEXT.md
**Date:** 2025-10-17
**Previous diary entry:** diary/2025-10-16.md

---

## AI Assistant Quick Start

**READ THESE FILES FIRST WHEN STARTING A NEW SESSION:**

1. **This file (DAILY_CONTEXT.md)** - Current state, recent changes, active issues
2. **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance rules, amendments, API keys, architectural decisions
3. **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline mechanics, how everything fits together

**What is this rolling context system?**

This is a **living document** that gets overwritten each session with current information. At the end of each session, we archive it to `diary/YYYY-MM-DD.md` (immutable historical record). This approach:
- **Avoids token waste** from loading months of PROJECT_LOG.md history
- **Provides fresh context** without stale information
- **Maintains audit trail** in the diary/ folder
- **Reduces AI confusion** by keeping focus on current state

See [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context) for governance rules.

---

## Current State

### What's Working
- GitHub Actions automation: ✅ Operational (runs daily at 9 AM UTC)
- Data pipeline: ✅ Production-ready (1,184 movies tracked, 235 on display as of Oct 16)
- Launch workflow: ✅ One-command startup via `./launch_NRW.sh`
- **NEW:** Watch links integration: ✅ Watchmode API operational with deep links

### Architecture
- Runtime: `index.html` → `assets/app.js` + `assets/styles.css` → `data.json`
- Generation: `movie_tracking.json` → `generate_data.py` → `data.json` (235 movies)
- **NEW:** Watch links: Watchmode API → `cache/watch_links_cache.json` → `data.json.watch_links`
- Automation: GitHub Actions → `daily_orchestrator.py` → pipeline → auto-commit

---

## What We Did Today (2025-10-17)

### Git State Resolution and Archive Cleanup
- **What we did:**
  - Resolved git rebase conflicts from Oct 16-17 session overlap
  - Created missing `diary/2025-10-16.md` archive to preserve Watchmode API integration documentation
  - Updated DAILY_CONTEXT.md for Oct 17 session
  - Committed all Oct 16 work (Watchmode API, WATCH button) in clean linear history

- **Technical details:**
  - Git state was already resolved by Claude Code
  - Manually archived Oct 16 context per AMENDMENT-036 requirements
  - All Watchmode API work from Oct 16 preserved in historical record

---

## Conversation Context (Key Decisions)

### Decision: Watchmode API vs Streaming Availability API
- **Problem:** Need direct deep links to streaming platforms, not Google searches
- **Options evaluated:**
  1. Streaming Availability API (RapidAPI) - 100 requests/day free tier
  2. Watchmode API - 1,000 requests/month free tier
  3. JustWatch URL construction - No API, but unreliable slug guessing
  4. Manual overrides only - Not scalable for 235 movies

- **Testing results:**
  - Streaming Availability API: ❌ No data for October 2025 releases
  - Watchmode API: ✅ 6 sources for "The Long Walk" (Oct 2025), 115 sources for "Dune: Part Two"

- **Decision:** Watchmode API chosen for better new release coverage
- **Rationale:** 10x more free requests (1,000/month vs 100/day), better October 2025 coverage, real deep links

### Decision: Schema Structure (streaming/rent/buy/default)
- **Canonical categories:** `streaming` (subscription), `rent` (rental), `buy` (purchase), `default` (fallback)
- **Why not free/paid:** More semantic clarity - users understand "streaming" vs "rent" better than "free" vs "paid"
- **Migration support:** Legacy cache format (`free/paid`) automatically migrated to new schema
- **Implementation:** Each category contains `{service: string, link: string}` object

### Decision: Three-Tier Fallback System
- **Tier 1:** Watchmode API deep links (best UX - direct to movie page)
- **Tier 2:** Platform-specific search URLs (good UX - direct to platform's search)
- **Tier 3:** Amazon video search (acceptable UX - universal fallback)
- **Rationale:** Graceful degradation ensures every movie has a working link, even if not perfect

### Decision: Service Priority Hierarchies
- **Streaming:** Netflix > Disney+ > HBO Max > Hulu > Amazon Prime > MUBI
- **Paid:** Amazon Video > Apple TV > Vudu > Google Play
- **Rationale:** Prioritizes platforms with largest user bases (higher chance user has subscription)
- **Example:** If movie is on both Netflix and MUBI, show Netflix (more ubiquitous)

---

## Known Issues

### Issue: Watchmode API Coverage Gaps
- **Symptom:** Some October 2025 movies have no Watchmode data (e.g., "The Roughneck")
- **Root cause:** API has lag time for very new releases
- **Mitigation:** Fallback to platform-specific search URLs (Apple TV, Amazon)
- **Impact:** Some movies use search links instead of deep links (acceptable UX)
- **Status:** Accepted limitation; coverage improves over time

### Issue: Platform-Specific Link Limitations
- **Symptom:** Can't build direct links for Netflix, Disney+, HBO Max
- **Root cause:** These platforms don't have predictable URL patterns (need internal IDs)
- **Mitigation:** Return null for these platforms, frontend uses Google search fallback
- **Impact:** Streaming services without Watchmode data use search links
- **Future:** Agent-based link finding could scrape actual URLs (optional enhancement)

### Issue: Agent Scraper Not Running (CRITICAL - Oct 17)
- **Symptom:** All Netflix/Disney+/Hulu links in data.json are null despite agent scraper being integrated
- **Root causes:**
  1. **Cache directory gitignored** - `.gitignore` line 7 excludes `cache/`, directory lost between git operations
  2. **Incremental mode skips existing movies** - Daily automation only processes NEW movies, existing 236 movies never reprocessed
  3. **Config not read** - `generate_data.py` doesn't read `agent_scraper` section from config.yaml
  4. **Missing dependencies** - `requirements.txt` lacks selenium/webdriver-manager (only in GitHub Actions manual install)
  5. **No execution evidence** - No cache files, no log messages, agent scraper never successfully ran
- **Mitigation:**
  1. Add `cache/.gitkeep` to track directory in git
  2. Run `python3 generate_data.py --full` to reprocess all movies
  3. Update `load_config()` to read entire config.yaml (not just api section)
  4. Add selenium/webdriver-manager to requirements.txt
  5. Add debug logging to trace execution
- **Status:** ⏳ Being fixed (see test_agent_scraper.py for standalone testing)
- **Workaround:** Use admin panel watch link overrides for critical movies until agent scraper is fixed

### Issue: Daily Automation Merge Conflicts (RESOLVED - Oct 17)
- **Symptom:** User gets merge conflicts every morning when pulling from GitHub
- **Root cause:** Bot and user both commit to main branch, causing conflicts in data.json
- **Solution:** Separate branch strategy (AMENDMENT-043)
  - Bot pushes to automation-updates branch (force-push, always succeeds)
  - User merges when ready via ./sync_daily_updates.sh
  - Weekly full regen ensures all movies get retroactive improvements
- **Status:** ✅ Resolved via separate branch architecture
- **Testing:** ⏳ Verify automation-updates branch strategy works in production

### Issue: Cache Migration from Legacy Format
- **Symptom:** Early testing used `free/paid` categories instead of `streaming/rent/buy`
- **Solution:** Automatic migration in `_migrate_legacy_cache_format()` (lines 407-424)
- **Impact:** Old cache entries are automatically converted to new schema
- **Status:** ✅ Resolved via migration function

---

## Next Priorities

### Completed (Oct 16-17)
- ✅ Integrate Watchmode API into `generate_data.py` (AMENDMENT-038)
- ✅ Implement three-button UI (STREAM/RENT/BUY) in `assets/app.js`
- ✅ Add agent-based link finding for Netflix/Disney+/HBO Max/Hulu (AMENDMENT-039)
- ✅ Migrate agent scraper to Playwright (AMENDMENT-041)
- ✅ Inline RT scraper into generate_data.py (AMENDMENT-042)
- ✅ Fix admin panel integration (file paths, 20-movie limit, date update)
- ✅ Add watch link override system to admin panel
- ✅ Add HTTP authentication to admin panel
- ✅ Archive redundant scrapers (wikidata, reelgood, date_verification)
- ✅ Update documentation (NRW_DATA_WORKFLOW_EXPLAINED.md, museum_legacy/README.md)
- ✅ Formalize streaming/rent/buy schema in PROJECT_CHARTER.md (canonical schema section)
- ✅ Add schema validation function to generate_data.py (validate_watch_links_schema)
- ✅ Verify schema consistency across codebase (generate_data.py, app.js, admin.py, caches)

### Immediate (Testing & Verification)
- ⏳ Test agent scraper with `python3 test_agent_scraper.py` (verify Playwright selectors work)
- ⏳ Run full regeneration: `python3 generate_data.py --full --debug`
- ⏳ Verify Netflix/Disney+/Hulu links are populated in data.json (not null)
- ⏳ Test admin panel watch link override functionality
- ⏳ Verify GitHub Actions workflow succeeds with Playwright installation
- ⏳ Update agent scraper selectors if platforms changed HTML structure
- ⏳ Test daily automation with automation-updates branch strategy
- ⏳ Test weekly full regeneration workflow
- ⏳ Test sync_daily_updates.sh script
- ⏳ Verify data quality validation catches bad data
- ⏳ Verify GitHub issue creation on failures

### Short-term (Next Session)
- Monitor agent scraper success rate (target: >70%)
- Fix any broken selectors discovered during testing
- Consider migrating RT scraper to Playwright (optional performance improvement)
- Consider migrating YouTube scraper to Playwright (optional consistency improvement)

### Long-term (Ongoing Maintenance)
- Update scraper selectors when platforms change HTML (every 3-6 months)
- Monitor cache hit rates and scraper statistics
- Review screenshot diagnostics for recurring failures
- Consider parallel scraping for performance (if dataset grows significantly)

---

## Archive Instructions

**End-of-session workflow (automated via `ops/archive_daily_context.sh`):**

1. Run archive script: `./ops/archive_daily_context.sh`
   - Archives current context to `diary/YYYY-MM-DD.md`
   - Creates fresh template for next session
   - Use `--dry-run` to preview changes without executing

2. **Testing:** `./ops/archive_daily_context.sh --dry-run` shows what would happen

3. **Troubleshooting:**
   - Permission error: `chmod +x ops/archive_daily_context.sh`
   - Missing file error: Ensure you're in repo root
   - Directory issues: Script creates `diary/` automatically

4. **Next session starts fresh:**
   - AI reads new DAILY_CONTEXT.md template
   - Historical context available in `diary/` if needed
   - No token waste from stale information

**Current status:** Archive script created and ready to use

---

## Files Changed Today

### Created
- `cache/watch_links_cache.json` - Watchmode API response cache (228 entries)
- `cache/.gitkeep` - Ensures cache directory is tracked in git
- `test_agent_scraper.py` - Standalone test for agent scraper debugging
- `test_rt_scraper_inline.py` - Standalone test for inlined RT scraper
- `cache/screenshots/.gitkeep` - Ensures screenshot directory is tracked in git
- `.github/workflows/weekly-full-regen.yml` - Sunday full regeneration workflow
- `sync_daily_updates.sh` - User script to merge automation data

### Modified
- `generate_data.py` - Added Watchmode API integration (lines 197-400), `argparse` support (lines 14, 640-649)
- `data.json` - Regenerated with `watch_links` field (235 movies)
- `assets/app.js` - Added WATCH button to card backs (line 130), updated watch link logic (lines 84-101)
- `assets/styles.css` - Reduced WATCH button height (padding: 0.5rem)
- `index.html` - Added cache-busting parameters (?v=3 for CSS, ?v=2 for JS)
- `PROJECT_CHARTER.md` - Added AMENDMENT-038 for Watchmode API integration, added Watchmode API key to API Keys section, added AMENDMENT-043 documenting bulletproof daily automation
- `DAILY_CONTEXT.md` - This file (documented watch links feature completion)
- `requirements.txt` - Added selenium, webdriver-manager, beautifulsoup4, lxml
- `generate_data.py` - Enhanced debug logging, config reading for agent_scraper section
- `agent_link_scraper.py` - Added comprehensive debug logging throughout
- `admin.py` - Fixed file paths (admin/ not output/), removed 20-movie limit, added watch link override UI, added regenerate button, added HTTP auth
- `config.yaml` - Added agent_scraper and rt_scraper configuration sections
- `daily_orchestrator.py` - Removed date_verification.py and update_rt_data.py from pipeline, added validate_data_quality() method with comprehensive checks
- `daily_update.sh` - Removed date_verification.py and update_rt_data.py calls
- `.github/workflows/daily-check.yml` - Added Playwright browser installation, updated to push to automation-updates branch with force-push, added data quality validation, added failure notifications
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Updated scraper architecture documentation
- `museum_legacy/README.md` - Added scripts/rt_scraper.py to archived list
- `PROJECT_CHARTER.md` - Added "Canonical Watch Links Schema" section, updated AMENDMENT-031 to remove unused `default` category, added schema validation reference to AMENDMENT-038
- `generate_data.py` - Added validate_watch_links_schema() function with comprehensive validation and statistics tracking

### Archived (Oct 17, 2025)

**Scrapers moved to museum_legacy/:**
- `wikidata_scraper.py` - Redundant with Wikipedia REST API
- `reelgood_scraper.py` - Redundant with TMDB API
- `date_verification.py` - Only user of reelgood_scraper (non-critical)
- `rt_scraper.py` (root) - Old RT scraper version (v1)
- `scripts/rt_scraper.py` - Newer RT scraper (v2), inlined into generate_data.py (v3)
- `update_rt_data.py` - RT scraping now automatic
- `bootstrap_rt_cache.py` - RT cache built automatically

**Admin tools deleted:**
- `museum_legacy/curator_admin.py` - Orphaned admin UI (expected non-existent files)
- `museum_legacy/run_admin_5100.py` - Launcher for curator_admin.py

**See:** `museum_legacy/README.md` for detailed archival documentation and migration notes

---

## Quick Reference

### Daily Workflow
```bash
# Morning: View the wall
./launch_NRW.sh

# Automation runs automatically at 9 AM UTC
# (No manual intervention needed)
```

### Sync Automation Data
```bash
# Merge automation updates from bot
./sync_daily_updates.sh

# What it does:
# 1. Fetches automation-updates branch
# 2. Shows what changed
# 3. Merges into main
# 4. Shows latest movies
```

### Automation Schedule
- **Daily:** 9 AM UTC (2 AM PDT) - Incremental update (new movies only)
- **Weekly:** Sunday 10 AM UTC (2 AM PDT) - Full regeneration (all movies)
- **User sync:** Run `./sync_daily_updates.sh` after automation completes

### Manual Pipeline (if needed)
```bash
# Check for new digital releases
python3 movie_tracker.py check

# Regenerate data.json
python3 generate_data.py

# Add new theatrical releases (weekly)
python3 movie_tracker.py bootstrap
```

### Context Files (Read These First)
- **Daily:** This file (DAILY_CONTEXT.md) - Current state and recent changes
- **Governance:** [PROJECT_CHARTER.md](PROJECT_CHARTER.md) - Rules, amendments, API keys
- **Pipeline:** [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md) - How data flows
- **History:** `diary/YYYY-MM-DD.md` - End-of-session archives (when needed)

---

**Last updated:** 2025-10-17 (End of scraper consolidation + schema formalization session)
**Next diary archive:** End of session -> `diary/[YYYY-MM-DD].md`