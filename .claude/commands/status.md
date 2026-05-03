---
description: Show git status, movie counts, and pipeline metrics
---

Show NRW system status dashboard:

1. Git status: `git status --short`
2. Recent commits: `git log --oneline -5`
3. Movie counts:
   - Total in data.json: `jq '.movies | length' data.json`
   - In tracking: `jq '[.movies | to_entries[] | select(.value.status == "tracking")] | length' movie_tracking.json`
4. Intake health (compute from movie_tracking.json + metrics/intake_run.json):
   - Last intake run: timestamp + total intaked (from metrics/intake_run.json)
   - 7-day intake volume: count entries in movie_tracking.json where `intake_date` is within last 7 days
5. Today's metrics (if exists):
   - `cat metrics/newly_available.json 2>/dev/null | jq '{date, count}' || echo "No pending enrichments"`
6. Last pipeline run: `ls -la metrics/*.json | head -5`

Format as a clean dashboard summary.
