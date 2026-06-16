---
description: Build & run the tvOS app in the simulator in DEBUG mode (live reload via Metro)
allowed-tools: Bash
---

Build and launch the tvOS app in the Apple TV simulator in **Debug** mode.

In Debug, the app loads its JavaScript live from the Metro dev server, so JS edits
hot-reload in the simulator within seconds (no rebuild). `run-ios` auto-starts Metro.

**Use this while actively working on the JS.** Downside: Metro must stay running —
if it's closed or the laptop sleeps, the app goes white until Metro is restarted.

Run this (start Metro first, wait until it's ready, build, then relaunch so the app
reliably fetches the freshly-served bundle — avoids the first-launch white screen):

```bash
cd NRWApp-tvOS
SIM='Apple TV 4K (3rd generation)'
BID=org.reactjs.native.example.NRWApp-tvOS

# 1) Ensure Metro is up (Debug loads JS from it). Start detached if not.
if ! lsof -iTCP:8081 -sTCP:LISTEN -n -P >/dev/null 2>&1; then
  (nohup npx react-native start >/tmp/nrw-metro.log 2>&1 &)
  for i in $(seq 1 30); do lsof -iTCP:8081 -sTCP:LISTEN -n -P >/dev/null 2>&1 && break; sleep 1; done
fi
lsof -iTCP:8081 -sTCP:LISTEN -n -P >/dev/null 2>&1 || { echo "ERROR: Metro failed to start (see /tmp/nrw-metro.log)"; exit 1; }

# 2) Build, install, launch — skip RN's own packager spawn (needs an interactive terminal)
npx react-native run-ios --mode Debug --scheme NRWAppTemp-tvOS --simulator "$SIM" --no-packager

# 3) Relaunch once so the app pulls the bundle now that Metro is serving it
DEV=$(xcrun simctl list devices booted | grep -oE '[0-9A-Fa-f-]{36}' | head -1)
[ -n "$DEV" ] && { xcrun simctl terminate "$DEV" "$BID" 2>/dev/null; xcrun simctl launch "$DEV" "$BID"; }
```

Note: `--no-packager` is required when launching outside an interactive terminal —
otherwise `run-ios` aborts trying to open Metro in a new Terminal window.

Notes:
- The real scheme is `NRWAppTemp-tvOS` (not `NRWApp-tvOS`).
- `--mode Debug` sets the configuration directly, so this works regardless of what
  the Xcode scheme's launch configuration is currently set to.
- First build of a session takes a couple minutes (native compile); after that JS
  edits reload instantly.
- To go standalone (no server needed), use `/TVOSreleasemode`.
