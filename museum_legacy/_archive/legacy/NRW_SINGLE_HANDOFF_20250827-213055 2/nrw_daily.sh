#!/usr/bin/env bash
set -euo pipefail
REPO="$HOME/Downloads/new-release-wall"
SITE="$REPO/output/site"
source "$REPO/.venv/bin/activate" 2>/dev/null || true

# 1) Update → build
python3 movie_tracker.py daily
python3 generate_from_tracker.py 14
python3 build_wall.py
python3 generate_site.py

# 2) Deploy (needs NETLIFY_AUTH_TOKEN + NETLIFY_SITE_ID)
cd "$SITE"
netlify deploy --prod --dir=. --site "$NETLIFY_SITE_ID"

# 3) Package handoff
cd "$REPO"
chmod +x ./sync_package.sh 2>/dev/null || true
./sync_package.sh
