#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$HOME/Downloads/new-release-wall}"
WITH_INDEX="${1:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BASE="CODE_SNAP_${STAMP}"
OUTDIR="$ROOT/snapshots"
TMP="$(mktemp -d)"
INCLUDE_EXT='py|js|ts|html|css|md|yaml|yml|toml|ini|cfg'
MAX_FILE=$((5*1024*1024))     # per-file cap
MAX_TOTAL=$((12*1024*1024))   # total cap

cd "$ROOT"
mkdir -p "$OUTDIR"

# Stage code-only tree
rsync -a --prune-empty-dirs \
  --include='*/' --include="*.@(${INCLUDE_EXT})" \
  --exclude='.git/' --exclude='.venv/' --exclude='_sync_tmp/' \
  --exclude='.cache/' --exclude='snapshots/' --exclude='_backup/' \
  --exclude='NRW_SYNC_*' --exclude='*.zip' --exclude='*.tar.gz' \
  --exclude='node_modules/' --exclude='dist/' --exclude='build/' \
  --exclude='**/*.jpg' --exclude='**/*.jpeg' --exclude='**/*.png' \
  --exclude='**/*.webp' --exclude='**/*.gif' --exclude='**/*.mp4' \
  --exclude='**/*.mov' --exclude='**/*.pdf' \
  --exclude='output/' \
  ./ "$TMP/src/" >/dev/null

# Optional: include generated index.html only
if [[ "$WITH_INDEX" == "--with-index" && -f output/site/index.html ]]; then
  mkdir -p "$TMP/src/output/site"
  install -m 0644 output/site/index.html "$TMP/src/output/site/index.html"
fi

# Always embed governance docs
STAMP=$(date -u +%Y%m%d-%H%M%SZ)
mkdir -p "$TMP/site" "$TMP/src"
[ -d output/site ] && rsync -a output/site/ "$TMP/site/"
CH_SHA=$(shasum -a 256 PROJECT_CHARTER.md | awk '{print $1}')
cp PROJECT_CHARTER.md "$TMP/src/PROJECT_CHARTER_${STAMP}.md"
mkdir -p charter_history
cp "$TMP/src/PROJECT_CHARTER_${STAMP}.md" "charter_history/PROJECT_CHARTER_${STAMP}.md"
echo "$CH_SHA  PROJECT_CHARTER_${STAMP}.md" > "$TMP/src/PROJECT_CHARTER_${STAMP}.sha256"
for d in PROJECT_CHARTER.md PROJECT_LOG.md complete_project_context.md; do
  if [[ -f "$d" ]]; then
    mkdir -p "$TMP/src/$(dirname "$d")"
    install -m 0644 "$d" "$TMP/src/$d"
  fi
done

# Build pack with caps
TOTAL=0
( cd "$TMP/src"
  mkdir -p ../pack
  LC_ALL=C find . -type f -print0 | sort -z | while IFS= read -r -d '' f; do
    sz=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f")
    [[ "$sz" -le "$MAX_FILE" ]] || continue
    (( TOTAL + sz <= MAX_TOTAL )) || continue
    mkdir -p "../pack/$(dirname "$f")"
    install "$f" "../pack/$f"
    TOTAL=$((TOTAL + sz))
  done
)

# Create ZIP deterministically
( cd "$TMP/pack" && LC_ALL=C find . -type f | sort | zip -q -X -@ "$OUTDIR/${BASE}.zip" )

# Manifest beside ZIP
MAN="$OUTDIR/${BASE}.manifest.txt"
{
  echo "# CODE MANIFEST ${STAMP}"
  echo "# root: $ROOT"
  unzip -Z1 "$OUTDIR/${BASE}.zip" | LC_ALL=C sort | while read -r f; do
    tmp="$(mktemp)"; unzip -p "$OUTDIR/${BASE}.zip" "$f" > "$tmp"
    sz=$(wc -c <"$tmp" | tr -d ' ')
    sum=$(shasum -a 256 "$tmp" | awk '{print $1}')
    printf "%10d  %s  %s\n" "$sz" "$sum" "$f"
    rm -f "$tmp"
  done
} > "$MAN"

# SHA beside ZIP
shasum -a 256 "$OUTDIR/${BASE}.zip" > "$OUTDIR/${BASE}.zip.sha256"

echo "${OUTDIR}/${BASE}"
# NOTE: could not auto-insert snapshot block; manual review needed.

# --- NRW snapshot parity (timestamped charter, no plain charter)
STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
SNAP="${SNAP:-$PWD/snapshot_${STAMP}}"
rm -rf "$SNAP"; mkdir -p "$SNAP"
rsync -a --exclude ".venv/" --exclude "*.zip" --exclude "*.sha256" --exclude "*.manifest.txt" --include "*/" \
      --include "*.py" --include "*.js" --include "*.css" --include "*.md" --include "*.yaml" --include "*.yml" \
      --include "templates/***" --exclude "*" ./ "$SNAP/"
CH="PROJECT_CHARTER_${STAMP}.md"
mkdir -p charter_history
cp PROJECT_CHARTER.md "$SNAP/$CH"
cp "$SNAP/$CH" "charter_history/$CH"
( cd "$SNAP" && zip -rq "../snapshot_${STAMP}.zip" . )
shasum -a 256 "snapshot_${STAMP}.zip" | awk '{print $1}' > "snapshot_${STAMP}.sha256"
echo "SNAPSHOT OK: snapshot_${STAMP}.zip"

# LEGACY_NRW_SYNC_DISABLED: do not produce or accept NRW_SYNC artifacts
