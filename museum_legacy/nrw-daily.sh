#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
# build site (tolerate offline)
python3 generate_site.py || true
./sync_package.sh
./nrw-post-validate.sh
