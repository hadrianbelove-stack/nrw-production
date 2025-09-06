# NRW - Current State (2025-09-06)

## Purpose
A "Blockbuster Wall for the streaming age." Reverse-chronological display of digital releases.

## Current Implementation
- **Repository:** nrw-production (migrated from new-release-wall on 2025-09-05)
- `index.html` → loads `assets/styles.css` + `assets/app.js`
- `data.json` → Movie database (30 movies displayed, 107 available, 73 tracking)
- Display works: date dividers, flip cards, Watch buttons
- **Issue:** All 107 bootstrap movies show Sept 5 (discovery date, not actual digital date)

## Data Pipeline Status
- `movie_tracker.py`: ✓ Working - tracks 180 movies total
- `generate_data.py`: ✓ Working - generates display from tracking
- `daily_update.sh`: ✓ Created - canonical update script
- **GitHub Actions:** ❌ Blocked - account flagged, support ticket filed

## Data Strategy (Learned from Museum)
1. Track ALL theatrical releases (Type 1,2,3)
2. Check daily for provider availability
3. First day with providers = actual digital release date
4. This catches movies that never get Type 4 flag

## Current Data State
- **Total tracked:** 180 movies
- **Already digital:** 107 (marked Sept 5 - bootstrap issue)
- **Still tracking:** 73 (waiting for providers)
- **Display limit:** 30 most recent

## Known Issues
1. **Bootstrap movies:** All show Sept 5 (when discovered, not when went digital)
2. **GitHub Actions:** Account flagged, using local automation
3. **Design issues:** Date markers small, no hover states, grid alignment

## Automation Status
- **Local:** cron job for daily checks
- **GitHub:** Awaiting account reinstatement
- **Script:** daily_update.sh runs check → generate → commit

## API Credentials
### TMDB (The Movie Database)
- **API Key:** 99b122ce7fa3e9065d7b7dc6e660772d
- **Read Access Token:** [token preserved as-is]

### OMDb API  
- **API Key:** 539723d9

## Next Steps
1. Wait for GitHub reinstatement
2. Fix design issues with current data
3. Consider filtering bootstrap movies or accepting clustered dates
4. Daily checks will gradually improve data quality
