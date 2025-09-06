#!/bin/bash
# nrw-session-start.sh — one-command session kickoff
# - Ensures Charter/Context patches (if present)
# - Creates fresh code snapshot
# - Prints exact files to upload
# Usage: ./nrw-session-start.sh
set -euo pipefail

REPO="${REPO:-$HOME/Downloads/new-release-wall}"
cd "$REPO"

# 0) Optional idempotent patches if the scripts exist
[[ -x ./nrw-append-rule-023-and-context.sh ]] && ./nrw-append-rule-023-and-context.sh || true
[[ -x ./nrw-clarify-rules-018-023.sh      ]] && ./nrw-clarify-rules-018-023.sh      || true

# 1) Snapshot prerequisites
test -x ./nrw-make-code-snapshot.sh || { echo "Missing nrw-make-code-snapshot.sh"; exit 2; }

# 2) Create snapshot (prefer including output/site/index.html when available)
SNAP="$(./nrw-make-code-snapshot.sh --with-index || ./nrw-make-code-snapshot.sh)"
ZIP="${SNAP}.zip"
MAN="${SNAP}.manifest.txt"

# 3) Print clear upload instructions with sizes
echo "UPLOAD THESE NOW:"
ls -lh "$ZIP" "$MAN" | awk '{printf "  %s %10s  %s\n",$1,$5,$9}'

# 4) Log snapshot creation (append-only)
STAMP="$(date +%Y-%m-%d\ %H:%M)"
if [[ -f PROJECT_LOG.md ]]; then
  printf "\n## %s\n- Code snapshot created: %s (%s)\n" "$STAMP" "$(basename "$ZIP")" "$(shasum -a 256 "$ZIP" | awk '{print $1}')" >> PROJECT_LOG.md
  git add PROJECT_LOG.md >/dev/null 2>&1 || true
  git commit -m "Log: create session code snapshot ${SNAP}" >/dev/null 2>&1 || true
  git push >/dev/null 2>&1 || true
fi

echo "Session start ready."