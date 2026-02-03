# External APIs & Rate Limits

**Source**: Extracted from SYSTEM_ARCHITECTURE.md (2026-02-02)

## TMDB (The Movie Database)
- **Sign up:** https://www.themoviedb.org/settings/api
- **Environment variable:** `TMDB_API_KEY`
- **Config fallback:** `api.tmdb_api_key` in config.yaml
- **Usage:** Movie metadata, posters, cast/crew information
- **Rate limit:** 40 requests per 10 seconds (handled automatically)

## JustWatch API (Primary Watch Links Source)
- **Type:** GraphQL API (unofficial, reverse-engineered)
- **Implementation:** `justwatch_client.py`
- **Usage:** Deep links to streaming platforms (Netflix, Amazon, HBO Max, etc.)
- **Authentication:** None required
- **Coverage:** 200+ streaming services, excellent for new releases
- **Rate Limit:** 1 request per second (self-imposed)

> **Note:** Watchmode API was deprecated in Dec 2024 due to quota/cost issues.

## OMDb API
- **Sign up:** http://www.omdbapi.com/apikey.aspx
- **Environment variable:** `OMDB_API_KEY`
- **Config fallback:** `api.omdb_api_key` in config.yaml
- **Usage:** IMDb ID fallback for Wikipedia/Wikidata lookup when TMDB doesn't have IMDb ID
- **Implementation:** `get_imdb_from_omdb()` method in `pipeline/generator.py`
- **Free Tier:** 1,000 requests/day

## Agent-Based Link Finding (No API Key Required)
- **Purpose:** Scrape direct watch links from streaming platforms when JustWatch API has no data
- **Platforms:** Netflix, Disney+, HBO Max, Hulu
- **Technology:** Playwright with headless Chrome
- **Rate Limiting:** 2-second minimum delay between scrapes
- **Cache:** `cache/agent_links_cache.json`
- **Usage:** Automatic fallback when JustWatch API returns no data
- **Optional:** Can be disabled by not initializing agent in `generate_data.py`
- **Terms of Service:** Web scraping may violate platform ToS; use responsibly
