---
description: Daily admin — overnight report + full curation (capsules, links, pull quotes, staff picks, sections)
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Start the day. Read the overnight report, then curate new arrivals film by film.

---

## Phase 1 — Overnight Report

**Step 0 — launch the code catch-up in the background FIRST**, before reading any report files, so it reviews while the report is gathered and the user curates. Use the Agent tool with `run_in_background: true` (subagent type `claude`) and this prompt:

> Execute `.claude/commands/cleanupcatchup.md` in `--report-only` mode for the NRW repo at /Users/hadrianbelove/Downloads/nrw-production. Follow that file exactly: find the marker, pin the range end, filter to code commits, run the behavior pass (bugs / NRW-rule violations) and the dead-code pass over the changed files, append findings to `.claude/catchup_findings.md` under today's date, and advance `.claude/last_reported_commit` to the pinned range end (never a fresh `git rev-parse HEAD` — commits land mid-review). Make NO code edits and never touch `.claude/last_catchup_commit`. Return a compact summary: N commits reviewed, each behavior finding as one line (file:line — plain-English issue), a mechanical-cleanup count, and any still-pending count from earlier ledger entries.

Do not wait for it — go straight to the report reads below.

Read all of the following before presenting anything:

1. `logs/launchagent.log` — last 150 lines. **Use `tail -150` via Bash** (the Read tool reads from the top; log files can be 30k+ lines so offset=0 will return stale entries from months ago)
2. `metrics/run_diagnostics.json` — CI pipeline summary (overall status, failures, stall)
3. `metrics/intake_run.json` — intake results
4. JustWatch breaker health — one field, don't read the whole file:
   ```bash
   /usr/bin/python3 -c "import json; print('jw_healthy:', json.load(open('metrics/discovery_run.json')).get('results',{}).get('jw_healthy'))"
   ```
5. The report body — **one call prints all three sections** (overnight: New Releases/Reverted/deferrals · backlog + health scan · quote coverage). **Never read `cache/pull_quotes_combined.json`** (it's 3.5MB):
   ```bash
   /usr/bin/python3 scripts/morning_report.py --section all
   ```

Run items 1–5 in ONE parallel batch. Discovery/enrichment detail comes from the script's OVERNIGHT section — do **not** read `discovery_run.json` or `enrichment_run.json` in full; only dig into them when the script or `run_diagnostics.json` flags a failure.

Then present this report in order:

---

### Launchagent
- Did it run last night? (look for most recent date in log)
- Git pull: was CI data current when it ran?
- Trailers: how many hosted / failed / skipped — title + reason for each failure
- Pull quotes: present the QUOTES section of the `--section all` output (cache size, scraped-today count, `⚠ No quotes yet:` flags). Its `⚠` lines become Concerns.

---

### Overnight Pipeline
- Overall: success or failure, total duration
- **Intake**: just the count of new films intaked — this is the "is intake still working?" signal. Flag in Concerns only if it's 0 or abnormally low. (No duplicates/scan-window detail — that's internal noise.)
- **New Releases & Reverted** — from the OVERNIGHT section of the `--section all` output (already run above; do not re-run).
  - **New Releases** = films that newly landed **and stuck** on the wall this run (a full successful transition). List each, shown vs slop.
  - **Reverted** = films that transitioned then got sent back **this run only** (new reversions, with the reason). Chronic/recurring reverters are not listed, just counted — that's noise. Reasons are humanized; **Platforms** prefers `jw_platforms` (what JustWatch actually saw), falling back to `tmdb_platforms`, "—" if neither.
  - Any non-revert deferrals (timeout/error) are pulled out for Concerns.

*(Logic lives in the script — reads data.json + metrics/discovery_run.json + metrics/enrichment_run.json. New Releases = films first discovered this run, shown vs slop; Reverted = new jw_revert deferrals this run, humanized + platforms; other deferrals split out for Concerns.)*

- **Any phase failures or warnings** → list in Concerns

---

### Curation Backlog

Two parts: the **backlog** (films still needing work — the number that matters, identical logic to `/curate`) and a **health scan** over all recent arrivals (only the flagged ones are listed). Do **not** present the raw arrivals count as a to-do — most of those are already curated from prior days. Comes from the BACKLOG section of the `--section all` output (already run above; do not re-run).

*(Logic lives in the script. Backlog = in-window films still needing `slop?` review / `capsule` / `quotes` — same capsule+quote presence test `/curate` Stage 4 uses, reissues included, auto-restorations skipped. Health scan flags any recent arrival missing a trailer or watch links (`⚠ PLEX ONLY` for Plex-only). Change the window via `WINDOW_DAYS` in the script.)*

Present the output directly. Lead with the backlog count. Any `⚠` flags become Concerns below.

---

### Code Catch-up (background)

The catch-up agent from Step 0 is still working — the report section is **one line**: *"Code catch-up: reviewing N commits in the background — findings will drop in when ready."* Never block the report or curation on it.

**When its completion notification arrives** (usually mid-curation): relay the summary between curation beats — behavior findings verbatim, one line each (these are late-arriving **Concerns**); mechanical cleanup as a count. Relay any still-pending count from earlier reports. Do **not** offer to fix anything in `/morning` — point the user to `/cleanupcatchup` for that. If the session ends before it finishes, say so — the findings still land in `.claude/catchup_findings.md` and surface in tomorrow's report.

---

### Concerns
Bullet list of anything actionable. Stall and JustWatch health live here — they only appear when something is actually wrong, not as a daily "all good" line:
- Phase failures (from `run_diagnostics.json` `failures`)
- **Pipeline stalled**: `run_diagnostics.json` `stall_status.stalled == true` — 3+ days with zero transitions, which usually means something broke (discovery/API/state), not a real dry spell. Note how many days.
- **JustWatch outage**: `discovery_run.json` `results.jw_healthy == false` — the JW_BREAKER detected JustWatch couldn't find its control titles, so reverts were suppressed this run (films held in tracking, strike counts untouched). Expect **fewer New Releases**; recheck tomorrow.
- Any `⚠ NO TRAILER` from the Curation Backlog script above
- Any `⚠ NO LINKS` or `⚠ PLEX ONLY` from the Curation Backlog script above
- Enrichment errors, plus any "Other enrichment deferrals" (timeout/error) flagged by the New Releases & Reverted script
- Pull quote gaps — any `⚠ No quotes yet:` line from the QUOTES section of the report output

If nothing: "No concerns."

---

## Phase 2 — Curation

After the overnight report, run `/curate` to handle recent arrivals: Confirm Reissues (Stage 0) → the combined review (Selects + Sections + Slop, one message / one reply) → per-film capsule + Wikipedia links + pull quotes (one reply per film). Stage 0 surfaces old films caught getting a new restoration/re-release (intake Pass D) for you to confirm onto the wall. `/curate` is **state-based** — it shows everything from the **last 7 days** still needing work (slop unconfirmed / no capsule / no quotes), newest first. There is no session to resume; skipped days just accumulate in the window until handled.

The curation queue is ready when:
- Capsule variants can be generated for films without one
- Pull quotes are in `cache/pull_quotes_combined.json` for films that need them

If any film is missing quotes (flagged above in Concerns), note it when you reach that film in curation and offer to skip or proceed without quotes.
