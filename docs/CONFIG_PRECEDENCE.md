# Config & Override Files — What Reads What, and Which One Wins

Every claim below was verified against loading code on 2026-07-02 (file:line cited).
If you change how a config file is consumed, update this doc.

## The one rule to remember

**`admin/overrides.json` is applied LAST in display generation** (pipeline/display.py:749-760).
Whatever it sets (genres_add/genres_remove/field sets, incl. `is_slop`) beats every
automatic rule upstream. When in doubt, that's the file a manual correction belongs in.

## Precedence chains (verified)

- **Watch links (enrichment)**: manual tracking → `overrides/watch_links_overrides.json` →
  cache → JustWatch → scrapers (pipeline/enrichment.py:114-228).
- **Restoration flag (display)**: `admin/reissue_labels.json` (manual label wins) →
  `admin/restorations.json` (manual ID list) → auto-detect using
  `admin/restoration_config.json` thresholds (display.py:580-598).
- **Pre-order flag (display)**: `preorder_overrides` in config.yaml (true forces, false removes) →
  tracking-DB recovery → detection (display.py:498-524).
- **Categories (display)**: `admin/category_overrides.json` beats auto-categorization
  (display.py:726-738), which is configured by `admin/category_config.json` +
  `admin/distributor_sources.json`.
- **Selects**: `admin/staff_picks.json` is read first; `admin/featured_movies.json` is a
  backwards-compat fallback only (display.py:351-357). The pipeline stamps
  `filters.is_staff_pick` into data.json (display.py:553-561), so clients don't need the list.

## Full map

| File | Loaded by | Phase | Notes |
|---|---|---|---|
| `config.yaml` | generator.py:118-132 | all phases | The only YAML config; includes `preorder_overrides`, `screening_names`, `slop_classifier` weights, scraper settings |
| `admin/overrides.json` | display.py:396-401 | display | **Applied last — wins over everything** |
| `admin/staff_picks.json` | display.py:351-353 | display | Selects list (string IDs) |
| `admin/featured_movies.json` | display.py:354-357 | display | Legacy fallback for staff_picks only |
| `admin/category_config.json` | display.py:361-363 | display | Category definitions |
| `admin/category_overrides.json` | display.py:385-387 | display | Per-movie category, beats auto |
| `admin/restoration_config.json` | display.py:367-369 | display | Auto-detect thresholds |
| `admin/restorations.json` | display.py:373-375 | display | Manual restoration IDs |
| `admin/reissue_labels.json` | display.py:379-381 | display | Manual reissue labels, beats auto-detect |
| `admin/ordering.json` | display.py:420-424 | display | Manual sort order beats date sort |
| `admin/festival_films.json` | slop_classifier.py `_festival_films()` | enrichment | -1 slop signal; auto-fed by scripts/detect_festivals.py |
| `admin/curate_reviewed.json` | scripts/curate_list.py | curation | Review-state tracker (not an override) |
| `admin/distributor_sources.json` | scripts/build_distributor_lookup.py:403 | display (via lookup cache) | Distributor seeding |
| `admin/reissue_candidates.json` | written by intake.py:1098-1105; read by confirm_reissue.py | curation | Reissue confirmation queue |
| `overrides/watch_links_overrides.json` | generator.py:80 → enrichment.py:103-112 | enrichment | Beats JustWatch/scrapers/cache |
| `overrides/rt_overrides.json` | generator.py:79 | enrichment | Manual RT score/link |
| `overrides/trailer_overrides.json` | generator.py:81 | enrichment | Manual trailer URLs |
| `overrides/trailer_suppress.json` | generator.py:83 | enrichment | "NO TRAILER" list, stops re-search |
| `overrides/wikipedia_overrides.json` | generator.py:78 | enrichment | Manual Wikipedia URLs |
| `constants.py` | imported | enrichment | Scraper timeouts/retries; per-scraper config.yaml sections override (constants.py:44-55) |

## Dead files (loaded by nothing — candidates for deletion)

- `admin/approval.json` — never loaded.
- `admin/movie_reviews.json` — never loaded.
- `admin/watch_link_overrides.json` — never loaded, and **dangerously named**: the active
  file is `overrides/watch_links_overrides.json` (note `links` plural + different folder).
  Editing the dead one silently does nothing.

## Slop classifier tuning

Tier-3 score weights and the threshold live in the `slop_classifier:` section of
config.yaml (defaults are also compiled into scripts/slop_classifier.py, so a missing
section changes nothing). Tier 1/2 studio + streaming lists remain in
slop_classifier.py; the prestige-festival regexes live in scripts/detect_festivals.py.
