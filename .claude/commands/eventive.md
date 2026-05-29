---
description: Scan Eventive for active virtual screenings and cross-reference against NRW tracking + wall movies
argument-hint: (no arguments needed)
allowed-tools: Bash, Read
---

Run the Eventive virtual screening scanner. Finds active festival screenings on Eventive, matches them against NRW tracking and wall movies, and reports what's relevant to add or watch.

Report-only — does NOT modify any data.

---

## Run the scanner

```bash
/usr/bin/python3 scripts/eventive_scanner.py 2>&1
```

This may take 30–60 seconds as it fetches live Eventive festival pages.

---

## Reading the output

The scanner reports three categories:

**Wall matches** — movies currently on the NRW wall that have an active Eventive screening. These are already visible to users; the screening just adds context.

**Tracking matches** — movies in our tracking database (status=tracking, not yet on wall) that have an active Eventive screening. These are the most actionable: they're movies we already know about that are now playing somewhere.

**Unmatched** — Eventive films with no NRW match. May be worth intaking if they look relevant.

---

## After the report

**If a tracking match looks interesting:**
- Use `/add-movie [title]` to manually add it to the wall now (virtual screening = available)
- Or note it and let the pipeline pick it up when it hits digital platforms

**If an unmatched film looks relevant:**
- Use `/add-movie [title]` to intake and add it

**If a wall movie has an expiring screening:**
- The pipeline's `check_virtual_screening_expirations()` handles this automatically
- If the expiration date is wrong, use `/correct [title] screening ends [date]`

---

## Tip

The pipeline also runs `--scan-eventive` automatically during `--intake`. This manual skill is for checking on-demand between pipeline runs.
