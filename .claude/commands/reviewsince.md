---
description: Review only the work done since your last review — tracks a marker so nothing is re-reviewed or missed
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, Skill
---

Review everything committed since the last time a review was run, then advance the marker.

## 1. Find the starting point

```bash
MARKER=$(cat .claude/last_review_commit 2>/dev/null | tr -d '[:space:]')
if [ -n "$MARKER" ] && git cat-file -e "${MARKER}^{commit}" 2>/dev/null; then
  echo "Last-review marker: $MARKER"
  echo "--- commits since then ($MARKER..HEAD) ---"
  git log --oneline "$MARKER..HEAD"
  echo "--- count ---"
  git rev-list --count "$MARKER..HEAD"
else
  echo "No valid marker yet (first run) — fall back to the last 3 commits."
  git log --oneline -3
fi
```

- If the count is **0** (no commits since the marker): tell the user *"Nothing new since your last review (`<short marker>`)."* and **STOP** — do not advance the marker, do not run a review.
- If **first run** (no marker): use `HEAD~3..HEAD` as the range, and mention you're starting fresh (next run will track from here).
- Otherwise the range is `<MARKER>..HEAD`.

## 2. Run the review

Run the standard **/review** on that range — invoke the `review` skill with the range string (e.g. `abc123..HEAD` or `HEAD~3..HEAD`) as its argument, and let it do its normal Phase 1 confirm + Phase 2 report. Do **not** duplicate the review checklist here.

## 3. Advance the marker — only AFTER the review has been presented

```bash
git rev-parse HEAD > .claude/last_review_commit
echo "Marker advanced to $(git rev-parse --short HEAD). Next /reviewsince starts here."
```

Notes:
- `.claude/last_review_commit` is gitignored (personal, per-machine — your review history, not the team's).
- The marker tracks **what you've already looked at**, not what's "yours" — concurrent/daily-pipeline commits in the range are reviewed too (and noted as not-our-work, per /review's normal behavior).
- If the user wants to re-review from further back, they can delete `.claude/last_review_commit` (resets to first-run) or run plain `/review <range>`.
