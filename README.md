# New Release Wall (NRW) - Automated Movie Tracker

![Daily NRW Update](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/daily-check.yml/badge.svg)
![Weekly Full Regeneration](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/weekly-full-regen.yml/badge.svg)

## Overview
Automated tracking of theatrical releases becoming available digitally, displayed in Netflix-style interface.

## 📚 Documentation

**Start here for system understanding:**

- 📖 **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)** - How everything works (read this first)
- 📋 **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance & amendments
- 📅 **[DAILY_CONTEXT.md](DAILY_CONTEXT.md)** - Rolling diary of recent work
- 🔄 **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline details
  - [Phase 3 (Admin Approval Gate)](NRW_DATA_WORKFLOW_EXPLAINED.md#phase-3-admin-approval-gate) - Mandatory quality assurance

**Additional guides:**
- [Full workflow overview (automated + manual)](docs/NRW_FULL_WORKFLOW.md) - Complete system overview
- [Admin diagnostics](docs/troubleshooting/admin_diagnostics.md) - Metrics and approval pattern analysis
- [docs/features/](docs/features/) - Feature setup guides (YouTube, Substack, newsletter)
- [docs/troubleshooting/](docs/troubleshooting/) - Troubleshooting guides
- [docs/](docs/) - Technical documentation

## 🔄 Automation Workflow

NRW uses a **single-branch strategy** per PROJECT_CHARTER.md to avoid divergence:

- **`main` branch** - All development work and automation commits
- **No two-branch complexity** - Direct main commits (revert to October working method)

**Daily workflow:**
1. Daily automation runs on `main` branch
2. Changes committed directly to main (no merging required)
3. Single source of truth with no branch divergence

**Charter alignment:**
- Avoids October 25-Nov 5 outage caused by branch divergence
- Simple, reliable automation per charter principles
- Matches proven October working methods

**For details:** See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) Section 2 (Branch Strategy)

## Known Issues

**Bootstrap Date Accuracy (Resolved Oct 2025):** ~50 movies from September 2025 have approximate dates marked with "~". See [docs/BOOTSTRAP_DATES.md](docs/BOOTSTRAP_DATES.md) for details.

## Setup

### Security Note ⚠️

**Admin Panel Credentials:** If using the admin panel beyond localhost, set `ADMIN_USERNAME` and `ADMIN_PASSWORD` as environment variables. Never use defaults in production.

```bash
# Set secure credentials before running admin panel
export ADMIN_USERNAME="your-secure-username"
export ADMIN_PASSWORD="your-secure-password"
python3 admin.py --full-review
```

**Default credentials are only for local development and are automatically rejected in production environments.**

For setup prerequisites and architecture overview, see [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) Section 2 (Branch Strategy). Legacy two-branch guide: [docs/legacy/AUTOMATION_BRANCH_WORKFLOW.md](docs/legacy/AUTOMATION_BRANCH_WORKFLOW.md).

## Quick Start

```bash
# Interactive launcher with menu (recommended)
./launch_all.sh

# Or launch specific tools directly:
python3 admin.py             # Admin panel (port 5555, requires auth)
python3 youtube_playlist_manager.py --help  # YouTube CLI
```

**For detailed usage and features:** See inline menu help

## Automation

### Daily Updates (9 AM UTC)
- Discovers new theatrical releases
- Checks for digital availability
- Commits directly to `main` branch
- **Charter-aligned**: Simple, reliable, no sync complexity

### Weekly Full Regeneration (Sunday 10 AM UTC)
- Reprocesses ALL movies
- Updates RT scores and watch links
- Commits directly to `main` branch
- **Matches**: October working automation

### Morning Review Checklist
1. Check automation results on GitHub Actions
2. Pull latest changes: `git pull origin main`
3. Review data quality in admin panel if needed

### Manual Testing
Trigger workflows manually in GitHub Actions tab → Select workflow → "Run workflow" button

**For troubleshooting:** See [docs/](docs/)

## Architecture

**Data flow:**
- Discovery: `generate_data.py --discover` → TMDB API → `movie_tracking.json`
- Generation: `movie_tracking.json` → `generate_data.py` → `data.json`
- Display: `index.html` → `assets/app.js` + `data.json`
- Admin: `admin.py` (port 5555) → manual corrections → regenerate

**For detailed architecture:** See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)


## Admin Panel

**Launch:** `./launch_all.sh` (option 2) or `python3 admin.py` → `http://localhost:5555`

**Authentication:** See SYSTEM_ARCHITECTURE.md §4.2 (API Keys & Secrets)

**Key features:**
- Hide/feature movies (post-publication curation)
- Edit metadata with inline editing
- Fix missing data (RT scores, Wikipedia, trailers)

**Note:** Admin artifacts (approvals, ordering preferences, diary entries) are ephemeral and not versioned in git. Only the final `data.json` is committed to preserve clean version history. See [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md) for details.
- Create YouTube playlists

**For detailed workflow and best practices:** See [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md)

## Newsletter Generation

Generate weekly newsletters in multiple formats (Markdown, HTML, plain text).

```bash
python3 generate_newsletter.py  # Generate all formats for past 7 days
python3 generate_newsletter.py --format markdown --days 14  # Custom options
```

**For detailed usage, output formats, workflow, and troubleshooting:** See [docs/features/SUBSTACK_NEWSLETTER_GUIDE.md](docs/features/SUBSTACK_NEWSLETTER_GUIDE.md)

## Daily Workflow

### Session Start
1. **Load context**: Read DAILY_CONTEXT.md → PROJECT_CHARTER.md → NRW_DATA_WORKFLOW_EXPLAINED.md
2. **Start services**: Run `./launch_all.sh` and choose Option 4 (All Services)
3. **Check status**: Review daily automation results and any issues in DAILY_CONTEXT.md

### Manual Pipeline Operations
```bash
# Standard data generation
python3 generate_data.py

# Quality assurance interface
python3 admin.py           # Access at localhost:5555

# Discovery and monitoring
python3 generate_data.py --discover    # Find new releases
python3 generate_data.py --check       # Monitor for digital availability
python3 generate_data.py --full        # Full regeneration (weekly)
```

### Session End
1. **Archive context**: Run `./ops/archive_daily_context.sh`
2. **Update diary**: Creates immutable snapshot in `diary/YYYY-MM-DD.md`
3. **Commit changes**: Git add/commit any modifications made during session

### Emergency Commands
```bash
# Fix branch divergence
git pull origin main

# Check processing load (Normal: 1-10 movies, Warning: 50+, Critical: 100+)
grep "Processing.*movies" logs/

# Restore from data corruption
cp movie_tracking.json.backup movie_tracking.json

# API quota check (monitor monthly usage vs 1,000 limit)
cat watchmode_quota.json
```

### Performance Monitoring
- **Normal operation**: 1-10 movies enriched daily, 30-second runtime
- **Warning threshold**: 50+ movies (possible corruption)
- **Critical threshold**: 100+ movies (definite corruption, 2+ hour runtime)

## Configuration

- **config.yaml** - API keys, scraper settings, display parameters
  - **Required setup:** Replace placeholder values for `tmdb_api_key` and `watchmode_api_key` with real API keys
  - Production: Use environment variables `TMDB_API_KEY` and `WATCHMODE_API_KEY` (see [SYSTEM_ARCHITECTURE.md §4](SYSTEM_ARCHITECTURE.md))
- **requirements.txt** - Python dependencies (Playwright-based, Selenium removed)
- **.gitignore** - Excludes cache/, config.yaml (API keys), various backup/temp files
- **launch_all.sh** - Unified launcher for all NRW tools (menu-driven)

## Troubleshooting

**Workflow failures:**
- Check GitHub Actions tab for error logs
- Workflow creates GitHub issue automatically on failure

**Merge conflicts:**
- Run `git merge --abort`
- Regenerate data: `python3 generate_data.py --full`

**Watch links issues:**
- See [docs/troubleshooting/WATCH_LINKS_TROUBLESHOOTING.md](docs/troubleshooting/WATCH_LINKS_TROUBLESHOOTING.md)

**Change detection issues:**
- See [docs/troubleshooting/change_detection.md](docs/troubleshooting/change_detection.md)

**For comprehensive troubleshooting:** See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

**Restoration planning:** Reference revert plan for outage recovery (IMPLEMENTATION_ROADMAP.md)

## Documentation Discipline (Charter-Aligned)

**Root Markdown Limit (AMENDMENT-032):** Strictly 7 root MDs per PROJECT_CHARTER.md:
- `PROJECT_CHARTER.md` - Governance & amendments
- `IMPLEMENTATION_ROADMAP.md` - Tactical planning
- `SYSTEM_ARCHITECTURE.md` - Technical pipeline
- `ADMIN_WORKFLOW.md` - Admin panel procedures
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Data mechanics
- `README.md` - Project overview (this file)
- `DAILY_CONTEXT.md` - Current session state

**Restoration Principle:** Maintain charter discipline; no new root files
- Restoration planning embedded in roadmap/context to maintain cleanliness
- All auxiliary (e.g., troubleshooting details) in docs/

**October Working State Alignment:**
- Clean, minimal documentation structure
- Guidance: Embed plans in existing files; revert docs to match restored code
- Reference charter principles: Clean, aligned with working state

**Proper Placement (Charter Guidelines):**
- Session work/analysis → `diary/`
- Feature guides → `docs/features/`
- Troubleshooting → `docs/`
- Technical docs → `docs/`

**Charter Size Management:**
`PROJECT_CHARTER.md` has a target budget of ≤450 lines with a hard cap at 1000 lines:
- Target: ≤450 lines for optimal readability and maintainability
- Hard cap: 1000 lines (enforced by pre-commit hook)
- Extract technical specs to `SYSTEM_ARCHITECTURE.md`
- Move feature docs to `docs/features/`
- Keep governance, amendments, core rules in charter