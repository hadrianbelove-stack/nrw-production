# New Release Wall - Project Context

## Current Status (Phase 5 - Complete)

**✅ SOLVED: Not enough movies problem**
- **Before:** 27 movies from scraping
- **After:** 95 movies from tracking database (last 60 days)
- **Database:** 1,132 total movies (623 resolved, 509 tracking)
- **Source:** Comprehensive movie_tracking.json database

## Project Overview

A VHS-style movie tracking website that displays recent digital releases with flippable cards and comprehensive movie information.

### Key Features
- **VHS Aesthetic:** Retro flippable cards with enhanced movie details
- **Real-time Data:** Live provider availability (rent/buy/stream)
- **Date Organization:** Grouped by digital release date (newest first)
- **Comprehensive Database:** 1,132+ movies tracked from theatrical to digital

## Current Architecture

### Database-First Approach (Implemented)
```
movie_tracking.json (1,132 movies)
    ↓
generate_from_tracker.py (filter by timeframe)
    ↓
current_releases.json (95 movies, last 60 days)
    ↓
generate_site.py (VHS interface)
    ↓
output/site/index.html (live at localhost:8000)
```

### File Structure
```
new-release-wall/
├── movie_tracking.json          # Master database (1,132 movies)
├── movie_tracker.py             # Database management
├── generate_from_tracker.py     # Data extraction by timeframe
├── generate_site.py             # VHS site generator
├── current_releases.json        # Current dataset (95 movies)
├── output/
│   ├── data.json               # Site data
│   └── site/index.html         # VHS interface
└── templates/site_enhanced.html # VHS template
```

## Core Scripts

### 1. Movie Database Management
```bash
# Daily updates (check for newly digital movies)
python3 movie_tracker.py daily

# Status check
python3 movie_tracker.py status

# Bootstrap comprehensive database
python3 movie_tracker.py bootstrap 730  # 2 years
```

### 2. Site Generation Workflow
```bash
# Generate from last 60 days (95 movies)
python3 generate_from_tracker.py 60

# Generate VHS site
python3 generate_site.py

# View results
open output/site/index.html
```

### 3. Local Development
```bash
# Start local server
cd output/site && python3 -m http.server 8000

# View at: http://localhost:8000
```

## Database Schema

### movie_tracking.json Structure
```json
{
  "movies": {
    "movie_id": {
      "title": "Movie Title",
      "tmdb_id": 123456,
      "theatrical_date": "2025-06-01",
      "digital_date": "2025-08-01",
      "rt_score": 85,
      "status": "resolved|tracking",
      "added_to_db": "2025-08-01",
      "last_checked": "2025-08-20"
    }
  },
  "stats": {
    "total_tracked": 1132,
    "resolved": 623,
    "still_tracking": 509
  }
}
```

### VHS Site Data Format
```json
[
  {
    "title": "Movie Title",
    "tmdb_id": 123456,
    "theatrical_date": "2025-06-01",
    "digital_date": "2025-08-01",
    "rt_score": 85,
    "status": "resolved",
    "providers": {
      "rent": ["Amazon Video", "Apple TV"],
      "buy": ["Amazon Video", "Apple TV"],
      "stream": ["Netflix"]
    }
  }
]
```

## VHS Interface Design

### Visual Features
- **Flippable Cards:** CSS3 3D transforms on hover
- **Date Dividers:** Organized by digital release date
- **Movie Details:** Poster, title, year, RT score, providers
- **Enhanced Information:** Director, cast, synopsis, trailer links

### Technical Implementation
- **Template:** `templates/site_enhanced.html`
- **TMDB Integration:** Live poster images, movie details
- **Provider Data:** Real-time rent/buy/stream availability
- **Responsive Design:** Works on desktop and mobile

## Problem Resolution History

### Phase 1: Initial Implementation ✅
- Basic scraping system with 27 movies
- VHS-style interface prototype

### Phase 2: API Rate Limiting Issues ✅
- **Problem:** 401 errors from TMDB API during scraping
- **Solution:** Implemented comprehensive tracking database approach

### Phase 3: Comprehensive Database ✅
- **Implementation:** movie_tracker.py system
- **Result:** 1,132 movies tracked (623 resolved, 509 tracking)

### Phase 4: Data Volume Problem ✅
- **Problem:** Only 27 movies showing on site
- **Solution:** Convert tracking database to VHS format
- **Result:** 95 movies from last 60 days

### Phase 5: Live Provider Integration ✅
- **Enhancement:** Real-time rent/buy/stream data
- **Implementation:** generate_from_tracker.py with TMDB providers API
- **Result:** Live availability data for all movies

## Configuration

### Required Files
- `config.yaml` - TMDB and OMDb API keys
- `.env` (optional) - Environment variables

### API Dependencies
- **TMDB API:** Movie data, posters, providers
- **OMDb API:** Rotten Tomatoes scores

## Development Workflow

### Daily Operations
```bash
# 1. Update database with new digital releases
python3 movie_tracker.py daily

# 2. Generate site with recent movies (last 60 days)
python3 generate_from_tracker.py 60

# 3. Regenerate VHS interface
python3 generate_site.py

# 4. View updated site
open output/site/index.html
```

### Bootstrap Operations
```bash
# Bootstrap comprehensive historical data
python3 movie_tracker.py bootstrap 730

# Check bootstrap progress
python3 movie_tracker.py status
ls -la movie_tracking.json
```

## Performance Characteristics

### Current Database Stats
- **Total Movies:** 1,132
- **Resolved (Digital):** 623
- **Still Tracking:** 509
- **Database Size:** ~276KB
- **Site Display:** 95 movies (last 60 days)

### API Usage
- **Rate Limiting:** 0.1-0.2s delays between requests
- **Provider Data:** Live TMDB providers API
- **Caching:** Database prevents repeated API calls for known movies

## Future Enhancements

### Potential Improvements
1. **Admin Interface:** curator_admin.py for content curation
2. **Extended Timeframes:** Configurable date ranges
3. **Provider Filtering:** Filter by specific streaming services
4. **Advanced Sorting:** By RT score, popularity, genre
5. **Search Functionality:** Movie title/actor search

### Scaling Considerations
- Database approach scales to thousands of movies
- Provider API calls only for actively displayed movies
- Template system supports unlimited movie count

## Technical Notes

### Caching Strategy
- **Database Persistence:** Avoid repeated API calls
- **Provider Updates:** Only for movies being displayed
- **Image Caching:** TMDB poster URLs cached by browser

### Error Handling
- **API Failures:** Graceful degradation with placeholder data
- **Missing Data:** Default values for all fields
- **Rate Limiting:** Built-in delays and retry logic

### Browser Compatibility
- **CSS3 Features:** 3D transforms, transitions
- **JavaScript:** Minimal dependencies
- **Responsive:** Mobile-friendly design

## Enhanced Movie Tracking System

### Implementation (August 21, 2025)
- **Created `movie_tracker_enhanced.py`** - Comprehensive tracking system
- **Tracks ALL release types**: Types 1 (Premiere), 2 (Limited), 3 (Theatrical), 4 (Digital)
- **Provider-based detection**: Uses JustWatch data to detect when movies actually go digital
- **Missing film recovery**: Successfully added "Ebony & Ivory", "Harvest", "Familiar Touch"

### Key Features
1. **Multiple discovery methods** during bootstrap:
   - Primary release dates (theatrical)
   - All release dates (premieres, festivals)
   - Popularity scanning (trending indies)

2. **Provider comparison logic**:
   - Detects when providers appear = "NEW to digital"
   - More reliable than TMDB Type 4 dates for indie films
   - Tracks provider count changes over time

3. **Manual film addition**:
   ```bash
   python3 movie_tracker_enhanced.py add "Movie Title" 2024
   ```

4. **Enhanced daily updates**:
   - Check TMDB digital dates
   - Check provider availability changes
   - Dual detection for maximum accuracy

### Results
- **"Ebony & Ivory"**: Found with 10 providers (missed by original tracker)
- **"Harvest"**: Type 1 premiere, tracking for providers
- **"Familiar Touch"**: Found as resolved, 98% RT score

### Enhanced Database Structure
```json
{
  "movies": {
    "movie_id": {
      "title": "...",
      "premiere_date": "2024-01-01",    // Type 1
      "limited_date": "2024-02-01",     // Type 2  
      "theatrical_date": "2024-03-01",  // Type 3
      "digital_date": "2024-06-01",     // Type 4
      "earliest_release": "2024-01-01", // Earliest of any type
      "provider_count": 10,
      "has_providers": true,
      "detected_via_providers": false,  // Found via provider scanning
      "status": "resolved|tracking"
    }
  }
}
```

## Git Management

### Push Policy
**"Please push to GitHub after any significant code changes or every hour, whichever comes first"**

This ensures:
- Regular backups of work
- Synchronization between Claude instances
- No loss of significant changes

---

**Last Updated:** August 21, 2025
**Current Status:** Enhanced tracking system implemented, bootstrap in progress
**Next Steps:** Complete enhanced bootstrap, integrate with site generation