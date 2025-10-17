# DAILY_CONTEXT.md
**Date:** 2025-10-16
**Previous diary entry:** diary/2025-10-15.md

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

## What We Did Today (2025-10-16)

### Watchmode API Integration
- **What we built:**
  - Integrated Watchmode API for deep links to streaming platforms
  - Added `get_watch_links()` method to `generate_data.py` (lines 197-400)
  - Implemented two-step API process: search by TMDB ID → get streaming sources
  - Created cache system in `cache/watch_links_cache.json` with source type tracking
  - Added `watch_links` field to movie schema with canonical `streaming/rent/buy/default` structure
  - Implemented service priority hierarchies (Netflix > Disney+ > HBO Max for streaming)
  - Built three-tier fallback system: Watchmode deep links → platform search URLs → Amazon search
  - Added `argparse` support for `--full` flag to force regeneration
  - Added WATCH button to movie card backs in `assets/app.js`

- **Results:**
  - Successfully tested with October 2025 releases ("The Long Walk" returned 6 Amazon sources)
  - Full regeneration completed: 235 movies with watch_links field
  - API usage: 456 calls for full regeneration (45.6% of 1,000/month free tier)
  - Cache effectiveness: Prevents 13,380 unnecessary API calls/month
  - Watchmode success rate: High coverage for new releases

- **Technical details:**
  - API key: `bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp`
  - Free tier: 1,000 requests/month
  - Coverage: Better than Streaming Availability API for new releases
  - Statistics tracking: search_calls, source_calls, cache_hits, success rate

### Frontend WATCH Button
- Added WATCH button to movie card backs
- Button height: 0.5rem padding (half of original design)
- Current behavior: Uses `movie.watch_links` data with priority order (streaming → rent → buy → default)
- Cache-busting: Added `?v=3` to CSS and `?v=2` to JS in `index.html`
- Status: ✅ Backend complete, ⏳ Two-button UI pending (subsequent phase)

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

### Issue: Cache Migration from Legacy Format
- **Symptom:** Early testing used `free/paid` categories instead of `streaming/rent/buy`
- **Solution:** Automatic migration in `_migrate_legacy_cache_format()` (lines 407-424)
- **Impact:** Old cache entries are automatically converted to new schema
- **Status:** ✅ Resolved via migration function

---

## Next Priorities

### Immediate (This Session)
- ✅ Integrate Watchmode API into `generate_data.py`
- ✅ Add `argparse` support for `--full` flag
- ✅ Test full regeneration with watch links
- ✅ Add WATCH button to movie card backs
- ✅ Document Watchmode API integration in PROJECT_CHARTER.md (AMENDMENT-038)
- ✅ Update DAILY_CONTEXT.md with feature completion (this task)
- ⏳ Commit all changes to GitHub

### Next Phase
- Implement two-button UI ("WATCH FREE" + "RENT/BUY") in `assets/app.js`
- Test with Oct 16 movies: "A Woman with No Filter" (Netflix), "The Long Walk" (Amazon rent)
- Update CSS for two-button layout

### Subsequent Phase (Optional)
- Agent-based link finding for movies without Watchmode data
- Admin panel section for manual watch link overrides
- Performance optimization for large datasets

### Short-term (Next Few Days)
[Fill in during session - list near-term tasks]

### Long-term (Ongoing)
[Fill in during session - list ongoing maintenance tasks]

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

### Modified
- `generate_data.py` - Added Watchmode API integration (lines 197-400), `argparse` support (lines 14, 640-649)
- `data.json` - Regenerated with `watch_links` field (235 movies)
- `assets/app.js` - Added WATCH button to card backs (line 130), updated watch link logic (lines 84-101)
- `assets/styles.css` - Reduced WATCH button height (padding: 0.5rem)
- `index.html` - Added cache-busting parameters (?v=3 for CSS, ?v=2 for JS)
- `PROJECT_CHARTER.md` - Added AMENDMENT-038 for Watchmode API integration, added Watchmode API key to API Keys section
- `DAILY_CONTEXT.md` - This file (documented watch links feature completion)

### Archived
[Fill in during session - list files moved to museum_legacy/]

---

## Quick Reference

### Daily Workflow
```bash
# Morning: View the wall
./launch_NRW.sh

# Automation runs automatically at 9 AM UTC
# (No manual intervention needed)
```

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

**Last updated:** [End of session]
**Next diary archive:** End of session -> `diary/[YYYY-MM-DD].md`