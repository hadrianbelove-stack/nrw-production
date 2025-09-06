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
