# **NRW Data Workflow - Complete Overview**

**Last Updated:** 2026-04-20

---

## **Terminology**

- **Platform** = streaming/VOD service (Netflix, Amazon, Apple TV). Where users watch content.
- **Source** = where pipeline data comes from. TMDB = discovery + metadata. JustWatch = watch links. These are data sources, not platforms.
- **Device** = distribution target (Desktop, Mobile, iOS, tvOS, Android TV, Roku, Newsletter). See `docs/DEVICE_REGISTRY.md`.

## **What This System Does**

NRW tracks when movies become digitally available (streaming, rental, purchase) and displays them on a curated wall with trailers, scores, and watch links.

### Design Principle
Discovery uses a **wide net**. If TMDB providers OR Type 4 digital dates indicate a movie is available, it transitions to the wall. Curation happens after discovery, not before.

### Core Problem
No API provides "when" a movie became available — only "what" is currently available. NRW polls daily and detects transitions.

### Pipeline Overview
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

---

## **The Data Journey**

### **Phase 1: Intake & Discovery Overview**
**What happens:** We intake new movies to track AND discover when tracked movies become available for digital (streaming/VOD (rental/purchase)).

**`generate_data.py --intake`** - *Intake: New Premiere Ingestion*
- **Intake:** Searches TMDB API for movies released in past 7 days (festival, limited theatrical, theatrical, direct to streaming, etc.)
- **Adds to database:** New movies get status = "tracking", digital_date = null

**`generate_data.py --discover`** - *Discovery: Detecting Digital Transitions*
- **Monitoring:** Checks ALL movies in database with status = "tracking" for digital availability
- **Two co-equal discovery signals:**
  1. **TMDB /watch/providers** — Detects streaming providers (Netflix, Disney+, etc.) and rent/buy availability (Amazon, Apple TV, etc.)
  2. **TMDB Type 4 digital release dates** — Detects when a movie's digital release date has arrived. Many movies have Type 4 dates before provider lists are populated. Both signals are co-equal; neither is primary or fallback.
- **Transition:** When either signal fires, sets `digital_date` = today (or Type 4 date), status = "available"
- **Pre-order detection:** Movies with JustWatch buy-only offers, or discovered movies that fail JW pre-check but are confirmed as pre-orders by Gemini, are flagged and displayed on the wall until released
- **JustWatch:** NOT used in discovery. JustWatch provides actual rent/buy deep links (Amazon/Apple TV URLs) during enrichment, not during discovery.
- **State file:** Writes list of newly available movie IDs to `metrics/newly_available.json`

**`movie_tracking.json`** - *The Master Database*
- **What it is:** Complete database of all movies we're monitoring (~15,000+ movies)
- **Contains:** Movie details, tracking status ("tracking" vs "available"), provider info
- **Example:** `{"1404864": {"title": "Inspector Zende", "status": "tracking", "digital_date": null}}`

### **Phase 2: Database Enrichment & Link Resolution**
**What happens:** We take movies that JUST BECAME digitally available (from today's discovery) and add rich metadata - trailers, Wikipedia pages, RT scores, watch links.

**`generate_data.py`** - *The Enrichment Overlay*
- **Reads today's queue:** `metrics/newly_available.json` contains movie IDs that transitioned TODAY
- **Self-healing retries:** If enrichment fails or is incomplete, movies are automatically retried on subsequent runs (up to 3 attempts). Newly available movies are always prioritized over catch-up retries.
- **Batch cap:** Maximum 100 movies per enrichment run (new arrivals + catch-up combined)
- **Overlay model:** Updates EXISTING entries in data.json (never creates new entries)
- **Performance:** 95%+ cost reduction by only enriching new arrivals (1-10 per day)
- **Link resolution:** Multi-tier waterfall: manual → overrides → cache → JustWatch API → VOD scraper → null (see `docs/features/WATCH_LINK_ARCHITECTURE.md`)

**Enrichment Step 0: JustWatch Pre-Verification (FIRST)**

Before any expensive enrichment (Wikipedia, RT, trailers), each newly discovered movie is verified against JustWatch:
- JustWatch is queried for the movie's current availability
- If the movie has valid offers on our target platforms (Amazon, Apple TV, YouTube) → proceed with full enrichment
- If the movie is only available on excluded services (Google Play, fuboTV, Philo, etc.) → **reverted to tracking** with reason stored in `_jw_revert_reason`
- If JustWatch finds nothing → **reverted to tracking** with reason `"justwatch_no_match"`
- On pre-check error → proceed with enrichment anyway (fail open, not fail closed)

This is the correct place for `excluded_services` filtering: enrichment phase verification, not discovery.

**Link Resolution System** - *Multi-Tier Intelligent Lookup*

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

**`data.json`** - *The Website Database* (Updated 2025-12-29)
- **Rolling window:** Movies are ADDED during discovery. After 90 days, auto-archived to data_archive.json
- **Two write sources:**
  1. **Discovery phase:** Writes minimal entry immediately when movie transitions to available
  2. **Enrichment phase:** Overlays rich data onto existing entries
- **Structure:** Movies include basic info (title, date, poster) plus enriched data when available (synopsis, director, cast, trailer, RT link, Wikipedia link, watch_links)
- **Reliability:** All discovered movies appear; enrichment enhances but never gates visibility
- **Admin integration:** Applies `admin/staff_picks.json` (marks as staff picks) and `admin/category_overrides.json` (category toggles, hide/show)

### **Phase 5: User Display**
**What happens:** Frontend renders data.json as the movie wall.

**Frontend Files:**
- `index.html` → loads `assets/styles.css` + `assets/app.js`
- `app.js` fetches data.json, renders cards, handles watch UI

---

## **Daily Automation Loop**

**`daily_orchestrator.py`** - *The Daily Pipeline*
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

## **Health Model & Status Indicators**

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

## **Pipeline Safeguards**

Several automated safeguards protect data quality. If you're debugging "why did a movie disappear from the wall?" — check these first.

### Content Blocklist (Intake Phase)
Non-film content (wrestling events, sports broadcasts) is blocked at intake via two mechanisms in `config.yaml`:
- **`blocked_companies`**: TMDB production company IDs (WWE, AEW, NJPW, etc.) excluded at the TMDB API level via `without_companies` parameter
- **`blocked_title_keywords`**: Title-based filter catches anything that slips past company blocking (e.g., "WrestleMania", "ISU Grand Prix")
- Blocked items are counted in `intake_stats['blocked_by_filter']` and logged when running with debug

### Service Exclusion List (Enrichment Phase — NOT Discovery)
`config.yaml > excluded_services` prevents unwanted VOD/streaming services from appearing in watch links. Current exclusions: fuboTV, Philo, Sun Nxt, Google Play Movies, Google Play, Shahid VIP, Viki. Always check `config.yaml` for the authoritative list.

**Important:** This filter is applied during enrichment (via JustWatch pre-verification), NOT during discovery. Discovery is binary — any TMDB provider signal means "discovered." If a movie is only available on excluded services, it gets discovered, then JustWatch pre-check reverts it to tracking with a note (see above). This prevents movies from being silently stuck in tracking because their only TMDB provider was an excluded service like fuboTV.

### False Positive Revert (Two stages)

**Stage 1 — JustWatch Pre-Verification (Pre-Enrichment, proactive):**
Before full enrichment, a JustWatch pre-check verifies each newly-discovered movie is available on our target platforms. If not, the movie is immediately reverted to tracking with a specific reason stored in `_jw_revert_reason` and `_jw_reverted_at`. The launch report shows these reverted movies so you know: "discovered, but only on excluded services — sent back to tracking."

**Stage 2 — Zero-Link Revert (Post-Enrichment, safety net):**
After enrichment, movies with `_enrichment_status=completed` but **zero watch links** (no VOD and no streaming) are automatically reverted to `status=tracking`. This catches false-positive discoveries — movies that passed JustWatch pre-check but still ended up with no usable deeplinks (e.g., movie exists on Plex but JustWatch has no purchase/rental/streaming URLs for it).

How it works:
- Sets `_jw_revert_reason: 'zero_watch_links'` in tracking and `_enrichment_status: 'reverted'` in data.json
- Increments `_jw_revert_count` in tracking
- `purge_removed_movies()` removes the movie from data.json (the wall) in the same pipeline run
- Discovery can re-find the movie tomorrow — if links appear, it stays; if still zero, it reverts again
- No max revert limit: a movie with zero links should never be on the wall
- Exceptions: pre-orders with future dates, virtual screenings, manually-added movies, and movies with watch link overrides are NOT reverted
- The wall health report shows reverted movies for 3 days, then stops alerting (pipeline keeps retrying silently)

---

## **Key Principles**

- Discovery adds, enrichment enhances, nothing deletes
- Enrichment failures don't hide movies — they just have less metadata
- data.json is append-only with 90-day auto-archive
- Links resolve via multi-tier fallback (overrides → cache → API → scraper → null)