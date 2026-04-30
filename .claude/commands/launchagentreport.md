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
- Intake: how many new movies intaked (from intake_run.json `results.total_intaked`)
- Discovery: how many movies polled, how many transitions (from discovery_run.json)
- Enrichment: movies requested / enriched / deferred and duration (from enrichment_run.json)
- Any failures or warnings (from run_diagnostics.json `failures` and `warnings`)

### Stall Detection
- From run_diagnostics.json `stall_status`: is the pipeline stalled? How many days without transitions?

### Data Quality Snapshot (LIVE from data.json)
Compute this LIVE by running the following Python snippet (do NOT read from run_diagnostics.json for these numbers):

```bash
/usr/bin/python3 -c "
import json, sys
from datetime import date
sys.path.insert(0, '.')
from daily_orchestrator import has_real_watch_link
data = json.load(open('data.json'))
movies = data['movies']
total = len(movies)
today = date.today().isoformat()
with_links = sum(1 for m in movies if has_real_watch_link(m))
no_links = [m for m in movies if not has_real_watch_link(m)]
preorders = [m for m in no_links if (m.get('digital_date') or '') > today]
missing = [m for m in no_links if (m.get('digital_date') or '') <= today]
with_rt = sum(1 for m in movies if m.get('links', {}).get('rt'))
with_wiki = sum(1 for m in movies if m.get('links', {}).get('wikipedia'))
with_trailers = sum(1 for m in movies if m.get('links', {}).get('trailer'))
print(f'total={total}')
print(f'with_links={with_links}')
print(f'without_links={len(no_links)}')
print(f'preorders={len(preorders)}')
print(f'missing_links={len(missing)}')
print(f'with_rt={with_rt}')
print(f'with_wiki={with_wiki}')
print(f'with_trailers={with_trailers}')
if preorders:
    print('PREORDERS:')
    for m in sorted(preorders, key=lambda x: x.get('digital_date','')):
        print(f'  {m[\"title\"]} — releasing {m.get(\"digital_date\")}')
if missing:
    print('MISSING_LINKS:')
    for m in sorted(missing, key=lambda x: x.get('digital_date','')):
        print(f'  {m[\"title\"]} — date {m.get(\"digital_date\")}')
today_str = date.today().isoformat()
arrivals = [m for m in movies if m.get('digital_date') == today_str]
gaps_found = []
for a in arrivals:
    mg = []
    lnk = a.get('links', {})
    crw = a.get('crew', {})
    wl = a.get('watch_links', {})
    wl_n = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
    if not lnk.get('trailer') and not lnk.get('trailer_hosted'): mg.append('trailer')
    if not lnk.get('wikipedia'): mg.append('wikipedia')
    if wl_n == 0: mg.append('watch_links')
    if not a.get('rt_score'): mg.append('rt_score')
    if not a.get('imdb_rating'): mg.append('imdb_rating')
    dn = crw.get('director', '')
    if not dn or dn == 'Unknown': mg.append('director')
    if not a.get('country'): mg.append('country')
    if not a.get('year'): mg.append('year')
    if not a.get('runtime'): mg.append('runtime')
    if mg:
        gaps_found.append((a['title'], mg))
if gaps_found:
    print('ENRICHMENT_GAPS (%d of %d arrivals):' % (len(gaps_found), len(arrivals)))
    for t, mg in gaps_found:
        print('  %s — missing: %s' % (t, ', '.join(mg)))
elif arrivals:
    print('ENRICHMENT_GAPS: 0 — all %d arrivals fully enriched' % len(arrivals))
"
```

Report these numbers:
- Total movies on site
- Movies with watch links
- Movies without links, split into:
  - **Pre-orders** (digital_date in the future) — list each title + release date. These are expected to have no links yet.
  - **Missing links** (digital_date in the past) — list each title. These are the ones to investigate/fix.
- Flag if missing_links > 20 as a concern.
- Movies with RT scores
- Movies with Wikipedia summaries
- Movies with trailers (and percentage of total)

### JW Reversions (last 3 days)
Compute this LIVE by running:

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta
three_days_ago = (date.today() - timedelta(days=3)).isoformat()
t = json.load(open('movie_tracking.json'))
jw_reverted = []
for mid, m in t.get('movies', {}).items():
    rev_at = m.get('_jw_reverted_at', '')
    if rev_at >= three_days_ago and m.get('_jw_revert_reason'):
        provs = m.get('providers', {})
        plats = [p for cat in ['rent','buy','streaming'] for p in provs.get(cat, [])]
        jw_reverted.append((rev_at, m.get('title', mid), m['_jw_revert_reason'], plats))
if jw_reverted:
    print(f'JW REVERTED: {len(jw_reverted)} movies discovered but sent back to tracking')
    by_reason = {}
    for rev_at, title, reason, plats in sorted(jw_reverted):
        by_reason.setdefault(reason, []).append((rev_at, title, plats))
    for reason, items in by_reason.items():
        label = {'justwatch_no_valid_offers': 'Only on excluded platforms', 'justwatch_no_match': 'No JustWatch match found'}.get(reason, reason)
        print(f'  [{label}]')
        for rev_at, title, plats in items:
            plat_str = f' ({\", \".join(plats)})' if plats else ''
            print(f'    {rev_at}  {title}{plat_str}')
else:
    print('JW REVERTED: 0 — no reversions in last 3 days')
"
```

Report these numbers:
- Total JW reversions in the last 3 days (first-revert date is preserved, so movies only appear for 3 days after initial reversion)
- Each movie listed with its reversion date, grouped by reason
- Explain that `justwatch_no_valid_offers` means the movie was only on excluded platforms, and `justwatch_no_match` means JustWatch couldn't find it at all
- Note that reversions are healthy — they prevent the wall from showing movies without working links

Format as a short summary (not raw log). Flag any failures or concerns clearly.
