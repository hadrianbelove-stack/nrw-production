#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
./sync_package.sh
./nrw-post-validate.sh

# LEGACY_NRW_SYNC_DISABLED: do not produce or accept NRW_SYNC artifacts
