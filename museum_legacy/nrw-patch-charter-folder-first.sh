#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
mkdir -p charter_history
cp -n PROJECT_CHARTER.md "charter_history/PROJECT_CHARTER_before_folderFirst_${STAMP}.md" 2>/dev/null || true

read -r -d '' NEW <<'MD'
## Session Handoff Checklist (Immutable)

At end of each work session:

1) Run smoke tests as needed to produce a valid site.
2) Verify outputs exist:
   - output/site/index.html
   - output/site/assets/current_releases.json (static mode)
3) Ensure required docs exist:
   - PROJECT_CHARTER.md (repo root, sacrosanct)
   - PROJECT_LOG.md
   - complete_project_context.md
4) Produce the Working Set **folder** (primary handoff):
   - `NRW_WORKINGSET_<UTC-YYYYMMDD-HHMMSSZ>/`
   Contents MUST include only:
   - Runtime truth: `ui/index.html`, `assets/*` (assets referenced by the page)
   - UI sources: `src/templates/site*.html`, `src/render_*.js` (if used), `src/generate_site.py`, `src/adapter.py`
   - Data pipeline: `src/movie_tracker.py`, `src/generate_from_tracker.py`, `src/new_release_wall_balanced.py`, `data/movie_tracking.json`, `data/current_releases.json`, `data/curated_selections.json`
   - Governance/context: `gov/PROJECT_CHARTER_<timestamp>.md`, `gov/PROJECT_LOG.md`, `gov/complete_project_context.md`
   - Canonical scripts: `scripts/sync_package.sh`, `scripts/nrw-make-code-snapshot.sh`, `scripts/nrw-post-validate.sh`, `scripts/nrw-handoff.sh`
   (For archival audit only, an optional backup zip may be written to `bundle_history/`. Do **not** upload zips to the assistant.)
5) Run post-validation on the Working Set.
6) **Resuming with assistant:** open the Working Set folder locally and upload its contents (folders/files) into the chat. Do not upload zips.

# LEGACY_NRW_SYNC_REMOVED **This checklist supersedes and retires all legacy NRW_SYNC handoffs.**
**IF/THEN rule:** When later steps depend on prior results, assistants must wait for results before issuing the next executable block. Safe parallel steps should be bundled into a single labeled block.
MD

# Replace existing checklist section with NEW
awk -v RS= -v ORS="\n\n" -v new="$NEW" '
{
  if ($0 ~ /##[[:space:]]*Session Handoff Checklist/) {
    n = split($0, a, /\n/)
    start = 0; end = n
    for (i=1; i<=n; i++) { if (start==0 && a[i] ~ /^##[[:space:]]*Session Handoff Checklist/) start=i
      if (start>0 && i>start && a[i] ~ /^##[[:space:]]+/) { end=i-1; break } }
    for (i=1; i<start; i++) print a[i]
    print new
    for (i=end+1; i<=n; i++) print a[i]
  } else print
}' PROJECT_CHARTER.md > .char && mv .char PROJECT_CHARTER.md

echo "- ${STAMP}: Handoff checklist updated — folder-first Working Set; zips archival-only" >> PROJECT_LOG.md
echo "Charter folder-first handoff: applied."
