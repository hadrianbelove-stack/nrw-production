---
description: Bump build number, archive the tvOS app, and upload it to TestFlight (App Store Connect API key)
allowed-tools: Bash, Read, Edit
---

Ship a new tvOS build to TestFlight, fully automatic (no Xcode, no clicks).

This: (1) bumps the build number, (2) archives `NRWAppTemp-tvOS` in Release, (3) exports
and uploads to App Store Connect using an App Store Connect API key. The build then shows
up in TestFlight after Apple finishes processing it (usually 5–30 min).

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

## Run

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

# 3) Archive (Release)
rm -rf build && mkdir -p build
xcodebuild -workspace ios/NRWApp.xcworkspace \
  -scheme NRWAppTemp-tvOS \
  -configuration Release \
  -sdk appletvos \
  -destination 'generic/platform=tvOS' \
  -archivePath build/NRWApp-tvOS.xcarchive \
  -allowProvisioningUpdates \
  clean archive

# 4) Export + upload to TestFlight in one step
xcodebuild -exportArchive \
  -archivePath build/NRWApp-tvOS.xcarchive \
  -exportOptionsPlist ios/ExportOptions.plist \
  -exportPath build/export \
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

- `ios/ExportOptions.plist` uses `method = app-store-connect`. If export fails complaining
  about the method value on this toolchain, change it to `app-store`.
- The scheme is `NRWAppTemp-tvOS` and the bundle ID is `org.reactjs.native.example.NRWApp-tvOS`.
- The first archive of a session takes several minutes (full native compile + JS bundle).
