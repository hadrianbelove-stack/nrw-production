# New Release Wall (NRW) - Automated Movie Tracker

## Overview
Automated tracking of theatrical releases becoming available digitally, displayed in Netflix-style interface.

## Quick Start
Run the one-command startup:
```bash
./launch_NRW.sh
```

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

Watch links: Watchmode API → cache → `data.json.watch_links`

Admin QA: `admin.py` (port 5555) → manual corrections → regenerate

Automation: GitHub Actions → `daily_orchestrator.py` → pipeline → auto-commit

## Documentation

- **PROJECT_CHARTER.md** - Governance rules, amendments, API keys, architectural decisions
- **NRW_DATA_WORKFLOW_EXPLAINED.md** - Data pipeline mechanics
- **DAILY_CONTEXT.md** - Current state and recent changes (rolling context)
- **diary/** - Historical session archives

## Admin Panel

QA database editor at `http://localhost:5555` (requires authentication per `PROJECT_CHARTER.md`)
- Inline editing of all movie fields
- Missing data detection and visual indicators
- Manual correction tracking with protection flags
- YouTube playlist creation with custom dates

## Configuration

- **config.yaml** - API keys, scraper settings, display parameters
- **requirements.txt** - Python dependencies
- **.gitignore** - Excludes cache/, config.yaml, movie_tracking.json

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
- Currently disabled in `config.yaml` (line 21: `enabled: false`)
- See `AGENT_SCRAPER_DIAGNOSTICS.md` for details
- Playwright infrastructure ready for future re-enablement