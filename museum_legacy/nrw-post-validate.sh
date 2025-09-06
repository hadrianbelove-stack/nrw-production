#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$HOME/Downloads/new-release-wall}"

echo "▶ S1: Snapshot"
SNAP_DIR="$(./nrw-make-code-snapshot.sh || true)"
test -n "${SNAP_DIR:-}" || { echo "Snapshot step didn't return a path"; exit 2; }

ZIP="${SNAP_DIR}.zip"

echo "▶ S2: Audit"
if ./nrw-audit.sh; then
  STATUS="PASS"
else
  STATUS="FAIL"
fi

echo "▶ S3: Diff (light)"
if [[ -n "$LAST" ]]; then
  echo "— changed files since previous snapshot:"
  comm -3 <(cut -c 23- "$LAST" | sort) <(cut -c 23- "$MAN" | sort) | sed 's/^/  /' || true
else
  echo "— first snapshot this session (no previous manifest)"
fi

echo
echo "==== POST-VALIDATION ${STATUS} ===="
if [[ "$STATUS" == "PASS" ]]; then
  ls -lh "$ZIP" "$MAN"
  echo "UPLOAD THESE:"
  echo "  $ZIP"
  echo "  $MAN"
  exit 0
else
  echo "Fix the reported issue(s) above, reapply patch if needed, then rerun: ./nrw-post-validate.sh"
  exit 1
fi
# === Charter & bundle validation (AMENDMENT-021) ===
set -euo pipefail
cd "${REPO:-$PWD}"

fail(){ echo "FAIL: $*"; exit 1; }

# Required outputs
[ -f output/data.json ] || fail "missing output/data.json"
[ -f output/site/index.html ] || fail "missing output/site/index.html"
RNDR=$(unzip -p "$Z" output/site/index.html | grep -Eo 'render_[A-Za-z0-9_]+\.js' | head -1 || true)
RNDR=$(unzip -p "$Z" output/site/index.html | grep -Eo 'render_[A-Za-z0-9_]+\.js' | head -1 || true)
[ -f PROJECT_LOG.md ] || fail "missing PROJECT_LOG.md"
[ -f complete_project_context.md ] || fail "missing complete_project_context.md"

# Charter checks
MIN_AMEND=${CHARTER_MIN_AMENDMENTS:-20}
A_COUNT=$(grep -c '^### AMENDMENT-' PROJECT_CHARTER.md || true)
[ "${A_COUNT:-0}" -ge "$MIN_AMEND" ] || fail "charter has ${A_COUNT:-0} amendments (< $MIN_AMEND)"

# Timestamped charter presence and hash parity
STAMPED=$(ls -1t PROJECT_CHARTER_*.md 2>/dev/null | head -1 || true)
[ -n "${STAMPED:-}" ] || fail "no timestamped charter in repo root (expected created during packaging)"
SHA_REPO=$(shasum -a 256 PROJECT_CHARTER.md | awk '{print $1}')
SHA_STAMP=$(shasum -a 256 "$STAMPED" | awk '{print $1}')
[ "$SHA_REPO" = "$SHA_STAMP" ] || fail "repo charter vs timestamped charter hash mismatch"

# Charter history copy
[ -f "charter_history/$(basename "$STAMPED")" ] || fail "missing charter_history copy"

echo "POSTVALIDATION: OK"

# Forbid plain charter inside latest bundle
if [ -n "$BZIP" ] && unzip -l "$BZIP" | grep -q '\bPROJECT_CHARTER.md\b'; then
  echo "FAIL: bundle contains plain PROJECT_CHARTER.md"; exit 1
fi

# === Working-set validation ===
Z=$(ls -1t NRW_WORKINGSET_*.zip 2>/dev/null | head -1 || true)
[ -z "$Z" ] && { echo "WARN: no working set zip detected"; exit 0; }

# must contain index.html
unzip -l "$Z" | awk '{print $4}' | grep -q '^ui/index.html$' || { echo "FAIL: index.html missing"; exit 1; }

# renderer asset exists if referenced
RNDR=$(unzip -p "$Z" ui/index.html | grep -Eo 'render_[A-Za-z0-9_]+\.js' | head -1 || true)
if [ -n "$RNDR" ]; then
  unzip -l "$Z" | awk '{print $4}' | grep -q "^assets/$RNDR$" || { echo "FAIL: renderer asset $RNDR missing"; exit 1; }
fi

# forbid stray html
BAD=$(unzip -l "$Z" | awk '{print $4}' | grep -Ei '\.html$' | grep -Ev '^ui/index\.html$|^src/site.*\.html$' || true)
[ -z "$BAD" ] || { echo "FAIL: stray HTML in working set"; echo "$BAD"; exit 1; }

# approved renderer requires curated ids (best-effort if jq absent)
if echo "$RNDR" | grep -q 'render_approved\.js'; then
  if ! unzip -l "$Z" | awk '{print $4}' | grep -q '^assets/curated_selections\.json$'; then
    echo "FAIL: approved renderer but curated_selections.json missing"; exit 1
  fi
fi



# === FLAT_HANDOFF_VALIDATION ===
set -euo pipefail
HANDOFF_DIR="$(ls -1dt WORKING_SET_HANDOFF_* 2>/dev/null | head -1 || true)"
if [ -n "${HANDOFF_DIR:-}" ]; then
  if find "$HANDOFF_DIR" -mindepth 1 -type d | read; then echo "FAIL: subdirectories present in $HANDOFF_DIR"; exit 1; fi
  for f in index.handoff.html _ASSET_MAP.txt _MANIFEST.txt; do
    [ -f "$HANDOFF_DIR/$f" ] || { echo "FAIL: missing $f"; exit 1; }
  done
  if ls "$HANDOFF_DIR"/PROJECT_CHARTER.md 1>/dev/null 2>&1; then echo "FAIL: plain PROJECT_CHARTER.md in handoff"; exit 1; fi
  ls "$HANDOFF_DIR"/PROJECT_CHARTER_*.md 1>/dev/null 2>&1 || { echo "FAIL: missing timestamped charter"; exit 1; }
  # verify rewritten refs exist
  awk -F'"' '/(src|href)=/ {print $2}' "$HANDOFF_DIR/index.handoff.html" | grep -vE '^(https?|data:)' | while read -r p; do
    b="$(basename "$p")"; [ -f "$HANDOFF_DIR/$b" ] || { echo "FAIL: missing asset $b"; exit 1; }
  done
fi
# FLAT_HANDOFF_ONLY

# === VALIDATION_SUMMARY ===
if [ -n "${HANDOFF_DIR:-}" ]; then
  echo "VALIDATION: OK (flat handoff)" || true
fi
