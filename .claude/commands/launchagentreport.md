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
  - **Deferred breakdown**: from `deferred_details` in enrichment_run.json — show as a table with columns: Title | Digital Date | Discovered | Reverts | TMDB Platforms | Reason. List all titles grouped by reason. Use date-only format (strip timestamps to YYYY-MM-DD). Column notes: "Discovered" = `discovered_at`, "Reverts" = `revert_count` (how many times reverted), "TMDB Platforms" = `tmdb_platforms` (what services TMDB says have it).
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

The script outputs a full structured report — present it as-is. Key sections:

- **Coverage**: RT, MC, Wiki, Trailers, IMDb, Links (count + percentage)
- **Pipeline Trend**: 14-day table of daily intake + transitions. Flags stall days (0 transitions) and below-average days.
- **Today's arrivals**: table with columns: Movie | RT | MC | Wiki | Trailer | IMDb | Links | Services. Uses `yes`/`--` for enrichment fields, `NONE` for missing links, and shows which VOD services each movie links to.
- **Zero watch links**: Each movie shows its digital date, days on wall, and a detailed status explaining WHY it has no links (JW revert reason, which excluded platform, TMDB platform info, revert count). A CRITICAL alert (>5%) means the pipeline is likely broken. Movies age out of this section after 3 days.
- **JW REVERTS**: Grouped by reason (summary counts, excluded platform breakdown, repeat offenders reverted 2+ times), then full list with TMDB platforms. Tracking only — not on wall.
- **Pre-orders & upcoming**: All future-dated movies sorted by date with link count and service names. Summary line shows how many have links.
- **Orphans**: Movies that are available in tracking but NOT on the live wall — invisible to enrichment catch-up.
- **Trailer hosting failures**: Recent failures with reasons.

Format as a short summary (not raw log). Flag any failures or concerns clearly.
