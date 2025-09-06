#!/usr/bin/env bash
set -euo pipefail
cd ~/Downloads/new-release-wall

# Creds (optional)
[[ -f ~/.nrw.env ]] && set -a && source ~/.nrw.env && set +a || true
[[ -z "${TMDB_BEARER:-}" && -z "${TMDB_API_KEY:-}" ]] && echo "WARN: TMDB creds missing (core may 401)"
[[ -z "${OMDB_API_KEY:-}" ]] && echo "WARN: OMDb key missing"

# Require latest one-file bundle
ZIP="$(ls -t NRW_SYNC_*.zip 2>/dev/null | head -1 || true)"
[[ -z "$ZIP" ]] && { echo "ERROR: No NRW_SYNC_*.zip found. Upload latest then rerun."; exit 2; }
echo "Using bundle: $ZIP"
unzip -oq "$ZIP"

# Preflight locks
[[ -x ./ui_lock.sh ]] && ./ui_lock.sh verify || echo "UI-LOCK: skipped (no ui_lock.sh)"
./code_lock.sh verify

# Python env
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip -q install --upgrade pip
pip -q install -r requirements.txt

# Scrapers
python3 new_release_wall_balanced.py --region US --days 14 --max-pages 2 || true
if [[ -n "${TMDB_BEARER:-}" || -n "${TMDB_API_KEY:-}" ]]; then
  python3 new_release_wall_balanced.py --region US --days 14 --max-pages 2 --use-core --core-limit 5 || true
fi

# Tracker + site
python3 movie_tracker.py daily || true
python3 generate_from_tracker.py 14 || true
python3 generate_site.py || true

# Serve
pkill -f "http.server 3001" >/dev/null 2>&1 || true
( cd output/site && python -m http.server 3001 >/dev/null 2>&1 & ) || true

# Snapshot + drift
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p snapshots
SNAP_DIR="snapshots/SNAP_${STAMP}"
mkdir -p "$SNAP_DIR"
find . -type f ! -path "./snapshots/*" ! -path "./.git/*" ! -path "./.venv/*" ! -path "./node_modules/*" ! -path "./web/.next/*" -print0 \
 | sort -z \
 | xargs -0 -I{} sh -c 'printf "%s  %s\n" "$(shasum -a 256 "{}" | cut -d" " -f1)" "{}"' > "${SNAP_DIR}/TREE.sha256"
tar -czf "${SNAP_DIR}/TREE.tgz" --exclude './snapshots' --exclude './.git' --exclude './.venv' --exclude './node_modules' --exclude './web/.next' .

REPORT="DRIFT_REPORT.md"
PREV="$(ls -1dt snapshots/SNAP_* 2>/dev/null | sed -n 2p || true)"
{
  echo "# Drift Report — ${STAMP}"
  if [[ -n "$PREV" ]]; then
    echo "Comparing to: $(basename "$PREV")"
    diff -u <(cut -d" " -f1 "${PREV}/TREE.sha256" | sort) \
            <(cut -d" " -f1 "${SNAP_DIR}/TREE.sha256" | sort) || true
  else
    echo "Baseline session."
  fi
} > "$REPORT"

# One-file handoff
chmod +x sync_package.sh || true
./sync_package.sh

echo "== COMPLETE =="
echo "Open: output/site/index.html  (served on :3001)"
echo "Bundle: $(ls -t NRW_SYNC_*.zip | head -1)"
echo "Snapshot: ${SNAP_DIR}"
echo "Drift: ${REPORT}"
