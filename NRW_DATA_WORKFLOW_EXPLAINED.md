# **NRW Data Workflow - Complete Overview**

## **🎯 End Goal: A Netflix-Style Movie Wall**
We want a beautiful webpage that shows the latest movies available for streaming/rental, with working links to trailers, reviews, and Wikipedia pages. Think "Blockbuster wall for the streaming age."

---

## **📊 The Data Journey: From API to Your Screen**

### **Phase 1: Intake & Discovery Overview**
**What happens:** We intake new movies to track AND discover when tracked movies become available for digital (streaming/VOD (rental/purchase)).

**🔧 `generate_data.py --intake`** - *Intake: New Premiere Ingestion*
- **Intake:** Searches TMDB API for movies released in past 7 days (festival, limited theatrical, theatrical, direct to streaming, etc.)
- **Adds to database:** New movies get status = "tracking", digital_date = null

**🔧 `generate_data.py --discover`** - *Discovery: Provider Availability*
- **Monitoring:** Checks ALL movies in database with status = "tracking" for digital availability on Netflix, Amazon, etc.
- **The Core Problem:** APIs don't tell us "this movie became available digitally today" - they only show what's available right now. We have to detect transitions ourselves.
- **Magic moment:** When it finds new providers, sets `digital_date` = today, status = "available"
- **State file:** Writes list of newly available movie IDs to `metrics/newly_available.json`

**📄 `movie_tracking.json`** - *The Master Database*
- **What it is:** Complete database of all movies we're monitoring (~330 movies)
- **Contains:** Movie details, tracking status ("tracking" vs "available"), provider info
- **Example:** `{"1404864": {"title": "Inspector Zende", "status": "tracking", "digital_date": null}}`

### **Phase 2: Database Enrichment & Link Resolution**
**What happens:** We take movies that JUST BECAME digitally available (from today's provider check) and fill out ALL their details - cast, director, synopsis, posters, trailers, Wikipedia pages, review links, watch links (streaming/vod).

**🔧 `generate_data.py`** - *The Complete Data Enricher*
- **Enrichment-on-transition:** Reads `metrics/newly_available.json` to find which movies were discovered as digitally available TODAY
- **Smart filtering:** Only processes movies in the state file (1-10 per day) + stale enrichment (>90 days old, batch of 10)
- **Performance:** 95%+ cost reduction by avoiding re-enrichment of already-processed movies
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
Daily Intake & Discovery → movie_tracking.json → data.json (minimal) → Enrichment Overlay → Public Site
                          (automated)          (immediate)         (when possible)    (auto-update)
```

**Optional Curation Workflow:**
```
Daily Intake & Discovery → movie_tracking.json → OPTIONAL REVIEW → data.json (minimal) → Enrichment → Public Site
                          (raw scraped)         (when desired)    (immediate)        (overlay)   (visitors)
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

**📄 `data.json`** - *The Website Menu* (Updated 2025-12-05)
- **What it is:** Complete dataset of ALL available movies (minimal records + enriched data when available)
- **Structure:** Movies include basic info (title, date, providers) plus enriched data when successful (poster, synopsis, director, cast, trailer, RT link, Wikipedia link, watch_links)
- **Key change:** Enrichment failures no longer hide movies - minimal records remain visible
- **Reliability:** All discovered movies appear; enrichment overlays when possible

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
1. python3 generate_data.py --intake       # Intake new premieres from TMDB into tracking database
2. python3 generate_data.py --discover     # Discover provider availability for tracking movies
                                           # → Writes metrics/newly_available.json with IDs
3. python3 generate_data.py               # Enrich movies discovered as digitally available from step 2
                                           # → Reads metrics/newly_available.json
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