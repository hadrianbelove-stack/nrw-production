#!/bin/bash
# nrw-release-latest.sh [TAG] — attach latest bundle to a GitHub Release for TAG (default = latest golden-*)
# Requires: gh CLI authenticated (gh auth status), internet, and bundle in $HOME/NRW_BUNDLES
set -euo pipefail
cd ~/Downloads/new-release-wall

# 0) Preconditions
command -v gh >/dev/null || { echo "Install GitHub CLI: https://cli.github.com/"; exit 2; }
gh auth status >/dev/null || { echo "Run: gh auth login"; exit 2; }
TAG="${1:-$(git tag --list 'golden-*' | sort | tail -n1)}"
test -n "$TAG" || { echo "No golden tag found. Provide TAG explicitly."; exit 2; }

STAMP="${TAG#golden-}"
ARCH_DIR="${ARCH_DIR:-$HOME/NRW_BUNDLES}"
test -d "$ARCH_DIR" || { echo "Archive dir not found: $ARCH_DIR"; exit 2; }

# 1) Locate artifacts by timestamp first, else fallback to newest
ZIP="$(ls -1t "$ARCH_DIR"/*"$STAMP"*.zip 2>/dev/null | head -n1 || true)"
SHA="$(ls -1t "$ARCH_DIR"/*"$STAMP"*.sha256 2>/dev/null | head -n1 || true)"
if [[ -z "${ZIP:-}" ]]; then
  ZIP="$(ls -1t "$ARCH_DIR"/*.zip 2>/dev/null | head -n1 || true)"
  SHA="$(ls -1t "$ARCH_DIR"/*.sha256 2>/dev/null | head -n1 || true)"
fi
test -f "$ZIP" || { echo "No bundle .zip found in $ARCH_DIR"; exit 2; }
test -f "$SHA" || { echo "No bundle .sha256 found in $ARCH_DIR"; exit 2; }

# 2) Create or update release
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "Release $TAG exists. Uploading assets…"
  gh release upload "$TAG" "$ZIP" "$SHA" --clobber
else
  echo "Creating release $TAG…"
  gh release create "$TAG" "$ZIP" "$SHA" -t "$TAG" -n "NRW sync bundle for $TAG"
fi

# 3) Log URL into PROJECT_LOG.md
URL="$(gh release view "$TAG" --json url -q .url)"
echo "- ${STAMP}: Release published → ${URL} (assets: $(basename "$ZIP"), $(basename "$SHA"))" >> PROJECT_LOG.md
git add PROJECT_LOG.md
git commit -m "Log: publish $TAG release with bundle assets" || true
git push || true

echo "Release published for $TAG:"
echo "  ZIP: $(basename "$ZIP")"
echo "  SHA: $(basename "$SHA")"
echo "  URL: $URL"