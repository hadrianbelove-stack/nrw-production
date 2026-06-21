#!/usr/bin/env bash
# Grab a single still frame from a Mac camera (default: iPhone Continuity Camera)
# and save it locally so it can be Read. Lets an agent "look through" a phone
# pointed at a TV / physical device on demand.
#
# Usage:   scripts/cam_shot.sh [output_path]
#   default output: /tmp/cam_shot.jpg
# Env:     CAM_DEVICE  camera name as ffmpeg/avfoundation lists it
#                      (default "iPhone Camera"). Matched by name, not index,
#                      because avfoundation indices shift as devices connect.
#
# Requires: ffmpeg (brew). The iPhone must be active as a Continuity Camera
# (nearby, unlocked once, Wi-Fi+Bluetooth on, same Apple ID). Wake it by opening
# Photo Booth once if it isn't listed.
set -euo pipefail

CAM_DEVICE="${CAM_DEVICE:-iPhone Camera}"
OUT="${1:-/tmp/cam_shot.jpg}"

# Confirm the camera is currently present. Capture the list first (ffmpeg always
# exits non-zero on -list_devices, which would poison a piped grep under pipefail).
DEVLIST="$(ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true)"
if ! grep -qF "$CAM_DEVICE" <<<"$DEVLIST"; then
  echo "ERROR: camera '$CAM_DEVICE' not found. Is the iPhone awake as a Continuity Camera?" >&2
  echo "       (open Photo Booth once to wake it, or set CAM_DEVICE to a listed camera)" >&2
  echo "Available:" >&2
  grep -E "\[[0-9]+\] " <<<"$DEVLIST" >&2
  exit 1
fi

# Capture one frame. uyvy422 is what Continuity Camera offers; convert on write.
ffmpeg -hide_banner -loglevel error \
  -f avfoundation -pixel_format uyvy422 -framerate 30 -i "$CAM_DEVICE" \
  -frames:v 1 -update 1 -y "$OUT"

if ! file "$OUT" | grep -qi "JPEG\|image"; then
  echo "ERROR: capture failed (no image written)." >&2
  exit 1
fi

echo "$OUT"
