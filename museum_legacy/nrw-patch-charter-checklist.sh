#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"

STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
mkdir -p charter_history
cp -n PROJECT_CHARTER.md "charter_history/PROJECT_CHARTER_before_WSChecklist_${STAMP}.md" 2>/dev/null || true

read -r -d '' NEW <<'MD'
## Session Handoff Checklist (Immutable)

At end of each work session:

1) Run smoke tests as needed to produce a valid site.
2) Verify outputs exist:
   - output/site/index.html
   - output/site/assets/current_releases.json  (static mode)
3) Ensure required docs exist:
   - PROJECT_CHARTER.md  (repo root, sacrosanct)
   - PROJECT_LOG.md
   - complete_project_context.md
4) Produce a Working Set artifact (choose one):
   - `NRW_WORKINGSET_<UTC-YYYYMMDD-HHMMSSZ>.zip`
   - `_assistant/` folder with identical contents
   Contents MUST include only:
   - Runtime truth: `output/site/index.html`, `output/site/assets/*` (and only assets referenced by the page)
   - UI sources: `templates/site*.html`, `render_*.js` (if used), `generate_site.py`, `adapter.py`
   - Data pipeline: `movie_tracker.py`, `generate_from_tracker.py`, `new_release_wall_balanced.py`, `movie_tracking.json`, `current_releases.json`, `curated_selections.json`
   - Governance/context: repo-root charter + timestamped copy in `charter_history/`, `PROJECT_LOG.md`, `complete_project_context.md`
   - Canonical scripts: `sync_package.sh`, `nrw-make-code-snapshot.sh`, `nrw-post-validate.sh`, `nrw-handoff.sh`
5) Run post-validation on the Working Set (static mode rules apply).
6) Upload the Working Set to the next session.

**IF/THEN rule:** When later steps depend on prior results, assistants must wait for results before issuing the next executable block. Safe parallel steps should be bundled into a single clearly labeled block.
MD

# Replace existing "Session Handoff Checklist" section with NEW
awk -v RS= -v ORS="\n\n" -v new="$NEW" '
{
  if ($0 ~ /##[[:space:]]*Session Handoff Checklist/) {
    # split by lines
    n = split($0, a, /\n/)
    start = 0; end = n
    for (i=1; i<=n; i++) {
      if (start==0 && a[i] ~ /^##[[:space:]]*Session Handoff Checklist/) start=i
      if (start>0 && i>start && a[i] ~ /^##[[:space:]]+/) { end=i-1; break }
    }
    # print before section
    for (i=1; i<start; i++) print a[i]
    print new
    # print after section
    for (i=end+1; i<=n; i++) print a[i]
  } else {
    print
  }
}' PROJECT_CHARTER.md > .char && mv .char PROJECT_CHARTER.md

echo "- ${STAMP}: Replaced Session Handoff Checklist with Working Set policy" >> PROJECT_LOG.md
echo "Checklist updated."
