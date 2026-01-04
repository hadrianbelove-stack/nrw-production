# New Release Wall (NRW) - Automated Movie Tracker

![Daily NRW Update](https://github.com/hadrianbelove-stack/nrw-production/actions/workflows/daily-check.yml/badge.svg)

## Overview
**The New Release Wall tracks when movies become available for digital streaming/rental.**

Since no API provides "when" a movie became available (only "what" is currently available), NRW polls daily to detect transitions and records them. The result: an ongoing, accumulating database of digital release dates that no one else tracks, displayed in a Netflix-style interface.

## Quick Start

1. Make executable: `chmod +x launch_all.sh`
2. Run: `./launch_all.sh`
3. Select option 3 (Launch All) for full stack
4. Access: Admin http://localhost:5556 (curation, no auth), Site http://localhost:3000

Menu-driven interface handles everything - no separate terminals needed.

For full menu details, see [docs/features/UNIFIED_LAUNCHER.md](docs/features/UNIFIED_LAUNCHER.md). Ctrl+C in 'All' mode stops both services cleanly.

**Ports:** Standard Admin 5556, Site 3000; custom via env vars in launcher.

## 📚 Documentation

**Start here for system understanding:**

- 📖 **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)** - How everything works (read this first)
- 📋 **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance & amendments
- 🔄 **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline details

**Additional guides:**
- [Full workflow overview (automated + manual)](docs/NRW_FULL_WORKFLOW.md) - Complete system overview
- [docs/features/](docs/features/) - Feature setup guides (YouTube, Substack)
- [docs/troubleshooting/](docs/troubleshooting/) - Troubleshooting guides
- [docs/](docs/) - Technical documentation

## 🔄 Automation Workflow

NRW uses a **single-branch strategy** per PROJECT_CHARTER.md to avoid divergence:

- **`main` branch** - All development work and automation commits
- **No two-branch complexity** - Direct main commits (revert to October working method)

**Daily workflow:**
1. Intakes new theatrical releases and discovers provider availability
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

### Local Development

**No authentication required** - the admin panel runs without credentials for local development.

For setup prerequisites and architecture overview, see [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) Section 2 (Branch Strategy).

## Launch Commands

```bash
# Unified launcher (recommended)
./launch_all.sh

# Additional tools:
python3 youtube_playlist_manager.py --help  # YouTube CLI
```

## Automation

### Automation Strategy
- **Daily:** Discovery, monitoring, and publishing (via `.github/workflows/daily-check.yml`)
- **Manual:** Full regeneration and maintenance tasks (via admin panel Operations tab - planned)
- **Philosophy:** Intentional maintenance over automated complexity

### Daily Updates (9 AM UTC)
- Intakes new theatrical releases from TMDB
- Discovers provider availability for tracking movies
- Auto-publishes `data.json` directly to `main` branch
- **Charter-aligned**: Simple, reliable, no sync complexity
- **Curation model**: Publish-then-curate via admin panel hide/feature controls

### Morning Review Checklist
1. Check automation results on GitHub Actions
2. Pull latest changes: `git pull origin main`
3. Review data quality in admin panel if needed

### Manual Testing
Trigger workflows manually in GitHub Actions tab → Select workflow → "Run workflow" button

**For troubleshooting:** See [docs/](docs/)

## Architecture

**Data flow:**
- Intake: `generate_data.py --intake` → TMDB API → `movie_tracking.json`
- Discovery: `generate_data.py --discover` → Provider availability for tracked movies
- Generation: `movie_tracking.json` → `generate_data.py` → `data.json`
- Display: `index.html` → `assets/app.js` + `data.json`
- Admin: `admin.py` (port 5556) → manual corrections → regenerate

**For detailed architecture:** See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)


## Admin Panel

**Launch:** `./launch_all.sh` or `python3 admin.py` → `http://localhost:5556`

**Authentication:** None required for local development

**Key features:**
- Hide/feature movies (post-publication curation)
- Edit metadata with inline editing
- Fix missing data (RT scores, Wikipedia, trailers)

**Note:** Admin artifacts (ordering preferences and curation overrides) are ephemeral and not versioned in git. Only the final `data.json` is committed to preserve clean version history.
- Create YouTube playlists

**For detailed workflow and best practices:** See [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)


## Daily Workflow

### Session Start
1. **Load context**: Read PROJECT_CHARTER.md → NRW_DATA_WORKFLOW_EXPLAINED.md
2. **Start services**: Run `./launch_all.sh` (select option 3 for full stack)
3. **Check status**: Review daily automation results and metrics files for current system state

### Manual Pipeline Operations
```bash
# Standard data generation
python3 generate_data.py

# Quality assurance interface (or via launcher option 1)
python3 admin.py           # Access at localhost:5556

# Intake and provider discovery operations
python3 generate_data.py --intake      # Intake new premieres from TMDB into tracking database
python3 generate_data.py --discover    # Provider discovery: check availability for tracking movies
python3 generate_data.py --full        # Full regeneration (manual, via admin panel)
```

### Session End
1. **Commit changes**: Git add/commit any modifications made during session
2. **Optional**: Document significant work in `diary/YYYY-MM-DD.md` for future reference

### Emergency Commands
Quick reference for common issues. **For detailed troubleshooting:** See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Configuration

- **config.yaml** - API keys, scraper settings, display parameters
  - **Required setup:** Replace placeholder value for `tmdb_api_key` with real API key
  - Production: Use environment variable `TMDB_API_KEY` (see [SYSTEM_ARCHITECTURE.md §4](SYSTEM_ARCHITECTURE.md))
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

**Restoration planning:** See SYSTEM_ARCHITECTURE.md for current architecture and troubleshooting

## Documentation Discipline (Charter-Aligned)

**Root Markdown Limit:** Strictly 4 root MDs:
- `PROJECT_CHARTER.md` - Governance & amendments
- `SYSTEM_ARCHITECTURE.md` - Technical pipeline & core data model
- `NRW_DATA_WORKFLOW_EXPLAINED.md` - Data mechanics & daily workflow
- `README.md` - Project overview (this file)

*Historical: IMPLEMENTATION_ROADMAP.md archived to museum_legacy/ (2025-12-29)*

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