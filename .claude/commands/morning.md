---
description: Daily admin — overnight report + full curation (capsules, links, pull quotes, staff picks, sections)
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Start the day. Read the overnight report, then curate new arrivals film by film.

---

## Phase 1 — Overnight Report

Read all of the following before presenting anything:

1. `logs/launchagent.log` — last 150 lines. **Use `tail -150` via Bash** (the Read tool reads from the top; log files can be 30k+ lines so offset=0 will return stale entries from months ago)
2. `metrics/run_diagnostics.json` — CI pipeline summary
3. `metrics/discovery_run.json` — discovery results
4. `metrics/enrichment_run.json` — enrichment results
5. `metrics/intake_run.json` — intake results
6. `cache/pull_quotes_combined.json` — quote scrape coverage

Then present this report in order:

---

### Launchagent
- Did it run last night? (look for most recent date in log)
- Git pull: was CI data current when it ran?
- Trailers: how many hosted / failed / skipped — title + reason for each failure
- Pull quotes: did the overnight scrape run? How many movies now have quote entries in `pull_quotes_combined.json`?
  - Cross-reference against curation candidates (movies needing capsules or quotes) — flag any that have no quote entry: "⚠ No quotes yet: [Title]"

---

### Overnight Pipeline
- Overall: success or failure, total duration
- **Intake**: total intaked, scan window, duplicates skipped
- **Discovery**: movies polled, transitions (newly available)
- **Enrichment**: movies enriched, deferred — show deferred as a table:
  Title | Digital Date | Discovered | Reverts | TMDB Platforms | Reason
  - JW revert deferrals only shown if `discovered_at` is within last 3 days; after that, hide them (add: "N deferrals hidden — aged out")
  - All other deferral reasons (timeout, error, etc.) always show
- **Any phase failures or warnings**

---

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

Present the output directly. Any `⚠` flags become Concerns below.

---

### Stall Detection
From `run_diagnostics.json` `stall_status` — is the pipeline stalled? How many days without transitions?

---

### Concerns
Bullet list of anything actionable:
- Phase failures (from `run_diagnostics.json` `failures`)
- Any `⚠ NO TRAILER` from the New Arrivals script above
- Any `⚠ NO LINKS` or `⚠ PLEX ONLY` from the New Arrivals script above
- Enrichment errors
- Pull quote gaps (films in curation queue with no entry in `pull_quotes_combined.json`)

If nothing: "No concerns."

---

## Phase 2 — Curation

After the overnight report, run `/curate` to handle new arrivals in full: staff picks → section review → per-film (capsule + Wikipedia links + pull quotes).

The curation queue is ready when:
- Capsule variants can be generated for films without one
- Pull quotes are in `cache/pull_quotes_combined.json` for films that need them

If any film is missing quotes (flagged above in Concerns), note it when you reach that film in curation and offer to skip or proceed without quotes.
