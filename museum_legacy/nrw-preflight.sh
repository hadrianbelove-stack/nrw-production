#!/bin/bash
set -euo pipefail
REPO="${REPO:-$HOME/Downloads/new-release-wall}"
SITE_PORT=3001
ADMIN_PORT=5100
cd "$REPO"
[[ -f .venv/bin/activate ]] || { echo "Missing .venv. Create it and install requirements."; exit 2; }
# shellcheck disable=SC1091
source .venv/bin/activate
python3 - <<PY || { echo "Missing Python deps. Run: pip install -r requirements.txt"; exit 2; }
import importlib
for m in ["requests","jinja2","flask","yaml"]:
    importlib.import_module(m)
PY
for f in movie_tracker.py generate_from_tracker.py generate_site.py new_release_wall_balanced.py; do
  [[ -f "$f" ]] || { echo "Missing $f"; exit 2; }
done
if [[ -z "${TMDB_BEARER:-${TMDB_API_KEY:-}}" ]]; then
  if ! grep -qiE 'tmdb\.(bearer|api_key)' config.yaml 2>/dev/null; then
    echo "TMDB credentials missing"
    exit 2
  fi
fi
grep -q 'RULE-010: No amendment, change, or update is considered binding' PROJECT_CHARTER.md || { echo 'RULE-010 missing'; exit 2; }
echo "Preflight OK"
