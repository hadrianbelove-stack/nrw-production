# NRW System Architecture - Master Reference

**Purpose**: This is the authoritative guide to how the NRW movie tracking system works. Read this document FIRST before diving into code or other documentation.

**Last Updated**: 2025-11-06
**Maintained By**: Development Team

## 📖 Reading Order for AI Assistants

When analyzing this codebase, read in this order:
1. **This document (SYSTEM_ARCHITECTURE.md)** - Master reference
2. **Section 2 & 5 below** - Critical for understanding recent failures
3. **docs/TROUBLESHOOTING.md** - Workflow debugging and common failures
4. PROJECT_CHARTER.md - Business requirements and amendments
5. NRW_DATA_WORKFLOW_EXPLAINED.md - Detailed data flow
6. DAILY_CONTEXT.md - Daily operational context
7. Core scripts: daily_orchestrator.py, generate_data.py

## ⚠️ Critical Sections

- **Section 2**: Branch strategy with single-branch daily workflow
- **Section 5**: Enrichment-on-transition pattern (prevents 2+ hour runtimes)
- **Section 8**: Common failure modes overview with links to detailed troubleshooting

---

## 🔄 Branch Strategy

### 2.1 Single-Branch Daily Workflow (Default)

**Current Implementation**: The daily CI workflow operates on a single-branch model for simplicity.

**Daily Workflow**:
1. Checkout `main` branch
2. Run daily pipeline directly on `main`
3. Commit and push changes to `main`

**Benefits**:
- Simplified workflow with no branch synchronization
- Immediate updates to main branch
- No merge conflicts between branches

### 2.2 Advanced Two-Branch Flow (Optional)

**Status**: Deprecated. Single-branch workflow on `main` is now the only supported approach per PROJECT_CHARTER.md.

**Current State**:
- Daily workflow: Single-branch on `main` ✅
- Weekly workflow: Single-branch on `main` ✅

**Branch Roles**:
- `main`: Source of truth, all development, all automation

### 2.3 Current Daily Workflow

```bash
# Bot workflow (automated) - Single branch
git checkout main
python3 daily_orchestrator.py
git add -A
git commit -m "Daily update $(date)"
git push origin main

# Legacy two-branch workflow (deprecated)
# The following commands are no longer used but kept for reference:
# git checkout automation-updates
# git merge origin/main --no-edit
# python3 daily_orchestrator.py
# git add -A
# git commit -m "Daily update $(date)"
# git push --force origin automation-updates
```

### 2.4 Legacy: Branch Divergence Issues (Single-Branch Prevents This)

**Historical Issue**: When using multiple branches, automation could run on stale code.

**Impact** (no longer applicable with single-branch):
- 2+ hour runtimes instead of 30 seconds
- Validation failures
- API quota exhaustion
- Data corruption cascades

**Historical Example**: Oct 25-Nov 5, 2025
- Two-branch system had synchronization issues
- Bot ran old enrichment logic on corrupted data
- Runtime: 2.3 hours, validation timeouts

**Current Solution**: Single-branch workflow eliminates this entire class of failures

### 2.5 Legacy: Manual Sync Commands (No Longer Needed)

```bash
# These commands are no longer needed with single-branch workflow:
# git checkout automation-updates
# git reset --hard main
# git push --force origin automation-updates
# git diff main automation-updates --stat
```

---

## 📂 File Hierarchy

### 3.1 Runtime Files

| File | Purpose | Size | Updates |
|------|---------|------|---------|
| `index.html` | Main user interface | ~15KB | Daily |
| `data.json` | Movie data for frontend | ~80KB | Daily |
| `assets/` | CSS, images, static files | ~2MB | Rarely |

### 3.2 Core Data Files

| File | Purpose | Records | Format |
|------|---------|---------|---------|
| `movie_tracking.json` | Master movie database | ~330 | JSON array |
| `config.yaml` | System configuration | N/A | YAML |
| `watchmode_quota.json` | API usage tracking | N/A | JSON |

### 3.3 Core Scripts

| Script | Purpose | Runtime | Frequency |
|--------|---------|---------|-----------|
| `daily_orchestrator.py` | Daily automation controller | 30s | Daily |
| `generate_data.py` | Data processing engine | 20-30s | Daily |
| `admin.py` | Web admin interface | N/A | On-demand |

### 3.4 Scrapers

| Scraper | Technology | Rate Limit | Cache TTL |
|---------|------------|------------|-----------|
| `rt_scraper_playwright.py` | Playwright | 2s delay | 90 days |
| `agent_link_scraper.py` | Playwright | 2s delay | 30 days |
| `streaming_platform_scraper.py` | Selenium | 3s delay | 7 days |
| `scripts/youtube_trailer_scraper.py` | Playwright | 2s delay | 90 days |

### 3.5 Directories

| Directory | Purpose | Contents |
|-----------|---------|----------|
| `.github/workflows/` | GitHub Actions | `daily-check.yml` |
| `admin/` | Admin interface | Flask app files |
| `assets/` | Frontend assets | CSS, images, fonts |
| `cache/` | Scraper cache | HTML, JSON cache files |
| `overrides/` | Manual data fixes | Override JSON files |
| `ops/` | Operational scripts | Backup, archive scripts |
| `docs/` | Documentation | Legacy docs |

### 3.6 Cache Files

**Rotten Tomatoes Cache** (`cache/rt_cache.json`): 90-day TTL, ~328 entries
**Wikipedia Cache** (`cache/wikipedia_cache.json`): 90-day TTL, ~300 entries
**YouTube Trailer Cache** (`cache/youtube_trailer_cache.json`): 90-day TTL, ~250 entries
**Agent Links Cache** (`cache/agent_links_cache.json`): 30-day TTL, ~50 entries
**Watch Links Cache** (`cache/watch_links_cache.json`): 7-day TTL, ~50 entries

---

## ⚙️ Configuration & Secrets

### 4.1 Configuration Pattern

All API keys follow the 12-factor app pattern:
1. **Environment variables** (production, CI/CD) - highest priority
2. **config.yaml** (local development only) - fallback
3. **Error if neither is set** - fail fast with clear message

### 4.2 API Keys & Secrets

**Required for Production:**
- `TMDB_API_KEY` - The Movie Database API key
- `WATCHMODE_API_KEY` - Watchmode streaming links API key
- `OMDB_API_KEY` - OMDb API key (optional, for fallbacks)

**Admin Panel Security:**
- `ADMIN_USERNAME` - Admin panel username (default: admin)
- `ADMIN_PASSWORD` - Admin panel password (default: admin)

**Local Development:**
See `config.yaml` for local development configuration. Replace placeholder values with real API keys. Never commit real keys to version control.

### 4.3 config.yaml Structure

```yaml
api:
  tmdb_api_key: ""  # TMDB API key (can be set via TMDB_API_KEY env var)
  tmdb_rate_limit: 0.1  # Seconds between API calls
  max_retries: 3

workflow:
  daily_check_time: "02:00"  # 2 AM PST
  weekly_bootstrap_day: "sunday"

display:
  days_back: 90  # Show movies from last N days
  min_movies: 20  # Minimum movies to display
  max_movies: 100  # Maximum movies to display

tracking:
  bootstrap_days: 7  # Look back N days for new releases
  check_interval_hours: 24  # How often to check

discovery:
  max_pages: 10  # Maximum TMDB pages to process
  days_back: 30  # Look back N days for releases
  min_movies: 5  # Minimum movies to discover per run
  timeout: 30    # API timeout in seconds

agent_scraper:
  enabled: true
  headless: true
  rate_limit: 2.0
  timeout: 10
  max_retries: 3
  cache_ttl_days: 30
  screenshots_enabled: true
  screenshot_retention_days: 7

rt_scraper:
  enabled: true
  headless: true
  rate_limit: 2.0
  timeout: 10
  max_retries: 1
  cache_ttl_days: 90
```

### 4.4 Cache Strategies

**Rotten Tomatoes Cache** (`cache/rt_cache.json`): 90-day TTL, ~328 entries
**Wikipedia Cache** (`cache/wikipedia_cache.json`): 90-day TTL, ~300 entries
**YouTube Trailer Cache** (`cache/youtube_trailer_cache.json`): 90-day TTL, ~250 entries
**Agent Links Cache** (`cache/agent_links_cache.json`): 30-day TTL, ~50 entries
**Watch Links Cache** (`cache/watch_links_cache.json`): 7-day TTL, ~50 entries

**Cache Efficiency**: 99.4% hit rate in normal operation, prevents API quota exhaustion.

**Cache Strategy Per Component**:
- **Static data (RT ratings, Wikipedia)**: 90-day TTL
- **Dynamic streaming links**: 7-day TTL (faster platform changes)
- **Video trailers**: 90-day TTL (stable YouTube URLs)
- **Agent scraping results**: 30-day TTL (balance between performance and freshness)

## 🌐 External APIs & Rate Limits

### TMDB (The Movie Database)
- **Sign up:** https://www.themoviedb.org/settings/api
- **Environment variable:** `TMDB_API_KEY`
- **Config fallback:** `api.tmdb_api_key` in config.yaml
- **Usage:** Movie metadata, posters, cast/crew information
- **Rate limit:** 40 requests per 10 seconds (handled automatically)

### Watchmode API
- **Sign up:** https://api.watchmode.com/
- **Environment variable:** `WATCHMODE_API_KEY`
- **Config fallback:** `api.watchmode_api_key` in config.yaml
- **Free Tier:** 1,000 requests/month (no credit card required)
- **Usage:** Deep links to streaming platforms (Netflix, Amazon, HBO Max, etc.)
- **Endpoints used:**
  - Search: https://api.watchmode.com/v1/search/ (search by TMDB ID)
  - Details: https://api.watchmode.com/v1/title/{watchmode_id}/details/ (get streaming sources)
- **Authentication:** Pass `apiKey` as query parameter
- **Coverage:** 200+ streaming services in 50+ countries (US data on free tier)

### OMDb API
- **Sign up:** http://www.omdbapi.com/apikey.aspx
- **Environment variable:** `OMDB_API_KEY`
- **Config fallback:** `api.omdb_api_key` in config.yaml (if implemented)
- **Usage:** Alternative movie data source, poster fallbacks
- **Free Tier:** 1,000 requests/day

### Agent-Based Link Finding (No API Key Required)
- **Purpose:** Scrape direct watch links from streaming platforms when Watchmode API has no data
- **Platforms:** Netflix, Disney+, HBO Max, Hulu
- **Technology:** Playwright with headless Chrome
- **Rate Limiting:** 2-second minimum delay between scrapes
- **Cache:** `cache/agent_links_cache.json`
- **Usage:** Automatic fallback when Watchmode API returns no data
- **Optional:** Can be disabled by not initializing agent in `generate_data.py`
- **Terms of Service:** Web scraping may violate platform ToS; use responsibly

## 🔗 Watch Links Schema & Cache

### Canonical Watch Links Schema

**Official Structure (as defined in [PROJECT_CHARTER.md](PROJECT_CHARTER.md)):**

The `watch_links` field in `data.json` uses a **three-category structure** representing different access methods:

```json
{
  "watch_links": {
    "streaming": {
      "service": "Netflix",
      "link": "https://www.netflix.com/title/12345"
    },
    "rent": {
      "service": "Amazon Video",
      "link": "https://www.amazon.com/..."
    },
    "buy": {
      "service": "Apple TV",
      "link": "https://tv.apple.com/..."
    }
  }
}
```

### Category Definitions
- **`streaming`**: Subscription-based services (Netflix, Prime, Disney+, HBO Max, Hulu, MUBI, Criterion)
- **`rent`**: Rental options (Amazon Video, Apple TV, Google Play, Vudu)
- **`buy`**: Purchase options (Amazon Video, Apple TV, Google Play, Microsoft Store)

### Schema Rules
1. **Optional categories**: Only present when available for the movie (sparse structure)
2. **Required fields per category**: `service` (string, provider name) and `link` (string URL or null)
3. **Null links allowed**: `link: null` indicates service is available but URL not found (frontend shows error state)
4. **No search URLs**: System returns `null` instead of Google/Amazon search fallbacks (curator can add overrides)
5. **Service priority**: Best service selected per category (Netflix > Disney+ for streaming, Amazon > Apple TV for rent/buy)

### Cache Strategy
- **Location:** `cache/watch_links_cache.json`
- **Key:** TMDB ID (string)
- **Value:** `{links: {...}, cached_at: ISO-8601, source: 'watchmode_api'|'tmdb_providers'}`
- **Purpose:** Prevents redundant API calls (saves 13,380 calls/month)
- **Effectiveness:** With cache, monthly usage is ~300 calls (new movies only); without cache, would be 13,680 calls (exceeds free tier)
- **Migration support:** Automatically migrates legacy `free/paid` format to canonical `streaming/rent/buy` schema

## 📊 Data Contracts

### movie_tracking.json Schema

```json
{
  "title": "Movie Name",
  "tmdb_id": 12345,
  "status": "available|tracking|removed",
  "enriched": true,
  "enrichment_date": "2025-11-05T10:30:00Z",
  "digital_date": "2025-10-15",
  "rt_url": "https://...",
  "rt_rating": 85,
  "platforms": ["netflix", "hulu"],
  "manually_corrected": true,
  "manual_rt_score": true,
  "last_manual_edit": "2025-10-19T..."
}
```

### data.json Schema

Filtered, enriched subset for frontend display:

```json
{
  "tmdb_id": 12345,
  "imdb_id": "tt1234567",
  "title": "Movie Title",
  "original_title": "Original Title",
  "digital_date": "2025-10-15",
  "poster": "https://image.tmdb.org/...",
  "crew": {
    "director": "Director Name",
    "cast": ["Actor 1", "Actor 2"]
  },
  "synopsis": "Movie description...",
  "metadata": {
    "runtime": 120
  },
  "links": {
    "trailer": "https://youtube.com/...",
    "rt": "https://rottentomatoes.com/...",
    "wikipedia": "https://en.wikipedia.org/..."
  },
  "watch_links": {
    "streaming": {"service": "Netflix", "link": "https://..."},
    "rent": {"service": "Amazon", "link": "https://..."},
    "buy": {"service": "Apple TV", "link": "https://..."}
  }
}
```

### Required Fields Per Movie
- `tmdb_id`, `imdb_id`, `title`, `original_title`
- `digital_date` (ISO‑8601 format)
- `poster`, `crew.director`, `crew.cast[]`, `synopsis`
- `metadata.runtime`
- `links.{trailer,rt,wikipedia}` (nullable)
- `watch_links` (optional, but structured per schema above)

### Enrichment Flags
- `enriched` (boolean): Skip enrichment if true
- `enrichment_date` (timestamp): When movie was last enriched
- `manually_corrected` (boolean): Protected from automation overwrites
- `manual_*` flags: Field-specific manual correction tracking

## 🔄 Pipeline Contracts

### Daily Pipeline Phases

**Phase 1: Discovery** (`generate_data.py --discover`)
- Finds new theatrical releases from TMDB
- Updates `movie_tracking.json` with new entries
- Status: "tracking"
- Expected: 10-20 movies/day

**Phase 2: Provider Monitoring** (`generate_data.py --check`)
- Monitors tracking movies for digital availability
- Updates status from "tracking" to "available"
- Records digital_date and platform details
- Expected: 2-5 movies/day transition

**No API Dates; Full Change Detection Poll**

Always poll ALL tracking movies in `movie_tracking.json` (no time limits). Fetch TMDB providers; if appears (null → value), set `digital_date = today`, `status = available`. Our detection defines availability – no external dates. Once found, status change excludes from future tracking polls (status != "tracking" means no longer monitored). Priority ordering is allowed but not skipping. Link: [docs/troubleshooting/change_detection.md](docs/troubleshooting/change_detection.md)

**Phase 3: Enrichment** (`generate_data.py` main)
- Only processes newly available movies (enrichment-on-transition)
- Adds RT ratings, Wikipedia links, watch links
- Sets `enriched: true` flag
- Expected: 1-10 movies/day processing

**Phase 4: Display Generation**
- Filters available movies for `data.json`
- Applies admin overrides (hidden/featured)
- Generates public-facing display data
- Expected: 250-350 movies in output

### Performance Expectations
- **Normal operation**: 1-10 movies enriched daily, 30-second runtime
- **Warning threshold**: 50+ movies (possible corruption)
- **Critical threshold**: 100+ movies (definite corruption, 2+ hour runtime)

---

## 🔄 Data Flow Overview

### 4.1 The Five Phases

```
Phase 1: Discovery & Monitoring
    ↓ generate_data.py --discover
    ↓ Updates: movie_tracking.json
    ↓ Tracks: 330+ movies across platforms

Phase 2: Enrichment (ONLY newly available)
    ↓ generate_data.py (main process)
    ↓ Enriches: 1-10 movies/day (transition only)
    ↓ Caching: 99.4% efficiency (328/330 cached)

Phase 3: Quality Assurance
    ↓ admin.py (manual QA interface)
    ↓ Validates: Links, ratings, metadata
    ↓ See ADMIN_WORKFLOW.md for the operational steps

Phase 4: Display Generation
    ↓ generate_data.py (final step)
    ↓ Generates: data.json, index.html

Phase 5: User Display
    ↓ index.html + assets/
    ↓ Renders: Movie grid with filters
```

### 4.2 Key Data Transformations

**movie_tracking.json structure**:
```json
{
  "title": "Movie Name",
  "tmdb_id": 12345,
  "status": "available|tracking|removed",
  "enriched": true,
  "enrichment_date": "2025-11-05T10:30:00Z",
  "rt_url": "https://...",
  "platforms": ["netflix", "hulu"]
}
```

**data.json structure**: Filtered, enriched subset for frontend display

**Filtering Rules**:
- Include: `status == "available"`
- Exclude: Missing critical data (RT rating, watch links)
- Sort: By release date, rating

### 4.3 Link Resolution

**5-Tier Fallback Waterfall**:
1. Direct platform links (Netflix, Hulu, etc.)
2. JustWatch aggregator
3. Streaming platform search
4. TMDB recommendations
5. Manual override files

**Null-Link Policy**: When no real deep link is available, the backend returns `link: null` (no search fallbacks); the UI renders a disabled NOT AVAILABLE button.

See [NRW_DATA_WORKFLOW_EXPLAINED.md](./NRW_DATA_WORKFLOW_EXPLAINED.md) for detailed data flow documentation.

---

## ⚡ Enrichment-on-Transition Pattern

**THIS IS THE MOST CRITICAL SECTION FOR UNDERSTANDING SYSTEM PERFORMANCE**

### 5.1 The Problem (Before Optimization)

**Before Oct 24, 2025**: System enriched ALL 300+ movies on every run
- **Runtime**: 75 minutes per run
- **API Calls**: 9,540 per month
- **Cost**: Exceeded free tier limits
- **User Impact**: Slow updates, quota exhaustion

### 5.2 The Solution

**Core Principle**: Only enrich movies when they transition from "tracking" to "available"

**Implementation**: Check `enriched` flag before expensive operations
- Location: `generate_data.py` lines 2333-2426
- Logic: `if not movie.get('enriched', False): enrich_movie(movie)`
- Flags: `enriched` boolean + `enrichment_date` timestamp

### 5.3 Performance Impact

**Before vs After Optimization**:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **API Calls/Month** | 9,540 | 150-300 | 98% reduction |
| **Runtime** | 75 minutes | 30 seconds | 96% faster |
| **Movies Processed** | 300+ daily | 1-10 daily | 97% reduction |
| **Cache Hit Rate** | 0% | 99.4% | Cache efficiency |

**Real-world Example** (Nov 5, 2025 logs):
```
Processing 7 movies for enrichment (out of 330 total)
Cache hits: 323/330 (98.8%)
Runtime: 32 seconds
```

### 5.4 Flags Used in movie_tracking.json

**`enriched` (boolean)**:
- `true`: Skip enrichment (use cached data)
- `false`: Perform full enrichment
- Set to `false` when movie transitions to "available"

**`enrichment_date` (ISO timestamp)**:
- When movie was last enriched
- Used for cache expiry (90 days)
- Format: "2025-11-05T10:30:00Z"

**Example JSON**:
```json
{
  "title": "Dune: Part Two",
  "status": "available",
  "enriched": true,
  "enrichment_date": "2025-11-05T10:30:00Z",
  "rt_rating": 93,
  "rt_url": "https://www.rottentomatoes.com/m/dune_part_two"
}
```

**Flag Setting Logic** (generate_data.py:2422-2423):
```python
movie['enriched'] = True
movie['enrichment_date'] = datetime.now().isoformat()
```

### 5.5 Common Failure Mode - Data Corruption Cascade

⚠️ **CRITICAL**: Data corruption can trigger massive re-enrichment, causing 2+ hour runtimes

**How Corruption Triggers Cascade**:
1. Bug corrupts `enriched` flags (sets all to `false`)
2. System sees 330+ movies needing enrichment
3. Runtime explodes: 330 × 15s = 1.4 hours
4. API quotas exceeded
5. Validation timeouts
6. User sees "No recent movies" errors

**Recent Example - Oct 25-Nov 5, 2025 Outage**:
- **Trigger**: Line 1848 bug in generate_data.py
  ```python
  # BROKEN (corrupted all enriched flags)
  data_movies = json.load(df)  # Loaded wrong object
  for dm in data_movies:       # Iterated over dict keys
  ```
- **Impact**: 550 movies marked `enriched=false`
- **Runtime**: 550 × 15s = 2.3 hours
- **Validation**: Failed with "Processing timeout"
- **Fix**: Corrected bug, added schema validation

**Detection**: Monitor logs for "Processing X movies"
- **Normal**: 1-10 movies
- **Warning**: 50+ movies (possible corruption)
- **Critical**: 100+ movies (definite corruption)

**Prevention**:
- Schema validation on data load
- Enrichment consistency checks
- Performance monitoring (TICKET-11)

### 5.6 Decision Tree Diagram

```mermaid
flowchart TD
    A[Movie Status Check] --> B{Status = available?}
    B -->|No| C[Skip - Not Available]
    B -->|Yes| D{enriched = true?}

    D -->|Yes| E[Check Cache Age]
    E --> F{Age > 90 days?}
    F -->|No| G[✅ Use Cache - FAST PATH]
    F -->|Yes| H[🔄 Re-enrich - Stale Data]

    D -->|No| I[🔴 Full Enrichment Required]
    I --> J[Scrape RT Rating]
    J --> K[Scrape Wikipedia]
    K --> L[Find Watch Links]
    L --> M[Update Flags]
    M --> N[✅ Enrichment Complete]

    O[❌ CORRUPTION DETECTED] --> P[ALL enriched = false]
    P --> Q[330+ movies to process]
    Q --> R[⚠️ CRITICAL: 2+ hour runtime]

    style G fill:#90EE90
    style I fill:#FFB6C1
    style H fill:#FFEB3B
    style R fill:#FF4444,stroke:#000,stroke-width:3px
    style O fill:#FF4444,stroke:#000,stroke-width:3px
```

### 5.7 Monitoring and Alerts

**Normal Operation**: 1-10 movies processed daily
**Warning Threshold**: 50+ movies (TICKET-11 implementation)
**Critical Threshold**: 100+ movies (automatic failure)

**Alert Triggers**:
- Warn: Processing > 50 movies
- Fail: Processing > 100 movies
- Timeout: Runtime > 5 minutes

See [NRW_DATA_WORKFLOW_EXPLAINED.md Section 2.1](./NRW_DATA_WORKFLOW_EXPLAINED.md) for additional enrichment details.

---

## 🤖 Automation Workflow

### 6.1 GitHub Actions Daily Update

**File**: `.github/workflows/daily-check.yml`
**Schedule**: 1:00 AM PT daily (cron: '0 9 * * *' = 9 AM UTC)
**Trigger**: Also manual via workflow_dispatch

### 6.2 GitHub Actions Weekly Full Regeneration

**File**: `.github/workflows/weekly-full-regen.yml`
**Schedule**: 10:00 AM UTC on Sundays
**Trigger**: Also manual via workflow_dispatch

**Process**:
1. Checkout main branch
2. Run `generate_data.py --full`
3. Validate data quality
4. Commit and push to main

### 6.3 Workflow Steps

1. **Checkout main** - Get latest main branch code
2. **Setup Python 3.11** - Runtime environment
3. **Install Dependencies** - pip install -r requirements.txt
4. **Set API Keys** - From GitHub secrets
5. **Run daily pipeline** - python3 daily_orchestrator.py
6. **Validate Results** - 5 validation checks
7. **Commit Changes** - Git add/commit
8. **Commit & push to main** - Direct push to main branch
9. **Report Status** - Success/failure notification

**Simplified Workflow**: Single-branch approach eliminates sync complexity and branch divergence issues.

### 6.4 Legacy: Force Push Strategy (No Longer Used)

**Historical Concept**: In the two-branch system, automation-updates was ephemeral
- No longer applicable with single-branch workflow
- Single-branch commits directly to main (no force pushing needed)
- User maintains control with admin approval gates

### 6.5 User Sync Workflow

```bash
# Single-branch workflow - direct commits to main
# 1. git checkout main
# 2. git pull origin main
# 3. Changes committed directly to main (no merging needed)
```

### 6.6 Validation Gates

1. **Data File Existence** - data.json, movie_tracking.json exist
2. **Recent Movies Check** - At least 3 movies released in last 30 days
3. **Data Integrity** - Valid JSON structure
4. **Performance Check** - Runtime under 5 minutes
5. **API Quota Check** - Under 80% monthly limit

**For detailed workflow documentation:** See [docs/NRW_FULL_WORKFLOW.md](docs/NRW_FULL_WORKFLOW.md)

---

## 🔑 Key Concepts

### 7.1 Smart Caching

**Cache-First Strategy**: Check cache before API calls
**TTL Management**: 90 days for static data, 7 days for streaming
**Efficiency**: 99.4% cache hit rate in normal operation

See Section 5 above for detailed enrichment-on-transition caching.

### 7.2 Rate Limiting

**Default Delays** (config.yaml):
- Rotten Tomatoes: 2 seconds
- Streaming platforms: 3 seconds
- Wikipedia: 1 second
- YouTube API: 100 requests/day

### 7.3 Playwright Scrapers

**Migration Status**: RT scraper migrated to Playwright (Oct 2025)
**Benefits**: Better anti-bot detection, more reliable
**Remaining**: Other scrapers still use BeautifulSoup/Selenium

### 7.4 Multi-Tier Fallback

**5-Tier Waterfall**:
1. Direct platform APIs
2. JustWatch integration
3. Streaming platform search
4. TMDB recommendations
5. Manual override files

### 7.5 Admin Panel

**Purpose**: Manual data quality assurance
**Access**: `python3 admin.py` (local only)
**Features**: Edit movies, force re-enrichment, view logs

**Detailed specification:** [docs/features/ADMIN_PANEL_SPEC.md](docs/features/ADMIN_PANEL_SPEC.md)

---

## ⚠️ Common Failure Modes

**For detailed troubleshooting guides with step-by-step solutions, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).**

This section provides a quick overview of failure patterns. Each subsection below links to the corresponding detailed troubleshooting guide with commands, examples, and historical post-mortems.

### 8.1 Branch Divergence

**Symptoms**:
- Validation errors about "old code"
- 2+ hour runtimes
- Processing 100+ movies

**Historical Root Cause**: Two-branch system had synchronization issues

**Current Solution**: Single-branch workflow eliminates this issue entirely
- No branch synchronization needed
- Direct commits to main prevent divergence

**Detailed troubleshooting:** [docs/TROUBLESHOOTING.md - Branch Divergence](docs/TROUBLESHOOTING.md#5-branch-divergence)

### 8.2 Data Corruption Cascade

**Symptoms**:
- "Processing 300+ movies" in logs
- Runtime over 1 hour
- Validation timeouts

**Root Cause**: `enriched` flags corrupted (all set to `false`)

**Example**: Line 1848 bug (Oct 25-Nov 5)
```python
# BROKEN CODE that caused corruption
data_movies = json.load(df)  # Wrong object loaded
for dm in data_movies:       # Iterated over keys, not movies
```

**Detection**: Check log for processing count
**Fix**: Restore enriched flags from backup
**Prevention**: Schema validation, consistency checks

**Detailed troubleshooting:** [docs/TROUBLESHOOTING.md - Workflow Timeout](docs/TROUBLESHOOTING.md#3-workflow-timeout--2-hour-runtimes)

### 8.3 API Quota Exhaustion

**Symptoms**:
- HTTP 429 errors
- Missing ratings/data
- Quota warnings

**Root Cause**: Processing too many movies (see 8.2)

**Detection**: Check `watchmode_quota.json`
**Fix**: Wait for quota reset, optimize requests
**Prevention**: Enrichment-on-transition pattern

**Detailed troubleshooting:** [docs/TROUBLESHOOTING.md - Watchmode Quota](docs/TROUBLESHOOTING.md#4-watchmode-api-quota-exhausted)

### 8.4 Scraper Failures

**Symptoms**:
- Missing RT ratings
- Empty watch links
- Cache miss spikes

**Root Cause**: Website changes, anti-bot measures

**Detection**: Low success rates in logs
**Fix**: Update scraper logic, add retries
**Prevention**: Playwright migration, fallback scrapers

**Detailed troubleshooting:** See docs/TROUBLESHOOTING.md for scraper-specific debugging (future enhancement)

### 8.5 Change Detection finds 0 transitions

**Symptoms**:
- Provider checks find no transitions despite known releases
- Movies stuck in "tracking" status
- 0 "✓ now on [service]" messages

**Root Cause**: API key issues, TMDB provider API failures, cache problems

**Detection**: Monitor logs for transition counts
**Fix**: Validate API keys, test TMDB provider endpoint
**Prevention**: Regular API validation, proper error handling

**Detailed troubleshooting:** [docs/troubleshooting/change_detection.md](docs/troubleshooting/change_detection.md)

### 8.6 Validation Errors

**Symptoms**:
- "No recent movies found"
- Workflow failures
- Empty data.json

**Common Errors**:
- Data corruption (see 8.2)
- Network timeouts
- Invalid JSON structure

**Fix**: Check data integrity, re-run generation
**Recent Improvements**: Better error handling, validation gates

**Detailed troubleshooting:** [docs/TROUBLESHOOTING.md - Validation Failures](docs/TROUBLESHOOTING.md#2-validation-failures---no-recent-movies)

---

## 📚 Additional Documentation

**Related Documentation**:
- [PROJECT_CHARTER.md](./PROJECT_CHARTER.md) - Business requirements, amendments
- [NRW_DATA_WORKFLOW_EXPLAINED.md](./NRW_DATA_WORKFLOW_EXPLAINED.md) - Detailed data flow
- [DAILY_CONTEXT.md](./DAILY_CONTEXT.md) - Daily operational context
- [README.md](./README.md) - Quick start guide
- [docs/](./docs/) - Legacy documentation

**Key Amendments to Reference**:
- [025: Two-Branch Automation Strategy](./PROJECT_CHARTER.md#025-two-branch-automation-strategy): Two-branch deployment strategy
- [023: Agent-Based Link Finding for Streaming Platforms](./PROJECT_CHARTER.md#023-agent-based-link-finding-for-streaming-platforms): Playwright migration for agent scraper
- [027: Admin Panel - Post-Publication Curation & Data Quality](./PROJECT_CHARTER.md#027-admin-panel---post-publication-curation--data-quality): Admin panel redesign

---

**Last Updated**: 2025-11-05
**Maintained By**: Development Team
**Questions**: See DAILY_CONTEXT.md or create GitHub issue