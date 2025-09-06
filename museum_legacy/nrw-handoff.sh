#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
D="$(./nrw-make-handoff.sh | tail -1)"
echo "HANDOFF: $D"
# green light
req=(index.handoff.html _ASSET_MAP.txt _MANIFEST.txt POSTVALIDATION.txt)
for r in "${req[@]}"; do [ -f "$D/$r" ] || { echo "FAIL: missing $r"; exit 1; }; done
ls "$D"/PROJECT_CHARTER_*.md >/dev/null 2>&1 || { echo "FAIL: missing timestamped charter"; exit 1; }
[ -z "$(find "$D" -mindepth 1 -type d)" ] || { echo "FAIL: subdirectories present"; exit 1; }
echo "PRE-UPLOAD: OK"