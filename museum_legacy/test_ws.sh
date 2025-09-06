#!/bin/bash
set -euo pipefail

STAMP=$(date -u +%Y%m%d-%H%M%SZ)
BUILD="_ws_tmp_$STAMP"
rm -rf "$BUILD" 
mkdir -p "$BUILD"/{ui,assets,src,data,gov,scripts}

echo "Step 1: Runtime truth"
cp output/site/index.html "$BUILD/ui/"
cp output/site/assets/* "$BUILD/assets/"

echo "Step 2: UI sources" 
cp templates/site*.html "$BUILD/src/"
cp render_*.js "$BUILD/src/" 2>/dev/null || true
cp generate_site.py adapter.py "$BUILD/src/"

echo "Step 3: Data pipeline"
cp movie_tracker.py generate_from_tracker.py new_release_wall_balanced.py "$BUILD/src/"
cp movie_tracking.json current_releases.json curated_selections.json "$BUILD/data/" 2>/dev/null || true

echo "Step 4: Governance"
CH_NAME="PROJECT_CHARTER_${STAMP}.md"
cp PROJECT_CHARTER.md "$BUILD/gov/$CH_NAME"
mkdir -p charter_history
cp "$BUILD/gov/$CH_NAME" "charter_history/$CH_NAME"
cp PROJECT_LOG.md complete_project_context.md "$BUILD/gov/"

echo "Step 5: Scripts"
cp sync_package.sh nrw-make-code-snapshot.sh nrw-post-validate.sh nrw-handoff.sh "$BUILD/scripts/"

echo "Step 6: Package"
ZIP="NRW_WORKINGSET_${STAMP}.zip"
(cd "$BUILD" && zip -rq "../$ZIP" .)
shasum -a 256 "$ZIP" | awk '{print $1}' > "NRW_WORKINGSET_${STAMP}.sha256"

echo "WORKING SET OK: $ZIP"
ls -lh "$ZIP"