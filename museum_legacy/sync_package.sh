#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"
./nrw-make-handoff.sh
./nrw-post-validate.sh || true
HANDOFF="$(ls -1dt WORKING_SET_HANDOFF_* | head -1 || true)"
echo "WORKING SET HANDOFF: ${HANDOFF:-none}"