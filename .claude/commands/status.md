---
description: Show git status, movie counts, and pipeline metrics
allowed-tools: Bash, Read
---

Show NRW system status dashboard. Run all of the following, then present as a clean summary.

---

## Step 1 — Git state

```bash
git status --short && echo "---" && git log --oneline -5
```

---

## Step 2 — Movie counts and pipeline metrics

```bash
/usr/bin/python3 -c "
import json, os
from datetime import date, datetime

# Wall
data = json.load(open('data.json'))
wall = data['movies']
print(f'Wall: {len(wall)} movies')

# Tracking
tracking = json.load(open('movie_tracking.json'))
movies = tracking.get('movies', {})
by_status = {}
for m in movies.values():
    s = m.get('status', 'unknown')
    by_status[s] = by_status.get(s, 0) + 1
for s, n in sorted(by_status.items()):
    print(f'  Tracking {s}: {n}')

# Intake
if os.path.exists('metrics/intake_run.json'):
    intake = json.load(open('metrics/intake_run.json'))
    ts = intake.get('timestamp', '')[:16]
    total = intake.get('results', {}).get('total_intaked', '?')
    print(f'Last intake: {ts}  total_intaked={total}')

# Discovery
if os.path.exists('metrics/discovery_run.json'):
    disc = json.load(open('metrics/discovery_run.json'))
    ts = disc.get('timestamp', '')[:16]
    transitions = disc.get('transitions', '?')
    print(f'Last discovery: {ts}  transitions={transitions}')

# Enrichment
if os.path.exists('metrics/enrichment_run.json'):
    enr = json.load(open('metrics/enrichment_run.json'))
    ts = enr.get('timestamp', '')[:16]
    enriched = enr.get('enriched', '?')
    deferred = enr.get('deferred', '?')
    print(f'Last enrichment: {ts}  enriched={enriched}  deferred={deferred}')

# Diagnostics
if os.path.exists('metrics/run_diagnostics.json'):
    diag = json.load(open('metrics/run_diagnostics.json'))
    stall = diag.get('stall_status', {})
    days = stall.get('days_without_transition', 0)
    if days and days > 1:
        print(f'Stall: {days} days without transitions')
    failures = diag.get('failures', [])
    if failures:
        print(f'Failures: {failures}')
"
```

---

## Output format

Present as a clean dashboard — no raw terminal output. Group as:

```
Git: [N files modified / clean]
Recent: [last 5 commits one-liners]

Wall: [N] movies
Tracking: available=[N]  tracking=[N]  removed=[N]

Last intake:      [date]  total_intaked=[N]
Last discovery:   [date]  transitions=[N]
Last enrichment:  [date]  enriched=[N]  deferred=[N]

[Stall warning if days > 1]
[Failures if any]
```
