# Watch Link Architecture

How NRW finds clickable "Watch on Amazon / Apple TV / Netflix" links for each movie.

## Two Separate Jobs

**Discovery** (daily, TMDB only): Answers "is this movie available yet?"
- Checks TMDB watch/providers endpoint → returns provider **names** only (no links)
- Also: TMDB Type 4 digital release date (co-equal signal, checked first)
- Output: movie transitions from `tracking` → `available`, provider names saved

**Enrichment** (after discovery): Answers "where exactly can you watch it?"
- Uses the waterfall below to find actual deep links (Amazon product pages, Apple TV pages, etc.)

## Watch Link Waterfall (enrichment.py)

Priority order — first match wins:

| Tier | Source | What It Returns | When Used |
|------|--------|-----------------|-----------|
| 1 | **Manual watch links** (`movie_tracking.json`) | Full links | Hand-set by curator |
| 2 | **Overrides** (`overrides/watch_links_overrides.json`) | Full links | Admin quick-fix file |
| 3 | **Cache** (`cache/watch_links_cache.json`) | Full links | Results from previous enrichment runs |
| 4 | **JustWatch API** | Deep links + prices + provider names | **PRIMARY automated source** |
| 5 | **VOD scraper** (Playwright: Amazon + Apple TV) | Deep links only | **Backup** — only if JustWatch fails |
| 6 | **TMDB provider names** | Names only, `link: null` | Last resort — shows "on Amazon" with no URL |

### Tier 4: JustWatch API (primary)
- Source: JustWatch GraphQL API (`pipeline/justwatch.py`)
- Returns actual product URLs (e.g., `amazon.com/gp/video/detail/B0ABC...`) with prices
- Confidence matching prevents linking to the wrong movie (`min_confidence` in config)
- Config: `justwatch_verification.enabled`, `justwatch_verification.min_confidence`

### Tier 5: VOD Scraper (backup)
- Source: Playwright headless browser (`streaming_platform_scraper.py`)
- Scrapes Amazon.com and Apple TV search pages to find deep links
- Only runs when JustWatch returned nothing
- "Speculative scraping" tries Amazon/Apple even when TMDB doesn't list them as providers
- Config: `vod_scraper.enabled`, `vod_scraper.speculative_scraping`, `vod_scraper.per_movie_timeout`

## What Is NOT Part of Watch Links

**YouTube / Trailers** — completely separate pipeline:
- Trailer discovery (TMDB → YouTube → Gemini search) → stored in `links.trailer`
- Trailer hosting (YouTube → Backblaze B2 MP4) → stored in `links.trailer_hosted`
- See `docs/features/TRAILER_HOSTING.md`

## Config Controls

```yaml
# Tier 4: JustWatch
justwatch_verification:
  enabled: true
  min_confidence: 'close_year'    # Rejects low-confidence title matches
  rate_limit: 0.5                 # Seconds between API calls

# Tier 5: VOD Scraper
vod_scraper:
  enabled: true
  speculative_scraping: true      # Try Amazon/Apple even without TMDB data
  per_movie_timeout: 90           # Hard cap per movie (seconds)
  timeout: 10                     # Page load timeout
  max_retries: 2
```

## Troubleshooting Watch Links

If a movie has no watch links, check in waterfall order:
1. Is JustWatch finding the movie? Check confidence level in enrichment logs
2. Is the VOD scraper timing out? Check for `VOD scraping timed out` warnings
3. Is the movie genuinely not available for digital purchase yet?
4. Manual fix: add links to `movie_tracking.json` or `overrides/watch_links_overrides.json`

## Source Code
- Waterfall orchestration: `pipeline/enrichment.py` → `get_watch_links()`
- JustWatch API: `pipeline/justwatch.py` → `verify_availability()`
- VOD scraper: `streaming_platform_scraper.py`
- Discovery: `pipeline/generator.py` → discovery loop (inside `generate()`, ~line 830+)
