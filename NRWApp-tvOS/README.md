# New Release Wall - tvOS App (NRWApp-tvOS)

React Native app for Apple TV (tvOS) featuring curated indie films.

> **Folder**: This is the Apple TV version. See `NRWApp-Android/` for Android TV (planned).

## Features

- **Vertical Grid Layout**: 8-column grid optimized for 10-foot viewing
- **Focus-Based Navigation**: Full support for Siri Remote (d-pad and gestures)
- **Fullscreen Poster View**: Long-press any card for side-by-side poster + info
- **Parallax Effects**: Native tvOS visual effects on movie posters
- **Top Shelf Extension**: Featured movies displayed on Apple TV home screen
- **Streaming Integration**: Deep links to Netflix, Prime, Disney+, Plex, etc.

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
NRWApp-tvOS/
├── App.js                         # Main app, navigation setup
├── src/
│   ├── screens/
│   │   ├── HomeScreen.tvos.js     # Main grid view (8 columns)
│   │   ├── MovieDetail.tvos.js    # Movie details screen
│   │   ├── SearchScreen.tvos.js   # Search functionality
│   │   └── useHomeScreen.js       # Shared state/logic
│   ├── components/
│   │   ├── MovieCard.tvos.js      # Focusable poster card
│   │   └── FullscreenPosterModal.tvos.js  # Fullscreen side-by-side view
│   ├── services/
│   │   ├── api.tvos.js            # Data fetching
│   │   ├── analytics.tvos.js      # Usage tracking
│   │   └── sentry.tvos.js         # Crash reporting
│   ├── utils/
│   │   └── focusManager.tvos.js   # TV remote event handling
│   └── constants/
│       └── colors.js              # Colors, typography, dimensions
├── ios/                           # Xcode project files
├── tvos/
│   └── TopShelfExtension/         # Top Shelf widget (Swift)
└── assets/                        # App assets
```

## Remote Control

| Button | Action |
|--------|--------|
| D-pad | Navigate between movies |
| Select (click) | Open movie details |
| Select (long press) | Open fullscreen poster view |
| Play/Pause | Refresh movie list |
| Menu | Go back / close modal |
| Left/Right (in fullscreen) | Cycle through movies |

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
