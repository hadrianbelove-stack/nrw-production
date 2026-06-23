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

```bash
MARKER=$(cat .claude/last_catchup_commit 2>/dev/null | tr -d '[:space:]')
if [ -n "$MARKER" ] && git cat-file -e "${MARKER}^{commit}" 2>/dev/null; then
  echo "Last catch-up marker: $MARKER"
  echo "--- commits since then ($MARKER..HEAD) ---"
  git log --oneline "$MARKER..HEAD"
  echo "--- count ---"
  git rev-list --count "$MARKER..HEAD"
else
  echo "No valid marker yet (first run) — fall back to the last 5 commits."
  git log --oneline -5
fi
```

- Count **0** (nothing since the marker): tell the user *"Nothing new since your last catch-up (`<short marker>`)."* and **STOP** — do not advance the marker.
- **First run** (no marker): use `HEAD~5..HEAD` as the range and say you're starting fresh.
- Otherwise the range is `<MARKER>..HEAD`.

## 2. Filter to code commits

The catch-up reviews **code only** — not data/curation churn. Get the code files changed in the range:

```bash
RANGE="<MARKER>..HEAD"   # or HEAD~5..HEAD on first run
git diff --name-only "$RANGE" \
  | grep -E '\.(py|js|jsx|ts|css|html|brs|kt|swift|sh|ya?ml)$' \
  | grep -v -E '^(data|movie_tracking|data_archive)\.json$'
```

- If the list is **empty** → only data/curation commits landed. Report **"No new code since last catch-up."**
  - `--report-only`: STOP, do not advance.
  - real run: advance the marker (Step 5) so these data commits aren't re-listed next time, then STOP.
- Otherwise that file list is the **scope** for both passes below.

## 3. Behavior pass (bugs / NRW-rule violations)

Run the standard **/review** on the range — invoke the `review` skill with the range string (e.g. `abc123..HEAD`) as its argument and let it do its normal report. It already knows the NRW Tier-1/Tier-2 rules and bug checklist; do **not** duplicate that here.

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

- **`--report-only`** → STOP here. No edits, **do not** advance the marker. (When `/morning` calls this, it just relays the summary and points the user to a real `/cleanupcatchup`.)
- **Real run** → ask: *"Fix all, pick numbers, or skip?"* Apply only what's approved (NRW Tier-1: never modify code without explicit approval). After presenting — whether the user fixes or skips — advance the marker:

```bash
git rev-parse HEAD > .claude/last_catchup_commit
echo "Catch-up marker advanced to $(git rev-parse --short HEAD)."
```

Notes:
- `.claude/last_catchup_commit` is gitignored (personal, per-machine — your catch-up history, not the team's).
- The marker tracks **what you've already caught up on**, not what's "yours" — concurrent/daily-pipeline commits in the range are reviewed too (and noted as not-our-work, per /review's normal behavior).
- To re-run from further back, delete `.claude/last_catchup_commit` (resets to first-run).
