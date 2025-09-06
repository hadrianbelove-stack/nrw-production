#!/bin/bash
set -euo pipefail
REPO="${REPO:-$HOME/Downloads/new-release-wall}"
cd "$REPO"
rm -rf output/site2 output2 2>/dev/null || true
find output -maxdepth 1 -type f -name 'data*.json' ! -name 'data.json' ! -name 'data_core.json' -delete
find output -type f -name 'index*.html' ! -path 'output/site/index.html' -delete
echo "Cleaned non-canonical outputs"
