# Method Call Replacements Reference Card

This document lists all method calls that will be replaced during pipeline extraction migration.

## Phase 1: Storage Service (23 occurrences)

### File Operations
```python
# Before                              # After
self.load_cache(...)          →      self.storage.load_cache(...)
self.save_cache(...)          →      self.storage.save_cache(...)
self.load_json(...)           →      self.storage.load_json(...)
```

### Atomic Operations
```python
# Before                              # After
self.atomic_write_json(...)   →      self.storage.atomic_write_json(...)
self.atomic_move_to_archive(...)  →  self.storage.atomic_move_to_archive(...)
```

### Database Operations
```python
# Before                              # After
self.load_all_movies()        →      self.storage.load_all_movies()
```

## Phase 2: Validation Service (8 occurrences)

### Schema Validation
```python
# Before                                    # After
self.validate_watch_links_schema(...)  →  self.validator.validate_watch_links_schema(...)
self.validate_data_json_schema(...)    →  self.validator.validate_data_json_schema(...)
```

### Consistency Validation
```python
# DELETED 2025-12-05 - was causing loop bug
# self.validate_enrichment_consistency() - no longer exists
```

## Phase 3: Enrichment Service (30+ occurrences)

### Watch Link Discovery
```python
# Before                              # After
self.get_watch_links(...)      →     self.enrichment.get_watch_links(...)
```

### Scraper Integration
```python
# Before                                    # After
self._try_agent_scraper(...)          →   self.enrichment.try_agent_scraper(...)
self._try_platform_scraper(...)       →   self.enrichment.try_platform_scraper(...)
```

### Platform Scraper Utilities
```python
# Before                                          # After
self._get_platform_deep_link_with_cache(...)  → self.enrichment.get_platform_deep_link_with_cache(...)
self._enforce_platform_scraper_rate_limit()   → self.enrichment.enforce_platform_scraper_rate_limit()
```

### URL Normalization
```python
# Before                                      # After
self._normalize_watch_links_urls(...)   →   self.enrichment.normalize_watch_links_urls(...)
self._migrate_legacy_cache_format(...)  →   self.enrichment.migrate_legacy_cache_format(...)
```

### Affiliate Tagging
```python
# Before                                # After
self.append_affiliate_tag(...)    →   self.enrichment.append_affiliate_tag(...)
```

### Service Validation
```python
# Before                                           # After
self.is_excluded_service(...)                 →  self.enrichment.is_excluded_service(...)
self.is_actual_amazon_service(...)            →  self.enrichment.is_actual_amazon_service(...)
self.is_actual_apple_service(...)             →  self.enrichment.is_actual_apple_service(...)
self.validate_service_link_consistency(...)   →  self.enrichment.validate_service_link_consistency(...)
```

## Total Replacements by Phase

| Phase | Service | Method Calls | Methods Deleted | Lines Deleted |
|-------|---------|--------------|-----------------|---------------|
| 1     | Storage | 23           | 5               | 135           |
| 2     | Validation | 8         | 3               | 281           |
| 3     | Enrichment | 30+       | 13              | 962           |
| **Total** | **3 services** | **61+** | **21** | **~1,378** |

## Methods NOT Being Replaced

These methods remain in generate_data.py:

### Configuration & Setup
- `load_config()`
- `_init_rt_scraper()`

### Metadata Discovery
- `scrape_rt_score(title, year)`
- `find_wikipedia_url(title, year, imdb_id, movie_id)`
- `find_trailer_url(movie_details)`
- `find_rt_url(title, year, imdb_id)`
- `get_movie_details(movie_id)`

### Utilities
- `simplify_provider_name(provider_name)`
- `generate_google_search_fallback(title, year, service)`
- `get_excluded_services()`

### Validation & Safety
- `perform_startup_consistency_check()`
- `validate_enrichment_changes(new_db, filepath)`

### Discovery Operations
- `discover_new_premieres(...)`
- `check_tracking_movies(...)`
- `save_daily_metrics(...)`
- `get_3_day_baseline()`
- `_load_discovery_state(...)`
- `_update_discovery_state(...)`
- `_write_discovery_metrics(...)`

### Generation Operations
- `generate(...)`  # Main orchestration method
- All other generation-related methods

## Quick Verification Commands

After migration, verify replacements:

```bash
# Check no old method calls remain (should return 0)
grep -c "self\.load_cache(" generate_data.py
grep -c "self\.validate_watch_links_schema(" generate_data.py
grep -c "self\.get_watch_links(" generate_data.py

# Check new service calls exist (should return counts)
grep -c "self\.storage\." generate_data.py
grep -c "self\.validator\." generate_data.py
grep -c "self\.enrichment\." generate_data.py
```

## Import Verification

After migration, verify imports are present:

```bash
grep "from pipeline.storage import StorageService" generate_data.py
grep "from pipeline.validation import ValidationService" generate_data.py
grep "from pipeline.enrichment import EnrichmentService" generate_data.py
```

## Service Initialization Verification

After migration, verify services are initialized:

```bash
grep "self.storage = StorageService" generate_data.py
grep "self.validator = ValidationService" generate_data.py
grep "self.enrichment = EnrichmentService" generate_data.py
```
