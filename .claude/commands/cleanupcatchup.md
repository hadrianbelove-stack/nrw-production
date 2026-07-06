---
description: Quality catch-up over every code commit since the last manual catch-up — bugs/rule fails + dead-code candidates, then advance the marker
argument-hint: [--report-only]
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, Skill, Agent
---

A quality pass over every **code** commit since the last manual catch-up. Two kinds of finding:

- **Behavior findings** — bugs and NRW-rule violations (the review pass). These are the serious ones; in `/morning` they become **Concerns**.
- **Mechanical cleanup** — dead code, stale comments, leftover debug, orphans (the cleanup pass). Listed, but not Concerns.

**Mode**: `$ARGUMENTS`

- `--report-only` → present findings, make **no edits**, and do **not** advance the marker. This is what `/morning` calls — the findings stay waiting for a real run.
- no flag (a real run) → present findings, offer to fix (with approval), apply approved fixes, then **advance the marker** to HEAD.

---

## 1. Find the starting point

Two gitignored markers, so daily `--report-only` runs (from `/morning`) never re-review the same commits:

- `.claude/last_catchup_commit` — advanced only by a **real** run: what's actually been caught up.
- `.claude/last_reported_commit` — advanced by every **`--report-only`** run: what a morning report has already shown. Findings shown but not yet fixed live in `.claude/catchup_findings.md` (the pending ledger, cleared by a real run).

A **real run** starts from `last_catchup_commit`. A **`--report-only` run** starts from `last_reported_commit` when that exists and is valid, falling back to `last_catchup_commit`:

```bash
MARKER=$(cat .claude/last_catchup_commit 2>/dev/null | tr -d '[:space:]')
# --report-only ONLY: prefer the reported marker (skip this line on a real run)
REPORTED=$(cat .claude/last_reported_commit 2>/dev/null | tr -d '[:space:]'); [ -n "$REPORTED" ] && git cat-file -e "${REPORTED}^{commit}" 2>/dev/null && MARKER=$REPORTED
# Pin the range end NOW. Concurrent windows push to main mid-review; a fresh
# `git rev-parse HEAD` at marker-advance time would silently skip those commits.
RANGE_END=$(git rev-parse HEAD)
if [ -n "$MARKER" ] && git cat-file -e "${MARKER}^{commit}" 2>/dev/null; then
  echo "Starting from marker: $MARKER (range end pinned: $RANGE_END)"
  echo "--- commits since then ($MARKER..$RANGE_END) ---"
  git log --oneline "$MARKER..$RANGE_END"
  echo "--- count ---"
  git rev-list --count "$MARKER..$RANGE_END"
else
  echo "No valid marker yet (first run) — fall back to the last 5 commits."
  git log --oneline -5
fi
```

- Count **0** (nothing since the marker):
  - `--report-only`: say *"No new code commits since yesterday's report."* If `.claude/catchup_findings.md` exists and is non-empty, add one line: *"Earlier findings are still pending — run `/cleanupcatchup` to handle them"* (with a short count from that file). **STOP.**
  - real run: tell the user *"Nothing new since your last catch-up (`<short marker>`)."* and **STOP** — do not advance the marker.
- **First run** (no marker): use `HEAD~5..$RANGE_END` as the range and say you're starting fresh.
- Otherwise the range is `<MARKER>..$RANGE_END`.

## 2. Filter to code commits

The catch-up reviews **code only** — not data/curation churn. Get the code files changed in the range:

```bash
RANGE="<MARKER>..$RANGE_END"   # or HEAD~5..$RANGE_END on first run
git diff --name-only "$RANGE" \
  | grep -E '\.(py|js|jsx|ts|css|html|brs|kt|swift|sh|ya?ml)$' \
  | grep -v -E '^(data|movie_tracking|data_archive)\.json$'
```

- If the list is **empty** → only data/curation commits landed. Report **"No new code since last catch-up."**
  - `--report-only`: advance only the reported marker (`echo "$RANGE_END" > .claude/last_reported_commit`) so tomorrow's morning doesn't re-list the same data-only range, then STOP.
  - real run: advance the markers (Step 5) so these data commits aren't re-listed next time, then STOP.
- Otherwise that file list is the **scope** for both passes below.

## 3. Behavior pass (bugs / NRW-rule violations)

Run the standard **/review** on the range — invoke the `review` skill with the pinned range string (e.g. `abc123..def456`, using the resolved `$RANGE_END`, never a bare `HEAD`) as its argument and let it do its normal report. It already knows the NRW Tier-1/Tier-2 rules and bug checklist; do **not** duplicate that here.

- In `--report-only` mode: do **not** let it offer or apply fixes — report only.

## 4. Dead-code pass (mechanical cleanup)

Apply the **`cleanup` skill's methodology** — verification-first, grep before reporting, 90%+ confidence, and its full **WHAT TO IGNORE** list (intentional pipeline `print()`s, back-compat fallbacks, `museum_legacy/`, etc.) — but **scope it to only the code files from Step 2**, not the whole repo. For each changed file look for: dead functions/imports introduced or left behind, stale comments, leftover debug, dead CSS selectors, orphaned files. Verify every finding by reading the file and grepping the project for references.

## 5. Present + decide

Present in two clearly separated sections:

```
Catch-up: <N> code commits since <short marker>

Behavior findings (→ Concerns)
  1. file:line — bug/rule violation, plain English
  ...  (or "none")

Mechanical cleanup
  1. file:line — dead code / stale comment / debug, plain English
  ...  (or "none")
```

Then:

- **`--report-only`** → no edits, and **never** touch `.claude/last_catchup_commit`. Do these two things, then STOP:
  1. **Append** the two sections just presented to `.claude/catchup_findings.md` under a heading `## <today's date> (<range>)` — the pending ledger a real run works from and clears.
  2. **Advance the reported marker** so tomorrow's `/morning` reviews only new commits: `echo "$RANGE_END" > .claude/last_reported_commit` — the pinned end of the range actually reviewed, **never** a fresh `git rev-parse HEAD` (commits landing mid-review would be skipped forever).
  If `.claude/catchup_findings.md` already had findings from earlier reports, add one line to the summary: *"Plus N earlier finding(s) still pending — see a real `/cleanupcatchup`."* (When `/morning` calls this, it just relays the summary and points the user to a real `/cleanupcatchup`.)
- **Real run** → ask: *"Fix all, pick numbers, or skip?"* Apply only what's approved (NRW Tier-1: never modify code without explicit approval). If `.claude/catchup_findings.md` holds findings from mornings whose commits fall inside this run's range, they'll re-surface in this run's passes — the ledger is a reminder, not a second source. After presenting — whether the user fixes or skips — advance the markers and clear the ledger:

```bash
echo "$RANGE_END" > .claude/last_catchup_commit
echo "$RANGE_END" > .claude/last_reported_commit
rm -f .claude/catchup_findings.md
echo "Catch-up marker advanced to $(git rev-parse --short "$RANGE_END")."
```

Notes:
- `.claude/last_catchup_commit`, `.claude/last_reported_commit`, and `.claude/catchup_findings.md` are gitignored (personal, per-machine — your catch-up history, not the team's).
- The marker tracks **what you've already caught up on**, not what's "yours" — concurrent/daily-pipeline commits in the range are reviewed too (and noted as not-our-work, per /review's normal behavior).
- To re-run from further back, delete `.claude/last_catchup_commit` (and `.claude/last_reported_commit` to re-report) — resets to first-run.
