#!/usr/bin/env bash
set -euo pipefail

# NRW — rebuild + serve + sanity
cd "$(dirname "$0")" || exit 2
source .venv/bin/activate 2>/dev/null || { python3 -m venv .venv && source .venv/bin/activate; }

# Clean + regenerate
rm -rf output/site && mkdir -p output/site
python3 generate_site.py || echo "WARN: generate_site.py returned non-zero"

# Sanity checks
if [ -s output/data.json ]; then
  echo "OK: output/data.json exists"
  if command -v jq >/dev/null; then
    jq 'length as $n | "Movie count=\($n)"' output/data.json
    jq '.[0] | keys' output/data.json | head -20
    echo "Null RT scores count:"; jq '[.[] | select(.rt_score==null)] | length' output/data.json
    echo "Missing posters count:"; jq '[.[] | select((.poster//"")=="" or (.poster|type=="null"))] | length' output/data.json
  else
    echo "Tip: brew install jq"; head -40 output/data.json
  fi
else
  echo "FAIL: output/data.json missing or empty"
fi

# Serve locally
cd output/site
python -m http.server 3001 >/tmp/nrw_http.log 2>&1 &
SRV_PID=$!
echo "Local site: http://localhost:3001/  (PID $SRV_PID)"
echo "To stop server: kill $SRV_PID"
