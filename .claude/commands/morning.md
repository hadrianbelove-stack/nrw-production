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
- **Intake**: just the count of new films intaked — this is the "is intake still working?" signal. Flag in Concerns only if it's 0 or abnormally low. (No duplicates/scan-window detail — that's internal noise.)
- **New Releases & Reverted** — run the script below.
  - **New Releases** = films that newly landed **and stuck** on the wall this run (a full successful transition). List each, shown vs slop.
  - **Reverted** = films that transitioned then got sent back **this run only** (new reversions, with the reason). Chronic/recurring reverters are not listed, just counted — that's noise. Reasons are humanized; **Platforms** prefers `jw_platforms` (what JustWatch actually saw), falling back to `tmdb_platforms`, "—" if neither.
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

- **Any phase failures or warnings** → list in Concerns

---

### Curation Backlog

Two parts: the **backlog** (films still needing work — the number that matters, identical logic to `/curate`) and a **health scan** over all recent arrivals (only the flagged ones are listed). Do **not** present the raw arrivals count as a to-do — most of those are already curated from prior days. Run this script — reads exact field paths, no guessing:

```bash
/usr/bin/python3 -c "
import json
from datetime import date, timedelta

def svc_names(val):
    # watch_links entries may be a list of dicts, a single dict (legacy
    # single-object form), or plain strings — normalize to service names.
    items = val if isinstance(val, list) else ([val] if val else [])
    out = []
    for s in items:
        if isinstance(s, dict):
            out.append(s.get('service', '?'))
        elif isinstance(s, str):
            out.append(s)
    return out

WINDOW_DAYS = 7

data = json.load(open('data.json'))
today = str(date.today())
from_date = str(date.today() - timedelta(days=WINDOW_DAYS))

# Capsule presence — same source /curate Stage 4 uses.
try:
    caps = json.load(open('cache/approved_capsules.json'))
    ct = set(t.lower() for t in (caps.keys() if isinstance(caps, dict)
             else [c.get('title','') for c in caps]))
except Exception:
    ct = set()

arrivals = [m for m in data['movies']
            if from_date <= m.get('digital_date', '') <= today]
arrivals.sort(key=lambda m: m.get('digital_date', ''), reverse=True)

# --- Curation backlog: state-based, mirrors /curate (NOT the raw arrivals count) ---
def needs_work(m):
    needs = []
    if m.get('_is_slop_guess') == True:
        needs.append('slop?')
    # Reissues (confirmed Pass D, _reissue) are normal arrivals — they need capsule + quotes.
    # Only AUTO-detected restorations are skipped. (_restoration was never set — bug fix.)
    skip_resto = m.get('filters',{}).get('is_restoration') and not m.get('_reissue')
    if m.get('title','').lower() not in ct and not skip_resto:
        needs.append('capsule')
    if 'pull_quotes' not in m and not skip_resto:
        needs.append('quotes')
    return needs

backlog = [(m, needs_work(m)) for m in arrivals]
backlog = [(m, n) for m, n in backlog if n]

print(f'{len(backlog)} film(s) still need work:')
if not backlog:
    print('  Nothing outstanding — caught up.')
for m, n in backlog:
    print(f'  • {m.get(\"title\")} ({m.get(\"year\")}) [{m.get(\"digital_date\")}] — {\"+\".join(n)}')

# --- Health scan: all recent arrivals, but only print the flagged ones ---
print()
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
clean = len(arrivals) - flagged
if flagged == 0:
    print(f'Health scan: all {len(arrivals)} arrival(s) in the last {WINDOW_DAYS} days have a trailer and working links.')
else:
    print(f'Health scan: {flagged} flagged above, {clean} clean (of {len(arrivals)} arrivals in {WINDOW_DAYS} days).')
"
```

Present the output directly. Lead with the backlog count. Any `⚠` flags become Concerns below.

---

### Code Catch-up (report-only)

Run `/cleanupcatchup --report-only` — a quality pass over every *code* commit since the last manual catch-up (review bugs/NRW-rule fails + dead-code candidates). This is **report-only**: it makes no edits and does **not** advance the catch-up marker, so the findings stay waiting for a real `/cleanupcatchup` run.

- If it reports "only data/curation commits" → say "No new code since last catch-up" and move on.
- Otherwise present a 1-line-per-item summary. Any **behavior findings (bugs / rule violations)** become Concerns below. Mechanical cleanup items are listed here but are not Concerns.
- Do **not** offer to fix anything in `/morning` — point the user to `/cleanupcatchup` for that.

---

### Concerns
Bullet list of anything actionable. Stall and JustWatch health live here — they only appear when something is actually wrong, not as a daily "all good" line:
- Phase failures (from `run_diagnostics.json` `failures`)
- **Pipeline stalled**: `run_diagnostics.json` `stall_status.stalled == true` — 3+ days with zero transitions, which usually means something broke (discovery/API/state), not a real dry spell. Note how many days.
- **JustWatch outage**: `discovery_run.json` `results.jw_healthy == false` — the JW_BREAKER detected JustWatch couldn't find its control titles, so reverts were suppressed this run (films held in tracking, strike counts untouched). Expect **fewer New Releases**; recheck tomorrow.
- Any `⚠ NO TRAILER` from the Curation Backlog script above
- Any `⚠ NO LINKS` or `⚠ PLEX ONLY` from the Curation Backlog script above
- Enrichment errors, plus any "Other enrichment deferrals" (timeout/error) flagged by the New Releases & Reverted script
- Pull quote gaps (films in curation queue with no entry in `pull_quotes_combined.json`)

If nothing: "No concerns."

---

## Phase 2 — Curation

After the overnight report, run `/curate` to handle recent arrivals: Confirm Reissues (Stage 0) → Selects → section review → slop review → per-film (capsule + Wikipedia links + pull quotes). Stage 0 surfaces old films caught getting a new restoration/re-release (intake Pass D) for you to confirm onto the wall. `/curate` is **state-based** — it shows everything from the **last 7 days** still needing work (slop unconfirmed / no capsule / no quotes), newest first. There is no session to resume; skipped days just accumulate in the window until handled.

The curation queue is ready when:
- Capsule variants can be generated for films without one
- Pull quotes are in `cache/pull_quotes_combined.json` for films that need them

If any film is missing quotes (flagged above in Concerns), note it when you reach that film in curation and offer to skip or proceed without quotes.
