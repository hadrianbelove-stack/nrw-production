---
description: Bump build number, archive the tvOS app, and upload it to TestFlight (App Store Connect API key)
allowed-tools: Bash, Read, Edit
---

Ship a new tvOS build to TestFlight, fully automatic (no Xcode, no clicks).

This: (0) **verifies the app actually runs** in the Release simulator, (1) bumps the build
number, (2) archives `NRWAppTemp-tvOS` in Release, (3) exports and uploads to App Store
Connect using an App Store Connect API key. The build then shows up in TestFlight after
Apple finishes processing it (usually 5–30 min).

**A clean archive + upload only proves the app *compiles and packages* — not that it runs.**
Step 0 below builds and launches the app in the Release simulator (the same configuration
TestFlight ships) and screenshots it, so a broken build is caught before it reaches testers
instead of after.

## One-time setup (required before first run)

1. Go to App Store Connect → **Users and Access → Integrations → App Store Connect API**.
2. Generate a **Team Key** with the **App Manager** role. Download the `.p8` file
   (you can only download it once). Note the **Key ID** and the **Issuer ID** shown on that page.
3. Put the key file here (create the folder if needed):
   `~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`
4. Create `NRWApp-tvOS/.testflight.env` (gitignored) with:
   ```
   ASC_KEY_ID=<KEY_ID>
   ASC_ISSUER_ID=<ISSUER_ID>
   ```

The `.p8` and `.testflight.env` are gitignored and never committed.

## Step 0 — Verify it runs in the Release simulator (do this FIRST)

Before bumping or archiving anything, build and launch the app in the Apple TV simulator in
**Release** mode, screenshot it, and look at the screenshot to confirm the wall renders (or
that whatever change you're shipping is actually present). Release mode bundles the JS, so
this matches what TestFlight ships — a white screen, a crash, or a missing change here means
the build is bad and must NOT be uploaded.

```bash
cd NRWApp-tvOS
mkdir -p build
# Build + install + launch in the Release simulator. --no-packager is REQUIRED:
# Release bundles the JS at build time (Metro not needed), and without the flag
# `run-ios` tries to open Metro in a new terminal window and aborts headless with
# "error Cannot start server in new window because no terminal app was specified"
# — building nothing (log has only that line). With --no-packager it compiles,
# installs, and launches normally.
npx react-native run-ios --mode Release --scheme NRWAppTemp-tvOS --simulator 'Apple TV' --no-packager > build/sim-release.log 2>&1
xcrun simctl launch booted org.reactjs.native.example.NRWApp-tvOS
# give it a few seconds to render, then capture:
xcrun simctl io booted screenshot build/sim-release-shot.png
```

Then **Read `build/sim-release-shot.png`** and confirm the app rendered correctly.

**STOP here and show the screenshot to the user. Do not proceed to the bump/archive/upload
steps until the user confirms the build looks good.** If the screenshot shows a white screen,
a crash, or the change is missing, do NOT upload — fix the build and re-run Step 0.

## Run (only after Step 0 passes and the user approves)

Execute the following, then report the build number and upload result. If any `ERROR:`
line prints, stop and show it — do not continue.

```bash
cd NRWApp-tvOS

# 1) Credentials
if [ ! -f .testflight.env ]; then echo "ERROR: NRWApp-tvOS/.testflight.env missing — see one-time setup."; exit 1; fi
set -a; . ./.testflight.env; set +a
P8="$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8"
[ -n "$ASC_KEY_ID" ] && [ -n "$ASC_ISSUER_ID" ] || { echo "ERROR: ASC_KEY_ID / ASC_ISSUER_ID not set in .testflight.env"; exit 1; }
[ -f "$P8" ] || { echo "ERROR: key file not found at $P8"; exit 1; }

# 2) Bump build number (CURRENT_PROJECT_VERSION) on the app target only
/usr/bin/python3 - <<'PY'
import re, pathlib
p = pathlib.Path("ios/NRWApp.xcodeproj/project.pbxproj")
s = p.read_text()
cur = max(int(m) for m in re.findall(r'CURRENT_PROJECT_VERSION = (\d+);', s))
nxt = cur + 1
s = s.replace(f'CURRENT_PROJECT_VERSION = {cur};', f'CURRENT_PROJECT_VERSION = {nxt};')
p.write_text(s)
print(f"Build number: {cur} -> {nxt}")
PY

# 3) Archive (Release) — timestamped paths so repeat runs never collide
#    (avoids `rm -rf`, which trips the destructive-command guard).
mkdir -p build
STAMP=$(date +%Y%m%d-%H%M%S)
ARCH="build/NRWApp-tvOS-$STAMP.xcarchive"
xcodebuild -workspace ios/NRWApp.xcworkspace \
  -scheme NRWAppTemp-tvOS \
  -configuration Release \
  -sdk appletvos \
  -destination 'generic/platform=tvOS' \
  -archivePath "$ARCH" \
  -allowProvisioningUpdates \
  clean archive

# 4) Export + upload to TestFlight in one step (destination=upload in ExportOptions)
xcodebuild -exportArchive \
  -archivePath "$ARCH" \
  -exportOptionsPlist ios/ExportOptions.plist \
  -exportPath "build/export-$STAMP" \
  -authenticationKeyPath "$P8" \
  -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  -allowProvisioningUpdates
```

## After a successful run

- The new build number is committed-worthy: stage `project.pbxproj` so the bump isn't lost.
  (Commit message must end with `APPROVED: DELETE` only if it removes lines — a version bump
  doesn't, so a normal message is fine.)
- The build appears under TestFlight in App Store Connect once processing finishes.

## Notes / first-run gotchas

- `ios/ExportOptions.plist` uses `method = app-store-connect` — confirmed working on
  Xcode 26 (build 22 uploaded cleanly Jun 16 2026). If a future toolchain rejects it,
  change it to `app-store`.
- The scheme is `NRWAppTemp-tvOS` and the bundle ID is `org.reactjs.native.example.NRWApp-tvOS`.
- The first archive of a session takes several minutes (full native compile + JS bundle).
- **Working directory does NOT persist between separate shell calls** — each one starts at
  the repo root, so re-`cd NRWApp-tvOS` (or use absolute paths) every call. Also note
  `clean archive` wipes loose files under `build/`, so don't stash the timestamp in a
  `build/` file expecting it to survive the archive — capture `STAMP` and the archive path
  in the same shell call that uses them.
