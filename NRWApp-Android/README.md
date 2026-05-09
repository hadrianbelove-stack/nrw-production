# NRWApp-Android

Android TV / Google TV app for New Release Wall.

## Features

- Movie poster grid with D-pad navigation
- Category filters (All, Studio, Indie, Staff Picks, Foreign, Limited Series, Plex, Restorations, Documentary, Virtual Screenings)
- Movie detail screen with full metadata
- Deep linking to streaming services (Netflix, Amazon, Plex, YouTube, Hulu, Max, Disney+, etc.)
- Trailer playback via YouTube
- Rotten Tomatoes score display
- 24-hour data caching with offline support

## Tech Stack

- **Kotlin** - Programming language
- **Jetpack Compose for TV** - UI framework
- **Retrofit** - Networking
- **Coil** - Image loading
- **DataStore** - Caching
- **Navigation Compose** - Screen navigation

## Requirements

- Android Studio Hedgehog (2023.1.1) or newer
- Android SDK 34
- Kotlin 1.9+
- JDK 17

## Building

1. Open the `NRWApp-Android` folder in Android Studio
2. Sync Gradle files
3. Build > Make Project

## Running

### On Emulator
1. Create an Android TV emulator in AVD Manager
2. Run > Run 'app'

### On Physical Device
1. Enable developer mode on your Android TV
2. Connect via ADB: `adb connect <TV_IP_ADDRESS>`
3. Run > Run 'app'

## Project Structure

```
app/src/main/java/com/nrw/app/
├── MainActivity.kt           # Entry point
├── NRWApplication.kt         # Application class
├── data/
│   ├── Movie.kt              # Data models
│   └── MovieRepository.kt    # Data fetching + caching
├── ui/
│   ├── theme/
│   │   ├── Color.kt          # Brand colors
│   │   └── Theme.kt          # Compose theme
│   ├── home/
│   │   ├── HomeScreen.kt     # Movie grid
│   │   └── HomeViewModel.kt  # Home logic
│   ├── detail/
│   │   ├── DetailScreen.kt   # Movie details
│   │   └── DetailViewModel.kt
│   └── components/
│       ├── MovieCard.kt      # Poster card
│       ├── FilterChips.kt    # Category filters
│       └── WatchButton.kt    # Service buttons
└── util/
    └── DeepLinkHelper.kt     # App deep linking
```

## Supported Streaming Services

- Plex (deep link)
- Amazon Prime Video
- Netflix
- Hulu
- Max (HBO Max)
- Disney+
- Peacock
- Paramount+
- YouTube (trailers)

## Data Source

Fetches from: `https://raw.githubusercontent.com/hadrianbelove-stack/nrw-production/main/data.json`

Same data format as the tvOS app and website.

## Related

- See `NRWApp-tvOS/` for the Apple TV implementation
