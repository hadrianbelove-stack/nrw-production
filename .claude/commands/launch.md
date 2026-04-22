---
description: Start site (3000) and admin (5556) servers
---

Run the unified launcher script:

```bash
./launch_all.sh
```

This handles everything automatically:
- Kills stale processes
- Verifies servers respond before reporting success
- Opens browsers
- Ctrl+C stops both cleanly

DO NOT manually start servers with `python3 -m http.server` or `python3 admin.py`. Always use the script.

## Post-Launch Report (REQUIRED)

After servers are running, you MUST generate a data quality report in the chat. Do this by running a Python one-liner that reads `data.json` and `metrics/run_diagnostics.json`, then present the results formatted as below.

```bash
python3 -c "
import json
from collections import Counter

d = json.load(open('data.json'))
movies = d['movies']
total = len(movies)

# Today's arrivals
from datetime import date
today = date.today().isoformat()
arrivals = [m for m in movies if m.get('digital_date') == today]

# Last 7 days by date
from datetime import timedelta
week_ago = (date.today() - timedelta(days=7)).isoformat()
recent = [m for m in movies if (m.get('digital_date') or '') >= week_ago]
by_date = Counter(m.get('digital_date') for m in recent)

# Zero watch links — split future releases from actual failures
zero_future = []
zero_broken = []
for m in movies:
    wl = m.get('watch_links', {})
    wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
    if wl_count == 0:
        dd = m.get('digital_date') or ''
        if dd > today:
            zero_future.append((dd, m['title']))
        else:
            zero_broken.append(m['title'])

pct = round(len(zero_broken) / total * 100, 1) if total else 0

# Pipeline health
try:
    diag = json.load(open('metrics/run_diagnostics.json'))
    health = f\"{diag.get('timestamp', '?')} — {'SUCCESS' if diag.get('overall_success') else 'FAILURE'}\";
except: health = 'unknown'

print(f'WALL: {total} movies')
print(f'PIPELINE: {health}')
print(f'TODAY ({today}): {len(arrivals)} new arrivals')
for a in arrivals: print(f'  - {a[\"title\"]}')
print(f'LAST 7 DAYS:')
for dt in sorted(by_date): print(f'  {dt}: {by_date[dt]} titles')
if zero_future:
    print(f'🗓 UPCOMING ({len(zero_future)}) — no links yet, not released:')
    for dd, t in sorted(zero_future): print(f'  {dd}  {t}')
if len(zero_broken) == 0:
    print(f'✅ ZERO WATCH LINKS: 0 — All enriched OK')
elif pct > 5:
    print(f'🚨 CRITICAL ENRICHMENT FAILURE: {len(zero_broken)} movies unenriched ({pct}% of wall)')
    print(f'   This is NOT normal. Enrichment pipeline likely broken.')
    for t in sorted(zero_broken): print(f'   ✗ {t}')
else:
    print(f'⚠ WARNING: {len(zero_broken)} movies have zero watch links ({pct}%)')
    for t in sorted(zero_broken): print(f'  ⚠ {t}')
"
```

Present the output as a formatted report. The **ZERO WATCH LINKS** section is the most critical — zero watch links on a wall movie is NEVER normal. It signals enrichment failure. A 🚨 CRITICAL alert means the pipeline is likely broken and needs immediate investigation.
