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
    - **3-day window**: Only show JW revert deferrals (`jw_revert:justwatch_no_match` and `jw_revert:justwatch_no_valid_offers`) if `discovered_at` is within the last 3 days. After 3 days, exclude them — they're either dead ends or chronic. All other deferral reasons (timeout, error, not_in_data_json, etc.) always show.
    - After the table, add a summary line: "N deferrals hidden (aged out past 3-day window)"
- Any failures or warnings (from run_diagnostics.json `failures` and `warnings`)

### Stall Detection
- From run_diagnostics.json `stall_status`: is the pipeline stalled? How many days without transitions?

### Concerns
- Aggregate any failures or warnings from run_diagnostics.json
- Note any enrichment gaps for today's arrivals
- Flag trailer hosting failures
- If no concerns, say "No concerns."

### Data Quality Snapshot (LIVE from data.json)
Run `/wallhealth` and present the full report in the chat. Do NOT read from run_diagnostics.json for these numbers.

### Curation
After the report, run `/curate` to curate new arrivals (staff picks, sections, pull quotes, capsules).
