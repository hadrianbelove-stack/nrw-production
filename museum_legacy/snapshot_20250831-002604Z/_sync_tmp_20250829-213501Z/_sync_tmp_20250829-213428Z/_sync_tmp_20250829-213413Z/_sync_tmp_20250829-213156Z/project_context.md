# New Release Wall - Project Context

## Overview
A movie scraper that tracks digitally available films using TMDB API data. The project evolved from finding too few movies (5) to successfully identifying major releases (49+) through improved API querying strategy.

## Problem Solved
**Original Issue**: The scraper was too restrictive, finding only 5 movies when 65+ should have been available. Major releases like Superman, Jurassic World Rebirth, and 28 Years Later were missing.

**Root Cause**: Using `with_release_type` filter in the initial TMDB API query was incorrect. Movies can have BOTH theatrical (3) and digital (4) releases simultaneously, but the filter was excluding them.

**Solution**: Fetch ALL movies first without release_type filter, then check each movie's release types individually.

## Key Technical Evolution

### Phase 1: Original Complex System (new_release_wall.py)
- Used complex classification system (confirmed_available, early_pvod, etc.)
- Applied `with_release_type` filter in API query
- Only found 5 movies - too restrictive

### Phase 2: Improved Classification (new_release_wall.py - enhanced)
- Added fallback logic for major releases
- Enhanced classification functions
- Added estimated dates for popular movies
- Still used API filtering - found more but missed major releases

### Phase 3: Balanced Approach (new_release_wall_balanced.py)
- **Key Insight**: Fetch ALL movies first, then filter by checking release types
- Process:
  1. Get ALL movies from time period (no release_type filter)
  2. Check each movie's actual release types individually
  3. Include movies with digital (type 4) or TV (type 6) releases
- Result: Found 49 movies including major releases

### Phase 4: Tracking Database Approach (movie_tracker.py) - NEW!
- **Key Innovation**: Build persistent tracking database instead of re-scanning everything
- **Initial Bootstrap**: One-time scan of 365-730 days of movies (~5,000-10,000 titles)
- **Daily Maintenance**: 
  1. Add new theatrical releases (10-15/day)
  2. Check only unresolved movies for digital availability (~500-1000)
  3. Mark resolved movies as complete (stop checking them)
- **Efficiency Gains**: 90% reduction in API calls after initial setup
- **Smart Data**: Database tracks theatrical date, digital date, resolution status
- **Result**: Found 31 movies that went digital in last 30 days with actual providers

## Core Technical Concepts

### TMDB Release Types
- 1: Premiere
- 2: Theatrical (Limited)
- 3: Theatrical
- 4: Digital
- 5: Physical
- 6: TV

### Provider Categories
- **Rent**: Available for rental
- **Buy**: Available for purchase
- **Stream**: Available on streaming platforms

### Movie Classification Logic
```python
# OLD (incorrect) - filtered during API query
params = {
    'with_release_type': '2|3|4|6',  # This excludes movies with multiple types
    # ...
}

# NEW (correct) - check after fetching
# Step 1: Get ALL movies
params = {
    'primary_release_date.gte': start_date,
    'primary_release_date.lte': end_date,
    # No release_type filter
}

# Step 2: Check each movie individually
movie['has_digital'] = 4 in release_info['types'] or 6 in release_info['types']
```

## Current State
- **Working Script**: new_release_wall_balanced.py
- **Last successful run**: 2025-08-18 (49 movies found)
- **Performance**: 49% inclusion rate vs 1% with old method
- **Major releases**: Successfully finding Superman, Smurfs, etc.

## Usage Examples

### Traditional Approach (Still Works)
```bash
python3 new_release_wall_balanced.py --region US --days 45 --max-pages 5
```

### NEW Tracking Database Approach (More Efficient)
```bash
# Initial one-time setup (do this once)
python3 movie_tracker.py bootstrap 365

# Daily updates (run this daily)
python3 movie_tracker.py daily

# Check status
python3 movie_tracker.py status

# Generate current releases
python3 generate_from_tracker.py 30
```

### Parameters
- `--region`: Country code (default: US)
- `--days`: Days back to search (default: 45)
- `--max-pages`: Max API pages to fetch (default: 5)

## File Structure

### Core Scripts
- **new_release_wall.py**: Original complex scraper (enhanced but still API-filtered)
- **new_release_wall_balanced.py**: Fixed version with proper approach ✅
- **movie_tracker.py**: Tracking database system (NEW - most efficient approach) 🚀
- **generate_from_tracker.py**: Generate output from tracking database
- **config.yaml**: API keys and configuration
- **templates/site.html**: HTML template for output

### Cache System
- **cache/review_cache.json**: OMDb review data cache
- **cache/provider_cache.json**: TMDB provider data cache  
- **cache/release_types.json**: Release type information cache
- **movie_tracking.json**: Persistent tracking database (NEW)

### Output
- **output/data.json**: Raw movie data
- **output/site/index.html**: Generated HTML page

## Key Learnings

1. **API Filtering Gotcha**: Never use `with_release_type` filter in initial query
2. **Multiple Release Types**: Movies commonly have both theatrical AND digital releases
3. **Provider Lag**: TMDB provider data may lag behind actual availability
4. **Classification Strategy**: Fetch broadly, then filter specifically
5. **Rate Limiting**: Essential for API stability (0.1s minimum between calls)

## Performance Metrics

### Before Fix (new_release_wall.py)
- Found: 5 movies
- Major releases: Missing
- Inclusion rate: ~1%

### After Fix (new_release_wall_balanced.py)
- Found: 49 movies  
- Major releases: Included (Superman, etc.)
- Inclusion rate: ~49%
- Confirmed digital: 46 movies
- Likely digital: 3 movies

## API Dependencies
- **TMDB API**: Movie data, release types, providers
- **OMDb API**: Review scores (RT, Metacritic, IMDB)

## Future Improvements
- Add support for more regions
- Implement streaming-only detection
- Add release date prediction models
- Enhance provider data accuracy
- Add notification system for new releases
## SESSION HISTORY UPDATE - 2025-08-18 (PM Session)

### Major Discoveries:
- **TMDB Type 4 Reliability:** Confirmed type 4 dates indicate actual digital availability, not pre-orders
- **Provider Data Accuracy:** Provider data is 100% accurate for "available now" but lacks historical dates
- **Release Windows:** Found 25-117 day theatrical-to-digital windows (most 60 days, but outliers exist)
- **Coverage Requirements:** 99% coverage requires tracking 365+ days of movies
- **Tracking Solution:** Built movie_tracker.py database that detects state changes

### Implementation Progress:
- Created movie_tracker.py - tracks movies and detects digital transitions
- Created generate_from_tracker.py - generates lists from tracking database
- Created admin.py - Flask admin panel for curation
- Created site_enhanced.html - flip cards with hover effects, smaller posters
- Added comprehensive caching system to main scrapers

### Key Insights:
- Pre-orders do NOT appear in provider data (Weapons example proved this)
- Same-day releases show providers on release day (Bad Guys 2 at 9pm example)
- Hostile Takeover case: Has providers but no type 4 (data inconsistency)
- Need to track state changes ourselves for "new to digital this week" feature

### Next Steps:
- Bootstrap tracking database with full 365-day history
- Integrate enhanced site template with real data
- Deploy admin panel for curation workflow
- Add Netflix/Shudder exclusive detection

## SESSION HISTORY UPDATE - 2025-08-18 (PM Session)

### Major Discoveries:
- **TMDB Type 4 Reliability:** Confirmed type 4 dates indicate actual digital availability, not pre-orders
- **Provider Data Accuracy:** Provider data is 100% accurate for "available now" but lacks historical dates
- **Release Windows:** Found 25-117 day theatrical-to-digital windows (most 60 days, but outliers exist)
- **Coverage Requirements:** 99% coverage requires tracking 365+ days of movies
- **Tracking Solution:** Built movie_tracker.py database that detects state changes

### Implementation Progress:
- Created movie_tracker.py - tracks movies and detects digital transitions
- Created generate_from_tracker.py - generates lists from tracking database
- Created admin.py - Flask admin panel for curation
- Created site_enhanced.html - flip cards with hover effects, smaller posters
- Added comprehensive caching system to main scrapers

### Key Insights:
- Pre-orders do NOT appear in provider data (Weapons example proved this)
- Same-day releases show providers on release day (Bad Guys 2 at 9pm example)
- Hostile Takeover case: Has providers but no type 4 (data inconsistency)
- Need to track state changes ourselves for "new to digital this week" feature

### Next Steps:
- Bootstrap tracking database with full 365-day history
- Integrate enhanced site template with real data
- Deploy admin panel for curation workflow
- Add Netflix/Shudder exclusive detection
