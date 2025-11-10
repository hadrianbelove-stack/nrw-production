# Admin Diagnostics Guide

## Overview

⚠️ **Note**: Daily automation proceeds ungated by default, with waiting/rejection only when optional review is enabled. This guide explains how to read and analyze admin metrics when optional review mode is used.

This guide explains how to read and analyze admin metrics and delta summaries from the optional admin review system. Use this to understand approval patterns, identify data quality issues, and correlate admin actions with system behavior when editorial curation is enabled.

## Where Metrics Live

### `metrics/daily.jsonl`
Location of structured admin metrics data. When optional review mode is enabled, each approval creates one JSON line with the following fields:

- `date`: UTC date of approval (YYYY-MM-DD)
- `timestamp`: Full ISO timestamp of approval
- `reviewer`: Username of admin who approved changes
- `session_seconds`: Session duration (currently null, tracked in future)
- `movies_reviewed`: Total number of movies reviewed in approval session
- `edits`: Number of field edits made during session (currently 0, tracked in future)
- `additions`: Number of movies manually added during session (currently 0, tracked in future)
- `hidden`: Count of movies currently hidden from display
- `featured`: Count of movies currently featured

## Testing Scenarios

### Simulation Script

Use `ops/simulate_scenarios.sh` to test various approval gate scenarios:

```bash
# Test low watch links coverage validation
./ops/simulate_scenarios.sh low-coverage

# Test missing review config behavior
./ops/simulate_scenarios.sh missing-review-config

# Test stale review config validation
./ops/simulate_scenarios.sh stale-review-config

# Run validation without making changes
./ops/simulate_scenarios.sh dry-run

# Restore original state after testing
./ops/simulate_scenarios.sh restore
```

### Testing Workflow

1. **Prepare scenario** - Run simulation script with desired scenario
2. **Execute test** - Run `python3 daily_orchestrator.py`
3. **Observe behavior** - Check logs for expected validation behavior
4. **Restore state** - Run `./ops/simulate_scenarios.sh restore`

### Expected Behaviors (When Optional Review Mode is Enabled)

- **Low coverage**: Orchestrator should fail with link coverage error
- **Missing review config**: If optional review mode is enabled, orchestrator should wait for admin approval
- **Stale review config**: If optional review mode is enabled, orchestrator should reject old timestamps
- **Dry run**: Full validation without committing changes

### Additional Metrics Fields

- `ordered`: Count of movies with editorial ordering applied
- `issues`: Object containing counts of data quality issues by type

### `admin/approval.json`
Most recent approval artifact (when optional review mode is enabled) containing:
- `timestamp`: When approval was created
- `reviewer`: Who approved the changes
- `tracking_digest`: SHA-256 hash of movie_tracking.json for validation
- `delta`: Same structure as metrics entry

### `diary/YYYY-MM-DD.md`
Daily diary entries with admin delta summaries appended in markdown format. Each approval adds a timestamped entry with JSON delta data.

## How to Read an Approval Line

Example metrics entry:
```json
{
  "date": "2025-11-07",
  "timestamp": "2025-11-07T14:30:45.123456",
  "reviewer": "admin",
  "session_seconds": null,
  "movies_reviewed": 245,
  "edits": 0,
  "additions": 0,
  "hidden": 12,
  "featured": 8,
  "ordered": 5,
  "issues": {
    "missing_rt": 45,
    "missing_trailer": 23,
    "missing_stream_link": 67,
    "missing_rent_link": 89,
    "missing_buy_link": 134
  }
}
```

**Interpretation:**
- Admin reviewed 245 movies and approved publication at 2:30 PM UTC
- 12 movies are hidden from display, 8 are featured
- 5 movies have editorial ordering applied
- Data quality issues: 45 movies missing RT scores, 67 missing streaming links

## Common Patterns

### High Hidden Count
**Pattern:** `"hidden": 50+`
**Indicates:** Low link coverage or quality issues in scraped data
**Action:** Review hidden movies in admin panel, check scraper health

### High Missing Stream Links
**Pattern:** `"missing_stream_link": 100+`
**Indicates:** Provider API issues or geographic availability problems
**Action:** Check Watchmode API status, review provider coverage

### High Missing RT Scores
**Pattern:** `"missing_rt": 30+`
**Indicates:** Rotten Tomatoes scraper issues or new movies without reviews
**Action:** Check RT scraper functionality, consider manual RT link additions

### Zero Movies Reviewed
**Pattern:** `"movies_reviewed": 0`
**Indicates:** No data.json generated or approval on empty dataset
**Action:** Check if discovery phase ran successfully

### High Featured Count
**Pattern:** `"featured": 20+`
**Indicates:** Active editorial curation, possible newsletter preparation
**Action:** Normal editorial workflow

## How to Correlate with approval.json

1. **Timestamp Matching**: approval.json timestamp should match latest metrics entry
2. **Digest Validation**: tracking_digest provides movie_tracking.json integrity check
3. **Delta Consistency**: approval.json delta should match metrics entry fields

Example correlation check:
```bash
# Get latest approval timestamp
jq -r '.timestamp' admin/approval.json

# Find matching metrics entry
tail -1 metrics/daily.jsonl | jq -r '.timestamp'
```

## Quick jq/grep Examples

### Get approval count by reviewer
```bash
jq -r '.reviewer' metrics/daily.jsonl | sort | uniq -c
```

### Find approvals with high hidden counts
```bash
jq 'select(.hidden > 20)' metrics/daily.jsonl
```

### Get average movies reviewed per approval
```bash
jq -s 'map(.movies_reviewed) | add/length' metrics/daily.jsonl
```

### Find approvals with missing data issues
```bash
jq 'select(.issues.missing_rt > 30 or .issues.missing_stream_link > 50)' metrics/daily.jsonl
```

### Get daily approval frequency
```bash
jq -r '.date' metrics/daily.jsonl | sort | uniq -c
```

### Find latest approval status
```bash
tail -1 metrics/daily.jsonl | jq '.'
```

### Check for approval gaps
```bash
jq -r '.date' metrics/daily.jsonl | sort | uniq | tail -10
```

## Reference Documentation

- **[NRW_DATA_WORKFLOW_EXPLAINED.md](../../NRW_DATA_WORKFLOW_EXPLAINED.md)** - Phase 3: Manual Review & Quality Gate
- **[ADMIN_WORKFLOW.md](../../ADMIN_WORKFLOW.md)** - Complete admin panel workflow and approval gate documentation
- **[admin.py](../../admin.py)** - `/approve` route implementation (lines 1799-1921)

## Troubleshooting Common Issues

### Missing Metrics Entries
**Symptom:** No entries in daily.jsonl for recent dates
**Cause:** Optional review mode not enabled or admin panel not used
**Solution:** Enable optional review mode if needed, or run `./launch_all.sh` and use "Approve & Generate" button

### Inconsistent Delta Data
**Symptom:** Metrics entry doesn't match approval.json
**Cause:** Race condition or partial write failure
**Solution:** Check logs/admin.log for write errors, re-approve if necessary

### High Issue Counts
**Symptom:** Consistently high missing_* counts across approvals
**Cause:** Upstream scraper failures or API issues
**Solution:** Review generate_data.py logs, check external API status

### Zero Session Data
**Symptom:** All entries show null session_seconds, 0 edits/additions
**Cause:** Session tracking not yet implemented
**Solution:** Future enhancement - currently expected behavior