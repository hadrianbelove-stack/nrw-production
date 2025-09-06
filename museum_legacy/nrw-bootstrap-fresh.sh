#!/bin/bash
set -euo pipefail
REPO="${REPO:-$HOME/Downloads/new-release-wall}"
mkdir -p "$REPO"; cd "$REPO"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt
echo "Set TMDB_BEARER or TMDB_API_KEY in env or config.yaml before running daily."
