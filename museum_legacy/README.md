# New Release Wall 🎬

A sophisticated movie tracking system that monitors when films transition from theatrical to digital/streaming availability. Recreates the "new release wall" experience of video stores with modern web UI.

## Features

### Dual Tracking System
- **Tracking Database**: Monitors 1000+ movies over 2 years, detecting digital transitions
- **Direct Scraper**: Real-time TMDB queries for comprehensive coverage

### Interactive Web Interface
- **Flippable movie cards** with 3D CSS animations
- **Front**: Poster, title, year, director, cast, streaming providers
- **Back**: Studio, runtime, synopsis, RT score, trailer link
- Responsive grid layout with dark theme

### Smart Detection
- Tracks TMDB release type 4 (Digital) and type 6 (TV)
- US-specific digital release dates
- Provider categorization (rent/buy/stream/free)
- Rotten Tomatoes score integration

## Quick Start

```bash
# Clone repository
git clone https://github.com/hadrianbelove-stack/new-release-wall.git
cd new-release-wall

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp config.example.yaml config.yaml
# Edit config.yaml with your TMDB and OMDb API keys

# Run interactive menu
chmod +x menu.sh
./menu.sh
```

## Menu Options

1. **Run Full Update** - Complete tracking database update + generation
2. **Custom Scrape** - Choose specific date range for discovery
3. **Open Website Only** - Launch web interface without refresh
4. **Database Status** - View tracking statistics and recent finds
5. **Stop Server** - Terminate web server
6. **Exit** - Clean shutdown

## Advanced Usage

### Manual Commands

```bash
# Bootstrap tracking database (2 years of data)
python3 movie_tracker.py bootstrap 730

# Update all tracked movies
python3 movie_tracker.py update

# Check for new digital releases
python3 movie_tracker.py check

# Generate website from tracking data
python3 generate_from_tracker.py 14

# Direct scraping (alternative approach)
python3 new_release_wall_balanced.py --region US --days 14 --max-pages 0
```

### Configuration

Edit `config.yaml`:

```yaml
tmdb_api_key: "your_tmdb_key"
omdb_api_key: "your_omdb_key"
min_rotten_tomatoes: 60
site_title: "The New Release Wall"
```

## How It Works

### Phase 1: Discovery
- Scans TMDB's `/discover/movie` endpoint with date filters
- Identifies movies released theatrically in specified timeframe
- Builds comprehensive tracking database

### Phase 2: Monitoring
- Checks release dates for each tracked movie
- Detects when `type: 4` (Digital) or `type: 6` (TV) dates appear
- Captures exact US digital availability dates

### Phase 3: Enrichment
- Fetches detailed movie metadata (cast, crew, runtime)
- Queries OMDb for Rotten Tomatoes scores
- Gathers streaming provider information

### Phase 4: Presentation
- Generates interactive HTML with flippable cards
- Creates Markdown lists for newsletter/blog use
- Launches local web server with real-time updates

## API Requirements

- **TMDB API**: Free account at [themoviedb.org](https://www.themoviedb.org/settings/api)
- **OMDb API**: Free key at [omdbapi.com](http://www.omdbapi.com/apikey.aspx)

## File Structure

```
new-release-wall/
├── menu.sh                 # Interactive menu system
├── movie_tracker.py        # Tracking database management
├── new_release_wall_balanced.py  # Direct scraper
├── generate_from_tracker.py      # Website generator
├── adapter.py             # Data normalization
├── templates/             # HTML templates
│   ├── site_flip.html     # Flippable card interface
│   └── site_enhanced.html # Enhanced layout
├── output/                # Generated content
│   ├── site/             # Web files
│   ├── list.md           # Markdown output
│   └── data.json         # Raw data
└── config.yaml           # Configuration
```

## Performance

- **Tracking Database**: 90% fewer API calls after initial setup
- **Bootstrap**: Scans up to 500 pages (10,000 movies) in one pass
- **Updates**: Only checks tracked movies for status changes
- **Caching**: 7-day TTL on movie metadata

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

MIT License - see LICENSE file for details

## Changelog

### v2.0.0 (Latest)
- Dynamic pagination (up to 500 TMDB pages)
- Flippable card web interface
- Unified menu system with auto-bootstrap
- Comprehensive data enrichment pipeline
- Better US digital release detection

### v1.0.0
- Basic TMDB scraping
- Simple HTML output
- Manual configuration required

---

## Archived Scrapers (Oct 17, 2025)

This directory contains scrapers that have been superseded by better solutions or are no longer used in the production workflow.

### Archived Files

#### wikidata_scraper.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** IMDb ID → Wikidata → Wikipedia page title + RT ID
- **Why Archived:** Redundant with built-in Wikipedia REST API in `generate_data.py` (lines 177-228)
- **Replacement:** Wikipedia REST API (faster, no Selenium, more reliable)
- **Technology:** Selenium-based browser automation
- **Migration Notes:** If Wikipedia REST API fails, use `wikipedia_scraper.py` (manual fallback tool in root)

#### reelgood_scraper.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** Scrape Reelgood.com for digital release dates
- **Why Archived:** TMDB API provides release dates directly (more reliable)
- **Replacement:** TMDB `/movie/{id}/release_dates` endpoint
- **Technology:** Selenium-based browser automation
- **Migration Notes:** Use TMDB API for all release date queries

#### date_verification.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** Verify TMDB digital dates against Reelgood data
- **Why Archived:** Only user of reelgood_scraper.py; marked "Non-critical" in orchestrator
- **Replacement:** TMDB dates are authoritative (no verification needed)
- **Technology:** Python script using reelgood_scraper.py
- **Migration Notes:** Trust TMDB dates; manual verification if needed

#### curator_admin.py
- **Archived:** Oct 16, 2025 (deleted in Phase 7)
- **Original Purpose:** Alternative admin UI on port 5100 with batch operations
- **Why Archived:** Orphaned (expected non-existent `current_releases.json`); duplicate of main admin.py
- **Replacement:** Main admin panel (`admin.py` on port 5555)
- **Technology:** Flask web application
- **Migration Notes:** Use main admin panel for all curation tasks

#### update_rt_data.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** Standalone RT cache population script
- **Why Archived:** RT scraping now automatic in `generate_data.py` (inlined in previous phase)
- **Replacement:** Automatic RT scraping during data generation
- **Technology:** Python script using rt_scraper.py
- **Migration Notes:** RT scraping happens automatically; no separate step needed

#### bootstrap_rt_cache.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** Bulk populate RT cache for initial setup
- **Why Archived:** RT scraping now automatic in `generate_data.py`
- **Replacement:** Automatic RT cache building during data generation
- **Technology:** Python script using rt_scraper.py
- **Migration Notes:** First `--full` regeneration will populate cache

#### rt_scraper.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** Basic RT search and URL extraction (v1)
- **Why Archived:** Superseded by `scripts/rt_scraper.py` (v2), then inlined into generate_data.py (v3)
- **Replacement:** Inlined RT scraper in `generate_data.py`
- **Technology:** Selenium-based browser automation (no cache management)
- **Migration Notes:** Use inlined RT scraper (automatic during data generation)

#### scripts_rt_scraper.py
- **Archived:** Oct 17, 2025
- **Original Purpose:** RT search and URL extraction with cache management (v2)
- **Why Archived:** Logic inlined into `generate_data.py` (v3) in Phase 9
- **Replacement:** Inlined RT scraper in `generate_data.py` (automatic during data generation)
- **Technology:** Selenium-based browser automation with cache management
- **Evolution:** Improved version of root `rt_scraper.py`, then superseded by inlined approach
- **Migration Notes:** RT scraping is now automatic; no external class needed

### Active Scrapers (Production)

For reference, these scrapers are actively used in the production workflow:

#### Integrated into generate_data.py
1. **Wikipedia REST API** (built-in, lines 177-228)
   - Fast HTTP-based Wikipedia lookup
   - No Selenium required
   - Primary Wikipedia link source

2. **RT Scraper** (inlined into generate_data.py, AMENDMENT-042)
   - Selenium-based Rotten Tomatoes scraping
   - Waterfall: Overrides → Cache → Scraper → Search URL
   - Finds RT URLs and scores

3. **Agent Link Scraper** (`agent_link_scraper.py`)
   - Playwright-based watch link scraping
   - Platforms: Netflix, Disney+, HBO Max, Hulu
   - Waterfall: Overrides → Cache → Watchmode API → Agent → null

4. **YouTube Trailer Scraper** (`scripts/youtube_trailer_scraper.py`)
   - Selenium-based YouTube link resolution
   - Converts search URLs to direct watch URLs
   - Cache: `youtube_trailer_cache.json`

#### Manual Fallback Tools (Root Directory)
1. **wikipedia_scraper.py**
   - Selenium-based Wikipedia search
   - Use when REST API fails or returns wrong results
   - Not integrated into automation (manual use only)

### Scraper Technology Summary

- **Playwright:** `agent_link_scraper.py` (modern, reliable, 4-6 selector fallbacks per platform)
- **Selenium:** RT scraper (inlined into generate_data.py), `scripts/youtube_trailer_scraper.py`, `wikipedia_scraper.py` (manual tool)
- **REST APIs:** Wikipedia API (built-in), TMDB API, Watchmode API (preferred when available)
- **Inlined:** RT scraper, Wikipedia REST API (no external classes)
- **External Classes:** Agent scraper, YouTube scraper (separate files)

### Future Consolidation Opportunities

**Playwright Migration (Remaining Selenium Scrapers):**
- RT scraper (currently inlined with Selenium) → Migrate to Playwright for speed/reliability
- `scripts/youtube_trailer_scraper.py` → Migrate to Playwright
- `wikipedia_scraper.py` (manual tool) → Migrate to Playwright or keep as-is (low priority)

**Benefits of full Playwright migration:**
- Remove Selenium dependencies entirely (simplify requirements.txt)
- Consistent technology stack (easier maintenance)
- Performance improvements (~30% faster page loads)
- Better error diagnostics (screenshot/trace capabilities)

**Current Status:**
- ✅ Agent scraper migrated to Playwright (AMENDMENT-041)
- ⏳ RT scraper remains on Selenium (inlined, functional)
- ⏳ YouTube scraper remains on Selenium (external class, functional)
- ⏳ Wikipedia scraper remains on Selenium (manual tool, low priority)

**Estimated Effort:**
- RT scraper migration: 2-3 hours (already inlined, just swap Selenium for Playwright)
- YouTube scraper migration: 2-3 hours (external class, straightforward)
- Wikipedia scraper migration: 1-2 hours (manual tool, optional)
- Total: 5-8 hours for complete Playwright migration
