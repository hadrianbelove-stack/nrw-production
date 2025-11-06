# Automation Branch Workflow

## Overview
The NRW automation system uses a **two-branch workflow** to safely separate automated commits from the main codebase. This prevents the main branch from getting polluted with automated commits and allows for manual review before merging.

## Branch Architecture

```
main (protected)
  ↑
  | (manual merge after review)
  |
automation-updates (automated commits)
```

### Main Branch
- **Purpose**: Production-ready code
- **Commits**: Manual commits only (features, fixes, docs)
- **Status**: Protected, always deployable
- **Merges From**: automation-updates (after review)

### Automation-Updates Branch
- **Purpose**: Automated data updates
- **Commits**: Daily/weekly data.json updates
- **Status**: Force-pushed regularly
- **Merges To**: main (manually, after review)

## How It Works

### 1. Daily NRW Update Workflow
**File**: [.github/workflows/daily-check.yml](../.github/workflows/daily-check.yml)

**Schedule**: 9:00 AM UTC daily

**Process**:
1. Checkout automation-updates branch
2. **Sync main → automation-updates** (merge origin/main to get latest fixes)
3. Run `daily_orchestrator.py` to fetch new releases
4. Check if data.json changed
5. If changed:
   - Commit changes: `Daily update - YYYY-MM-DD [automated]`
   - Force push to `automation-updates`

**Key Lines** (51-77):
```yaml
- name: Sync main → automation-updates
  run: |
    git fetch origin main
    git merge origin/main --no-edit || {
      echo "⚠️ Merge conflict detected - branches have diverged"
      echo "Manual intervention required to resolve conflicts"
      echo "Run: git checkout automation-updates && git merge main"
      git merge --abort
      exit 1
    }

- name: Switch to automation branch
  if: steps.changes.outputs.changes == 'true'
  run: git checkout -B automation-updates

- name: Commit changes
  if: steps.changes.outputs.changes == 'true'
  run: |
    git add data.json
    git commit -m "Daily update - $(date +%Y-%m-%d) [automated]"

- name: Force push to remote
  if: steps.changes.outputs.changes == 'true'
  run: git push --force origin automation-updates
```

### 2. Weekly Full Regeneration Workflow
**File**: [.github/workflows/weekly-full-regen.yml](../.github/workflows/weekly-full-regen.yml)

**Schedule**: 10:00 AM UTC on Sundays

**Process**:
1. Checkout main branch
2. Run `generate_data.py --full` to regenerate ALL movie data
3. Validate data quality
4. If changed:
   - Commit changes: `Weekly full regeneration - YYYY-MM-DD [automated]`
   - Switch to `automation-updates` branch
   - Force push to `automation-updates`

**Key Lines** (69-79):
```yaml
- name: Commit changes
  if: steps.changes.outputs.changes == 'true'
  run: |
    git add data.json
    git commit -m "Weekly full regeneration - $(date +%Y-%m-%d) [automated]"

- name: Switch to automation branch
  run: git checkout -B automation-updates

- name: Force push to remote
  run: git push --force origin automation-updates
```

## Merging to Main

### Manual Merge Process
After automation updates are pushed to `automation-updates`:

1. **Review Changes**:
   ```bash
   # Check what changed
   git fetch origin
   git diff main..origin/automation-updates -- data.json
   ```

2. **Verify Data Quality** (locally):
   ```bash
   git checkout automation-updates
   python3 -c "
   import daily_orchestrator
   daily_orchestrator.NRWOrchestrator().validate_data_quality()
   "
   ```

3. **Merge to Main**:
   ```bash
   git checkout main
   git merge automation-updates -m "Merge automated updates from $(date +%Y-%m-%d)"
   git push origin main
   ```

### Automated Merge (Future Enhancement)
Could add workflow to automatically merge after validation:
```yaml
- name: Merge to main if validation passes
  run: |
    git checkout main
    git merge automation-updates
    git push origin main
```

## Why Force Push?

The `automation-updates` branch uses `git push --force` because:

1. **History Doesn't Matter**: Automated commits have no historical value
2. **Prevents Bloat**: Avoid thousands of automated commits in git history
3. **Clean Merges**: Each merge to main is a single logical update
4. **Easy Rollback**: If something breaks, just don't merge the branch

## Branch Divergence Prevention

### Automatic Sync (Nov 5, 2025)

**Problem:** The workflow previously ran on `main` but committed to `automation-updates`, causing branch divergence. This led to 10 days of automation failures (Oct 25-Nov 5, 2025) when `automation-updates` was 22 commits behind `main`.

**Solution:**
- ✅ **Automatic sync in workflow**: GitHub Actions automatically merges main → automation-updates before each run
- ✅ **Manual sync for user** (daily): Run `./sync_daily_updates.sh` to merge automation-updates → main
- ✅ **Both branches stay in sync** automatically with no manual intervention needed for bot runs

**How it works:**
- Bot syncs main → automation-updates (gets latest fixes from user)
- User syncs automation-updates → main (gets latest data from bot)
- Two-way sync keeps branches consistent

**Error handling:**
If the sync fails due to merge conflicts, the workflow fails fast with a clear error message and manual intervention is required:
```bash
git checkout automation-updates && git merge main
```

**Historical note:** This automatic sync was added on Nov 5, 2025 to fix the Oct 25-Nov 5 automation failures caused by branch divergence. Before this fix, the workflow ran on main but committed to automation-updates, causing the branches to drift apart by 22 commits.

## Branch Lifecycle

### Daily Cycle
```
09:00 UTC - Daily workflow runs
          ↓
automation-updates updated with new releases
          ↓
[Manual Review]
          ↓
Merge to main when ready
          ↓
Next day: automation-updates force-pushed again
```

### Weekly Cycle
```
10:00 UTC Sunday - Weekly full regen runs
                 ↓
automation-updates updated with full dataset
                 ↓
[Manual Review + Data Quality Check]
                 ↓
Merge to main when validated
                 ↓
Next week: automation-updates force-pushed again
```

## Troubleshooting

### automation-updates not created
If the branch doesn't exist, the workflow will create it:
```bash
git checkout -B automation-updates  # Creates if doesn't exist
```

### Merge conflicts
Shouldn't happen since only data.json is automated. If conflicts occur:
1. Check if manual commits modified data.json on main
2. Always prefer automation-updates version for data.json
3. Use `git checkout --theirs data.json` to take automated version

### Failed workflow
Check workflow logs and GitHub Issues (auto-created on failure):
```bash
gh run list --workflow="Daily NRW Update"
gh run view <run-id> --log
```

## Security

### Protected Branches
- main: Should be protected (require PR reviews, status checks)
- automation-updates: No protection needed (force-pushed regularly)

### Secrets Used
Both workflows require:
- `TMDB_API_KEY` - TMDB API access
- `OMDB_API_KEY` - OMDB API access
- `WATCHMODE_API_KEY` - WatchMode API access

### Permissions
Both workflows need:
```yaml
permissions:
  contents: write  # To push commits
  issues: write    # To create failure issues
```

## Manual Testing

### Test Daily Workflow Locally
```bash
python3 daily_orchestrator.py
git diff data.json  # See what changed
```

### Test Weekly Workflow Locally
```bash
python3 generate_data.py --full
git diff data.json  # See what changed
```

### Test Workflow in GitHub Actions
```bash
# Trigger manually
gh workflow run "Daily NRW Update"
gh workflow run "Weekly Full Regeneration"

# Check status
gh run list --workflow="Daily NRW Update" --limit 1
gh run watch
```

## References

- Daily workflow: [.github/workflows/daily-check.yml](../.github/workflows/daily-check.yml)
- Weekly workflow: [.github/workflows/weekly-full-regen.yml](../.github/workflows/weekly-full-regen.yml)
- Orchestrator: [daily_orchestrator.py](../daily_orchestrator.py)
- Data generator: [generate_data.py](../generate_data.py)
