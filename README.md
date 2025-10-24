# New Release Wall (NRW) - Automated Movie Tracker

![Daily NRW Update](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/daily-check.yml/badge.svg)
![Weekly Full Regeneration](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/weekly-full-regen.yml/badge.svg)

## Overview
Automated tracking of theatrical releases becoming available digitally, displayed in Netflix-style interface.

## Known Data Quality Issues

### Bootstrap Date Accuracy (Resolved Oct 2025)

**Issue:** During the initial bootstrap on September 6, 2025, approximately 50 movies were marked as "digitally available" with the discovery date (2025-09-06) rather than their actual digital release dates. This occurred because the legacy tracking system set `digital_date = today` when providers were first detected.

**Impact:** Movies with August 2025 premiere dates showing September 6 digital dates are inaccurate by days or weeks.

**Resolution:**
- All affected movies are flagged with `bootstrap_date: true` in the database
- Website displays a visual indicator ("~" prefix or tooltip) for bootstrap dates
- Admin panel highlights these movies for manual correction
- High-profile titles are being corrected manually over time
- Future movies use TMDB's release date field for accuracy

**For Users:** If you see a "~" symbol or approximate date indicator, this means the exact digital release date is uncertain. The movie was discovered on that date but may have been available earlier.

**For Developers:** See `IMPLEMENTATION_ROADMAP.md` (CRITICAL-001) and `PROJECT_CHARTER.md` (AMENDMENT-049) for full technical details and implementation.

**Correction Tools:**
- Admin panel: `/update-date` endpoint for manual corrections
- CLI tool: `python3 date_verification.py` for batch corrections
- CSV import: `python3 date_verification.py --csv corrections.csv`

**Prevention:** The current discovery system (integrated into `generate_data.py --discover`) uses TMDB's `release_date` field and no longer sets dates to "today" when providers are detected. This issue will not recur for new movies.

## Quick Start
```bash
# Interactive launcher with menu (recommended)
./launch_all.sh

# Or launch specific tools directly:
./launch_NRW.sh              # Public site only
python3 admin.py             # Admin panel only
python3 youtube_playlist_manager.py --help  # YouTube CLI
```

The unified launcher (`launch_all.sh`) is the easiest way to start working with NRW.

## Unified Launcher

### Overview

The `launch_all.sh` script provides a menu-driven interface to launch all NRW tools from a single command. Choose from four menu options: (1) Public Site, (2) Admin Panel, (3) YouTube Manager, (4) All Services. The launcher automatically opens browser windows for web interfaces and provides clear instructions for CLI tools.

### Usage

- **Basic command:** `./launch_all.sh`
- **Menu navigation:** Enter 1-5 to select an option
- **Stopping services:** Press Ctrl+C to stop running services
- **Returning to menu:** YouTube manager returns to menu after command completes

### Menu Options

**Option 1: Launch Public Site**
- Starts HTTP server on port 8000 (or 8001 if 8000 is busy)
- Opens browser automatically to `http://localhost:8000`
- Displays movie wall interface
- Press Ctrl+C to stop

**Option 2: Launch Admin Panel**
- Starts Flask server on port 5555
- Opens browser automatically to `http://localhost:5555`
- **Authentication required**: See `PROJECT_CHARTER.md` for credentials
- Use for post-publication curation (hide/feature movies, edit metadata)
- Press Ctrl+C to stop

**Option 3: YouTube Playlist Manager**
- Interactive CLI tool (not a web interface)
- Prompts for command to run (e.g., `test`, `weekly`, `auth`)
- Returns to menu after command completes
- See `YOUTUBE_PLAYLIST_SETUP.md` for detailed usage

**Option 4: Launch All Services**
- Starts public site AND admin panel simultaneously
- Opens both in browser (site first, then admin)
- Runs YouTube Playlist Manager --help and displays output
- Press Ctrl+C to stop all services

**Option 5: Exit**
- Closes the launcher

### Authentication Reminder

When launching admin panel (options 2 or 4), the script displays credentials reminder. Default credentials are in `PROJECT_CHARTER.md` (search for "Admin Panel Authentication").

**Security note**: Change default credentials in production environments.

### Troubleshooting

**"Port already in use" error**:
- Another service is using port 8000, 8001, or 5555
- Find and stop conflicting process: `lsof -ti:8000 | xargs kill`
- Or choose a different menu option

**"Permission denied" error**:
- Make script executable: `chmod +x launch_all.sh`

**Browser doesn't open automatically**:
- Script will display URLs to open manually
- Install browser opener: `brew install open` (macOS) or ensure `xdg-open` is available (Linux)

**Admin panel shows "Authentication Required"**:
- This is expected behavior
- Enter credentials from `PROJECT_CHARTER.md`
- Browser should remember credentials for future sessions

## Automation

### Daily Updates (9 AM UTC)
- Discovers new theatrical releases
- Checks for digital availability
- Updates tracking database and public display data
- Pushes to `automation-updates` branch

### Weekly Full Regeneration (Sunday 10 AM UTC)
- Reprocesses ALL movies (not just new ones)
- Populates agent scraper links retroactively
- Updates RT scores for movies with new reviews
- Refreshes all data enrichment

### Morning Sync Checklist
1. Run `./sync_daily_updates.sh` to merge automation updates
2. Review diff to ensure data quality looks healthy
3. If changes look good, merge and proceed with work
4. If issues detected, investigate before merging

### Syncing Automation Data
Run `./sync_daily_updates.sh` to merge automation updates into your main branch.

## GitHub Actions Workflows

### `.github/workflows/daily-check.yml`
- Trigger: Daily at 9 AM UTC (cron: `0 9 * * *`)
- Runs: `daily_orchestrator.py` (incremental mode)
- Output: Updates to `automation-updates` branch
- Duration: 3-5 minutes

### `.github/workflows/weekly-full-regen.yml`
- Trigger: Sunday at 10 AM UTC (cron: `0 10 * * 0`)
- Runs: `generate_data.py --full` (full regeneration)
- Output: Updates to `automation-updates` branch
- Duration: 5-20 minutes (depending on cache)

### Manual Testing
Both workflows can be triggered manually:
1. Go to GitHub Actions tab
2. Select workflow (Daily Update or Weekly Full Regeneration)
3. Click "Run workflow" button
4. Select branch (main)
5. Click "Run workflow"

## Architecture

Runtime: `index.html` → `assets/app.js` + `assets/styles.css` → `data.json`

Generation: `movie_tracking.json` → `generate_data.py` → `data.json`

Discovery: `generate_data.py --discover` → TMDB API → `movie_tracking.json` (replaces legacy movie_tracker.py)

Watch links: Watchmode API → cache → `data.json.watch_links`

Admin QA: `admin.py` (port 5555) → manual corrections → regenerate

Automation: GitHub Actions → `daily_orchestrator.py` → pipeline → auto-commit

## Documentation

- **PROJECT_CHARTER.md** - Governance rules, amendments, API keys, architectural decisions
- **NRW_DATA_WORKFLOW_EXPLAINED.md** - Data pipeline mechanics
- **DAILY_CONTEXT.md** - Current state and recent changes (rolling context)
- **diary/** - Historical session archives

## Admin Panel - Post-Publication Curation

**Quick Launch**: Use `./launch_all.sh` and select option 2 (Admin Panel) or option 4 (All Services).

**Direct Launch**: `python3 admin.py` then visit `http://localhost:5555`

Post-publication curation interface at `http://localhost:5555` (requires authentication per `PROJECT_CHARTER.md`)

**Workflow Overview:**
Movies are **automatically visible** when discovered by automation. The admin panel is used to curate after publication (not pre-approve). Workflow: Automation discovers → Movies appear on site → Admin curates → Regenerate.

**Main Curation Actions:**
- **Hide movies** (🚫 Hide button): Remove unwanted releases from public display
- **Feature movies** (⭐ Feature button): Highlight important releases
- **Edit metadata**: Inline editing of all movie fields with manual correction tracking
- Missing data detection with visual indicators
- YouTube playlist creation with custom dates

**Daily Curation Workflow:**
1. Sync automation updates: `./sync_daily_updates.sh`
2. Launch admin panel: `python3 admin.py`
3. Review new movies and hide/feature as needed
4. Fix missing data using "⚠️ Missing Data" filter
5. Regenerate `data.json` to apply changes
6. Verify on public site

For detailed curation guidelines and best practices, see `ADMIN_WORKFLOW.md`.

## Newsletter Generation

Generate weekly newsletters from the movie database in multiple formats.

### Status

✅ **Fully Implemented and Tested** (2025-10-23)

### Basic Usage

```bash
# Generate all formats (markdown, HTML, plain text) for past 7 days
python3 generate_newsletter.py

# Generate only markdown for Substack
python3 generate_newsletter.py --format markdown

# Generate newsletter for past 14 days
python3 generate_newsletter.py --days 14

# Specify output directory
python3 generate_newsletter.py --output-dir newsletters/
```

### Output Formats

1. **Markdown** (`newsletter_YYYY-MM-DD.md`)
   - Substack-ready format
   - Clean, readable text with headers and lists
   - Includes review text and author attribution
   - **Best for:** Substack, Medium, blog posts

2. **HTML** (`newsletter_YYYY-MM-DD.html`)
   - Email-friendly with inline styles
   - Responsive design (max-width: 800px)
   - Colored RT score badges and prominent CTAs
   - **Best for:** Email distribution (Gmail, Mailchimp, etc.)

3. **Plain Text** (`newsletter_YYYY-MM-DD.txt`)
   - Simple list format for quick sharing
   - No styling, just content
   - Easy to copy/paste into any platform
   - **Best for:** Plain text email, social media, SMS

### Newsletter Sections

- **🌟 Hero Review**: Featured movie with full review (if reviews exist)
- **📽️ This Week's Highlights**: 3-5 reviewed movies with excerpts
- **📺 By Platform**: Movies grouped by streaming service (Netflix, Amazon, etc.)
- **📋 Quick List**: Alphabetical reference of all movies with RT scores

### Requirements

- `data.json` must exist (generated by `generate_data.py`)
- `admin/movie_reviews.json` is optional (newsletter works without reviews)
- No external dependencies (uses only Python standard library)

### Workflow

1. **Add Reviews** (optional but recommended):
   ```bash
   python3 admin.py  # Open admin panel at http://localhost:5555
   # Write reviews for 3-5 movies
   # Mark your top pick as "featured in newsletter"
   ```

2. **Generate Newsletter**:
   ```bash
   python3 generate_newsletter.py
   # Generates 3 files in newsletters/ directory
   ```

3. **Distribute**:
   - Copy markdown to Substack editor
   - Copy HTML to email client (Gmail, Mailchimp)
   - Share plain text on social media

### Testing Results

**Tested:** 2025-10-23

- ✅ All 3 formats generate successfully
- ✅ CLI flags work correctly
- ✅ Platform grouping with normalization
- ✅ Review integration (after bug fix)
- ✅ Error handling for missing files
- ✅ Email-compatible HTML output
- ✅ Professional formatting in all formats

### Tips

- Add reviews in the admin panel before generating newsletter
- Mark reviews as "featured in newsletter" to make them the Hero Review
- Use `--days 7` for weekly newsletters, `--days 30` for monthly roundups
- HTML format is best for email distribution (Gmail, Mailchimp, etc.)
- Markdown format is best for Substack, Medium, or blog posts
- Plain text format is best for quick sharing on social media
- Review excerpts are automatically truncated to 200 characters in Highlights section
- Platform names are normalized ("Amazon Video" → "Amazon Prime Video")

### Troubleshooting

**"No movies found in the last X days"**
- Check that `data.json` is up to date
- Run `python3 generate_data.py` to regenerate
- Try increasing `--days` parameter

**"Error: Data file data.json not found"**
- Run `python3 generate_data.py` to generate data file
- Ensure you're in the correct directory

**Reviews not appearing in newsletter**
- Check that `admin/movie_reviews.json` exists and has reviews
- Verify movie IDs match between reviews and data.json
- ✅ **FIXED:** Review field name bug resolved (2025-10-23)

**HTML looks broken in email**
- Ensure you're copying the entire HTML file content
- Test in different email clients (Gmail, Outlook)
- Some email clients strip certain styles (this is normal)

### Configuration

Optional: Configure defaults in `config.yaml`:
```yaml
newsletter:
  days_back: 7  # Default date range
  output_dir: "newsletters/"  # Output directory
```

CLI arguments override config file settings.

## Configuration

- **config.yaml** - API keys, scraper settings, display parameters
- **requirements.txt** - Python dependencies
- **.gitignore** - Excludes cache/, config.yaml, movie_tracking.json
- **launch_all.sh** - Unified launcher for all NRW tools (menu-driven)
- **launch_NRW.sh** - Legacy launcher for public site only

## Troubleshooting

### Workflow Failures
- Check GitHub Actions tab for error logs
- Workflow creates GitHub issue automatically on failure
- Review `daily_orchestrator.py` output for specific errors

### Merge Conflicts
- Run `git merge --abort`
- Regenerate data: `python3 generate_data.py --full`
- Run `./sync_daily_updates.sh` again

### Agent Scraper Issues
- Currently enabled in `config.yaml` (line 31: `enabled: true`) as fallback when Watchmode API has no data
- See `AGENT_SCRAPER_DIAGNOSTICS.md` for details
- Playwright infrastructure ready for production use

### Watch Links Troubleshooting

#### Problem: All watch links are Google search URLs

**Symptoms:**
- Watch links in `data.json` look like: `https://www.google.com/search?q=Movie%20Title%20watch%20Platform`
- No deep links to Amazon, Apple TV, or other platforms
- Users have to search manually instead of going directly to movie page

**Root Cause:**
The Watchmode API key is invalid, expired, or returning no data. The system falls back to Google search URLs.

**Diagnosis:**

1. **Test API Key:**
   ```bash
   curl "https://api.watchmode.com/v1/search/?apiKey=YOUR_KEY&search_field=tmdb_movie_id&search_value=507244"
   ```
   - 200 OK with data → API works
   - 401 Unauthorized → API key invalid
   - 429 Too Many Requests → Rate limit exceeded

2. **Check Logs:**
   ```bash
   grep -i watchmode logs/generate_data.log
   ```
   Look for error messages or warnings.

3. **Check Statistics:**
   Run `python3 generate_data.py` and look for:
   ```
   Watchmode API Statistics:
     Watchmode successes: 0  ← Problem if zero
   ```

**Solutions:**

**Option 1: Get New API Key (Recommended)**
1. Sign up at https://api.watchmode.com/ (free tier: 1000 calls/month)
2. Copy your new API key
3. Set environment variable:
   ```bash
   export WATCHMODE_API_KEY="YOUR_NEW_API_KEY"
   ```
   Note: You can also set the key in `config.yaml` but environment variables are preferred for security
4. Regenerate data:
   ```bash
   python3 generate_data.py --full
   ```

### Watch Links System Status (Updated 2025-10-23)

**Three-Tier Strategy Performance:**

| Tier | Source | Coverage | Status |
|------|--------|----------|--------|
| 1 | Watchmode API | ⚠️ Not Tested | 🔴 Test Invalid |
| 2 | Amazon Scraper | 100% (validated) | ✅ Working |
| 3 | Manual Overrides | TBD (pending re-test) | ⏳ Pending |
| **Total** | **Combined** | **⚠️ Invalid Test** | **🔴 Re-test Required** |

⚠️ **TEST INVALIDATION NOTICE (2025-10-24)**

The validation test failed due to missing TMDB API key configuration. The script crashed before testing Watchmode API. Only Amazon scraper results are valid.

**Action Required:** Fix config.yaml (add TMDB API key) and re-run validation test.

See `IMPLEMENTATION_ROADMAP.md` (CRITICAL-003) for detailed re-test checklist.

**Last Tested:** 2025-10-24 (INVALID - configuration error)
**Last Selector Update:** 2025-10-23
**Next Maintenance:** 2026-01-23 (quarterly)

### Known Limitations

**Watchmode API:**
- Tends to miss recent 2025 releases: ⚠️ Not tested (configuration error)
- Coverage: ⚠️ Not tested (re-test required)
- Free tier: 1,000 requests/month (sufficient for daily automation)
- **Status:** Configuration error prevented testing - add TMDB API key to config.yaml

**Amazon Scraper (Backup):**
- Success rate: ~100% (excellent performance)
- Only runs when Watchmode has no data
- Focuses on recent releases
- Some failures expected:
  - Anti-bot detection: No
  - Movies not available on Amazon: No (all test movies found)
  - Selectors may need quarterly updates: Yes
- Performance: Measured 10.8 seconds per search (266 attempts = ~48 minutes for full regeneration)

**Manual Overrides (Final Fallback):**
- Required for: ~132 movies (53.4%)
- Use admin panel to add: http://localhost:5555
- Format: `admin/watch_link_overrides.json`

**Option 2: Enable Platform Scraper (Amazon/Apple TV)**

**Status:** ✅ Enabled and tested (2025-10-23)

**Configuration:**
```yaml
# config.yaml lines 44-61
platform_scraper:
  enabled: true
  headless: true
  platforms:
    amazon: true
    apple_tv: false  # User doesn't need Apple TV
```

**Test Results:**
- ✅ Amazon scraper success rate: 100% (validated)
- ✅ Average search time: 10.8 seconds
- ✅ Selectors verified: 2025-10-24
- ❌ Watchmode API: Not tested (TMDB API key missing)
- ⚠️ Overall coverage: Invalid test - re-run required
- Known issues: Configuration error - TMDB API key not set in config.yaml

**Test Command:**
```bash
python3 streaming_platform_scraper.py
```

**Maintenance:**
- Selectors may need updates every 3-6 months
- Check if success rate drops below 40%
- Update selectors in lines 96-123 of `streaming_platform_scraper.py`
- Last update: 2025-10-23

**Option 3: Manual Overrides (Quick Fix)**
For high-priority movies, add manual deep links:
1. Edit `overrides/watch_links_overrides.json`:
   ```json
   {
     "507244": {
       "rent": {
         "service": "Amazon",
         "link": "https://www.amazon.com/gp/video/detail/B0XXXXXX"
       }
     }
   }
   ```
2. Regenerate data:
   ```bash
   python3 generate_data.py
   ```

**Validation:**

After applying a fix:
1. Check `data.json` for real deep links (not Google search)
2. Count success rate:
   ```bash
   grep -c "google.com/search" data.json  # Should decrease
   ```
3. Test 3-5 links manually in a browser
4. Verify they go directly to movie pages

### Monitoring Watch Links Health

**Daily Checks:**
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

**Warning Signs:**
- ⚠️ Watchmode success rate drops below 50% → Check API quota
- ⚠️ Platform scraper success rate drops below 40% → Update selectors
- ⚠️ Many "No Amazon link found" messages → Check anti-bot detection
- ⚠️ Final coverage drops below 80% → Investigate both tiers

**Quick Fixes:**
```bash
# If Watchmode API fails (quota exceeded)
# Wait for quota reset or get new API key from https://api.watchmode.com/

# If Amazon scraper fails (selectors outdated)
# Run with visible browser to inspect HTML:
python3 streaming_platform_scraper.py  # headless=False in test function

# If specific movies missing links
# Add manual overrides via admin panel: http://localhost:5555
```

**Success Criteria:**
- At least 50% of Amazon/Apple TV movies have real deep links (Watchmode API handles most)
- Links work (no 404 errors)
- Platform scraper statistics show success rate > 40%
- Watchmode API should handle majority of movies

**Related Documentation:**
- `IMPLEMENTATION_ROADMAP.md` - CRITICAL-003: Watch Links Broken
- `DAILY_CONTEXT.md` - Watch Links Enhancement (Oct 22)
- `generate_data.py` - Lines 815-1121: Watch links waterfall logic