#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
STAMP="$(date -u +%Y%m%d-%H%M%SZ)"; mkdir -p charter_history
# Any PROJECT_CHARTER.md not at repo root gets timestamped and removed
while IFS= read -r f; do
  [ "$f" = "./PROJECT_CHARTER.md" ] && continue
  tgt="charter_history/PROJECT_CHARTER_${STAMP}.md"
  cp -f "$f" "$tgt"; rm -f "$f"
  echo "SANITIZED stray charter -> $tgt"
done < <(find . -type f -name 'PROJECT_CHARTER.md' -not -path './PROJECT_CHARTER.md')
