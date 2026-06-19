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
- Discovery: how many movies polled, plus the two transition numbers below — show BOTH, labeled. The raw count is inflated whenever a local run put films on the wall before CI transitioned them, so it is not "new things that happened":

```bash
/usr/bin/python3 -c "
import json
data = json.load(open('data.json'))
ms = data['movies'] if isinstance(data, dict) else data
disc = json.load(open('metrics/discovery_run.json'))
run_date = disc.get('timestamp', '')[:10]
new_today = [m for m in ms if str(m.get('_discovered_at', ''))[:10] == run_date]
print(f'Total transition events: {disc.get(\"total_transitions\", 0)} (raw — includes films a local run already put on the wall, re-counted by CI)')
print(f'Genuinely new today (first appeared on the wall this run): {len(new_today)}')
for m in sorted(new_today, key=lambda m: not m.get('is_slop')):
    print(f'  • {m.get(\"title\")} ({m.get(\"year\")}) — {\"SLOP\" if m.get(\"is_slop\") else \"shown\"}')
"
```
- Enrichment: movies requested / enriched / deferred and duration (from enrichment_run.json)
  - **Deferred breakdown**: from `deferred_details` in enrichment_run.json — show as a table with columns: Title | Digital Date | Discovered | Reverts | Platforms | Reason. List all titles grouped by reason. Use date-only format (strip timestamps to YYYY-MM-DD). Column notes: "Discovered" = `discovered_at`, "Reverts" = `revert_count` (how many times reverted), "Platforms" = prefer `jw_platforms` (what JustWatch saw at revert time — the accurate source), fall back to `tmdb_platforms` (what TMDB says have it), show "—" if both empty.
    - **3-day window**: Only show JW revert deferrals (`jw_revert:justwatch_no_match` and `jw_revert:justwatch_no_valid_offers`) if `discovered_at` is within the last 3 days. After 3 days, exclude them — they're either dead ends or chronic. All other deferral reasons (timeout, error, not_in_data_json, etc.) always show.
    - After the table, add a summary line: "N deferrals hidden (aged out past 3-day window)"
- Any failures or warnings (from run_diagnostics.json `failures` and `warnings`)

### Stall Detection
- From run_diagnostics.json `stall_status`: is the pipeline stalled? How many days without transitions?

### New Arrivals

Run this script — reads exact field paths, no guessing:

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta

data = json.load(open('data.json'))
today = str(date.today())

try:
    sess = json.load(open('.claude/last_nrw_session.json'))
    from_date = sess['timestamp'][:10]
except Exception:
    from_date = str(date.today() - timedelta(days=1))

arrivals = [m for m in data['movies']
            if from_date <= m.get('digital_date', '') <= today]
arrivals.sort(key=lambda m: m.get('digital_date', ''), reverse=True)

if not arrivals:
    print(f'No new arrivals since {from_date}')
else:
    print(f'{len(arrivals)} arrival(s) since {from_date}:')
    for m in arrivals:
        title = m.get('title', '?')
        year = m.get('year', '?')
        rt = m.get('rt_score') or '--'
        streaming = [s['service'] for s in m.get('watch_links', {}).get('streaming', [])]
        vod = [v['service'] for v in m.get('watch_links', {}).get('vod', [])]
        services = streaming + vod
        trailer_hosted = bool(m.get('links', {}).get('trailer_hosted', ''))
        trailer_yt = bool(m.get('links', {}).get('trailer', ''))
        has_links = bool(streaming or vod)
        plex_only = services == ['Plex']
        t_flag = 'trailer:hosted' if trailer_hosted else ('trailer:YT' if trailer_yt else '⚠ NO TRAILER')
        l_flag = ('⚠ PLEX ONLY' if plex_only else 'links:ok') if has_links else '⚠ NO LINKS'
        svc = ', '.join(services) if services else '—'
        print(f'  • {title} ({year}) — {svc} | RT:{rt} | {t_flag} | {l_flag}')
"
```

### Concerns
- Any failures or warnings from run_diagnostics.json `failures` and `warnings`
- Any `⚠ NO TRAILER` from the New Arrivals script above
- Any `⚠ NO LINKS` or `⚠ PLEX ONLY` from the New Arrivals script above
- Trailer hosting failures from launchagent log
- **Pull quote gaps**: check `cache/pull_quotes_combined.json` — for each new arrival, look up `"{title}_{year}"`. If a movie is absent from the cache entirely, flag it: `⚠ [Title] — no pull quotes scraped (morning batch missed it)`
- If no concerns, say "No concerns."

### Data Quality Snapshot (LIVE from data.json)
Run `/wallhealth` and present the full report in the chat. Do NOT read from run_diagnostics.json for these numbers.

### Curation
After the report, run `/curate` to curate new arrivals (staff picks, sections, pull quotes, capsules).
