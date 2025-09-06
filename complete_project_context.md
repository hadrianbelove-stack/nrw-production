# NRW - Current State (2025-09-05)

## Purpose
A "Blockbuster Wall for the streaming age." Reverse-chronological display of digital releases.

## Current Implementation
- `index.html` → loads `assets/styles.css` + `assets/app.js`
- `data.json` → Movie database (currently 5 sample entries)
- Display works: date dividers, flip cards, Watch buttons
- Missing: Full movie data pipeline

## Data Strategy (Learned from Museum)
The TMDB Type 4 (digital) dates are unreliable. Best approach found:
1. Track ALL theatrical releases (Type 1,2,3)
2. Check daily for provider availability
3. First day with providers = actual digital release date
4. This catches movies that never get Type 4 flag

## Implementation Plan
Phase 1: Database Tracker
- Bootstrap with 2 years of theatrical releases
- Daily check for provider availability
- Store in movie_tracking.json

Phase 2: Data Generator  
- Filter tracked movies to recent digital (last 30 days)
- Generate data.json for display

Phase 3: Display (Complete)
- Date dividers and movie cards working
- Flip functionality working
- Watch button routes to Amazon

## Data Structure Learned
- movie_tracking.json: Main database tracking all movies
  - theatrical_date: When movie premiered (Type 1,2,3)
  - digital_date: When providers first appeared
  - status: "tracking" or "available"
  - has_providers: Boolean flag
- data.json: Display format for website (generated from tracking DB)

## Key Insights from Museum
- Provider appearance is ground truth for digital availability
- TMDB Type 4 dates often missing or wrong
- Many movies never get Type 4 flag but ARE available
- Tracking database approach catches these missed movies

## API Credentials
### TMDB (The Movie Database)
- **API Key:** 99b122ce7fa3e9065d7b7dc6e660772d
- **Read Access Token:** eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5OWIxMjJjZTdmYTNlOTA2NWQ3YjdkYzZlNjYwNzcyZCIsIm5iZiI6MTc1NDc4NjMzNS4zOTUsInN1YiI6IjY4OTdlYTFmOTdlOGI3NGVkNDkyZWIxMSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.jBIIJ0Om5GS9Yjs4_VmegF-QCg_qamwSr7TK1yp9kjw

### OMDb API  
- **API Key:** 539723d9
- **Base URL:** http://www.omdbapi.com/?i=tt3896198&apikey=539723d9
- **Poster API:** http://img.omdbapi.com/?i=tt3896198&h=600&apikey=539723d9

## Next Session Should
1. Implement movie_tracker.py from museum learnings
2. Bootstrap initial database
3. Generate first real data.json
4. Test full pipeline