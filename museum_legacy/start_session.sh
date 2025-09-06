#!/usr/bin/env bash
set -euo pipefail
echo "== START SESSION =="
git status -sb || true
git pull --ff-only || true
python3 new_release_wall_balanced.py --region US --days 14 --max-pages 1 || true
test -f output/data.json && jq 'length' output/data.json || echo "no output/data.json yet"
echo "Ready."