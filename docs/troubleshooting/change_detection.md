# Change Detection Troubleshooting Guide

## Overview

The change detection system monitors all tracking movies in `movie_tracking.json` and detects when they become digitally available by polling TMDB providers API. This guide helps debug when the system finds 0 transitions or isn't working as expected.

## Symptoms

Common signs that change detection isn't working:

- Provider check finds 0 transitions despite known releases
- Movies stuck in "tracking" status that should be "available"
- Log shows "Found 0 tracking movies" or "Checking 0 movies"
- No "✓ now on [service]" messages in logs
- High false negative rate (missing actual availability)

## Quick Checks (Most Common Test Blockers)

### 1. API Keys Validation

**Most common blocker**: Missing or invalid TMDB API key

```bash
# Check TMDB API key is set
echo $TMDB_API_KEY
# Should show your API key, not empty

# Test TMDB API directly with known movie (The Matrix = 603)
curl -s "https://api.themoviedb.org/3/movie/603/watch/providers?api_key=$TMDB_API_KEY" | jq '.results.US'
# Should return 200 with US provider data, not 401 unauthorized

# Quick fix if missing:
export TMDB_API_KEY="99b122ce7fa3e9065d7b7dc6e660772d"
export WATCHMODE_API_KEY="bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp"
```

### 2. Admin Approval Freshness (Orchestrator Blocker)

**Second most common blocker**: Stale or missing admin approval

```bash
# Check if approval exists and is fresh (≤2h)
python3 -c "
import json
from datetime import datetime, timezone
try:
    with open('admin/approval.json', 'r') as f:
        approval = json.load(f)
    timestamp = datetime.fromisoformat(approval['timestamp'].replace('Z', '+00:00'))
    age_hours = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
    print(f'Approval age: {age_hours:.1f} hours (max 2 hours)')
    print(f'Valid: {age_hours <= 2}')
    print(f'Reviewer: {approval.get(\"reviewer\", \"N/A\")}')
except Exception as e:
    print(f'No approval found: {e}')
"

# Quick fix - create fresh approval:
python3 -c "
import json, hashlib
from datetime import datetime, timezone
with open('movie_tracking.json', 'rb') as f:
    digest = hashlib.sha256(f.read()).hexdigest()
approval = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'approved': True,
    'tracking_digest': digest,
    'reviewer': 'test-admin',
    'session_seconds': 60
}
with open('admin/approval.json', 'w') as f:
    json.dump(approval, f, indent=2)
print('Fresh approval created')
"
```

### 3. Working Directory Issues (CI/Local Blocker)

**Third most common blocker**: Wrong working directory

```bash
# Verify you're in the right directory
ls -la movie_tracking.json data.json config.yaml 2>/dev/null || echo "Missing required files"
pwd

# Quick fix for wrong directory:
export NRW_FORCE_CWD=/Users/hadrianbelove/Downloads/nrw-production
cd /Users/hadrianbelove/Downloads/nrw-production
```

### 4. TMDB Provider API Test

```bash
# Test provider lookup for a specific movie (example: TMDB ID 550)
curl "https://api.themoviedb.org/3/movie/550/watch/providers?api_key=$TMDB_API_KEY"
# Should return 200 with provider data for different countries
```

### 3. Offline Test for Specific Movie

Run a quick test for a known available movie:

```python
import requests
import json

# Replace with your API key and a known TMDB ID
api_key = "YOUR_TMDB_API_KEY"
tmdb_id = "550"  # Fight Club example

url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"
response = requests.get(url, params={"api_key": api_key})

if response.status_code == 200:
    data = response.json()
    print(f"Providers for TMDB {tmdb_id}:")
    print(json.dumps(data, indent=2))
else:
    print(f"Error: {response.status_code} - {response.text}")
```

## DB State Verification

### Before Run Check

Verify movies are in correct state before running change detection:

```bash
# Count tracking vs available movies
jq '.movies | to_entries | map(select(.value.status == "tracking")) | length' movie_tracking.json
jq '.movies | to_entries | map(select(.value.status == "available")) | length' movie_tracking.json

# Show sample tracking movies
jq '.movies | to_entries | map(select(.value.status == "tracking")) | .[0:5] | .[] | {title: .value.title, tmdb_id: .key, status: .value.status, digital_date: .value.digital_date}' movie_tracking.json

# Check for null digital_date in tracking movies
jq '.movies | to_entries | map(select(.value.status == "tracking" and .value.digital_date != null)) | length' movie_tracking.json
# Should be 0 - tracking movies should have null digital_date
```

### After Run Check

Compare state after change detection:

```bash
# Count newly available movies (digital_date = today)
today=$(date +%Y-%m-%d)
jq --arg today "$today" '.movies | to_entries | map(select(.value.status == "available" and .value.digital_date == $today)) | length' movie_tracking.json

# Show newly detected movies
jq --arg today "$today" '.movies | to_entries | map(select(.value.status == "available" and .value.digital_date == $today)) | .[] | {title: .value.title, tmdb_id: .key, digital_date: .value.digital_date, providers: .value.providers}' movie_tracking.json
```

## Log Analysis

### Key Log Patterns to Grep

Search for these patterns in your logs:

```bash
# Check discovery/monitoring summary
grep "Found .* tracking" *.log
# Should show "Found X tracking movies to check"

# Check individual movie checks
grep "Checking.*for digital availability" *.log
# Should show individual movie checks

# Check successful detections
grep "✓.*now on" *.log
# Should show "✓ [Movie] now on [service]" for successful detections

# Check API errors
grep "Error.*TMDB" *.log
grep "401\|403\|429" *.log
# Look for authentication or rate limit errors
```

### Monitor Progress

```bash
# Real-time monitoring during run
tail -f generate_data.log | grep -E "(Found|Checking|✓|Error)"
```

## Common Pitfalls

### Invalid API Keys

**Symptom**: 401 Unauthorized errors
**Solution**:
1. Verify API key in environment variable
2. Check TMDB dashboard for key status
3. Ensure key has correct permissions

### CI vs Local Environment Mismatch

**Symptom**: Works locally but fails in CI
**Solution**:
1. Check GitHub secrets are properly set
2. Verify environment variable names match
3. Test CI environment variables:
   ```bash
   # In GitHub Actions workflow
   - name: Test API key
     run: echo "API key length: ${#TMDB_API_KEY}"
   ```

### Rate Limiting

**Symptom**: 429 Too Many Requests errors
**Solution**:
1. Check rate limiting configuration in `config.yaml`
2. Increase delays between requests
3. Monitor TMDB API usage in their dashboard

### Cache Interference

**Symptom**: Stale results or incorrect data
**Solution**:
1. Clear relevant caches:
   ```bash
   rm cache/watch_links_cache.json
   rm cache/agent_links_cache.json
   ```
2. Force fresh API calls

### Data Corruption

**Symptom**: Movies have wrong status or missing fields
**Solution**:
1. Validate movie_tracking.json structure:
   ```bash
   jq empty movie_tracking.json  # Should return no errors
   ```
2. Check for required fields:
   ```bash
   jq '.movies | to_entries | map(select(.key == null or .value.status == null)) | .[]' movie_tracking.json
   ```

## Expected Performance & Scaling

### Current Runtime

**Normal operation** for provider monitoring (--check phase):

| Database Size | Expected Runtime | Status |
|---------------|------------------|--------|
| **2,608 movies** (Nov 2025) | 8.7-12 minutes | ✅ Normal |
| **5,000 movies** | 16-20 minutes | ✅ Expected |
| **10,000 movies** | 33-40 minutes | ✅ Expected |
| **20,000 movies** | 66-80 minutes | ✅ Expected |
| **50,000 movies** | 2.8-3.5 hours | ✅ Expected |
| **108,000+ movies** | 6+ hours | ⚠️ GitHub Actions timeout |

**Why it takes this long:**
- Rate limiting: 0.2 seconds per movie (5 req/sec)
- 2,608 tracking movies × 0.2s = 521 seconds = 8.7 minutes minimum
- Additional time for API retries, network latency, logging

### API Limits Analysis

**TMDB API limits:**
- ✅ No daily request limits (unlimited)
- ✅ Rate limit: 40-50 requests/second per IP
- ✅ Current implementation: 5 req/sec (10x under limit)

**GitHub Actions constraints:**
- Default timeout: 360 minutes (6 hours)
- Current implementation will NOT timeout until ~100,000+ movies
- At current growth rates, this is decades away

### When to Optimize

Consider optimization when:
1. **Database exceeds 10,000 tracking movies** (30-40 minute runtime)
2. **CI/CD pipeline blocks other workflows** (long queue times)
3. **Manual runs become disruptive** (affects development velocity)

**Optimization strategies** (defer until needed):
- Time-windowed checking (only movies released within N days)
- Daily batch limits (check max X movies per run)
- Parallel processing (multiple workers with rate limiting)
- Incremental checking (rotate through database in chunks)

### Performance Is Not a Bug

**Important:** Long runtimes (9-15 minutes) are EXPECTED BEHAVIOR, not performance issues. The system:
- Polls every tracking movie daily to detect availability changes
- Cannot rely on external "release date" APIs (they don't exist for digital)
- Uses rate limiting to respect TMDB's infrastructure
- Trades speed for reliability and completeness

Do not attempt to "fix" performance unless database exceeds 10,000 movies or CI pipeline is blocked.

## When to Escalate

Escalate to development team when:

1. **API Keys Valid But Still Failing**: TMDB returns 200 but no providers detected for known available movies
2. **Systematic Detection Failure**: 0 transitions over multiple days despite known releases
3. **Data Corruption**: Movie tracking database shows inconsistent state that basic validation can't fix
4. **Unexpected Timeout**: Change detection timing out in GitHub Actions (indicates >6 hours runtime or database corruption)
5. **Log Analysis Inconclusive**: No clear error patterns but system not working

When escalating, include:
- Recent log files
- Output of quick checks above
- Sample of movie_tracking.json state
- Specific TMDB IDs that should be detected but aren't
- Environment details (local vs CI, API key status)

## Test Cleanup & Backup Restoration

### Restore Pre-Test State

If you need to revert test changes and restore the original data:

```bash
# List available backups
ls -la backups/*.backup-*

# Restore movie_tracking.json from most recent backup
LATEST_BACKUP=$(ls -t backups/movie_tracking.backup-*.json | head -1)
echo "Restoring from: $LATEST_BACKUP"
cp "$LATEST_BACKUP" movie_tracking.json

# Restore data.json from most recent backup
LATEST_DATA_BACKUP=$(ls -t backups/data.backup-*.json | head -1)
echo "Restoring from: $LATEST_DATA_BACKUP"
cp "$LATEST_DATA_BACKUP" data.json

# Clean up test artifacts
rm -f admin/approval.json
rm -f admin/ordering.json

# Remove test diary entries (if created)
TODAY=$(date +%Y-%m-%d)
if [ -f "diary/${TODAY}.md" ]; then
    echo "Consider removing test diary entry: diary/${TODAY}.md"
fi
```

### Create Pre-Test Backups

Before running tests, always create timestamped backups:

```bash
# Create timestamped backups
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p backups/
cp movie_tracking.json "backups/movie_tracking.backup-${TIMESTAMP}.json"
cp data.json "backups/data.backup-${TIMESTAMP}.json"
echo "Backups created with timestamp: $TIMESTAMP"
ls -la backups/*${TIMESTAMP}*
```

### Backup Verification

Verify backups before proceeding with tests:

```bash
# Verify backup file sizes match originals
ls -la movie_tracking.json backups/movie_tracking.backup-*
ls -la data.json backups/data.backup-*

# Verify JSON structure is valid
python3 -c "
import json
try:
    with open('backups/movie_tracking.backup-$(date +%Y%m%d)*.json', 'r') as f:
        json.load(f)
    print('✅ movie_tracking backup is valid JSON')
except:
    print('❌ movie_tracking backup is corrupted')

try:
    with open('backups/data.backup-$(date +%Y%m%d)*.json', 'r') as f:
        json.load(f)
    print('✅ data.json backup is valid JSON')
except:
    print('❌ data.json backup is corrupted')
"
```