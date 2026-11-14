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
- Intake: just the count of new films intaked — `results.total_intaked` (films `results.intaked`, miniseries `results.miniseries_intaked`). This is the "is intake still working?" signal; flag in Concerns only if it's 0 or abnormally low. (No duplicates/scan-window detail — internal noise.)
- **New Releases & Reverted** — run the script below.
  - **New Releases** = films that newly landed and stuck on the wall this run (a full successful transition). List each, shown vs slop.
  - **Reverted** = films that transitioned then got sent back this run only (new reversions, with the reason). Chronic/recurring reverters are not listed, just counted. Reasons are humanized; **Platforms** prefers `jw_platforms` (what JustWatch saw at revert time), falling back to `tmdb_platforms`, "—" if neither.
  - Any non-revert deferrals (timeout/error) are pulled out for Concerns.

```bash
/usr/bin/python3 -c "
import json
from datetime import date
data = json.load(open('data.json'))
ms = data['movies'] if isinstance(data, dict) else data
disc = json.load(open('metrics/discovery_run.json'))
run_date = disc.get('timestamp', '')[:10] or str(date.today())
try:
    enr = json.load(open('metrics/enrichment_run.json'))
except Exception:
    enr = {}
deferred = enr.get('deferred_details', [])
REASONS = {
  'justwatch_no_valid_offers': 'Coming soon (JustWatch has no live offers yet)',
  'justwatch_theatrical_pvod': 'In theaters / PVOD only',
  'justwatch_no_match': 'No JustWatch listing yet',
  'zero_watch_links': 'No watch links after enrichment',
}
def humanize(r): return REASONS.get(r.split('jw_revert:')[-1], r.split('jw_revert:')[-1])
def plats(d):
    p = d.get('jw_platforms') or d.get('tmdb_platforms') or []
    return ', '.join(p) if p else '—'
def first_rev(d): return d.get('first_reverted_at') or str(d.get('discovered_at',''))[:10]

new_rel = [m for m in ms if str(m.get('_discovered_at',''))[:10] == run_date]
print(f'New Releases: {len(new_rel)}')
for m in sorted(new_rel, key=lambda m: not m.get('is_slop')):
    print(f'  • {m.get(\"title\")} ({m.get(\"year\")}) — {\"slop\" if m.get(\"is_slop\") else \"shown\"}')

reverts = [d for d in deferred if str(d.get('reason','')).startswith('jw_revert:')]
new_rev = [d for d in reverts if first_rev(d) == run_date]
hidden = len(reverts) - len(new_rev)
print(f'\nReverted (new this run): {len(new_rev)}')
for d in new_rev:
    print(f'  • {d.get(\"title\")} [{d.get(\"digital_date\") or \"—\"}] — {humanize(d.get(\"reason\",\"\"))} | {plats(d)}')
if hidden:
    print(f'  ({hidden} chronic/aged revert(s) not listed)')

other = [d for d in deferred if not str(d.get('reason','')).startswith('jw_revert:')]
if other:
    print(f'\n⚠ Other enrichment deferrals (→ Concerns): {len(other)}')
    for d in other:
        print(f'  • {d.get(\"title\")} — {d.get(\"reason\")}')
"
```

- Any failures or warnings (from run_diagnostics.json `failures` and `warnings`) → list in Concerns

### Health Scan

Recent arrivals (since the last local run) — only flagged films are listed. Run this script — reads exact field paths, no guessing:

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta

def svc_names(val):
    items = val if isinstance(val, list) else ([val] if val else [])
    out = []
    for s in items:
        if isinstance(s, dict): out.append(s.get('service','?'))
        elif isinstance(s, str): out.append(s)
    return out

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

flagged = 0
for m in arrivals:
    streaming = svc_names(m.get('watch_links', {}).get('streaming'))
    vod = svc_names(m.get('watch_links', {}).get('vod'))
    services = streaming + vod
    trailer_hosted = bool(m.get('links', {}).get('trailer_hosted', ''))
    trailer_yt = bool(m.get('links', {}).get('trailer', ''))
    has_links = bool(streaming or vod)
    plex_only = services == ['Plex']
    t_flag = 'trailer:hosted' if trailer_hosted else ('trailer:YT' if trailer_yt else '⚠ NO TRAILER')
    l_flag = ('⚠ PLEX ONLY' if plex_only else 'links:ok') if has_links else '⚠ NO LINKS'
    if '⚠' in t_flag or '⚠' in l_flag:
        flagged += 1
        rt = m.get('rt_score') or '--'
        svc = ', '.join(services) if services else '—'
        print(f'  ⚠ {m.get(\"title\")} ({m.get(\"year\")}) — {svc} | RT:{rt} | {t_flag} | {l_flag}')
if flagged == 0:
    print(f'Health scan: all {len(arrivals)} arrival(s) since {from_date} have a trailer and working links.')
else:
    print(f'Health scan: {flagged} flagged above (of {len(arrivals)} arrivals since {from_date}).')
"
```

### Concerns
Stall and JustWatch health live here — they only appear when something is actually wrong, not as a daily "all good" line:
- Any failures or warnings from run_diagnostics.json `failures` and `warnings`
- **Pipeline stalled**: `run_diagnostics.json` `stall_status.stalled == true` (3+ days with zero transitions — usually means something broke). Note how many days.
- **JustWatch outage**: `discovery_run.json` `results.jw_healthy == false` (the JW_BREAKER suppressed reverts this run — expect fewer New Releases; recheck tomorrow).
- Any `⚠ NO TRAILER` from the Health Scan script above
- Any `⚠ NO LINKS` or `⚠ PLEX ONLY` from the Health Scan script above
- Trailer hosting failures from launchagent log
- Enrichment timeouts/errors, plus any "Other enrichment deferrals" flagged by the New Releases & Reverted script
- **Pull quote gaps**: check `cache/pull_quotes_combined.json` — for each new arrival, look up `"{title}_{year}"`. If a movie is absent from the cache entirely, flag it: `⚠ [Title] — no pull quotes scraped (morning batch missed it)`
- If no concerns, say "No concerns."

### Data Quality Snapshot (LIVE from data.json)
Run `/wallhealth` and present the full report in the chat. Do NOT read from run_diagnostics.json for these numbers.

### Curation
After the report, run `/curate` to curate new arrivals (staff picks, sections, pull quotes, capsules).
