# New Release Wall (NRW) - Automated Movie Tracker

![Daily NRW Update](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/daily-check.yml/badge.svg)
![Weekly Full Regeneration](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/weekly-full-regen.yml/badge.svg)

## Overview
Automated tracking of theatrical releases becoming available digitally, displayed in Netflix-style interface.

## 📚 Documentation

**Start here for system understanding:**

- 📖 **[SYSTEM_ARCHITECTURE.md](docs/AUTOMATION_BRANCH_WORKFLOW.md)** - How everything works (read this first)
- 📋 **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance, amendments, API keys
- 📅 **[DAILY_CONTEXT.md](DAILY_CONTEXT.md)** - Rolling diary of recent work
- 🔄 **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline details

**Additional guides:**
- [QUICK_START.md](QUICK_START.md) - Detailed setup and usage
- [docs/guides/](docs/guides/) - Setup guides (YouTube, Admin, Newsletter)
- [docs/troubleshooting/](docs/troubleshooting/) - Troubleshooting guides

## 🔄 Two-Branch Workflow

NRW uses a two-branch strategy to prevent merge conflicts between automation and user work:

- **`main` branch** - Your development work (commits, pushes, pulls)
- **`automation-updates` branch** - Bot commits (daily at 9 AM UTC)

**Why?** Automation force-pushes to `automation-updates` to avoid conflicts. You control when to merge.

**Daily sync workflow:**
```bash
./sync_daily_updates.sh  # Merge automation data into main
```

**How it works:**
1. GitHub Actions runs on `automation-updates` (syncs from `main` automatically)
2. Bot generates data and commits to `automation-updates`
3. You run `./sync_daily_updates.sh` to merge into `main`

**For details:** See [SYSTEM_ARCHITECTURE.md](docs/AUTOMATION_BRANCH_WORKFLOW.md) Section 2 (Two-Branch Deployment Strategy)

## Known Issues

**Bootstrap Date Accuracy (Resolved Oct 2025):** ~50 movies from September 2025 have approximate dates marked with "~". See [BOOTSTRAP_DATES.md](BOOTSTRAP_DATES.md) for details.

## Quick Start

```bash
# Interactive launcher with menu (recommended)
./launch_all.sh

# Or launch specific tools directly:
./launch_NRW.sh              # Public site (port 8000)
python3 admin.py             # Admin panel (port 5555, requires auth)
python3 youtube_playlist_manager.py --help  # YouTube CLI
```

For setup prerequisites and architecture overview, see [docs/AUTOMATION_BRANCH_WORKFLOW.md](docs/AUTOMATION_BRANCH_WORKFLOW.md).

**For detailed usage, menu options, and troubleshooting:** See [QUICK_START.md](QUICK_START.md)

## Automation

### Daily Updates (9 AM UTC)
- Discovers new theatrical releases
- Checks for digital availability
- Commits to `automation-updates` branch
- **Sync:** Run `./sync_daily_updates.sh` to merge into `main`

### Weekly Full Regeneration (Sunday 10 AM UTC)
- Reprocesses ALL movies
- Updates RT scores and watch links
- Commits to `automation-updates` branch

### Morning Sync Checklist
1. Run `./sync_daily_updates.sh`
2. Review diff for data quality
3. Merge if changes look good

### Manual Testing
Trigger workflows manually in GitHub Actions tab → Select workflow → "Run workflow" button

**For troubleshooting:** See [docs/](docs/)

## Architecture

**Data flow:**
- Discovery: `generate_data.py --discover` → TMDB API → `movie_tracking.json`
- Generation: `movie_tracking.json` → `generate_data.py` → `data.json`
- Display: `index.html` → `assets/app.js` + `data.json`
- Admin: `admin.py` (port 5555) → manual corrections → regenerate

**For detailed architecture:** See [SYSTEM_ARCHITECTURE.md](docs/AUTOMATION_BRANCH_WORKFLOW.md)


## Admin Panel

**Launch:** `./launch_all.sh` (option 2) or `python3 admin.py` → `http://localhost:5555`

**Authentication:** See `PROJECT_CHARTER.md` for credentials

**Key features:**
- Hide/feature movies (post-publication curation)
- Edit metadata with inline editing
- Fix missing data (RT scores, Wikipedia, trailers)
- Create YouTube playlists

**For detailed workflow and best practices:** See [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md)

## Newsletter Generation

Generate weekly newsletters in multiple formats (Markdown, HTML, plain text).

```bash
python3 generate_newsletter.py  # Generate all formats for past 7 days
python3 generate_newsletter.py --format markdown --days 14  # Custom options
```

**For detailed usage, output formats, workflow, and troubleshooting:** See [SUBSTACK_NEWSLETTER_GUIDE.md](SUBSTACK_NEWSLETTER_GUIDE.md)

## Configuration

- **config.yaml** - API keys, scraper settings, display parameters
- **requirements.txt** - Python dependencies (Playwright-based, Selenium removed)
- **.gitignore** - Excludes cache/, config.yaml (API keys), various backup/temp files
- **launch_all.sh** - Unified launcher for all NRW tools (menu-driven)
- **launch_NRW.sh** - Legacy launcher for public site only

## Troubleshooting

**Workflow failures:**
- Check GitHub Actions tab for error logs
- Workflow creates GitHub issue automatically on failure

**Merge conflicts:**
- Run `git merge --abort`
- Regenerate data: `python3 generate_data.py --full`
- Run `./sync_daily_updates.sh` again

**Watch links issues:**
- See [WATCH_LINKS_TROUBLESHOOTING.md](WATCH_LINKS_TROUBLESHOOTING.md)

**For comprehensive troubleshooting:** See [docs/](docs/)