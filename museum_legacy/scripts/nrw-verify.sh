#!/usr/bin/env bash
set -euo pipefail
err=0
for f in assets/data.json assets/nrw_render.js; do
  [ -f "$f" ] || { echo "MISSING: $f"; err=1; }
done
grep -qE '<div[^>]+id="cards"|class="cards|class="grid"' index.runtime.html 2>/dev/null || {
  echo "MISSING: cards container in index.runtime.html"; err=1; }
if [ $err -ne 0 ]; then exit 2; else echo "VERIFY: OK"; fi
