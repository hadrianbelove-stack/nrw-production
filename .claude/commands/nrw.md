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

# JustWatch-reverted movies (last 3 days)
three_days_ago = (date.today() - timedelta(days=3)).isoformat()
jw_reverted = []
try:
    t = json.load(open('movie_tracking.json'))
    for mid, m in t.get('movies', {}).items():
        rev_at = m.get('_jw_reverted_at', '')
        if rev_at >= three_days_ago and m.get('_jw_revert_reason'):
            provs = m.get('providers', {})
            plats = [p for cat in ['rent','buy','streaming'] for p in provs.get(cat, [])]
            jw_reverted.append((rev_at, m.get('title', mid), m['_jw_revert_reason'], plats))
except: pass

# Pipeline health
try:
    diag = json.load(open('metrics/run_diagnostics.json'))
    health = f\"{diag.get('timestamp', '?')} — {'SUCCESS' if diag.get('overall_success') else 'FAILURE'}\";
except: health = 'unknown'

print(f'WALL: {total} movies')
print(f'PIPELINE: {health}')
print(f'TODAY ({today}): {len(arrivals)} new arrivals')
for a in arrivals: print(f'  - {a[\"title\"]}')

# Enrichment gaps for today's arrivals
gaps_found = []
for a in arrivals:
    missing = []
    links = a.get('links', {})
    crew = a.get('crew', {})
    wl = a.get('watch_links', {})
    wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
    if not links.get('trailer') and not links.get('trailer_hosted'): missing.append('trailer')
    if not links.get('wikipedia'): missing.append('wikipedia')
    if wl_count == 0: missing.append('watch_links')
    if not a.get('rt_score'): missing.append('rt_score')
    if not a.get('imdb_rating'): missing.append('imdb_rating')
    d_name = crew.get('director', '')
    if not d_name or d_name == 'Unknown': missing.append('director')
    if not a.get('country'): missing.append('country')
    if not a.get('year'): missing.append('year')
    if not a.get('runtime'): missing.append('runtime')
    if missing:
        gaps_found.append((a['title'], missing))
if gaps_found:
    print('ENRICHMENT GAPS (%d of %d arrivals):' % (len(gaps_found), len(arrivals)))
    for title, missing in gaps_found:
        print('  %s — missing: %s' % (title, ', '.join(missing)))
elif arrivals:
    print('ENRICHMENT GAPS: 0 — all %d arrivals fully enriched' % len(arrivals))

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
if jw_reverted:
    print(f'🔄 JW REVERTED ({len(jw_reverted)}) — discovered but sent back to tracking (last 3 days):')
    by_reason = {}
    for rev_at, title, reason, plats in sorted(jw_reverted):
        by_reason.setdefault(reason, []).append((rev_at, title, plats))
    for reason, items in by_reason.items():
        label = {'justwatch_no_valid_offers': 'Only on excluded platforms', 'justwatch_no_match': 'No JustWatch match found'}.get(reason, reason)
        print(f'  [{label}]')
        for rev_at, title, plats in items:
            plat_str = f' ({", ".join(plats)})' if plats else ''
            print(f'    {rev_at}  {title}{plat_str}')
else:
    print(f'✅ JW REVERTED: 0 — no reversions in last 3 days')
"
```

Present the output as a formatted report. The **ZERO WATCH LINKS** section is the most critical — zero watch links on a wall movie is NEVER normal. It signals enrichment failure. A 🚨 CRITICAL alert means the pipeline is likely broken and needs immediate investigation.

The **JW REVERTED** section shows movies discovered by TMDB but sent back to tracking after JustWatch couldn't confirm them on our platforms. This is expected and healthy — it means the pipeline correctly filtered out movies only available on excluded services (Google Play, fuboTV, Philo, etc.) or with no JustWatch match at all.
