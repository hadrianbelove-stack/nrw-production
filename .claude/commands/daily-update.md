---
description: Run the full daily NRW pipeline (intake → discovery → enrichment)
allowed-tools: Bash, Read
---

Run the full daily NRW pipeline with verification. Use `/usr/bin/python3` — bare `python3` is Homebrew 3.13 and lacks all packages.

**If any phase fails, STOP and report the error. Do not continue to the next phase.**

---

## Step 1 — Pull latest

```bash
git pull origin main
```

---

## Step 2 — Intake

```bash
/usr/bin/python3 generate_data.py --intake 2>&1
```

After completion, report: how many new movies added to tracking (from output or `metrics/intake_run.json`).

---

## Step 3 — Discovery

```bash
/usr/bin/python3 generate_data.py --discover 2>&1
```

After completion, report: how many movies polled, how many transitioned to available (from output or `metrics/discovery_run.json`).

---

## Step 4 — Enrichment

```bash
/usr/bin/python3 generate_data.py --enrich 2>&1
```

After completion, report: how many movies enriched, how many deferred (from output or `metrics/enrichment_run.json`).

---

## Step 5 — Report

Read `metrics/run_diagnostics.json` and summarize:
- Overall: success or failure
- Intake count, discovery transitions, enrichment count
- Any failures or warnings

If all phases succeeded, suggest a commit message:
```
Daily NRW Update - YYYY-MM-DD, new_arrivals=N
```

---

## Step 6 — Commit if there are changes

```bash
git add data.json movie_tracking.json metrics/
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Daily NRW Update - YYYY-MM-DD, new_arrivals=N"
git push origin main || (git pull --rebase origin main && git push origin main)
```
