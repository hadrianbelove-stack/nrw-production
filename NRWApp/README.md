# New Release Wall - tvOS App

React Native app for Apple TV (tvOS) featuring curated indie films.

## Features

- **Horizontal Shelf Layout**: Netflix-style browsing optimized for 10-foot viewing
- **Focus-Based Navigation**: Full support for Siri Remote (d-pad and gestures)
- **Parallax Effects**: Native tvOS visual effects on movie posters
- **Top Shelf Extension**: Featured movies displayed on Apple TV home screen
- **Affiliate Integration**: Amazon (tag=nrw04-20) and Apple TV affiliate links

## Requirements

- Node.js 18+
- Xcode 14+
- React Native tvOS (react-native-tvos)
- Apple TV (4th gen or later) or Simulator

## Getting Started

### Installation

```bash
# Install dependencies
npm install

# Install iOS/tvOS pods
cd tvos && pod install && cd ..
```

### Running the App

```bash
# Start Metro bundler
npm start

# Run on tvOS Simulator
npm run tvos

# Run on Apple TV 4K Simulator
npm run tvos-4k
```

## Project Structure

```
NRWApp/
├── src/
│   ├── screens/
│   │   ├── HomeScreen.js          # Shared logic
│   │   ├── HomeScreen.tvos.js     # tvOS UI (horizontal shelves)
│   │   ├── MovieDetail.js         # Shared logic
│   │   └── MovieDetail.tvos.js    # tvOS UI (full-screen layout)
│   ├── components/
│   │   ├── MovieCard.tvos.js      # Focusable card with parallax
│   │   ├── WatchButton.tvos.js    # Focusable button with glow
│   │   ├── FilterSidebar.tvos.js  # Left sidebar for filters
│   │   └── MovieShelf.tvos.js     # Horizontal scrolling row
│   ├── services/
│   │   ├── api.js                 # Shared data fetching
│   │   ├── analytics.tvos.js      # tvOS analytics
│   │   └── sentry.tvos.js         # Crash reporting
│   ├── utils/
│   │   ├── focusManager.tvos.js   # Focus engine utilities
│   │   ├── links.tvos.js          # Universal Links handler
│   │   └── cache.js               # AsyncStorage caching
│   └── constants/
│       └── colors.js              # Brand colors
├── tvos/
│   └── NRWApp-tvOS/
│       ├── Info.plist
│       └── TopShelfExtension/     # Top Shelf widget
└── assets/
    └── logos/                     # Service logos
```

## Remote Control

| Button | Action |
|--------|--------|
| D-pad | Navigate between movies and shelves |
| Select (click) | Open movie details |
| Play/Pause | Play trailer or refresh |
| Menu | Go back or open filter sidebar |
| Swipe up | Open filter sidebar |

## Configuration

### API Endpoint

Update the data URL in `src/services/api.js`:

```javascript
const DATA_URL = 'https://raw.githubusercontent.com/YOUR_USERNAME/nrw-production/main/data.json';
```

### Analytics

Add your Mixpanel token in `src/services/analytics.tvos.js`:

```javascript
const MIXPANEL_TOKEN = 'YOUR_MIXPANEL_TOKEN';
```

### Crash Reporting

Add your Sentry DSN in `src/services/sentry.tvos.js`:

```javascript
const SENTRY_DSN = 'YOUR_SENTRY_DSN';
```

## Building for Release

```bash
# Archive in Xcode
# Product > Archive

# Or use fastlane (if configured)
fastlane tvos release
```

## App Store Submission

1. Create tvOS app in App Store Connect
2. Upload build via Xcode or Transporter
3. Required assets:
   - App icon (1280x768 layered)
   - Top Shelf image (1920x720)
   - Screenshots (1920x1080)
4. Submit for review

## License

Proprietary - New Release Wall
