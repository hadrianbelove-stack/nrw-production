# Service Logos

Standardized copies of service logos from `logos_and_images/` (the original source folder).
Filenames use normalized service IDs matching `SERVICE_NAME_MAP` in each platform's codebase.

## Naming Convention

Filenames match the internal service ID used across all platforms:
- `amazon.png` — Amazon "a" with smile (VOD/rent)
- `amazon_prime.png` — Prime Video app icon
- `prime_video.png` — Prime Video wordmark
- `apple_tv.png` — Apple logo silhouette (works with tintColor for buttons)
- `netflix.png`, `hulu.png`, `max.jpg`, `disney_plus.jpg`, etc.

## Usage Notes

- **apple_tv.png** is a clean black silhouette — ideal for button icons with white `tintColor`
- Most others are full-color square logos — better for grid/list displays than small button icons
- For tvOS/Roku/Android watch buttons, prefer text labels with brand colors; use logos only when the image is a clean silhouette
- Score logos (rt*.png, metacritic*.png, imdb.png) are used on detail screens across all platforms

## Source

Copied from `logos_and_images/` at project root. That folder contains the original files with their original filenames.
