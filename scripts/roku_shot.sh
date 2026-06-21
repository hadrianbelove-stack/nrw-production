#!/usr/bin/env bash
# Capture a screenshot from the sideloaded NRW Roku app's dev server and save it
# locally so it can be Read. Replaces the slow take-a-photo-of-the-TV loop.
#
# Usage:   scripts/roku_shot.sh [output_path]
#   default output: /tmp/roku_shot.jpg
# Env:     ROKU_IP   (default 192.168.4.53 — DHCP, may drift)
#          ROKU_USER (default rokudev)
#          ROKU_PASS (default 2463)
set -euo pipefail

ROKU_IP="${ROKU_IP:-192.168.4.53}"
ROKU_USER="${ROKU_USER:-rokudev}"
ROKU_PASS="${ROKU_PASS:-2463}"
OUT="${1:-/tmp/roku_shot.jpg}"

# Ask the dev server to grab a fresh frame, then download it.
curl -sf -m5 --digest -u "$ROKU_USER:$ROKU_PASS" \
  "http://$ROKU_IP/plugin_inspect" \
  -F "mysubmit=Screenshot" -F "archive=" >/dev/null

curl -sf -m5 --digest -u "$ROKU_USER:$ROKU_PASS" \
  "http://$ROKU_IP/pkgs/dev.jpg" -o "$OUT"

# Sanity check we actually got a JPEG, not an error page.
if ! file "$OUT" | grep -qi "JPEG"; then
  echo "ERROR: capture failed (not a JPEG). Is ROKU_IP=$ROKU_IP correct and the app sideloaded?" >&2
  exit 1
fi

echo "$OUT"
