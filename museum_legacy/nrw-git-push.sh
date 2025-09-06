#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"

# initialize repo if needed
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || git init

STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
# Stage only source/governance and scripts (no handoff artifacts)
git add -A \
  :/templates :/*.py :/scripts :/*.sh \
  :/PROJECT_CHARTER.md :/PROJECT_LOG.md :/complete_project_context.md \
  :/.gitignore 2>/dev/null || true

# Commit if there are changes
if ! git diff --cached --quiet; then
  git commit -m "Daily handoff ${STAMP}: code+governance snapshot (flat handoff canonical)"
  # Optional golden tag for milestones (uncomment next line when desired)
  # git tag -a "golden-${STAMP}" -m "Golden snapshot ${STAMP}"
else
  echo "No staged changes; nothing to commit."
fi

# Optional push if remote configured
if git remote get-url origin >/dev/null 2>&1; then
  git push --follow-tags || true
else
  echo "No git remote configured. To set: git remote add origin <URL> && git push -u origin main"
fi