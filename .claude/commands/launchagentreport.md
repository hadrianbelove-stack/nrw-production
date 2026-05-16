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
- **Trailer hosting failures**: Recent failures with reasons.

Format as a short summary (not raw log). Flag any failures or concerns clearly.

### Pull Quote Curation

After the report, curate pull quotes for any new movies. Follow these steps:

1. **Find the window**: Read `.claude/last_nrw_session.json` to get the last session timestamp. If the file doesn't exist, default to 7 days ago.

2. **Find candidates**: From `data.json`, find movies where ALL of these are true:
   - `digital_date` is after the last session timestamp
   - Movie has an `rt_score`
   - Movie does NOT already have a `pull_quotes` array
   - Movie is NOT a reissue/restoration (`is_restoration` flag, or title contains "Remaster"/"Restoration"/"4K", or `year` is 10+ years before current year suggesting a classic re-release)

3. **If no candidates**: Report "No new movies need pull quotes since last session." and stop.

4. **If candidates exist**:
   - Check `cache/pull_quotes_cache.json` for existing scraped quotes
   - Scrape any uncached movies using `GeminiPullQuoteFinder` from `gemini_scraper.pull_quotes`
   - Present each movie **one at a time, most recent first**, showing:
     - Movie title, year, RT score, digital date
     - All quotes numbered, with full text, critic name, and outlet
   - Wait for user response: numbers to select, "skip", or trimmed text (an edit)
   - **When the user shortens a quote, that trimmed text IS the final version** — they are editing
   - For reissues/restorations: only show quotes specifically about the reissue, not original-era reviews
   - After all movies are curated, inject selected quotes into `data.json` using the same logic as `pipeline/display.py`'s `inject_selected_pull_quotes()`

### Capsule Rewrites

After pull quotes are done, rewrite capsules for new arrivals. Follow these steps:

1. **Same window as pull quotes**: Use the last session timestamp from `.claude/last_nrw_session.json`.

2. **Find candidates**: From `data.json`, find movies where ALL of these are true:
   - `digital_date` is after the last session timestamp
   - Movie is NOT already in `cache/approved_capsules.json`
   - Movie is NOT a reissue/restoration (`is_restoration` flag, or title contains "Remaster"/"Restoration"/"4K", or `year` is 10+ years before current year)

3. **If no candidates**: Report "No new movies need capsules since last session." and stop.

4. **If candidates exist**, process each movie **one at a time, most recent first**:
   - Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "TITLE" --force --variants 3 --skip-verify`
   - Present 3 variants with word counts (use the same format as `/capsule`)
   - Wait for user response: pick a number, provide a rewrite, or "skip"
   - **When the user provides edited text, that IS the final version** — they are editing
   - If picked/rewritten:
     1. Apply standard capsule formatting (**bold** names, *italic* titles)
     2. Write final text to `cache/rewrite.txt`
     3. Run: `cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "TITLE" --file cache/rewrite.txt`
     4. Commit + push: `cd /Users/hadrianbelove/Downloads/nrw-production && git add data.json cache/approved_capsules.json cache/capsule_cache.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && git push origin main`
   - After each movie, move to the next candidate
