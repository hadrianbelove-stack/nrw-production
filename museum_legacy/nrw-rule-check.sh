#!/bin/bash
set -euo pipefail
cd ~/Downloads/new-release-wall
grep -q 'RULE-010: No amendment, change, or update is considered binding' PROJECT_CHARTER.md \
  || { echo "RULE-010 missing. Run ./nrw-append-rule-010.sh"; exit 2; }
echo "RULE-010 present."
