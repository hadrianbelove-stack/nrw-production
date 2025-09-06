# complete_project_context.md

## Project: New Release Wall (NRW)

### Purpose
A "Blockbuster Wall for the streaming age" — curated wall of newly released digital movies (US streaming/TV).  
Core features:
- Weekly curation (approved vs unapproved)
- Provider pills (Netflix, Amazon, Apple TV, etc.)
- Posters, RT scores, links
- VHS-style flip-card UI

### Current Status (as of 2025-08-26)
- **Data**
  - 186 approved movies in `assets/data.json`
  - 41 with streaming providers
  - TMDB poster cache populated (~95%)
  - RT cache initialized (null values)
  - Trailer cache empty
- **Frontend**
  - Renderer: rebuilt (`render_approved.js`) with guard, poster resolver, provider chips, RT badges, filtering
  - Template: clean `#cards` container, assets in `<head>`, deferred JS
  - Styling: VHS flip-card CSS + modern overrides (grid, 220x330 cards)
- **Server**
  - Port 3001 locked
  - Offline mode active
- **Known Issues**
  - Posters not displaying in UI though valid URLs exist
  - Approved dataset integration may be inconsistent between Aug 20 baseline and current JS-only build

### Next Steps
1. Compare Aug 20 site.html vs current index.html
2. Choose patch vs rebuild
3. Debug poster rendering pipeline
4. Confirm rendering of 186 approved / 41 provider-active movies

---

⚡ **Handoff State**
- All three docs aligned (Charter, Log, Context).
- Offline mode stable, cache prepared, renderer functional but poster display bug persists.

## Canonical Data Flow and Rendering
1) Track titles daily; detect digital via provider first-seen.
2) Approve via curated_selections.json.
3) Normalize to output/data.json and output/data_core.json.
4) Cache TMDB posters/trailers/RT for offline safety.
5) Client-only render via render_approved.js into <div id="cards"> with style_overrides.css.
6) No server-side Jinja loops remain.

## End-of-Session Policy
- Always update Charter, Log, and Context.
- Always package NRW_SYNC_YYYYMMDD-HHMM.zip and NRW_SYNC_YYYYMMDD-HHMM.sha256.

## Canonical Data Flow and Rendering
1) Track titles daily; detect digital via provider first-seen.
2) Approve via curated_selections.json.
3) Normalize to output/data.json and output/data_core.json.
4) Cache TMDB posters/trailers/RT for offline safety.
5) Client-only render via render_approved.js into <div id="cards"> with style_overrides.css.
6) No server-side Jinja loops remain.

## End-of-Session Policy
- Always update Charter, Log, and Context.
- Always package NRW_SYNC_YYYYMMDD-HHMM.zip and NRW_SYNC_YYYYMMDD-HHMM.sha256.

## Mode Policy
- Offline mode: `offline: true` in config.yaml or `NRW_OFFLINE=1`. Uses cached data only. Safe for styling, packaging, and local testing. No API calls required.
- Online mode: `offline: false` and valid TMDB credentials in env (`TMDB_BEARER` preferred, or `TMDB_API_KEY`). Required for fetching new data and refreshing caches.
- Every executable block must declare mode per RULE-018. Do not propose online-only steps when offline is active.
- Switch helpers:
  - `./nrw-mode.sh` → report current mode.
  - `./nrw-set-mode.sh offline|online` → set mode explicitly (updates config.yaml).

## Snapshot Workflow
- Start of session: run `./nrw-session-open.sh` → upload the printed snapshot `.zip` and `.manifest.txt`.
- Long sessions: run `./nrw-session-refresh.sh` about every 1–2 hours or after major edits; upload the new snapshot.
- Assistants must base code suggestions on the most recent snapshot or the unpacked NRW_SYNC, per RULE-022 and RULE-023.

## Handoff (Flat Working Set)

- **Primary artifact:** `WORKING_SET_HANDOFF_<UTC-YYYYMMDD-HHMMSSZ>/` — files only, no directories.
- **Upload to assistant:** select all files inside the flat handoff folder and upload; do not upload folders or zips.
- **Required files:** `index.handoff.html`, `index.html`, `_ASSET_MAP.txt`, `_MANIFEST.txt`, `PROJECT_CHARTER_<timestamp>.md`, `PROJECT_LOG.md`, `complete_project_context.md`, and minimal sources/data/scripts.
- **Optional archive:** a structured `NRW_WORKINGSET_<UTC>.zip` may be stored in `bundle_history/` for audit only.

### Deprecated (Legacy)
- NRW_SYNC `<timestamp>.zip` + manifest + sha256 are retired. Use the flat handoff instead.
