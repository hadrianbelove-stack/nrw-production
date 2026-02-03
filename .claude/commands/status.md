---
description: Show git status, movie counts, and pipeline metrics
---

Show NRW system status dashboard:

1. Git status: `git status --short`
2. Recent commits: `git log --oneline -5`
3. Movie counts:
   - Total in data.json: `jq '.movies | length' data.json`
   - In tracking: `jq '[.movies | to_entries[] | select(.value.status == "tracking")] | length' movie_tracking.json`
4. Today's metrics (if exists):
   - `cat metrics/newly_available.json 2>/dev/null | jq '{date, count}' || echo "No pending enrichments"`
5. Last pipeline run: `ls -la metrics/*.json | head -5`

Format as a clean dashboard summary.
