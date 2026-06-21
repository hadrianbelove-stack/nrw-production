# NRW Roku App

Roku channel for **New Release Wall** - your guide to new digital releases.

## Overview

This Roku app is part of the NRW multi-platform ecosystem, sharing data and design patterns with:
- **Web**: `index.html` (vanilla JS/CSS)
- **tvOS**: `NRWApp-tvOS/` (React Native)
- **Android TV**: `NRWApp-Android/` (Kotlin Compose)

## Features

- **8-column movie grid** matching other platforms
- **Filtering**: Pre-Orders, Studio, Indie, NRW Picks, Foreign, Miniseries, Reissues, Docs, V. Screenings
- **Search** by title, director, or genre
- **Movie details** with large poster, metadata, and watch buttons
- **Deep linking** to streaming apps (Netflix, Prime, Disney+, Max, Hulu, etc.)
- **24-hour caching** with offline fallback
- **Focus management** for Roku remote navigation

## Project Structure

```
NRWApp-Roku/
├── manifest                    # App metadata
├── source/
│   ├── main.brs               # Entry point
│   ├── api/
│   │   ├── NRWApi.brs         # Data fetching
│   │   └── CacheManager.brs   # 24-hour caching
│   ├── utils/
│   │   ├── MovieUtils.brs     # Filter/search logic
│   │   └── DeepLinkUtils.brs  # Streaming app launches
│   └── constants/
│       └── Colors.brs         # Design system colors
├── components/
│   ├── screens/
│   │   ├── HomeScreen.xml/brs # Main grid screen
│   │   └── DetailScreen.xml/brs # Movie details
│   └── ui/
│       ├── MovieCard.xml/brs  # Poster card
│       ├── FilterBar.xml/brs  # Category filters
│       └── WatchButton.xml/brs # Service buttons
├── images/                    # App icons, service logos
└── locale/en_US/             # Localization
```

## Data Source

All NRW apps fetch from the same data.json:
```
https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json
```

## Design System

Colors match the web and other apps (from `docs/STYLE_GUIDE.md`):

| Color | Hex | Usage |
|-------|-----|-------|
| Background | `#0A0A0A` | Main background |
| Primary | `#00D4AA` | Teal accent |
| Staff Pick (Select) | `#00D4AA` | Featured items (teal brand) |
| Text Primary | `#FFFFFF` | Headings |
| Text Secondary | `#BBBBBB` | Body text |

## Remote Controls

| Button | Action |
|--------|--------|
| D-pad | Navigate |
| OK | Select |
| Back | Go back |
| Play | Play trailer |
| Options (*) | Show filters |
| Rewind/FF | Prev/next movie |

## Development

### Prerequisites
- Roku Developer account
- Roku device in Developer Mode
- VS Code with BrightScript extension (recommended)

### Sideloading
1. Enable Developer Mode on your Roku
2. Package the app: `zip -r nrw.zip . -x "*.git*"`
3. Upload via Roku's Developer Application Installer

### Debugging
- Use Roku's debug console: `telnet <roku-ip>:8085`
- View logs via BrightScript console

### Live testing loop (no phone / no photos)

Instead of photographing the TV, pull a real screenshot off the dev server and
drive the app over the network. Two helpers in `../scripts/`:

- `scripts/roku_shot.sh [out.jpg]` — captures the current screen to a JPEG
  (default `/tmp/roku_shot.jpg`) via the dev server's `plugin_inspect` +
  `dev.jpg`. Pixel-perfect, no glare.
- `scripts/roku_key.sh KEY [KEY ...]` — sends d-pad/remote keypresses over ECP
  (e.g. `Down Down Select`, or `Lit_a` to type a char), then auto-captures a
  screenshot. `NOSHOT=1` skips the shot.

Both default to `ROKU_IP=192.168.4.53` (DHCP — override with the env var). Dev
server creds: user `rokudev`, password `2463`. If the IP changed, rescan:
`for i in $(seq 1 254); do (curl -s -m1 http://192.168.4.$i:8060/query/device-info | grep -qi roku && echo 192.168.4.$i) & done; wait`

Note: `roku_key.sh` needs remote control enabled on the device —
**Settings → System → Advanced system settings → Control by mobile apps →
Network access → Permissive**. Without it ECP returns HTTP 403. (Screenshots
work regardless; that's a separate dev-server endpoint.)

## Dependencies

No external dependencies - uses only Roku's native SceneGraph framework.

## Channel IDs (for deep linking)

| Service | Channel ID |
|---------|------------|
| Netflix | 12 |
| Prime Video | 13 |
| Hulu | 2285 |
| Disney+ | 291097 |
| Max | 61322 |
| Peacock | 593099 |
| Paramount+ | 57665 |
| Apple TV+ | 551012 |
| Plex | 27707 |
| YouTube | 837 |

## License

Part of the NRW project.
