# **NRW Data Workflow - Complete Overview**

## **🎯 End Goal: A Netflix-Style Movie Wall**
We want a beautiful webpage that shows the latest movies available for streaming/rental, with working links to trailers, reviews, and Wikipedia pages. Think "Blockbuster wall for the streaming age."

---

## **📊 The Data Journey: From API to Your Screen**

### **Phase 1: Daily Discovery & Monitoring**
**What happens:** We check if tracked movies became available for digital (streaming/VOD (rental/purchase)) AND discover new movies to track.

**🔧 `generate_data.py --discover`** - *The Production Discovery System*
- **Discovery:** Searches TMDB API for movies released in past 7 days (festival, limited theatrical, theatrical, direct to streaming, etc.)
- **Monitoring:** Checks ALL movies in database for digital availability on Netflix, Amazon, etc.
- **The Core Problem:** APIs don't tell us "this movie became available digitally today" - they only show what's available right now. We have to detect transitions ourselves.
- **Magic moment:** When it finds new providers, sets `digital_date` = today, status = "available"

**📄 `movie_tracking.json`** - *The Master Database*
- **What it is:** Complete database of all movies we're monitoring (~330 movies)
- **Contains:** Movie details, tracking status ("tracking" vs "available"), provider info
- **Example:** `{"1404864": {"title": "Inspector Zende", "status": "tracking", "digital_date": null}}`

### **Phase 2: Database Enrichment & Link Resolution**
**What happens:** We take movies that became digitally available and fill out ALL their details - cast, director, synopsis, posters, trailers, Wikipedia pages, review links, watch links (streaming/vod).

**🔧 `generate_data.py`** - *The Complete Data Enricher*
- **Smart caching:** Only processes movies transitioning from "tracking" to "available" (1-10 per day)
- **Performance:** 98% cost reduction through enrichment-on-transition pattern
- **Link resolution:** Multi-tier waterfall (overrides → cache → API → scraper → null)
- **TMDB API calls:** Fetches complete movie details including cast, crew, synopsis, posters

**📂 Link Resolution System** - *Multi-Tier Intelligent Lookup*

**Watch Links (Streaming/Rent/Buy):**
- **Tier 1:** `admin/watch_link_overrides.json` - Manual curator fixes (highest priority)
- **Tier 2:** `cache/watch_links_cache.json` - Watchmode API deep links cache
- **Tier 3:** Watchmode API - Direct links to Netflix, Amazon, Apple TV, etc.
- **Tier 4:** `agent_link_scraper.py` - Playwright-based scraping for Netflix, Disney+, HBO Max, Hulu
- **Tier 5:** TMDB provider names with null links - Frontend shows error state

**Wikipedia/RT/YouTube Links:**
- Similar multi-tier approach with manual overrides → cache → API/scraper → fallback
- **Wikipedia:** REST API (primary), Playwright fallback (manual only)
- **Rotten Tomatoes:** Playwright scraper with 90-day cache
- **YouTube Trailers:** Playwright scraper integrated into generate_data.py

### **Phase 3: Optional Editorial Review**
**What happens:** Optional manual curation when editorial review is desired. By default, the daily automation auto-commits discovered content directly to `main` and produces data.json without requiring admin approval.

**Default Workflow (Automated - No Approval Gate):**
```
Daily Discovery → movie_tracking.json → data.json → Public Site
                  (automated)          (automated) (auto-update)
```

**Optional Curation Workflow:**
```
Daily Discovery → movie_tracking.json → OPTIONAL REVIEW → data.json → Public Site
                  (raw scraped)         (when desired)    (curated)   (visitors)
```

**Admin Panel Features** (`./launch_all.sh` → http://localhost:5556):
- **Missing Data Detection:** Visual flagging of incomplete movies with red borders
- **Inline Database Editing:** Edit all fields directly with single "💾 Save All Changes" button
- **UI Preferences:** Hide/show and feature movies (separate from data corrections)
- **YouTube Playlist Creation:** Custom date ranges with dry-run preview
- **Manual Correction Tracking:** All edits flagged with `manual_*` flags to prevent automation overwrites

**Authentication:** No authentication required for local development

### **Phase 4: Display Generation**
**What happens:** We incorporate admin curation decisions and create the final JSON file for the website.

**🔧 `generate_data.py` with Admin Integration**
- **Data enrichment:** Creates complete movie profiles with all metadata
- **Admin corrections:** Reads `manual_*` flags from movie_tracking.json and preserves user edits
- **Admin filtering:** Applies decisions from `admin/hidden_movies.json` (removes from display)
- **Admin featuring:** Marks movies from `admin/featured_movies.json` with `"featured": true` flag

**📄 `data.json`** - *The Website Menu*
- **What it is:** Clean, final dataset of recent movies with verified data and working links
- **Structure:** Each movie has poster, synopsis, director, cast, trailer, RT link, Wikipedia link, watch_links (streaming/vod)
- **Key rule:** Only verified links included - null indicates link failure (not hidden with search URLs)

### **Phase 5: User Display**
**What happens:** User visits the website and sees the beautiful movie wall.

**🌐 Frontend Files**
- **`index.html`:** Basic HTML structure, loads CSS and JavaScript
- **`assets/styles.css`:** Netflix-quality visual design - card layouts, animations, colors
- **`assets/app.js`:** Interactive engine - fetches data.json, renders cards, handles three-button watch UI

---

## **🔄 Daily Automation Loop**

**🔧 `daily_orchestrator.py`** - *The Modern Orchestra Conductor*
```bash
1. python3 generate_data.py --discover     # Discover new movies + monitor existing for availability
2. python3 generate_data.py --check        # Check tracking movies for digital availability
3. python3 generate_data.py               # Create enriched display data with links
4. git commit & push                       # Save changes (automated)
```

**Automated via GitHub Actions:**
- Runs daily at 9 AM UTC
- Installs Playwright browsers (`playwright install chromium`)
- Executes full pipeline automatically
- Commits results to repository

**Note:** Daily automation runs without admin approval by default. Optional admin review can be enabled when editorial curation is desired.

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

**The Result:** A professional movie discovery website that updates itself and never shows broken links.