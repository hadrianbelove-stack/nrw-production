# Admin Panel Specification

**Spec-Moved-From:** PROJECT_CHARTER.md
**Amendment:** AMENDMENT-045
**Date:** 2025-10-19 to 2025-10-20
**Maintainer:** Development Team

## Overview

The admin panel is a comprehensive QA database editor for post-publication curation. Movies are automatically visible when discovered by automation unless explicitly hidden. The admin panel allows curators to hide unwanted movies, feature important releases, and fix incomplete data through inline editing.

## Role - Post-Publication Curation

The admin panel is designed for **post-publication curation** where movies are refined after they appear on the public site. This approach reduces friction compared to pre-publication approval workflows.

### Data Flow with Post-Publication Curation

```
Daily Scraper → movie_tracking.json → data.json → Public Site
                (all discovered)      (filtered)   (visitors)
                                         ↓
                                   ADMIN PANEL (post-publication curation)
                                   - Hide unwanted movies
                                   - Feature important releases
                                   - Fix incomplete data
```

### Default Visibility Model

Movies are **visible by default** (no approval required). The `apply_admin_overrides()` method in `generate_data.py` (lines 2197-2228) filters out movies in `admin/hidden_movies.json` during data generation.

**Rationale:** Publish-first model reduces friction, allows rapid discovery, and trusts automation with manual refinement.

## Inline Database Editing Capabilities

All movie fields are directly editable in the UI:

### Editable Fields
- **Digital release date** (date picker)
- **RT score** (0-100 number input)
- **RT link** (URL with test button 🔗)
- **Trailer link** (URL with play button ▶️)
- **Director** (text input)
- **Country** (text input)
- **Synopsis** (textarea)
- **Poster URL** (URL with TMDB button 🎬)
- **Watch links** - streaming/vod (service + URL pairs)

### Save Mechanism
- Single "💾 Save All Changes" button per movie card
- Changes save directly to `movie_tracking.json` with `manual_*` flags
- Auto-regenerates `data.json` after save

## Missing Data Detection System

### "⚠️ Missing Data" Filter
- Shows all incomplete movies at once
- Badge displays count of movies needing attention (e.g., "93")
- Incomplete movies have:
  - Red left border
  - "⚠️ INCOMPLETE" badge in top-right corner
  - Red background on missing fields
  - Pink box listing exactly what's missing (RT Score, Trailer, Poster, Director, Country)
- Allows rapid quality control: click filter → scan flagged movies → fix or hide

## Manual Correction Tracking

All edits saved to `movie_tracking.json` with flags:
- `manually_corrected: true` (overall flag)
- `manual_rt_score: true`, `manual_rt_link: true`, etc. (field-specific flags)
- `last_manual_edit: "2025-10-19T..."` (timestamp)

**Protection:** Flags protect manual edits from being overwritten by daily scraper. Separate from UI preferences (hidden/featured stay in admin/*.json files).

## YouTube Playlist Integration

### "📺 Create YouTube Playlist" Feature
- Button in admin panel header
- Custom date parameters: "Last X Days" OR "From Date → To Date"
- Manual control (no automation) with dry-run preview mode
- Privacy settings (public/unlisted/private)
- Calls `youtube_playlist_manager.py` with custom parameters
- See `docs/features/YOUTUBE_PLAYLIST_SETUP.md` for OAuth setup instructions

## Implementation Details

### File Structure
**File:** `admin.py` (Flask application on port 5556)

### Routes
- `/` - Main admin panel with inline editing UI
- `/update-movie-fields` - Saves all editable fields to movie_tracking.json
- `/create-youtube-playlist` - Creates YouTube playlists with custom dates
- `/toggle-hidden`, `/toggle-featured` - UI preference toggles
- `/regenerate` - Manual data.json regeneration trigger

### Authentication
HTTP Basic Auth (default: admin/changeme)

### Frontend
Embedded JavaScript with fetch API for AJAX operations

## Daily Curation Workflow

### Morning Routine
1. Open http://localhost:5556 (after automation has run)
2. Review new movies on public site to identify candidates for hiding/featuring
3. Click "⚠️ Missing Data (93)" to see incomplete movies
4. For each flagged movie:
   - Missing RT score only? → Wait (reviews coming)
   - Missing trailer/poster? → Check TMDB → Fix or Hide
   - Wrong director/country? → Edit field → Save
5. All fixed movies turn from RED to normal
6. Hidden movies removed from public site via regeneration

## Data Files

### Admin Override Files
- `admin/hidden_movies.json` - Movies hidden from public display
- `admin/featured_movies.json` - Movies highlighted as important releases
- `admin/movie_reviews.json` - Editorial reviews written by curator
- `admin/watch_link_overrides.json` - Manual watch link corrections

### Interaction with movie_tracking.json
- Manual edits save directly to main database
- Protected by `manual_*` flags from automation overwrites
- Regeneration applies admin preferences during data.json creation

## Quality Assurance Features

### Visual Indicators
- Red borders and badges make quality control efficient
- Missing data highlighted with red backgrounds
- Pink boxes list exactly what's missing
- Color coding: RED = incomplete, normal = complete

### Batch Operations
- "⚠️ Missing Data" filter shows all incomplete movies
- Single save button reduces cognitive load
- Bulk hide/feature operations

### Data Protection
- Manual corrections protected from automation overwrites
- Backup management for admin override files
- Atomic writes prevent data corruption

## Rationale

### Why Post-Publication Curation
- **Scrapers are imperfect** - APIs have gaps, platforms change, data is incomplete
- **Publish-first model** - Reduces manual bottleneck, allows rapid intake of new releases
- **Manual QA ensures quality** - Quality control through post-publication refinement

### Why Inline Editing
- **Efficiency** - Faster than editing JSON files manually
- **Visual indicators** - Red borders, badges make quality control efficient
- **Single save button** - Reduces cognitive load
- **Protected corrections** - Prevents automation from overwriting manual fixes

## Related Files

### Implementation
- `admin.py` (lines 1-1987) - Main Flask application
- `admin/templates/index.html` - Admin UI template
- `admin/static/js/admin.js` - Frontend JavaScript
- `admin/static/css/admin.css` - Admin panel styles

### Integration
- `generate_data.py` (lines 2197-2228) - apply_admin_overrides() method
- `youtube_playlist_manager.py` (lines 573-662) - Custom playlist creation

### Documentation
- `docs/features/YOUTUBE_PLAYLIST_SETUP.md` - OAuth setup guide
- `ADMIN_WORKFLOW.md` - Detailed curation procedures

## Related Amendments
- AMENDMENT-038 (Watchmode API) - Watch links system
- AMENDMENT-044 (Auth token management) - Authentication handling
- AMENDMENT-050 (Review System) - Editorial content integration