#!/bin/bash
# Usage: ./nrw-restore-from-sync.sh /path/to/NRW_SYNC_YYYYMMDD-HHMM.zip
set -euo pipefail
ZIP="${1:-}"
[[ -f "$ZIP" ]] || { echo "Provide a valid NRW_SYNC zip path"; exit 2; }
REPO="${REPO:-$HOME/Downloads/new-release-wall}"
mkdir -p "$REPO"; cd "$REPO"
unzip -o "$ZIP" >/dev/null
if [[ -f requirements.txt ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt
fi
echo "Restored from $ZIP"
