# 🎬 Unified Hidden Gems Scraper

A comprehensive tool for discovering indie films across multiple platforms, now unified into a single powerful scraper.

## ✨ Features

### Core Capabilities
- **TMDB Discovery**: Find films with Type 4 (Digital) releases but no major platform providers
- **Live Scraping**: Real-time discovery from Vimeo On Demand, YouTube Movies, and Patreon creators
- **File Integration**: Import discoveries from external JSON files
- **Curation Export**: Specialized CSV/JSON exports for manual review and flagging
- **Smart Deduplication**: Cross-platform duplicate detection and removal

### Supported Platforms
- **Vimeo On Demand** - Browse categories and featured content
- **YouTube Movies** - Search for independent films and documentaries
- **Patreon** - Discover film creators and exclusive content
- **TMDB** - Query for films with digital releases

## 🚀 Quick Start

### Basic TMDB Discovery
```bash
# Discover hidden gems from last 30 days
python3 hidden_gems_scraper.py

# Specific time periods
python3 hidden_gems_scraper.py --days 7
python3 hidden_gems_scraper.py --month 2025-12
```

### Live Scraping (New Unified Approach)
```bash
# Scrape all platforms at once
python3 hidden_gems_scraper.py --scrape-all

# Individual platforms
python3 hidden_gems_scraper.py --scrape-vimeo
python3 hidden_gems_scraper.py --scrape-youtube
python3 hidden_gems_scraper.py --scrape-patreon

# Combine platforms
python3 hidden_gems_scraper.py --scrape-vimeo --scrape-patreon
```

### Advanced Configuration
```bash
# Adjust scraping parameters
python3 hidden_gems_scraper.py --scrape-all \\
    --max-creators 20 \\
    --max-pages 5 \\
    --min-runtime 60

# Run with visible browser (debugging)
python3 hidden_gems_scraper.py --scrape-vimeo --no-headless

# Hybrid: TMDB + Live scraping
python3 hidden_gems_scraper.py --days 7 --scrape-vimeo --scrape-youtube
```

### Curation Workflow
```bash
# Generate curator-friendly exports
python3 hidden_gems_scraper.py --scrape-all --export-for-curation

# This creates:
# - hidden_gems_curation.csv (with "Add to NRW" column)
# - hidden_gems_curation.json (structured metadata)
```

## 📋 Command Line Options

### Core Options
- `--days N` - Discover from last N days (default: 30)
- `--month YYYY-MM` - Discover from specific month
- `--output PREFIX` - Output filename prefix (default: hidden_gems)
- `--quiet` - Suppress progress output

### Live Scraping Options
- `--scrape-vimeo` - Directly scrape Vimeo On Demand
- `--scrape-youtube` - Directly scrape YouTube Movies
- `--scrape-patreon` - Directly scrape Patreon creators
- `--scrape-all` - Scrape all platforms

### Scraping Configuration
- `--max-creators N` - Max Patreon creators to scrape (default: 10)
- `--max-pages N` - Max pages to scrape per platform (default: 3)
- `--min-runtime N` - Minimum runtime in minutes (default: 70)
- `--headless` / `--no-headless` - Browser mode

### Legacy File Integration
- `--include-vimeo` - Include Vimeo discoveries file
- `--include-youtube` - Include YouTube discoveries file
- `--include-patreon` - Include Patreon discoveries file
- `--vimeo-file PATH` - Custom Vimeo file path
- `--youtube-file PATH` - Custom YouTube file path
- `--patreon-file PATH` - Custom Patreon file path

### Export Options
- `--export-for-curation` - Generate curation-ready exports

## 📊 Output Formats

### Standard Exports
- `output.csv` - Complete film data in CSV format
- `output.md` - Markdown report with categorized films
- `output.json` - Raw JSON data for programmatic use

### Curation Exports (--export-for-curation)
- `output_curation.csv` - Curator-friendly CSV with "Add to NRW" column
- `output_curation.json` - Structured JSON with enhanced metadata

### Curation CSV Fields
| Field | Description |
|-------|-------------|
| Add to NRW | Boolean flag for curator (defaults to FALSE) |
| Title | Film title |
| Platform | Discovery platform (Vimeo, YouTube, Patreon) |
| Runtime | Duration in minutes |
| Director/Channel | Filmmaker or channel name |
| Watch Link | Direct URL to watch/access |
| Price (Rent/Buy) | Pricing information |
| TMDB ID | TMDB database link |
| IMDB | IMDB database link |
| Discovery Source | How film was discovered |
| TMDB Confidence | Match confidence level |

## 🎯 Use Cases

### Film Curators
```bash
# Weekly curation workflow
python3 hidden_gems_scraper.py --days 7 --scrape-all --export-for-curation
# Review hidden_gems_curation.csv, mark films as TRUE to add to database
```

### Researchers
```bash
# Comprehensive discovery across all platforms
python3 hidden_gems_scraper.py --scrape-all --min-runtime 30 --max-pages 10
```

### Content Scouts
```bash
# Target specific platforms
python3 hidden_gems_scraper.py --scrape-patreon --max-creators 50
python3 hidden_gems_scraper.py --scrape-vimeo --max-pages 10
```

### Quick Discovery
```bash
# Fast scan of new content
python3 hidden_gems_scraper.py --days 3 --scrape-vimeo --min-runtime 60
```

## 🔧 Technical Details

### Architecture
- **Unified Design**: All scrapers integrated into single tool
- **Playwright Integration**: Robust browser automation
- **Rate Limiting**: Respectful scraping with configurable delays
- **Error Handling**: Graceful failure recovery with retry logic
- **Caching**: Smart caching to avoid redundant scraping

### Platform-Specific Details

#### Vimeo On Demand
- Browses categories: drama, documentary, comedy, thriller
- Extracts: title, URL, price, description, runtime
- Rate limit: 2 seconds between requests

#### YouTube Movies
- Searches terms: "independent film", "indie movie", "documentary"
- Extracts: title, URL, channel, duration, film indicators
- Rate limit: 3 seconds between requests

#### Patreon
- Known creators: FilmmakerIQ, One Month Movies, Happen Films, etc.
- Extracts: title, description, creator, post URL, runtime
- Rate limit: 3 seconds between requests

### Dependencies
- `playwright` - Browser automation
- `requests` - HTTP requests
- `pyyaml` - Configuration files
- Standard library modules

## 📈 Performance

### Typical Run Times
- **TMDB only**: 2-5 minutes (depends on date range)
- **Single platform**: 5-15 minutes (depends on max-pages/creators)
- **All platforms**: 15-30 minutes (comprehensive discovery)
- **Curation mode**: +2-3 minutes (additional processing)

### Output Volume
- **TMDB**: 50-200 films per month
- **Vimeo**: 20-100 films per run
- **YouTube**: 30-150 films per run
- **Patreon**: 10-50 films per run

## 🛠️ Development

### Adding New Platforms
1. Create `discover_from_PLATFORM()` function
2. Add command-line arguments
3. Integrate into main scraping logic
4. Update curation exports

### Customizing Scraping
- Modify selectors in platform-specific functions
- Adjust rate limits and timeouts
- Add new search terms or categories
- Enhance deduplication logic

## 🔍 Examples

### Real-World Workflows

#### Weekly Curation Review
```bash
#!/bin/bash
# Weekly curation script
python3 hidden_gems_scraper.py \\
    --days 7 \\
    --scrape-vimeo \\
    --scrape-patreon \\
    --export-for-curation \\
    --output weekly_gems

echo "Review weekly_gems_curation.csv for new additions"
```

#### Platform Comparison
```bash
# Compare discoveries across platforms
python3 hidden_gems_scraper.py --scrape-vimeo --output vimeo_only
python3 hidden_gems_scraper.py --scrape-youtube --output youtube_only
python3 hidden_gems_scraper.py --scrape-patreon --output patreon_only
```

#### Deep Discovery
```bash
# Comprehensive quarterly scan
python3 hidden_gems_scraper.py \\
    --month 2025-12 \\
    --scrape-all \\
    --max-creators 30 \\
    --max-pages 8 \\
    --min-runtime 45 \\
    --export-for-curation \\
    --output quarterly_gems
```

## 🎉 Benefits of Unified Approach

### Before (Separate Scripts)
- ❌ Multiple tools to maintain
- ❌ Inconsistent output formats
- ❌ Manual deduplication required
- ❌ Complex workflow orchestration

### After (Unified Scraper)
- ✅ Single tool for all platforms
- ✅ Consistent, standardized outputs
- ✅ Automatic deduplication
- ✅ Streamlined curation workflow
- ✅ Cross-platform discovery correlation

This unified approach dramatically simplifies the hidden gems discovery process while providing more comprehensive and reliable results.