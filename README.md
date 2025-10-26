# New Release Wall (NRW) - Automated Movie Tracker

![Daily NRW Update](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/daily-check.yml/badge.svg)
![Weekly Full Regeneration](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/weekly-full-regen.yml/badge.svg)

## Overview
Automated tracking of theatrical releases becoming available digitally, displayed in Netflix-style interface.

## Known Data Quality Issues

### Bootstrap Date Accuracy (Resolved Oct 2025)

**Issue:** ~50 movies from the September 2025 bootstrap have approximate digital dates marked with "~" indicators. These dates represent when movies were first discovered, not necessarily when they became digitally available.

**For Users:** The "~" symbol means the exact digital release date is uncertain. The movie was discovered on that date but may have been available earlier.

**For Developers:** See [BOOTSTRAP_DATES.md](BOOTSTRAP_DATES.md) for full technical details, correction tools, and prevention measures. Also see `IMPLEMENTATION_ROADMAP.md` (CRITICAL-001) and `PROJECT_CHARTER.md` (AMENDMENT-049).

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
- **Stopping services:** Press Ctrl+C to stop and exit
- **Returning to menu:** YouTube Playlist Manager returns to menu after command completes

### Menu Options

**Option 1: Launch Public Site**
- Starts HTTP server on port 8000 (or 8001 if 8000 is busy)
- Opens browser automatically to the selected port (8000 or 8001)
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
- Commits to `automation-updates` branch (not `main`) to avoid conflicts with local development
- Run `./sync_daily_updates.sh` to merge these updates into your local `main` branch

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
- Output: Commits to `automation-updates` branch (not `main`)
- Duration: 3-5 minutes
- Note: Use `./sync_daily_updates.sh` to merge updates into your local `main` branch

### `.github/workflows/weekly-full-regen.yml`
- Trigger: Sunday at 10 AM UTC (cron: `0 10 * * 0`)
- Runs: `generate_data.py --full` (full regeneration)
- Output: Commits to `automation-updates` branch (not `main`)
- Duration: 5-20 minutes (depending on cache)
- Note: Use `./sync_daily_updates.sh` to merge updates into your local `main` branch

### Manual Testing
Both workflows can be triggered manually:
1. Go to GitHub Actions tab
2. Select workflow (Daily Update or Weekly Full Regeneration)
3. Click "Run workflow" button
4. Select branch (main)
5. Click "Run workflow"

### Troubleshooting Automation

**Workflow runs but no commits:**
- Check if `daily_orchestrator.py` validation is failing in GitHub Actions logs
- Look for `validate_provider_coverage` errors - this method requires a minimum number of movies with real watch links
- Reference: `daily_orchestrator.py` lines 144-201 (validation logic)

**Validation threshold too high:**
- If Watchmode API quota is exhausted, fewer movies have real streaming links
- Adjust `min_provider_coverage` threshold in `config.yaml` line 80 (currently set to 5, was 10)
- This is a temporary fix while investigating Watchmode API/scraper issues

**Workflow not running on schedule:**
- Check GitHub Actions tab to see if workflow is disabled
- GitHub automatically disables workflows after 60 days of repository inactivity
- Re-enable manually if needed

**Manual testing:**
- Use the "Run workflow" button in GitHub Actions to test without waiting for scheduled run
- Helps verify fixes before the next scheduled execution

## Architecture

Runtime: `index.html` → `assets/app.js` + `assets/styles.css` → `data.json`

Generation: `movie_tracking.json` → `generate_data.py` → `data.json`

Discovery: `generate_data.py --discover` → TMDB API → `movie_tracking.json` (replaces legacy movie_tracker.py)

Watch links: Watchmode API → cache → `data.json` (watch_links section)

Admin QA: `admin.py` (port 5555) → manual corrections → regenerate

Automation: GitHub Actions → `daily_orchestrator.py` → pipeline → auto-commit

## Documentation

- **PROJECT_CHARTER.md** - Governance rules, amendments, API keys, architectural decisions
- **NRW_DATA_WORKFLOW_EXPLAINED.md** - Data pipeline mechanics
- **DAILY_CONTEXT.md** - Current state and recent changes (rolling context)
- **diary/** - Historical session archives (Oct 15, 2025 onwards)
- **PROJECT_LOG.md** - Deprecated session log (Aug 26 - Oct 14, 2025) - see diary/ for current logs
- **museum_legacy/** - Archived completion reports, deprecated code, and historical snapshots

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
- **requirements.txt** - Python dependencies (Playwright-based, Selenium removed)
- **.gitignore** - Excludes cache/, config.yaml (API keys), various backup/temp files
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
- Playwright infrastructure in production use (all scrapers migrated)
- All scrapers now use Playwright: RT scraper, platform scraper, YouTube scraper, agent scraper

### Watch Links Troubleshooting

**Common Problem:** Watch links showing as Google search URLs instead of deep links to streaming platforms.

**Quick Diagnosis:** The Watchmode API key may be invalid, expired, or rate-limited. Test with:
```bash
curl "https://api.watchmode.com/v1/search/?apiKey=YOUR_KEY&search_field=tmdb_movie_id&search_value=507244"
```

**Quick Fix:**
1. Get a new API key from https://api.watchmode.com/ (free tier: 1000 calls/month)
2. Set environment variable: `export WATCHMODE_API_KEY="YOUR_NEW_API_KEY"`
3. Regenerate data: `python3 generate_data.py --full`

**Comprehensive Guide:** See [WATCH_LINKS_TROUBLESHOOTING.md](WATCH_LINKS_TROUBLESHOOTING.md) for detailed diagnosis, multiple solution options, system status, monitoring guidance, and validation steps.

### Scraper Technology Stack

All scrapers use **Playwright** for browser automation:
- **RT Scraper**: `rt_scraper_playwright.py` - Rotten Tomatoes scores and URLs
- **Platform Scraper**: `streaming_platform_scraper.py` - Amazon and Apple TV deep links
- **YouTube Scraper**: `scripts/youtube_trailer_scraper.py` - YouTube trailer links
- **Agent Scraper**: `agent_link_scraper.py` - Netflix, Disney+, HBO Max, Hulu links

**Migration Completed**: October 2025
- Selenium and webdriver-manager removed from dependencies
- 30-40% performance improvement over Selenium
- Better reliability through auto-waiting and retry logic
- Backup Selenium versions preserved in `museum_legacy/` and `*_selenium_backup.py` files

**Benefits**:
- Unified technology stack (easier maintenance)
- Faster scraping (WebSocket-based protocol)
- Better anti-bot evasion (modern browser automation)
- Improved error handling and diagnostics

**Related Documentation:**
- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) - CRITICAL-003: Watch Links Broken
- [DAILY_CONTEXT.md](DAILY_CONTEXT.md) - Watch Links Enhancement (Oct 22)
- `generate_data.py` lines 815-1121 - Watch links waterfall logic