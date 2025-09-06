#!/bin/bash
set -euo pipefail
REPO="${REPO:-$HOME/Downloads/new-release-wall}"
cd "$REPO"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup python3 curator_admin.py >/tmp/nrw_admin.log 2>&1 &
sleep 2
grep -m1 -Eo 'http://127\.0\.0\.1:[0-9]+' /tmp/nrw_admin.log || tail -n 50 /tmp/nrw_admin.log
