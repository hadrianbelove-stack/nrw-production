# PROJECT_LOG.md

## 2025-08-26 — Session Summary

### Actions Completed
- **Charter Amendments Approved**
  - A3: Numbered step labels (7a, 7b, etc.) locked as standard.
  - A4: No assumptions — every step explicitly requires confirmation before proceeding.
  - A6: All code blocks must state run condition (`run now` vs `wait`).
  - A7: Removed vague phrases ("after it prints") — replaced with explicit sequencing.
  - A8: Optional steps must include pros/cons for decision-making.
  - A9: Every instruction batch includes a **⚡ To keep moving** summary.

- **System Configuration**
  - Port **3001** hard-locked for local server.
  - Offline mode set (`offline: true`, `fetch_tmdb/rt/trailers: false`).
  - Cache skeleton built with `.cache/rt/`, `.cache/tmdb/`, `.cache/trailers/`.
  - TMDB poster cache populated (~95% coverage, w500 image URLs).
  - RT cache and trailers cache initialized but not yet populated.

- **Renderer / Frontend**
  - Rebuilt `render_approved.js` with global guard, poster resolver, provider chips, RT badges, date filtering, and idempotent rendering.
  - Template cleanup: single `#cards` container, assets normalized.
  - Styling updated: VHS flip-card CSS preserved + modern overrides (grid, fixed 220x330px cards, provider chip styles).

### Issues / Observations
- Posters still not displaying in UI despite valid TMDB poster URLs.
- Duplicate `div` containers and script tags cleaned.
- Header consistent: **"The New Release Wall"**.
- Potential mismatch between Aug 20 baseline template and current JS-only renderer.

### Next Focus
1. Compare **Aug 20 site.html** vs current index.html.
2. Decide patch forward vs rebuild baseline.
3. Debug poster pipeline (`resolvePoster`, CSS sizing, container injection).
4. Validate renderer execution (cards counted, posters missing).

---

⚡ **To keep moving next session:**
- Upload latest sync (`NRW_SYNC_*.zip`).
- Compare Aug 20 baseline vs current index.
- Choose patch/rebuild strategy.
- Focus on poster rendering + layout polish.

## 2025-08-27 13:36
- RULE-010 enforced; preflight checks integrated.
- Structured rules (RULE-011..017) appended.
- Cache infra confirmed; offline mode acceptable for now (TMDB creds in config.yaml).
- Renderer and CSS stabilized; JS-only rendering is canonical.
- End-of-session bundling policy active.
- 20250827-1346: Handoff complete → tag golden-20250827-1346 (zip: NRW_SINGLE_HANDOFF_20250827-134640.zip)

## 2025-08-27 14:14
- Repo history rewritten to remove bundles and snapshots
- Pre-push guard installed (blocks NRW_SYNC and >50MB)
- Canonical branch: main (cleaned)
- 20250827-231948: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-231948.txt
- 20250827-232849: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-232849.txt
- 20250827-233050: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10352
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-233050.txt
- 20250827-233200: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10352
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250827-233200.txt
- 20250828-034817: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250828-034817.txt
- 20250828-035944: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=19455, data_core.json=2, index.html=10073
  Data: items=15; dups=0; bad_dates=0
  Report: output/nrw_audit_20250828-035944.txt
- 20250828-191116: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=2, data_core.json=2, index.html=10073
  Data: items=0; dups=0; bad_dates=0
  Report: output/nrw_audit_20250828-191116.txt
- 20250829-210506: Audit PASS
  Mode: offline
  Determinism: OK
  Sizes: data.json=2, data_core.json=2, index.html=9794
  Data: items=0; dups=0; bad_dates=0
  Report: output/nrw_audit_20250829-210506.txt
