# **NRW Data Workflow - Complete Overview**

## **🎯 End Goal: A Netflix-Style Movie Wall**
We want a beautiful webpage that shows the latest movies available for streaming/rental, with working links to trailers, reviews, and Wikipedia pages. Think "Blockbuster wall for the streaming age."

---

## **📊 The Data Journey: From API to Your Screen**

### **Phase 1: Daily Discovery & Monitoring**
**What happens:** We check if tracked movies became available for digital (streaming/rental/buy) AND discover new movies to track.

**🔧 `movie_tracker.py daily`** - *The Complete Movie Tracker*
- **Discovery:** Searches TMDB API for movies released in past 7 days (festival, limited theatrical, theatrical, direct to streaming, etc.)
- **Monitoring:** Checks ALL movies in database for digital availability on Netflix, Amazon, etc.
- **Why:** There is no functional DIGITAL premiere date in APIs. They only show current state. We detect the change by checking daily.
- **The Core Problem:** APIs don't tell us "this movie became available digitally today" - they only show what's available right now. We have to detect transitions ourselves.
- **When:** Daily (automated) - **CRITICAL:** Must run daily because both new movies appear and providers add movies unpredictably
- **Magic moment:** When it finds new providers, sets `digital_date` = today, status = "available"
- **Output:** Updates tracking database with new movies and availability changes

**📄 `movie_tracking.json`** - *The Master Database*
- **What it is:** Complete database of all movies we're monitoring (count always changing)
- **Why:** Single source of truth for all movie data and tracking status
- **Contains:** Movie details, tracking status ("tracking" vs "available"), provider info
- **Example:** `{"1404864": {"title": "Inspector Zende", "status": "tracking", "digital_date": null}}`
- **Updated by:** Daily command (adds new movies and updates availability)

### **Phase 2: Database Enrichment & Link Resolution**
**What happens:** We take movies that became digitally available and fill out ALL their details - cast, director, synopsis, posters, trailers, Wikipedia pages, review links, watch links (streaming/rent/buy), country, studio, runtime, genres.

**🔧 `generate_data.py`** - *The Complete Data Enricher*
- **What it does:** Takes recently available movies (90 days) and creates full movie profiles
- **Incremental mode (default):** Only processes NEW movies not already in data.json, then ADDS them to existing list (takes seconds)
- **Full regeneration mode:** Rebuilds entire data.json from scratch (takes 30+ minutes, use only when needed)
- **TMDB API calls:** Fetches complete movie details including cast, crew, synopsis, posters, genres, studio, runtime, country
- **Link resolution:** Finds working Wikipedia pages, trailers, and review links
- **Why:** Users need complete movie information to decide what to watch

**📂 Link Resolution System** - *Multi-Tier Intelligent Lookup*

**Watch Links (Streaming/Rent/Buy):**
- **Tier 1:** `admin/watch_link_overrides.json` - Manual curator fixes (highest priority)
- **Tier 2:** `cache/watch_links_cache.json` - Watchmode API deep links cache
- **Tier 3:** Watchmode API - Direct links to Netflix, Amazon, Apple TV, etc.
- **Tier 4:** `agent_link_scraper.py` - Playwright-based scraping for Netflix, Disney+, HBO Max, Hulu
- **Tier 5:** TMDB provider names with null links - Frontend shows error state
- **Technology:** Playwright (agent scraper), Watchmode API (primary source)
- **Cache:** `cache/agent_links_cache.json` with 30-day expiration, screenshot diagnostics on failure

**Wikipedia Links:**
- **Tier 1:** `overrides/wikipedia_overrides.json` - Manual fixes for wrong links
- **Tier 2:** `wikipedia_cache.json` - Cached successful lookups
- **Tier 3:** Wikipedia REST API - Fast HTTP-based search (built into generate_data.py)
- **Tier 4:** Search URL fallback - When REST API fails
- **Manual tool:** `wikipedia_scraper.py` - Selenium-based fallback for complex cases (not automated)
- **Technology:** REST API (primary), Selenium (manual fallback only)

**Rotten Tomatoes Links:**
- **Tier 1:** `overrides/rt_overrides.json` - Manual fixes
- **Tier 2:** `rt_cache.json` - Cached RT URLs and scores
- **Tier 3:** RT Scraper - Selenium-based scraping (inlined into generate_data.py)
- **Tier 4:** RT search URL fallback - When scraping fails
- **Technology:** Selenium (inlined), no external class
- **Cache:** `rt_cache.json` with 90-day expiration

**YouTube Trailer Links:**
- **Tier 1:** `youtube_trailer_cache.json` - Cached direct watch URLs
- **Tier 2:** `scripts/youtube_trailer_scraper.py` - Selenium-based scraping
- **Tier 3:** YouTube search URL fallback - When scraping fails
- **Technology:** Selenium (external class), integrated into generate_data.py

**Failure Tracking:**
- `missing_wikipedia.json` - Logs Wikipedia lookup failures for manual review
- `cache/screenshots/` - Agent scraper failure diagnostics (screenshots + HTML)

**Watch Links (Streaming/Rent/Buy):**
- **Streaming:** Subscription services (Netflix, Prime, Disney+, HBO Max, Hulu, MUBI, Criterion)
- **Rent:** Rental options (Amazon Video, Apple TV, Google Play, Vudu)
- **Buy:** Purchase options (Amazon Video, Apple TV, Google Play, Microsoft Store)
- **Service Priority:** Netflix > Disney+ > HBO Max > Hulu > Amazon Prime (streaming); Amazon > Apple TV (rent/buy)
- **Link Types:** Direct deep links (Watchmode API, agent scraper) or null (frontend shows error state)
- **No search URLs:** System returns null instead of Google/Amazon searches (curator can add overrides)

**What gets filled out:**
- **Basic info:** Title, year, synopsis, poster URL, IMDb ID
- **People:** Director, top 2 cast members
- **Metadata:** Genres, studio/production company, runtime, country of origin
- **Links:** Trailer (from TMDB videos), Rotten Tomatoes URL, Wikipedia page, watch links (streaming/rent/buy)

**Why this complexity?** 
- Simple approach: Generate URLs like "Inspector_Zende_(film)" → 50% are broken
- Smart approach: Verify URLs exist, use multiple methods → 80% success rate

### **Phase 3: Editorial Curation**
**What happens:** The admin panel lets you hide unwanted movies, feature special titles, edit dates, and manually override watch links.

**🔧 Admin Panel Interface** (`admin.py` on port 5555)
- **Hide/Show:** Remove movies from public display (saved to `admin/hidden_movies.json`)
- **Feature:** Mark special movies for highlighting (saved to `admin/featured_movies.json`)
- **Date Editing:** Correct digital release dates in `movie_tracking.json`
- **Watch Link Overrides:** Manually add/fix streaming, rent, buy links (saved to `admin/watch_link_overrides.json`)
- **Regenerate:** Trigger `generate_data.py` to apply changes to public site
- **Authentication:** HTTP Basic Auth (default: admin/changeme - change in production!)
- **Why:** Editorial control ensures quality curation and allows fixing API/scraper failures

### **Phase 4: Display Generation**
**What happens:** We create the final JSON file that the website reads, applying admin decisions and enriching with all metadata.

**🔧 `generate_data.py` with Admin Integration**
- **Data enrichment:** Creates complete movie profiles with all metadata (cast, crew, synopsis, posters, links)
- **Watch link resolution:** Multi-tier waterfall (overrides → cache → Watchmode API → agent scraper → null)
- **Admin filtering:** Applies decisions from `admin/hidden_movies.json` (removes from display)
- **Admin featuring:** Marks movies from `admin/featured_movies.json` with `"featured": true` flag
- **Admin overrides:** Applies manual watch links from `admin/watch_link_overrides.json`
- **Quality assurance:** Only curated content with verified links reaches users

**📄 `data.json`** - *The Website Menu*
- **What it is:** Clean, final dataset of all recent movies with verified data and working links
- **Why:** Website needs fast loading, verified data, no broken links
- **Structure:** Each movie has poster, synopsis, director, cast, trailer, RT link, Wikipedia link, watch_links (streaming/rent/buy)
- **Watch links:** Three categories with service names and URLs (or null if unavailable)
- **Key rule:** Only verified links included - null indicates link failure (not hidden with search URLs)
- **Display:** Endless scroll backwards week after week, three-button UI (STREAM/RENT/BUY)

### **Phase 5: User Display**
**What happens:** User visits the website and sees the beautiful movie wall.

**🌐 `index.html`** - *The Front Door*
- **What it does:** Basic HTML structure, loads the CSS and JavaScript
- **Why:** Entry point that browsers can understand

**🎨 `assets/styles.css`** - *The Visual Designer*
- **What it does:** Makes everything look beautiful - card layouts, animations, colors
- **Why:** Raw HTML looks terrible - CSS makes it Netflix-quality

**⚡ `assets/app.js`** - *The Interactive Engine*
- **What it does:** Fetches data.json, renders movie cards, handles flipping animations, manages three-button watch UI
- **Why:** Modern websites are interactive - this brings the data to life
- **Smart features:**
  - `wikiUrlFor()` function provides safe fallbacks if Wikipedia links fail
  - Three-button watch system: STREAM (shows platform name), RENT, BUY
  - Button states: Active (has link), Disabled (category unavailable), Error (link is null)
  - Platform name display: "NETFLIX", "PRIME", "MUBI", etc. for streaming button

---

## **🔄 Daily Automation Loop**

**🔧 `daily_orchestrator.py`** - *The Modern Orchestra Conductor*
```bash
1. python movie_tracker.py daily     # Discover new movies + monitor all existing for availability changes
2. python generate_data.py           # Create enriched display data with links (includes RT scraping, agent scraping)
3. git commit & push                 # Save changes
```

**Automated via GitHub Actions:**
- Runs daily at 9 AM UTC
- Installs Playwright browsers (`playwright install chromium`)
- Executes full pipeline automatically
- Commits results to repository

**Legacy:** `daily_update.sh` exists but `daily_orchestrator.py` is the modern implementation

**🔍 `ops/health_check.py`** - *The Quality Inspector*
- **What it does:** Checks data.json has correct structure, no broken links
- **Why:** Catches problems before users see them

---

## **📋 File Organization Logic**

**Why this folder structure?**
```
/index.html, /data.json, /assets/     ← Runtime files (what users see)
/movie_tracking.json                  ← Master tracking database
/wikipedia_cache.json, /rt_cache.json ← Speed optimization (root directory)
/youtube_trailer_cache.json           ← YouTube scraper cache (root directory)
/agent_link_scraper.py                ← Playwright-based watch link scraper
/wikipedia_scraper.py                 ← Manual fallback tool (Selenium)
/scripts/youtube_trailer_scraper.py   ← YouTube scraper (Selenium, integrated)
/admin/                               ← Editorial control files (hidden, featured, watch link overrides)
/cache/                               ← Watchmode API cache, agent scraper cache, screenshots
/overrides/                           ← Manual fixes for Wikipedia and RT links
/ops/                                 ← Operational tools (health check, archive script)
/museum_legacy/                       ← Archived experiments and deprecated scrapers
```

---

## **🤖 Scraper Architecture & Technology Stack**

### **Active Scrapers**

**Integrated into generate_data.py (Automatic):**

1. **Wikipedia REST API** (Built-in, lines 177-228)
   - **Technology:** HTTP requests to Wikipedia API endpoint
   - **Speed:** ~200ms per lookup
   - **Reliability:** High (official API)
   - **Cache:** `wikipedia_cache.json` (root directory)
   - **Fallback:** Search URL if API fails

2. **RT Scraper** (Inlined, AMENDMENT-042)
   - **Technology:** Selenium WebDriver with Chrome
   - **Speed:** ~6-8 seconds per scrape (includes rate limiting)
   - **Reliability:** Medium (CSS selectors can break)
   - **Cache:** `rt_cache.json` (root directory, 90-day TTL)
   - **Waterfall:** Overrides → Cache → Scraper → Search URL
   - **Selectors:** 3 search result selectors, 4 score selectors (fallback strategy)

3. **Agent Link Scraper** (External class, AMENDMENT-041)
   - **File:** `agent_link_scraper.py` (736 lines, Playwright-based)
   - **Technology:** Playwright with Chromium browser
   - **Platforms:** Netflix, Disney+, HBO Max, Hulu (services without predictable URLs)
   - **Speed:** ~10-15 seconds per scrape (includes exponential backoff retry)
   - **Reliability:** High (selector fallbacks, auto-wait, screenshot diagnostics)
   - **Cache:** `cache/agent_links_cache.json` (30-day TTL, enhanced metadata)
   - **Waterfall:** Admin overrides → Cache → Watchmode API → Agent scraper → null
   - **Features:** 4-6 selector fallbacks per platform, exponential backoff (3 retries), screenshot capture on failure
   - **Diagnostics:** Saves screenshots to `cache/screenshots/` when scraping fails

4. **YouTube Trailer Scraper** (External class)
   - **File:** `scripts/youtube_trailer_scraper.py` (192 lines, Selenium-based)
   - **Technology:** Selenium WebDriver with Chrome
   - **Speed:** ~3-5 seconds per scrape
   - **Reliability:** High (YouTube structure is stable)
   - **Cache:** `youtube_trailer_cache.json` (root directory)
   - **Integration:** Called by generate_data.py to convert search URLs to direct watch URLs

**Manual Fallback Tools (Not Automated):**

1. **wikipedia_scraper.py** (Root directory)
   - **Technology:** Selenium WebDriver with Chrome
   - **Use case:** When Wikipedia REST API fails or returns wrong results
   - **Usage:** Manual execution only (not integrated into daily automation)
   - **When to use:** Complex title searches, disambiguation pages, manual verification

### **Archived Scrapers (museum_legacy/)**

These scrapers have been superseded and archived:

- **wikidata_scraper.py** - Replaced by Wikipedia REST API (faster, no Selenium)
- **reelgood_scraper.py** - Replaced by TMDB API (more reliable release dates)
- **date_verification.py** - Only user of reelgood_scraper (non-critical)
- **rt_scraper.py** - Old version, replaced by inlined RT scraper
- **update_rt_data.py** - RT scraping now automatic in generate_data.py
- **bootstrap_rt_cache.py** - RT cache built automatically

See `museum_legacy/README.md` for detailed archival documentation.

### **Technology Comparison**

**Playwright vs Selenium:**
- **Playwright:** Modern, faster (~30% speed improvement), better auto-wait, screenshot/trace debugging
- **Selenium:** Legacy but stable, widely used, good for simple scraping
- **Migration status:** Agent scraper migrated to Playwright (AMENDMENT-041), others remain on Selenium

**REST APIs vs Scraping:**
- **REST APIs:** Preferred when available (Wikipedia, TMDB, Watchmode)
- **Scraping:** Fallback for platforms without APIs (Netflix, Disney+, RT scores)
- **Principle:** Use official APIs first, scrape only when necessary

### **Cache Strategy**

**Cache Locations:**
- **Root directory:** `wikipedia_cache.json`, `rt_cache.json`, `youtube_trailer_cache.json` (legacy location, works fine)
- **cache/ directory:** `watch_links_cache.json`, `agent_links_cache.json`, `screenshots/` (new organized location)
- **Why split:** Historical (old caches in root), new caches in cache/ directory

**Cache Expiration:**
- **Watch links:** 30 days (platforms can change URLs)
- **RT links:** 90 days (RT URLs are stable)
- **Wikipedia/YouTube:** No expiration (URLs rarely change)
- **Agent scraper:** Enhanced metadata (retry counts, error messages, screenshot paths)

**Cache Format:**
- **Watchmode:** `{movie_id: {links: {...}, cached_at, source}}`
- **Agent:** `{movie_id: {streaming: {service, link}, scraped_at, expires_at, success, retry_count, last_error, screenshot, selector_used}}`
- **RT:** `{title_year: {url, score}}` (simple key-value)
- **Wikipedia/YouTube:** `{title_year: url}` (simple key-value)

---

## **🎛️ Admin Panel & Editorial Control**

**🔧 `admin.py`** - *The Curator's Dashboard* (Port 5555)

**Purpose:** Editorial control over public display - hide unwanted movies, feature special titles, fix broken links

**Features:**
- **Hide/Show Movies:** Remove from public display (saves to `admin/hidden_movies.json`)
- **Feature Movies:** Mark for special highlighting (saves to `admin/featured_movies.json`)
- **Date Editing:** Correct digital release dates in `movie_tracking.json`
- **Watch Link Overrides:** Manually add/fix streaming, rent, buy links (saves to `admin/watch_link_overrides.json`)
- **Regenerate Button:** Trigger `generate_data.py` to apply changes to public site

**Authentication:**
- HTTP Basic Auth (username/password prompt)
- Default credentials: `admin` / `changeme` (CHANGE IN PRODUCTION!)
- Override via environment variables: `ADMIN_USERNAME`, `ADMIN_PASSWORD`

**Integration with generate_data.py:**
- Admin overrides are checked FIRST (highest priority in waterfall)
- Hidden movies are filtered out during display generation
- Featured movies get `"featured": true` flag in data.json
- Watch link overrides take precedence over Watchmode API and agent scraper

**Usage:**
```bash
# Start admin panel
python3 admin.py

# With custom credentials
ADMIN_USERNAME=curator ADMIN_PASSWORD=secret123 python3 admin.py

# Access at http://localhost:5555
```

**Admin Override Files:**
- `admin/hidden_movies.json` - Array of TMDB IDs to hide: `["1234567", "7654321"]`
- `admin/featured_movies.json` - Array of TMDB IDs to feature: `["1234567"]`
- `admin/watch_link_overrides.json` - Manual watch links: `{"movie_id": {"streaming": {"service": "Netflix", "link": "https://..."}}}`

---

**The Key Insight:** Separate "what users see" from "how we make it"
- Users never see the tracking database or scrapers
- Website only needs 4 files: index.html, data.json, app.js, styles.css
- Everything else is "behind the scenes" machinery

---

## **🎯 Why This Architecture Works**

1. **Speed:** Website loads fast (only reads 1 small JSON file)
2. **Reliability:** Links are verified before going live (multi-tier fallbacks)
3. **Maintainability:** Each script has one clear job
4. **Scalability:** Can track 1000+ movies, but only show 30 newest
5. **User Experience:** No broken links, no loading delays, three-button watch UI
6. **Automation:** Runs itself daily, commits changes to git
7. **Editorial Control:** Admin panel allows curation and manual fixes
8. **Resilience:** Multiple fallback tiers for every link type (overrides → cache → API → scraper → null)
9. **Diagnostics:** Screenshot capture and enhanced logging for debugging scraper failures
10. **Flexibility:** Can disable scrapers via config.yaml without code changes

**The Result:** A professional movie discovery website that updates itself and never shows broken links.