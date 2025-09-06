#!/usr/bin/env bash
set -euo pipefail
HTML="${1:-output/site/index.html}"
echo "== Cards present"
grep -n '<div class="card' "$HTML" | head -5 || echo "no cards"
echo "== Data-attrs sample"
sed -n '1,240p' "$HTML" | grep -E 'data-(country|lang|year|rt|platforms)=' -n | head || echo "no data-* attrs found"
