# NRW iOS App

iPhone/iPad app for **New Release Wall** - curated new releases you won't find elsewhere.

## Overview

This is the iOS (iPhone/iPad) version. See also:
- `NRWApp-tvOS/` - Apple TV (React Native tvOS)
- `NRWApp-Android/` - Android TV (Kotlin Compose)
- `NRWApp-Roku/` - Roku (BrightScript)

## Features

- **2-column movie grid** optimized for mobile
- **Filtering**: All, Staff Picks, Big Time, Niche, Foreign
- **Search** by title, director, or genre
- **"New This Week"** featured section
- **Movie details** with full metadata and watch buttons
- **Universal Links** - opens native streaming apps when installed
- **Affiliate integration** - Amazon and Apple TV affiliate links
- **Pull-to-refresh** for latest data
- **Offline support** with cached data

## Tech Stack

- **React Native 0.73** - Cross-platform UI
- **React Navigation** - Screen navigation
- **Axios** - HTTP requests
- **AsyncStorage** - Local caching
- **react-native-fast-image** - Optimized image loading

## Requirements

- Node.js 18+
- Xcode 15+
- CocoaPods
- iOS 13+ device or simulator

## Getting Started

### Installation

```bash
# Install dependencies
npm install

# Install CocoaPods
cd ios && LANG=en_US.UTF-8 pod install && cd ..
```

### Running

```bash
# Start Metro bundler
npm start

# Run on iOS Simulator
npm run ios

# Run on connected device
npm run ios-device
```

## Project Structure

```
NRWApp-iOS/
├── App.js                    # Main app, navigation setup
├── src/
│   ├── screens/
│   │   ├── HomeScreen.js     # Movie grid with filters
│   │   └── MovieDetail.js    # Full movie info + watch buttons
│   ├── components/
│   │   ├── MovieCard.js      # Poster card component
│   │   ├── WatchButton.js    # Streaming service buttons
│   │   └── FilterBar.js      # Category filter chips
│   ├── services/
│   │   ├── api.js            # Data fetching from GitHub
│   │   ├── analytics.js      # Mixpanel tracking (placeholder)
│   │   └── sentry.js         # Crash reporting (placeholder)
│   ├── utils/
│   │   ├── links.js          # Universal Links handler
│   │   └── cache.js          # AsyncStorage helpers
│   └── constants/
│       └── colors.js         # Brand colors, typography
├── ios/                      # Xcode project files
└── assets/                   # App icons, splash screen
```

## Data Source

Fetches from the same data.json as all NRW apps:
```
https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json
```

## Design System

Colors match the web and TV apps (from `docs/STYLE_GUIDE.md`):

| Color | Hex | Usage |
|-------|-----|-------|
| Background | `#0A0A0A` | Main background |
| Primary | `#00D4AA` | Teal accent |
| Staff Pick | `#DC143C` | Featured badge |
| Text Primary | `#FFFFFF` | Headings |
| Text Secondary | `#BBBBBB` | Body text |

## Watch Button Behavior

Uses iOS Universal Links - no custom URL schemes needed:
- If streaming app is installed: iOS prompts to open it
- If not installed: Opens in Safari
- Affiliate tags preserved in both cases

## App Store Submission

### Required Assets
- App icon (1024x1024)
- Launch screen image
- Screenshots (6.7", 6.5", 5.5" sizes)

### Listing
- **Name**: New Release Wall
- **Category**: Entertainment
- **Age Rating**: 12+

## Related

- [docs/features/NATIVE_APPS.md](../docs/features/NATIVE_APPS.md) - Multi-platform architecture
- [docs/STYLE_GUIDE.md](../docs/STYLE_GUIDE.md) - Design system
- [PROJECT_CHARTER.md](../PROJECT_CHARTER.md) - Governance
