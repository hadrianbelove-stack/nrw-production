---
description: Daily admin — overnight report + full curation (capsules, links, pull quotes, staff picks, sections)
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Start the day. Read the overnight report, then curate new arrivals film by film.

---

## Phase 1 — Overnight Report

Read all of the following before presenting anything:

1. `logs/launchagent.log` — last 150 lines. **Use `tail -150` via Bash** (the Read tool reads from the top; log files can be 30k+ lines so offset=0 will return stale entries from months ago)
2. `metrics/run_diagnostics.json` — CI pipeline summary (overall status, failures, stall)
3. `metrics/intake_run.json` — intake results
4. JustWatch breaker health — one field, don't read the whole file:
   ```bash
   /usr/bin/python3 -c "import json; print('jw_healthy:', json.load(open('metrics/discovery_run.json')).get('results',{}).get('jw_healthy'))"
   ```
5. Quote scrape coverage — **never read `cache/pull_quotes_combined.json`** (it's 3.5MB); the script prints cache size, scraped-today count, and any curation candidate with no entry:
   ```bash
   /usr/bin/python3 scripts/morning_report.py --section quotes
   ```

Discovery/enrichment detail (New Releases, Reverted, deferrals) comes from `morning_report.py --section overnight` below — do **not** read `discovery_run.json` or `enrichment_run.json` in full; only dig into them when the script or `run_diagnostics.json` flags a failure.

Then present this report in order:

---

### Launchagent
- Did it run last night? (look for most recent date in log)
- Git pull: was CI data current when it ran?
- Trailers: how many hosted / failed / skipped — title + reason for each failure
- Pull quotes: present the `--section quotes` output from above (cache size, scraped-today count, `⚠ No quotes yet:` flags). Its `⚠` lines become Concerns.

---

### Overnight Pipeline
- Overall: success or failure, total duration
- **Intake**: just the count of new films intaked — this is the "is intake still working?" signal. Flag in Concerns only if it's 0 or abnormally low. (No duplicates/scan-window detail — that's internal noise.)
- **New Releases & Reverted** — run the script below.
  - **New Releases** = films that newly landed **and stuck** on the wall this run (a full successful transition). List each, shown vs slop.
  - **Reverted** = films that transitioned then got sent back **this run only** (new reversions, with the reason). Chronic/recurring reverters are not listed, just counted — that's noise. Reasons are humanized; **Platforms** prefers `jw_platforms` (what JustWatch actually saw), falling back to `tmdb_platforms`, "—" if neither.
  - Any non-revert deferrals (timeout/error) are pulled out for Concerns.

```bash
/usr/bin/python3 scripts/morning_report.py --section overnight
```
*(Logic lives in the script — reads data.json + metrics/discovery_run.json + metrics/enrichment_run.json. New Releases = films first discovered this run, shown vs slop; Reverted = new jw_revert deferrals this run, humanized + platforms; other deferrals split out for Concerns.)*

- **Any phase failures or warnings** → list in Concerns

---

### Curation Backlog

Two parts: the **backlog** (films still needing work — the number that matters, identical logic to `/curate`) and a **health scan** over all recent arrivals (only the flagged ones are listed). Do **not** present the raw arrivals count as a to-do — most of those are already curated from prior days. Run this script — reads exact field paths, no guessing:

```bash
/usr/bin/python3 scripts/morning_report.py --section backlog
```
*(Logic lives in the script. Backlog = in-window films still needing `slop?` review / `capsule` / `quotes` — same capsule+quote presence test `/curate` Stage 4 uses, reissues included, auto-restorations skipped. Health scan flags any recent arrival missing a trailer or watch links (`⚠ PLEX ONLY` for Plex-only). Change the window via `WINDOW_DAYS` in the script.)*

Present the output directly. Lead with the backlog count. Any `⚠` flags become Concerns below.

---

### Code Catch-up (report-only)

Run `/cleanupcatchup --report-only` — a quality pass over *code* commits **not yet shown in a previous morning report** (review bugs/NRW-rule fails + dead-code candidates). It makes no edits and never advances the real catch-up marker; it advances only its own reported marker, so the same commits aren't re-reviewed every morning. Findings accumulate in `.claude/catchup_findings.md` until a real `/cleanupcatchup` clears them.

- If it reports "only data/curation commits" or "no new code commits since yesterday's report" → say so and move on (relay any still-pending count it mentions).
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
- Pull quote gaps — any `⚠ No quotes yet:` line from `morning_report.py --section quotes`

If nothing: "No concerns."

---

## Phase 2 — Curation

After the overnight report, run `/curate` to handle recent arrivals: Confirm Reissues (Stage 0) → Selects → section review → slop review → per-film (capsule + Wikipedia links + pull quotes). Stage 0 surfaces old films caught getting a new restoration/re-release (intake Pass D) for you to confirm onto the wall. `/curate` is **state-based** — it shows everything from the **last 7 days** still needing work (slop unconfirmed / no capsule / no quotes), newest first. There is no session to resume; skipped days just accumulate in the window until handled.

The curation queue is ready when:
- Capsule variants can be generated for films without one
- Pull quotes are in `cache/pull_quotes_combined.json` for films that need them

If any film is missing quotes (flagged above in Concerns), note it when you reach that film in curation and offer to skip or proceed without quotes.
