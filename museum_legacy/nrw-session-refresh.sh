#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
./sync_package.sh
./nrw-post-validate.sh
