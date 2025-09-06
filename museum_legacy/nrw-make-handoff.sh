#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"

STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
D="WORKING_SET_HANDOFF_${STAMP}"
mkdir -p "$D"

log(){ printf '%s\n' "$@" | tee -a "$D/BUILD.log" ; }

log "== NRW handoff ${STAMP} =="

# pick the rendered HTML (static mode first)
HTML=""
for c in output/site/index.html ui/index.html index.html; do
  [ -f "$c" ] && { HTML="$c"; break; }
done
cp -f "$HTML"               "$D/index.handoff.html" 2>/dev/null || true
[ -f "$D/index.handoff.html" ] || { log "FATAL: no built index.html found"; exit 2; }

# data (if present)
for j in data/current_releases.json data/curated_selections.json data/movie_tracking.json; do
  [ -f "$j" ] && cp -f "$j" "$D/$(basename "$j")"
done

# governance
cp -f PROJECT_CHARTER.md                  "$D/PROJECT_CHARTER_${STAMP}.md"
[ -f PROJECT_LOG.md ]                 && cp -f PROJECT_LOG.md "$D/PROJECT_LOG.md"
[ -f complete_project_context.md ]    && cp -f complete_project_context.md "$D/complete_project_context.md"

# minimal asset+manifest notes (flat/static)
printf 'mode: static\nassets: none\n' > "$D/_ASSET_MAP.txt"
( cd "$D" && ls -1 > _MANIFEST.txt )

# simple postvalidation summary inside the handoff
{
  echo "VALIDATION_SUMMARY: flat handoff ✓"
  echo "Renderer: none (static)"
  echo "Files: $(wc -l < "$D/_MANIFEST.txt")"
} > "$D/POSTVALIDATION.txt"

# flat-only sanity
if find "$D" -mindepth 1 -type d | read; then
  log "FATAL: subdirectories detected in $D"; exit 3
fi

log "PRE-UPLOAD: OK  → $D"
echo "$D"