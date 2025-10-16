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

**📄 `data/movie_tracking.json`** - *The Master Database* 
- **What it is:** Complete database of all movies we're monitoring (count always changing)
- **Why:** Single source of truth for all movie data and tracking status  
- **Contains:** Movie details, tracking status ("tracking" vs "available"), provider info
- **Example:** `{"1404864": {"title": "Inspector Zende", "status": "tracking", "digital_date": null}}`
- **Updated by:** Daily command (adds new movies and updates availability)

### **Phase 2: Database Enrichment**
**What happens:** We take movies that became digitally available and fill out ALL their details - cast, director, synopsis, posters, trailers, Wikipedia pages, review links, country, studio, runtime, genres.

**🔧 `generate_data.py`** - *The Complete Data Enricher*
- **What it does:** Takes recently available movies (90 days) and creates full movie profiles
- **Incremental mode (default):** Only processes NEW movies not already in data.json, then ADDS them to existing list (takes seconds)
- **Full regeneration mode:** Rebuilds entire data.json from scratch (takes 30+ minutes, use only when needed)
- **TMDB API calls:** Fetches complete movie details including cast, crew, synopsis, posters, genres, studio, runtime, country
- **Link resolution:** Finds working Wikipedia pages, trailers, and review links
- **Why:** Users need complete movie information to decide what to watch

**📂 Link Resolution Files** - *The Smart Lookup System*
- **`overrides/wikipedia_overrides.json`** - Manual fixes for wrong links
- **`cache/wikipedia_cache.json`** - Remembers successful finds (saves time)
- **`scripts/wikidata_scraper.py`** - Uses IMDb→Wikidata→Wikipedia chain
- **`scripts/wikipedia_scraper.py`** - Selenium browser automation (last resort)
- **`missing_wikipedia.json`** - Logs failures for manual review

**What gets filled out:**
- **Basic info:** Title, year, synopsis, poster URL, IMDb ID
- **People:** Director, top 2 cast members
- **Metadata:** Genres, studio/production company, runtime, country of origin
- **Links:** Trailer (from TMDB videos), Rotten Tomatoes URL, Wikipedia page

**Why this complexity?** 
- Simple approach: Generate URLs like "Inspector_Zende_(film)" → 50% are broken
- Smart approach: Verify URLs exist, use multiple methods → 80% success rate

### **Phase 3: Editorial Approval**
**What happens:** The admin panel lets you approve titles for the wall, feature them, and edit/fix missing information.

**🔧 Admin Panel Interface**
- **Review queue:** Shows enriched movies awaiting approval
- **Approve/reject:** Choose which movies appear on the public wall
- **Featured flags:** Mark special movies to highlight
- **Manual edits:** Fix synopsis, fill missing Wikipedia links, correct cast/director info
- **Quality control:** Ensure all displayed movies meet editorial standards
- **Why:** Not every digitally available movie should be featured - editorial curation creates a better user experience

### **Phase 4: Display Generation**  
**What happens:** We create the final JSON file that the website reads, applying admin decisions to hide/feature movies.

**🔧 `generate_data.py` with Admin Integration**
- **Data enrichment:** Creates complete movie profiles with all metadata
- **Admin filtering:** Applies decisions from `admin/hidden_movies.json` and `admin/featured_movies.json`  
- **Hidden movies:** Completely removed from public display
- **Featured movies:** Marked with `"featured": true` flag for special highlighting
- **Quality assurance:** Only approved, curated content reaches users

**📄 `data.json`** - *The Website Menu*
- **What it is:** Clean, final dataset of all recent movies with verified data
- **Why:** Website needs fast loading, verified data, no broken links
- **Structure:** Each movie has poster, synopsis, director, cast, trailer, RT link, Wikipedia link
- **Key rule:** Only verified links included - no guessing allowed
- **Display:** Endless scroll backwards week after week (may implement pagination like 50 per load for performance)

### **Phase 5: User Display**
**What happens:** User visits the website and sees the beautiful movie wall.

**🌐 `index.html`** - *The Front Door*
- **What it does:** Basic HTML structure, loads the CSS and JavaScript
- **Why:** Entry point that browsers can understand

**🎨 `assets/styles.css`** - *The Visual Designer*
- **What it does:** Makes everything look beautiful - card layouts, animations, colors
- **Why:** Raw HTML looks terrible - CSS makes it Netflix-quality

**⚡ `assets/app.js`** - *The Interactive Engine*
- **What it does:** Fetches data.json, renders movie cards, handles flipping animations
- **Why:** Modern websites are interactive - this brings the data to life
- **Smart feature:** `wikiUrlFor()` function provides safe fallbacks if Wikipedia links fail

---

## **🔄 Daily Automation Loop**

**🔧 `daily_update.sh`** - *The Orchestra Conductor*
```bash
1. python movie_tracker.py daily     # Discover new movies + monitor all existing for availability changes
2. python generate_data.py           # Create enriched display data with links
3. git commit & push                 # Save changes
```

**🔍 `ops/health_check.py`** - *The Quality Inspector*
- **What it does:** Checks data.json has correct structure, no broken links
- **Why:** Catches problems before users see them

---

## **📋 File Organization Logic**

**Why this folder structure?**
```
/index.html, /data.json, /assets/     ← Runtime files (what users see)
/scripts/                            ← Data generation tools
/data/                               ← Source databases  
/cache/                              ← Speed optimization files
/ops/                                ← Operational tools
/museum_legacy/                      ← Old experiments (ignored)
```

**The Key Insight:** Separate "what users see" from "how we make it"
- Users never see the tracking database or scrapers
- Website only needs 4 files: index.html, data.json, app.js, styles.css
- Everything else is "behind the scenes" machinery

---

## **🎯 Why This Architecture Works**

1. **Speed:** Website loads fast (only reads 1 small JSON file)
2. **Reliability:** Links are verified before going live
3. **Maintainability:** Each script has one clear job
4. **Scalability:** Can track 1000+ movies, but only show 30 newest
5. **User Experience:** No broken links, no loading delays
6. **Automation:** Runs itself daily, commits changes to git

**The Result:** A professional movie discovery website that updates itself and never shows broken links.