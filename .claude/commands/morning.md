---
description: Daily admin — overnight report + full curation (capsules, links, pull quotes, staff picks, sections)
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, Glob, WebSearch
---

Start the day. Read the overnight report, then curate new arrivals film by film.

---

## Phase 1 — Overnight Report

Read all of the following before presenting anything:

1. `logs/launchagent.log` — last 150 lines
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
List every movie added to the wall since yesterday's session (from `data.json` where `digital_date` is today or yesterday). For each:
```
• Title (Year) — Service | RT% | Trailer ✓/⚠ | Watch links ✓/⚠
```
Flag `⚠` for: no trailer, zero watch links, Plex-only.

**Watch link check**: a film has links if `watch_links.streaming` OR `watch_links.vod` is non-empty. Check both — VOD-only films (no streaming) still have links. Only flag `⚠ no links` if both arrays are empty or missing.

---

### Stall Detection
From `run_diagnostics.json` `stall_status` — is the pipeline stalled? How many days without transitions?

---

### Concerns
Bullet list of anything actionable:
- Phase failures
- Films with zero watch links
- Films missing trailers (more than 3 days old)
- Enrichment errors
- Pull quote gaps (films in curation queue with no scraped quotes)

If nothing: "No concerns."

---

## Phase 2 — Curation

After the overnight report, run `/curate` to handle new arrivals in full: staff picks → section review → per-film (capsule + Wikipedia links + pull quotes).

The curation queue is ready when:
- Capsule variants can be generated for films without one
- Pull quotes are in `cache/pull_quotes_combined.json` for films that need them

If any film is missing quotes (flagged above in Concerns), note it when you reach that film in curation and offer to skip or proceed without quotes.
