# New Release Wall - Quick Start Guide

Everything you need to get all NRW features running.

## One-Time Setup (15 minutes)

### 1. Install All Dependencies

```bash
cd ~/Downloads/nrw-production
pip install -r requirements.txt
```

This installs everything you need for:
- ✅ Website generation
- ✅ Admin panel
- ✅ YouTube playlist automation
- ✅ Newsletter generation
- ✅ All scrapers

### 2. Install Playwright Browsers (for agent scraper)

```bash
playwright install chromium --with-deps
```

This enables deep link scraping for Netflix/Disney+/Hulu.

---

## Daily Workflow

### Option A: Automated (Recommended)

**GitHub Actions runs at 2 AM PDT automatically:**
1. Discovers new movies
2. Finds RT scores, trailers, Wikipedia
3. Generates data.json
4. Commits to GitHub

**You just:**
1. Pull latest changes in the morning
2. View updated website
3. Done!

```bash
git pull origin main
./launch_NRW.sh  # Starts local server
```

### Option B: Manual Updates

```bash
# Run full pipeline
python3 daily_orchestrator.py

# Or step-by-step:
python3 movie_tracker.py daily         # Discover new releases
python3 generate_data.py               # Generate website data

# View website
./launch_NRW.sh
```

---

## Features & Tools

### 🌐 Website

**View locally:**
```bash
./launch_NRW.sh
# Opens http://localhost:8000
```

**Deploy:**
- Upload `index.html`, `assets/`, `data.json` to your host
- Or use GitHub Pages (free!)

### 🎛️ Admin Panel

**Manage movie visibility, featured status, watch links:**

```bash
python3 admin.py
# Opens http://localhost:5555
```

**Login:** Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` env vars

**Features:**
- Hide/show movies
- Mark as featured
- Update digital release dates
- Override watch links manually
- Regenerate data.json

### 🎬 YouTube Playlists

**Create automated playlists from your trailers:**

**Setup:** See [YOUTUBE_PLAYLIST_SETUP.md](YOUTUBE_PLAYLIST_SETUP.md)

**Usage:**
```bash
# Test extraction
python3 youtube_playlist_manager.py test

# Create weekly playlist
python3 youtube_playlist_manager.py weekly

# Create monthly playlist
python3 youtube_playlist_manager.py monthly

# Create certified fresh (RT 90%+)
python3 youtube_playlist_manager.py certified --threshold 90
```

**Automation:**
- Runs every Monday at 3 AM (weekly)
- Runs 1st of month at 3 AM (monthly)
- Via GitHub Actions (after setup)

### 📧 Substack Newsletter

**Generate beautiful newsletters:**

```bash
# Generate this week's newsletter
python3 substack_newsletter_generator.py weekly --output newsletter.html

# Preview in browser
open newsletter.html

# Copy/paste into Substack editor
```

**Features:**
- Top picks (5 highest rated)
- Hidden gems (80-89% RT)
- Organized by genre
- Complete alphabetical list
- Professional HTML styling

**Guide:** See [SUBSTACK_NEWSLETTER_GUIDE.md](SUBSTACK_NEWSLETTER_GUIDE.md)

---

## Data Sources

All features use `data.json` generated from:

1. **movie_tracking.json** - Main database (tracked movies)
2. **TMDB API** - Movie details, posters, trailers
3. **Watchmode API** - Watch links (Netflix, Amazon, etc.)
4. **Rotten Tomatoes** - RT scores (scraped)
5. **Wikipedia API** - Wikipedia links
6. **YouTube** - Trailer videos

See [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md) for details.

---

## File Structure

```
nrw-production/
├── index.html                          # Website
├── assets/
│   ├── app.js                         # Frontend logic
│   └── styles.css                     # Styling
├── data.json                          # Generated movie data (230+ movies)
│
├── movie_tracker.py                   # Discover new releases
├── generate_data.py                   # Generate data.json
├── daily_orchestrator.py              # Automated pipeline
│
├── admin.py                           # Admin panel (port 5555)
├── youtube_playlist_manager.py        # YouTube automation
├── substack_newsletter_generator.py   # Newsletter generator
│
├── config.yaml                        # API keys & config
├── requirements.txt                   # Python dependencies
│
└── Guides:
    ├── YOUTUBE_PLAYLIST_SETUP.md
    ├── SUBSTACK_NEWSLETTER_GUIDE.md
    ├── NRW_DATA_WORKFLOW_EXPLAINED.md
    └── PROJECT_CHARTER.md
```

---

## Configuration

### API Keys (config.yaml)

```yaml
api:
  tmdb_api_key: "your_key_here"

watchmode:
  api_key: "your_key_here"

agent_scraper:
  enabled: true
  headless: true

rt_scraper:
  enabled: true
  rate_limit_seconds: 2.0
```

Get API keys:
- **TMDB:** https://www.themoviedb.org/settings/api (free)
- **Watchmode:** https://api.watchmode.com/ (free tier)

### Environment Variables

For admin panel authentication:

```bash
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="your_secure_password"
```

Or create `.env` file (gitignored).

---

## Common Tasks

### Add a Movie Manually

```bash
# Edit movie_tracking.json directly or:
python3 movie_tracker.py add --tmdb-id 123456
```

### Force Regenerate All Data

```bash
python3 generate_data.py --full
```

This re-scrapes RT scores, Wikipedia links, watch links for ALL movies (not just new ones).

### Fix Missing RT Score

```bash
# Edit rt_cache.json to add score manually
# Or delete entry to force re-scrape:
python3 -c "
import json
cache = json.load(open('rt_cache.json'))
del cache['movie_title_2025']
json.dump(cache, open('rt_cache.json', 'w'), indent=2)
"
python3 generate_data.py
```

### Update Watch Link Manually

Use admin panel:
1. Go to http://localhost:5555
2. Find movie
3. Click "Override Watch Links"
4. Enter Netflix/Amazon/etc URL
5. Save

Or edit `admin/watch_link_overrides.json` directly.

---

## Troubleshooting

### "No API key found"
- Check `config.yaml` exists
- Ensure `tmdb_api_key` is set
- Or set `TMDB_API_KEY` environment variable

### "data.json not found"
```bash
python3 generate_data.py  # Generate it
```

### "Port 8000 already in use"
```bash
lsof -ti:8000 | xargs kill  # Kill existing server
./launch_NRW.sh             # Try again
```

### Admin panel login not working
```bash
# Set credentials
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="password123"
python3 admin.py
```

### YouTube authentication fails
- Delete `youtube_credentials/token.pickle`
- Run `python3 youtube_playlist_manager.py auth` again
- Sign in with correct Google account

### Newsletter looks broken
- Open `newsletter_sample.html` in browser
- Check for HTML errors in console
- Re-generate: `python3 substack_newsletter_generator.py weekly --output test.html`

---

## Performance

### Typical Generation Times

| Task | Time | Notes |
|------|------|-------|
| `movie_tracker.py daily` | ~30s | Checks ~100 tracked movies |
| `generate_data.py` (incremental) | ~5s | New movies only |
| `generate_data.py --full` | ~5min | All 230+ movies, all scrapers |
| Admin panel startup | <1s | Flask server |
| Newsletter generation | <1s | HTML from data.json |
| YouTube playlist creation | ~10s | 60 videos |

### Optimization Tips

1. **Use incremental mode** (default) - only processes new movies
2. **Run full regen weekly** - keeps all data fresh
3. **Use caches** - RT scores, Wikipedia, watch links all cached
4. **Rate limit scrapers** - avoid being blocked (configured in config.yaml)

---

## Getting Help

1. **Check guides:**
   - [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)
   - [PROJECT_CHARTER.md](PROJECT_CHARTER.md)
   - [YOUTUBE_PLAYLIST_SETUP.md](YOUTUBE_PLAYLIST_SETUP.md)
   - [SUBSTACK_NEWSLETTER_GUIDE.md](SUBSTACK_NEWSLETTER_GUIDE.md)

2. **Check script help:**
   ```bash
   python3 generate_data.py --help
   python3 youtube_playlist_manager.py --help
   python3 substack_newsletter_generator.py --help
   ```

3. **Review logs:**
   - GitHub Actions: Check workflow runs
   - Local: Check terminal output

4. **Debug mode:**
   ```bash
   python3 generate_data.py --debug  # Verbose logging
   ```

---

## What's Next?

### Week 1: Get Running
- ✅ Install dependencies
- ✅ Set up API keys
- ✅ Generate first data.json
- ✅ View website locally

### Week 2: Automation
- ✅ Set up GitHub Actions
- ✅ Test daily automation
- ✅ Configure admin panel

### Week 3: Content Creation
- ✅ Set up YouTube playlists
- ✅ Generate weekly newsletter
- ✅ Build audience!

### Ongoing: Maintenance
- Monitor automation runs
- Update scrapers if needed (sites change)
- Curate featured movies
- Publish newsletters

---

## Quick Reference Commands

```bash
# Daily workflow
git pull origin main
./launch_NRW.sh

# Manual update
python3 daily_orchestrator.py

# Admin panel
python3 admin.py

# Weekly newsletter
python3 substack_newsletter_generator.py weekly --output newsletter.html

# YouTube playlist
python3 youtube_playlist_manager.py weekly

# Full regeneration
python3 generate_data.py --full

# Check status
python3 -c "
import json
d = json.load(open('data.json'))
print(f'{len(d[\"movies\"])} movies')
print(f'Latest: {d[\"movies\"][0][\"title\"]}')
"
```

---

**You're all set!** 🎬✨

Start with `./launch_NRW.sh` to see your website, then explore the other features when ready.
