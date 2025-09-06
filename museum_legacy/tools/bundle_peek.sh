#!/usr/bin/env bash
set -euo pipefail
Z="${1:-$(ls -1t NRW_WORKINGSET_*.zip | head -1)}"
echo "== Bundle: $Z"
echo "== Renderer tag"
unzip -p "$Z" output/site/index.html | grep -n 'render_.*\.js' || echo "none (static)"
echo "== JSON counts"
unzip -p "$Z" output/site/assets/current_releases.json 2>/dev/null | jq 'length' || echo "no current_releases.json"
unzip -p "$Z" output/site/assets/curated_selections.json 2>/dev/null | jq '.approved_ids|length' || echo "no curated_selections.json"
echo "== Data-attrs sample"
unzip -p "$Z" output/site/index.html | sed -n '1,240p' | grep -E 'data-(country|lang|year|rt|platforms)=' -n | head || echo "no data-* attrs found"
