# Workflow Troubleshooting Guide

**Purpose:** Common failure modes for NRW automation workflows and how to fix them.

**Related Docs:**
- [AUTOMATION_BRANCH_WORKFLOW.md](AUTOMATION_BRANCH_WORKFLOW.md) - How workflows are designed to work
- [museum_legacy/troubleshooting/](../museum_legacy/troubleshooting/) - Historical post-mortems with detailed debugging

**Last Updated:** 2025-11-06

---

## Quick Diagnosis

| Symptom | Likely Cause | Jump To |
|---------|--------------|---------|
| `base64: invalid input` | YouTube token corruption | [YouTube Token Issues](#1-youtube-token-corruption) |
| `Memo value not found at index X` | Pickle corruption | [YouTube Token Issues](#1-youtube-token-corruption) |
| `No recent movies found` | Validation catch-22 or discovery failure | [Validation Failures](#2-validation-failures---no-recent-movies) |
| `Provider coverage too low` | Watchmode API quota exhausted | [API Quota Exhaustion](#4-watchmode-api-quota-exhausted) |
| Workflow runs 2+ hours | Branch divergence or enrichment bug | [Branch Divergence](#5-branch-divergence) |
| OAuth completes but no token.pickle | File permissions or swallowed exception | [YouTube Token Issues](#1-youtube-token-corruption) |

---

## YouTube Playlist Workflow Failures

### 1. YouTube Token Corruption

**Symptoms:**
- GitHub Actions error: `base64: invalid input`
- GitHub Actions error: `Memo value not found at index 148` (or similar number)
- Workflow fails at "Restore YouTube credentials" step
- Local OAuth completes but `youtube_credentials/token.pickle` not created

**Root Causes:**
1. **GitHub Secret corrupted** - Base64 encoding/decoding issue
2. **Token expired** - YouTube OAuth tokens can expire or be revoked
3. **Pickle file corruption** - Binary data corruption during encoding
4. **Local file write failure** - Permissions issue in youtube_credentials/ directory

**Solutions:**

#### If GitHub workflow is failing:

```bash
# 1. Re-authenticate locally (opens browser for OAuth)
python3 youtube_playlist_manager.py auth

# 2. Verify token was created
ls -la youtube_credentials/token.pickle

# 3. Test the token works
python3 -c "import pickle; pickle.load(open('youtube_credentials/token.pickle', 'rb'))"

# 4. Encode for GitHub (IMPORTANT: No tr -d '\n'!)
base64 -i youtube_credentials/token.pickle -o /tmp/youtube_token.txt

# 5. Update GitHub secret
gh secret set YOUTUBE_TOKEN < /tmp/youtube_token.txt

# 6. Test workflow
gh workflow run youtube-playlists.yml
gh run watch
```

#### If local OAuth is not saving token.pickle:

```bash
# 1. Check directory permissions
ls -ld youtube_credentials/
chmod 755 youtube_credentials/

# 2. Check for exceptions during OAuth
python3 youtube_playlist_manager.py auth 2>&1 | tee oauth.log

# 3. Try verbose mode (if available)
python3 youtube_playlist_manager.py auth --verbose

# 4. Check disk space
df -h .

# 5. Check if OAuth flow is actually completing
python3 youtube_playlist_manager.py auth 2>&1 | grep -E "Authentication|Credentials|saved"
# Should see: "✅ Credentials saved to youtube_credentials/token.pickle"
# If you see "✅ Authentication complete!" but NOT "Credentials saved",
# there's an exception being swallowed during file write

# 6. Test file write directly
touch youtube_credentials/test.txt
ls -la youtube_credentials/test.txt
rm youtube_credentials/test.txt
# If this fails, permissions issue confirmed

# 7. Run with Python error output
python3 -u youtube_playlist_manager.py auth
# The -u flag disables buffering, shows errors immediately
```

#### Common OAuth File Write Issues:

1. **Directory doesn't exist:**
   ```bash
   mkdir -p youtube_credentials
   chmod 755 youtube_credentials
   ```

2. **Insufficient permissions:**
   ```bash
   chmod 755 youtube_credentials/
   ls -ld youtube_credentials/  # Should show drwxr-xr-x
   ```

3. **Exception swallowed in code:**
   - Check youtube_playlist_manager.py for try/except blocks that catch file write errors
   - Look for logging statements that should appear but don't
   - Add debug prints around file write operations

4. **Disk full:**
   ```bash
   df -h .
   # Should show available space
   ```

**Prevention:**
- Tokens typically last months - shouldn't happen often
- Check YouTube account API access hasn't been revoked
- Verify OAuth app credentials in Google Cloud Console
- Don't manually revoke tokens in Google account settings

**See Also:**
- [Post-mortem: Oct 28, 2025](../museum_legacy/troubleshooting/2025-10-28-workflow-failures.md#issue-1-youtube-playlist-workflow-failure)
- [Post-mortem: Nov 3, 2025](../museum_legacy/troubleshooting/2025-11-03-workflow-status.md#1-youtube-playlist-workflow)

---

## Daily Update Workflow Failures

### 2. Validation Failures - No Recent Movies

**Symptoms:**
- GitHub Actions error: `No recent movies found - automation may not be discovering new releases`
- Workflow fails at data quality validation step
- `data.json` shows no movies with `digital_date` in last 7 days
- Consecutive daily failures creating a cascading cycle

**Root Causes:**

**Cascading Failure (Catch-22):**
1. Daily update fails for some reason → No new data generated
2. `data.json` becomes stale → Next day fails validation
3. Validation failure → No new data generated
4. Cycle continues → Data gets more stale each day

**Discovery Failure:**
1. TMDB API not returning new releases
2. Discovery logic broken (e.g., wrong date range)
3. All discovered movies filtered out (hidden/invalid)

**Why It's a Catch-22:**
- Workflow validates that `data.json` has movies with recent `digital_date`
- If data.json hasn't been regenerated, it can't have recent dates
- Validation prevents regeneration, regeneration prevents validation

**Solutions:**

#### Break the cascading failure cycle:

```bash
# 1. Check current state
python3 -c "
import json
with open('data.json') as f:
    data = json.load(f)
    recent = [m for m in data['movies'] if m.get('digital_date', '') >= '2025-10-01']
    print(f'Recent movies (since Oct 1): {len(recent)}')
    if recent:
        latest = max(m.get('digital_date', '') for m in recent)
        print(f'Latest digital_date: {latest}')
"

# 2. Check tracking database for new discoveries
python3 -c "
import json
with open('movie_tracking.json') as f:
    db = json.load(f)
    available = sum(1 for m in db.values() if m.get('status') == 'available')
    tracking = sum(1 for m in db.values() if m.get('status') == 'tracking')
    print(f'Total: {len(db)}, Available: {available}, Tracking: {tracking}')
"

# 3. Run full regeneration locally to break the cycle
python3 generate_data.py --full

# 4. Verify new data.json has recent movies
python3 -c "
import json
with open('data.json') as f:
    data = json.load(f)
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    recent = [m for m in data['movies'] if m.get('digital_date', '') >= cutoff]
    print(f'Movies in last 7 days: {len(recent)}')
"

# 5. Commit the updated data.json
git add data.json
git commit -m "Fix: Regenerate data.json to break validation cycle"
git push

# 6. Next automated run should succeed
```

#### Debug discovery issues:

```bash
# Run discovery manually to see what's being found
python3 generate_data.py --discover

# Check discovery output
git diff movie_tracking.json

# If no new movies discovered:
# - Check TMDB API is returning results
# - Verify date range in discovery logic
# - Check for filtering that's too aggressive
```

**Prevention:**
- Monitor workflow success rate - investigate after 2 consecutive failures
- Consider loosening validation temporarily during debugging
- Add alerting for extended validation failures

**See Also:**
- [Post-mortem: Nov 3, 2025](../museum_legacy/troubleshooting/2025-11-03-workflow-status.md#2-daily-update-workflow)

---

### 3. Workflow Timeout / 2+ Hour Runtimes

**Symptoms:**
- Workflow runs for 2+ hours instead of expected 30 seconds
- GitHub Actions timeout (workflow killed after max duration)
- Excessive API calls (hundreds or thousands)
- Processing hundreds of movies instead of 5-10

**Root Causes:**
1. **Branch divergence** - Bot running on stale code (common Oct 25-Nov 5, 2025)
2. **Enrichment logic broken** - Not respecting `enriched` flag
3. **Cache invalidation** - Enrichment cache cleared or corrupted
4. **`--full` flag accidentally used** - Full regeneration instead of incremental

**Solutions:**

```bash
# 1. Check if branches are diverged
git fetch origin
git log main..automation-updates --oneline
git log automation-updates..main --oneline

# 2. If diverged, sync immediately
git checkout automation-updates
git merge origin/main --no-edit
git push origin automation-updates

# 3. Check enrichment stats in movie_tracking.json
python3 -c "
import json
with open('movie_tracking.json') as f:
    db = json.load(f)
    enriched = sum(1 for m in db.values() if m.get('enriched'))
    total = len(db)
    print(f'Enriched: {enriched}/{total} ({enriched/total*100:.1f}%)')
"

# 4. If cache is broken, regenerate incrementally (not --full)
python3 generate_data.py  # Should only process new movies

# 5. Monitor runtime
time python3 generate_data.py
# Expected: < 1 minute for incremental
# Problem: > 10 minutes indicates full enrichment running
```

**Prevention:**
- Automatic sync added to workflows (Nov 5, 2025) - see [AUTOMATION_BRANCH_WORKFLOW.md](AUTOMATION_BRANCH_WORKFLOW.md#24-critical-failure-mode---branch-divergence)
- Monitor workflow runtime in GitHub Actions
- Alert on runtimes > 5 minutes

**See Also:**
- [SYSTEM_ARCHITECTURE.md Section 2.4](../SYSTEM_ARCHITECTURE.md) - Branch divergence failure mode

---

### 4. Watchmode API Quota Exhausted

**Symptoms:**
- Warning: `Provider coverage too low: X < 5`
- Most movies have no watch links (streaming/rent/buy)
- Only 1-5 movies out of 80+ have provider links
- Validation fails on provider coverage check

**Root Causes:**
- Watchmode API free tier: 1000 calls/month
- Quota typically exhausts around day 26-28 of month
- Won't reset until 1st of next month
- Without Watchmode, agent scraper only covers 4-5 platforms

**Solutions:**

#### Temporary fix (until quota resets):

```bash
# Lower provider coverage threshold temporarily
gh secret set MIN_PROVIDER_COVERAGE --body "1"

# Workflow will now succeed with minimal coverage
```

#### After quota resets (1st of month):

```bash
# Restore normal threshold
gh secret set MIN_PROVIDER_COVERAGE --body "10"

# Or disable the check entirely
gh secret set MIN_PROVIDER_COVERAGE --body "0"
```

#### Check quota status:

```bash
# Look for Watchmode API usage in logs
grep -i "watchmode" logs/*.log

# Check watchmode_quota.json if it exists
cat watchmode_quota.json
```

**Prevention:**
- Monitor Watchmode API usage weekly
- Consider upgrading to paid tier ($249/month) if needed
- Implement additional fallback scrapers for popular platforms
- Cache watch links for longer (currently 30 days)

**Long-term Solutions:**
- Reduce Watchmode API calls through better caching
- Add more agent scrapers (currently: Netflix, Disney+, HBO Max, Hulu)
- Consider alternative APIs or scraping strategies

**See Also:**
- [Post-mortem: Oct 28, 2025](../museum_legacy/troubleshooting/2025-10-28-workflow-failures.md#issue-2-daily-update-workflow-failure)

---

### 5. Branch Divergence

**Symptoms:**
- Automation runs on old code
- Features you added aren't being used by the bot
- Merge conflicts when trying to sync branches
- `automation-updates` is X commits behind `main`

**Root Causes:**
- User commits to `main` but bot doesn't sync before running
- Manual intervention broke the sync cycle
- Workflow checkout logic incorrect

**Solutions:**

See [AUTOMATION_BRANCH_WORKFLOW.md - Branch Divergence Prevention](AUTOMATION_BRANCH_WORKFLOW.md#branch-divergence-prevention) for complete details.

**Quick fix:**

```bash
# Check divergence
git log main..automation-updates --oneline
git log automation-updates..main --oneline

# Sync automation-updates with main
git checkout automation-updates
git merge origin/main --no-edit
git push origin automation-updates
```

**Prevention:**
- Automatic sync now built into workflows (Nov 5, 2025)
- Run `./sync_daily_updates.sh` regularly to merge automation data into main
- Both directions stay in sync automatically

---

## General Debugging Commands

### Check Workflow Status

```bash
# List recent runs
gh run list --workflow="Daily NRW Update" --limit 5
gh run list --workflow="YouTube Playlists" --limit 5

# View specific run logs
gh run view <run-id> --log

# Watch a running workflow
gh run watch
```

### Local Testing

```bash
# Test daily orchestrator
python3 daily_orchestrator.py

# Test data generation
python3 generate_data.py

# Test YouTube playlist manager
python3 youtube_playlist_manager.py test
python3 youtube_playlist_manager.py weekly --dry-run

# Check data quality
python3 -c "
import daily_orchestrator
daily_orchestrator.NRWOrchestrator().validate_data_quality()
"
```

### Data Inspection

```bash
# Check data.json stats
python3 -c "
import json
from datetime import datetime, timedelta
with open('data.json') as f:
    data = json.load(f)
    total = len(data['movies'])
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    recent = [m for m in data['movies'] if m.get('digital_date', '') >= cutoff]
    with_links = [m for m in data['movies'] if m.get('watch_links', {}).get('streaming')]
    print(f'Total movies: {total}')
    print(f'Recent (7d): {len(recent)}')
    print(f'With watch links: {len(with_links)}')
"

# Check movie_tracking.json stats
python3 -c "
import json
with open('movie_tracking.json') as f:
    db = json.load(f)
    total = len(db)
    available = sum(1 for m in db.values() if m.get('status') == 'available')
    enriched = sum(1 for m in db.values() if m.get('enriched'))
    print(f'Total in tracking: {total}')
    print(f'Available: {available}')
    print(f'Enriched: {enriched}')
"
```

---

## Escalation Path

If troubleshooting doesn't resolve the issue:

1. **Check historical post-mortems** in [museum_legacy/troubleshooting/](../museum_legacy/troubleshooting/)
2. **Review architecture docs** in [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md)
3. **Examine workflow configuration** in [AUTOMATION_BRANCH_WORKFLOW.md](AUTOMATION_BRANCH_WORKFLOW.md)
4. **Check recent code changes** - `git log --oneline -20`
5. **Run workflows with debug logging** (if available)
6. **File a GitHub issue** with detailed logs and symptoms

---

## Historical Post-Mortems

Detailed debugging sessions with timestamps:

- [2025-11-03: YouTube + Daily Update Failures](../museum_legacy/troubleshooting/2025-11-03-workflow-status.md)
- [2025-10-28: Workflow Failures Fix](../museum_legacy/troubleshooting/2025-10-28-workflow-failures.md)

These documents contain:
- Specific error messages and stack traces
- Step-by-step debugging process
- Exact commands used to diagnose and fix
- Lessons learned and prevention strategies
