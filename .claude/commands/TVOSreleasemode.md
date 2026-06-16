---
description: Build & run the tvOS app in the simulator in RELEASE mode (standalone, no Metro)
allowed-tools: Bash
---

Build and launch the tvOS app in the Apple TV simulator in **Release** mode.

In Release, the JavaScript is bundled into the app, so it runs standalone — no Metro
server, nothing to babysit. This is the "just works" mode and matches how the app ships.

**Use this to check the app the way it really ships, or when you don't want to run a
server.** Downside: every JS change needs a full rebuild (a minute or two); no live reload.

```bash
cd NRWApp-tvOS && npx react-native run-ios --mode Release --scheme NRWAppTemp-tvOS --simulator 'Apple TV'
```

Notes:
- The real scheme is `NRWAppTemp-tvOS` (not `NRWApp-tvOS`).
- `--mode Release` sets the configuration directly, so this works regardless of the
  Xcode scheme's stored launch configuration.
- For fast JS iteration with live reload instead, use `/TVOSdebugmode`.
