---
description: Check today's launchagent run — git pull + trailer hosting results
---

Show the result of today's local launchagent run. Read ALL of the following:

1. `logs/launchagent.log` — read the last 150 lines (use offset to get the tail)
2. `metrics/run_diagnostics.json` — CI pipeline summary + data quality
3. `metrics/discovery_run.json` — discovery results
4. `metrics/enrichment_run.json` — enrichment results
5. `metrics/intake_run.json` — intake results

Then report these sections:

### Launchagent Run
- Did it run today? (look for today's date in the log)
- Git pull result: was CI data current, or did it pull new commits?
- Trailer hosting results: how many hosted / failed / skipped?
- For each failure or skip: movie title + reason (e.g. "paywalled", "region locked", "timed out")
- For each success: movie title
- Final status line and timestamp

### CI Pipeline Summary (from run_diagnostics.json)
- Overall success/failure and total duration
- Intake (from intake_run.json):
  - Total intaked: `results.total_intaked` (films: `results.intaked`, miniseries: `results.miniseries_intaked`)
  - Scan window: `scan_window.start_date` to `scan_window.end_date` (`scan_window.mode`)
  - Duplicates skipped: `results.duplicates_skipped`, blocked: `results.blocked_by_filter`
- Discovery: how many movies polled, how many transitions (from discovery_run.json)
- Enrichment: movies requested / enriched / deferred and duration (from enrichment_run.json)
  - **Deferred breakdown**: from `deferred_details` in enrichment_run.json, list each movie title and reason (e.g. "jw_revert:justwatch_no_match", "zero_watch_links", "timeout")
- Any failures or warnings (from run_diagnostics.json `failures` and `warnings`)

### Stall Detection
- From run_diagnostics.json `stall_status`: is the pipeline stalled? How many days without transitions?

### Concerns
- Aggregate any failures or warnings from run_diagnostics.json
- Note any enrichment gaps for today's arrivals
- Flag trailer hosting failures
- If no concerns, say "No concerns."

### Data Quality Snapshot (LIVE from data.json)
Run the shared wall health script (do NOT read from run_diagnostics.json for these numbers):

```bash
python3 scripts/wall_health.py
```

Report these numbers in a formatted summary:

- **Coverage**: RT scores, MC scores, Wikipedia, Trailers (count + percentage)
- **Today's arrivals**: present as a table with columns: Movie | RT | MC | Wiki | Trailer | IMDb | Links (use `yes`/`--` for each field). The `wall_health.py` script outputs this format directly — present it as-is.
- **Last 7 days**: daily arrival counts
- **Upcoming**: pre-orders with no links yet (expected)
- **Zero watch links**: Each movie shows its digital date, days on wall, and a detailed status explaining WHY it has no links (JW revert reason, which excluded platform, TMDB platform info, revert count). A CRITICAL alert (>5%) means the pipeline is likely broken. Movies age out of this section after 3 days — only new/recent zero-link movies are shown.
- **JW REVERTED (tracking only)**: movies discovered and reverted but NOT on the wall — safely in tracking, just FYI.
- Movies reverted for "excluded platforms" should always name which platform (fuboTV, Philo, etc.). If not recorded, the report says so explicitly.

Format as a short summary (not raw log). Flag any failures or concerns clearly.
