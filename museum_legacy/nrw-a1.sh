#!/bin/bash
# NRW A1 — place prototype + ops, convert data, run, open Safari
set -euo pipefail
cd "${REPO:-$PWD}"

# Ensure folders
mkdir -p assets scripts ops/briefs

# If you downloaded files to ~/Downloads/new-release-wall-dropin, move them in:
D="${HOME}/Downloads/new-release-wall-dropin"
[ -d "$D" ] && {
  cp -f "$D"/prototype.html ./ || true
  cp -f "$D"/assets/* ./assets/ || true
  cp -f "$D"/scripts/* ./scripts/ || true
  cp -rf "$D"/ops/* ./ops/ || true
}

# Build data.json from your current_releases.json (repo root)
[ -f current_releases.json ] && python3 scripts/convert_current_to_data.py || true

# Serve and open prototype
pgrep -f "http.server 5500" >/dev/null || (python3 -m http.server 5500 >/dev/null 2>&1 &)
sleep 1
open -a Safari "http://localhost:5500/prototype.html" || true

echo "A1 done: prototype running (central panel UI)."