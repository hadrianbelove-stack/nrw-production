#!/usr/bin/env bash
# Send remote-control keypresses to the Roku over ECP (port 8060), then capture
# a screenshot so the result can be Read. Lets the app be navigated without the
# physical remote.
#
# Usage:   scripts/roku_key.sh KEY [KEY ...]
#   KEY = Up Down Left Right Select Back Home Play Rev Fwd InstantReplay Info
#         Backspace Enter  | or  Lit_<char> to type a literal character
#   examples:
#     scripts/roku_key.sh Down Down Select
#     scripts/roku_key.sh Lit_a Lit_l Lit_i Lit_e Lit_n   # types "alien" into search
#
# Pass NOSHOT=1 to skip the trailing screenshot.
# Env:     ROKU_IP (default 192.168.4.53)
set -euo pipefail

ROKU_IP="${ROKU_IP:-192.168.4.53}"

if [ "$#" -eq 0 ]; then
  echo "usage: scripts/roku_key.sh KEY [KEY ...]" >&2
  exit 1
fi

for key in "$@"; do
  code=$(curl -s -m3 -d '' -o /dev/null -w "%{http_code}" "http://$ROKU_IP:8060/keypress/$key" || echo 000)
  if [ "$code" = "403" ]; then
    echo "ERROR: keypress '$key' blocked (HTTP 403). Enable remote control on the device:" >&2
    echo "  Settings > System > Advanced system settings > Control by mobile apps > Network access > Permissive" >&2
    exit 1
  elif [ "$code" != "200" ]; then
    echo "ERROR: keypress '$key' failed (HTTP $code, ROKU_IP=$ROKU_IP)" >&2
    exit 1
  fi
  sleep 0.3   # let the UI settle/animate between presses
done

if [ "${NOSHOT:-0}" != "1" ]; then
  sleep 0.4
  "$(dirname "$0")/roku_shot.sh"
fi
