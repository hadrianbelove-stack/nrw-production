#!/usr/bin/env bash
# Capture the ACTUAL TV panel via the iPhone Continuity Camera.
# Unlike scripts/roku_shot.sh (which grabs the Roku framebuffer and CANNOT show
# overscan crop), this is a real photo of the screen — use it to verify edges/fit.
#
# Requires: iPhone set up as Continuity Camera (near the Mac, unlocked once),
# pointed at the TV. ffmpeg lists it as "iPhone Camera".
#
# Usage: scripts/roku_cam.sh [output.jpg] [device_index]
set -euo pipefail

OUT="${1:-/tmp/roku_cam.jpg}"
DEV="${2:-}"

# Auto-detect the iPhone Camera device index if not given.
if [ -z "$DEV" ]; then
  DEV=$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
    | grep -iE '\[[0-9]+\] iPhone Camera' \
    | grep -oE '\[[0-9]+\]' | head -1 | tr -d '[]')
fi
DEV="${DEV:-1}"

rm -f "$OUT"
# Grab several frames so the camera is warmed up; keep the last.
ffmpeg -y -f avfoundation -framerate 30 -i "$DEV" -frames:v 10 -update 1 "$OUT" >/dev/null 2>&1
echo "captured TV panel (device $DEV) -> $OUT"
