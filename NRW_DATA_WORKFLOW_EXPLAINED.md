# **NRW Data Workflow - Complete Overview**

**Last Updated:** 2026-03-26

---

## **🎯 What This System Does**

**The New Release Wall is a well-stocked video store for the streaming age.** It finds every cool movie that has debuted online — for streaming, rental, or purchase — and puts them on a wall where people can shop, watch trailers, and click through to rent, buy, or stream on the right platforms.

### The Video Store Design Principle
Discovery uses a **wide net**. If TMDB providers OR Type 4 digital dates indicate a movie is available, it transitions to the wall. The pipeline stocks the shelves; the admin curates (hides low-quality titles, features highlights). We want to find EVERY movie that's newly available digitally — curation happens after, not before.

### The Core Problem
When a movie leaves theaters, there's no API that says "this movie became available on Netflix today." TMDB's provider API only shows what's *currently* available, not *when* it became available. We solve this by polling daily and detecting transitions ourselves.

### Our Solution
```
┌─────────────────────────────────────────────────────────────────────┐
│                        NRW DATA PIPELINE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. INTAKE         2. DISCOVERY        3. ENRICHMENT    4. DISPLAY  │
│  ─────────         ───────────         ────────────     ───────     │
│  Ingest new        Poll for provider   Add RT scores,   Show wall   │
│  theatrical        availability        Wikipedia,       to users    │
│  releases          ↓                   trailers         ↓           │
│  ↓                 When found:         ↓                index.html  │
│  movie_tracking    • Write to data.json  Overlay onto               │
│  .json             • Queue for enrich    existing entry             │
│                                                                     │
│  KEY PRINCIPLE: data.json = rolling 90-day window                    │
│  - Discovery ADDS movies                                            │
│  - Enrichment OVERLAYS data                                         │
│  - Old movies auto-archived after 90 days → data_archive.json       │
└─────────────────────────────────────────────────────────────────────┘
```

### The Result
An ongoing, accumulating database of digital release dates that no one else tracks. A "Blockbuster wall for the streaming age."

---

## **📊 The Data Journey: From API to Your Screen**

### **Phase 1: Intake & Discovery Overview**
**What happens:** We intake new movies to track AND discover when tracked movies become available for digital (streaming/VOD (rental/purchase)).

**🔧 `generate_data.py --intake`** - *Intake: New Premiere Ingestion*
- **Intake:** Searches TMDB API for movies released in past 7 days (festival, limited theatrical, theatrical, direct to streaming, etc.)
- **Adds to database:** New movies get status = "tracking", digital_date = null

**🔧 `generate_data.py --discover`** - *Discovery: Detecting Digital Transitions*
- **Monitoring:** Checks ALL movies in database with status = "tracking" for digital availability
- **Two co-equal discovery signals:**
  1. **TMDB /watch/providers** — Detects streaming providers (Netflix, Disney+, etc.) and rent/buy availability (Amazon, Apple TV, etc.)
  2. **TMDB Type 4 digital release dates** — Detects when a movie's digital release date has arrived. Many movies have Type 4 dates before provider lists are populated, making this a primary discovery mechanism.
- **Magic moment:** When either signal fires, sets `digital_date` = today (or Type 4 date), status = "available"
- **Pre-order detection:** Buy-only + single-provider movies are checked against Amazon to catch pre-orders (not yet available for viewing)
- **JustWatch:** NOT used in discovery. JustWatch provides actual rent/buy deep links (Amazon/Apple TV URLs) during enrichment, not during discovery.
- **State file:** Writes list of newly available movie IDs to `metrics/newly_available.json`

**📄 `movie_tracking.json`** - *The Master Database*
- **What it is:** Complete database of all movies we're monitoring (~15,000+ movies)
- **Contains:** Movie details, tracking status ("tracking" vs "available"), provider info
- **Example:** `{"1404864": {"title": "Inspector Zende", "status": "tracking", "digital_date": null}}`

### **Phase 2: Database Enrichment & Link Resolution**
**What happens:** We take movies that JUST BECAME digitally available (from today's discovery) and add rich metadata - trailers, Wikipedia pages, RT scores, watch links.

**🔧 `generate_data.py`** - *The Enrichment Overlay*
- **Reads today's queue:** `metrics/newly_available.json` contains movie IDs that transitioned TODAY
- **Self-healing retries:** If enrichment fails or is incomplete, movies are automatically retried on subsequent runs (up to 3 attempts). Newly available movies are always prioritized over catch-up retries.
- **Batch cap:** Maximum 100 movies per enrichment run (new arrivals + catch-up combined)
- **Overlay model:** Updates EXISTING entries in data.json (never creates new entries)
- **Performance:** 95%+ cost reduction by only enriching new arrivals (1-10 per day)
- **Link resolution:** Multi-tier waterfall: manual → overrides → cache → JustWatch API → VOD scraper → null (see `docs/features/WATCH_LINK_ARCHITECTURE.md`)

**📂 Link Resolution System** - *Multi-Tier Intelligent Lookup*

**Watch Links (Streaming/VOD)** — see `docs/features/WATCH_LINK_ARCHITECTURE.md`:
- **Tier 1:** Manual watch links (`movie_tracking.json`) — hand-set by curator (highest priority)
- **Tier 2:** Overrides (`overrides/watch_links_overrides.json`) — admin quick-fix file
- **Tier 3:** Cache (`cache/watch_links_cache.json`) — previously-resolved deep links
- **Tier 4:** JustWatch API — **PRIMARY** source for rent/buy deep links (Amazon, Apple TV URLs with prices)
- **Tier 5:** VOD scraper (Playwright) — Amazon, Apple TV scraping (backup when JustWatch fails)
- **Tier 6:** TMDB provider names with null links — last resort, no clickable URL

**Wikipedia/RT/YouTube Links:**
- Similar multi-tier approach with manual overrides → cache → API/scraper → fallback
- **Wikipedia:** 4-tier waterfall (Cache → Wikidata SPARQL → REST API → Playwright). Uses OMDb API fallback for IMDb ID when TMDB doesn't have it.
- **Rotten Tomatoes:** Playwright scraper with 90-day cache
- **Trailers:** YouTube URLs found via Playwright scraper, then downloaded as MP4s and self-hosted on Backblaze B2 (see [docs/features/TRAILER_HOSTING.md](docs/features/TRAILER_HOSTING.md))

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
**What happens:** data.json accumulates discovered movies and gets enhanced with enrichment data.

**📄 `data.json`** - *The Website Database* (Updated 2025-12-29)
- **Rolling window:** Movies are ADDED during discovery. After 90 days, auto-archived to data_archive.json
- **Two write sources:**
  1. **Discovery phase:** Writes minimal entry immediately when movie transitions to available
  2. **Enrichment phase:** Overlays rich data onto existing entries
- **Structure:** Movies include basic info (title, date, poster) plus enriched data when available (synopsis, director, cast, trailer, RT link, Wikipedia link, watch_links)
- **Reliability:** All discovered movies appear; enrichment enhances but never gates visibility
- **Admin integration:** Applies `admin/hidden_movies.json` (hides from display) and `admin/staff_picks.json` (marks as staff picks)

### **Phase 5: User Display**
**What happens:** User visits the website and sees the beautiful movie wall.

**🌐 Frontend Files**
- **`index.html`:** Basic HTML structure, loads CSS and JavaScript
- **`assets/styles.css`:** Netflix-quality visual design - card layouts, animations, colors
- **`assets/app.js`:** Interactive engine - fetches data.json, renders cards, handles three-button watch UI

---

## **🔄 Daily Automation Loop**

**🔧 `daily_orchestrator.py`** - *The Daily Pipeline*
```bash
1. python3 generate_data.py --intake       # Intake: Add new theatrical releases to tracking database
                                           # → Updates movie_tracking.json

2. python3 generate_data.py --discover     # Discovery: Poll for provider availability
                                           # → When found: write minimal entry to data.json (IMMEDIATE)
                                           # → Writes metrics/newly_available.json with today's IDs

3. python3 generate_data.py               # Enrichment: Add RT, Wikipedia, trailers, watch links
                                           # → Reads metrics/newly_available.json (today's queue)
                                           # → ONE attempt per movie, overlays onto existing entries

4. git commit & push                       # Save changes (automated)
```

**Key behavior:** Movies appear in data.json during step 2 (discovery), NOT step 3 (enrichment). Enrichment enhances existing entries but never gates visibility.

**Automated via GitHub Actions:**
- Runs daily at 9 AM UTC
- Installs Playwright browsers (`playwright install chromium`)
- Executes full pipeline automatically
- Commits results to repository

**Local Daily Script (runs at 10 AM via launchd, AFTER CI completes):**
```
scripts/local_daily.sh
```
- **Step 1:** Pulls latest from GitHub (CI's data.json is authoritative)
- **Step 2:** Hosts new trailers — downloads from YouTube, uploads to B2 (`scripts/trailer_pipeline.py host`)
- **Step 3:** IMDb rating collection with Playwright (`scripts/imdb_backfill.py --limit 50`)

CI stamps YouTube URLs into data.json; the local script downloads and re-hosts them on Backblaze B2. The next CI run stamps the B2 URLs into data.json.

**Note:** Daily automation runs without admin approval by default. Optional admin review can be enabled when editorial curation is desired.

## **🏥 Current Health Model & Status Indicators**

The orchestrator provides comprehensive health monitoring with nuanced status reporting:

### **Run Status Indicators**
- 🟢 **GREEN (Completed Successfully):** All phases executed without failures or warnings
- 🟡 **YELLOW (Completed with Warnings):** Non-critical issues detected but core functionality working
- 🔴 **RED (Completed with Failures):** Errors detected in phases but pipeline continues with best-effort policy

### **Health Check Criteria**
The orchestrator evaluates these factors for overall health:

**Discovery Health Checks:**
- ✅ Metrics files exist (`metrics/discovery_run.json`, `metrics/intake_run.json`)
- ✅ Metrics are from current run (not stale artifacts from previous runs)
- ✅ Discovery polled > 0 movies (TMDB API functional)
- ✅ Operation type matches expected phase (`discover_availability`, `intake_premieres`)

**Data Quality Monitoring:**
- ✅ JSON structure validation and file size checks
- ✅ Minimum movie count thresholds
- ✅ Provider coverage validation for recent movies
- ✅ Watch link quality assessment (real links vs search URLs)

**Stall Detection:**
- ⚠️ 3-day consecutive periods with zero transitions detected as potential system stalls
- 📊 Stall state persisted to `metrics/stall_state.json` for external monitoring

**Best-Effort Policy:**
The orchestrator records all failures and warnings in `metrics/run_diagnostics.json` but continues execution. Only hard crashes (lock conflicts) result in non-zero exit codes.

---

## **🎯 Why This Architecture Works**

1. **No Data Loss:** Old movies preserved in data_archive.json, recent movies in data.json
2. **Immediate Visibility:** Movies appear the moment they're discovered, not after enrichment
3. **Graceful Degradation:** Enrichment failures don't hide movies - they just have less metadata
4. **Simple Mental Model:** Discovery adds, enrichment enhances, nothing deletes
5. **Speed:** Website loads fast (only reads 1 JSON file)
6. **Reliability:** Links verified via multi-tier fallbacks (overrides → cache → API → scraper → null)
7. **Scalability:** Can track 15,000+ movies, display ~670 most recent
8. **Automation:** Runs itself daily, commits changes to git
9. **Editorial Control:** Admin panel allows curation and manual fixes

**The Result:** An ongoing database of digital release dates that no one else tracks, displayed as a professional movie wall that updates itself daily.