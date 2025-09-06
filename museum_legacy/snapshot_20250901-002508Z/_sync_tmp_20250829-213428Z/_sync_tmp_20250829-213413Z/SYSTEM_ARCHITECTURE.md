# New Release Wall - System Architecture

## Core Components

### 1. Movie Tracking System
- **movie_tracker.py**: Main tracking engine with TMDB API integration
- **Database**: movie_tracking.json (10,818+ movies with provider data)
- **RT Scores**: Integration with OMDb API for Rotten Tomatoes ratings

### 2. Site Generation
- **generate_site.py**: Creates VHS-style movie discovery site
- **Templates**: Enhanced HTML templates with flip cards and metadata
- **Data**: Uses current_releases.json (201 recent movies) for performance

### 3. Admin Panel
- **admin.py**: Modern Flask-based curation interface (Port 5555)
- **Features**: Hide/show, feature, search, filter, date editing
- **Data Files**: hidden_movies.json, featured_movies.json, movie_reviews.json

### 4. Discovery & Enhancement
- **find_all_indie_films.py**: Comprehensive indie/foreign film discovery
- **rt_score_collector.py**: Rotten Tomatoes score collection utilities
- **generate_from_tracker.py**: Extract current releases with provider data

## Data Flow
```
TMDB API → movie_tracker.py → movie_tracking.json
                ↓
generate_from_tracker.py → current_releases.json
                ↓
generate_site.py → output/site/index.html

Admin Panel (admin.py) ←→ Curation Files
```

## Key Features
- **RT Scores**: 51+ movies with Rotten Tomatoes ratings
- **Provider Tracking**: Rent/buy/stream availability from JustWatch
- **Admin Curation**: Hide/feature movies with modern interface
- **Indie Discovery**: A24, Neon, foreign films, festival coverage
- **Performance**: Optimized for 201 current releases vs full 10,818 database

## API Integrations
- **TMDB**: Movie metadata, posters, trailers, release dates
- **OMDb**: Rotten Tomatoes scores
- **JustWatch**: Streaming provider availability

## Recent Enhancements (Aug 22, 2025)
- Restored RT score display from tracking database
- Enhanced admin panel with dark theme and movie cards
- Fixed data format compatibility issues
- Added comprehensive indie film discovery
- Corrected movie release dates (e.g., Ebony & Ivory)
