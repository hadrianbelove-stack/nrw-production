# Pipeline Extraction Migration Plan

## Overview
This document details the complete reapplication of all three phases of pipeline extraction to `generate_data.py`.

## Current State
- **File**: `generate_data.py`
- **Current Lines**: 3,350
- **Status**: All three pipeline service files exist but integration was reverted

## Existing Pipeline Services

### 1. pipeline/storage.py (433 lines)
- `StorageService` class
- Methods: `load_cache`, `save_cache`, `atomic_write_json`, `atomic_move_to_archive`, `load_all_movies`, `load_json`

### 2. pipeline/validation.py (402 lines)
- `ValidationService` class
- Methods: `validate_watch_links_schema`, `validate_enrichment_consistency`, `validate_data_json_schema`

### 3. pipeline/enrichment.py (1,087 lines)
- `EnrichmentService` class
- Methods: `get_watch_links`, `try_agent_scraper`, `try_platform_scraper`, `get_platform_deep_link_with_cache`, `enforce_platform_scraper_rate_limit`, `normalize_watch_links_urls`, `migrate_legacy_cache_format`
- Utility methods: `append_affiliate_tag`, `is_excluded_service`, `is_actual_amazon_service`, `is_actual_apple_service`, `validate_service_link_consistency`

## Migration Steps

### Step 1: Add Pipeline Imports
**Location**: After line 21 (after `from constants import`)

```python
# Pipeline services (extracted 2025-11-10)
from pipeline.storage import StorageService
from pipeline.validation import ValidationService
from pipeline.enrichment import EnrichmentService
```

### Step 2: Initialize Services
**Location**: In `__init__` method, after line 183 (`self.perform_startup_consistency_check()`)

```python
# ============================================================================
# Pipeline Services (Extracted 2025-11-10)
# ============================================================================

# Phase 1: Storage Service - File I/O operations
self.storage = StorageService(logger=self.logger)

# Phase 2: Validation Service - Schema and consistency validation
self.validator = ValidationService(
    logger=self.logger,
    storage_service=self.storage,
    config=self.config,
    stats_dict=self.watchmode_stats  # Share stats dict
)

# Phase 3: Enrichment Service - Watch link discovery
self.enrichment = EnrichmentService(
    logger=self.logger,
    config=self.config,
    storage_service=self.storage,
    validator_service=self.validator,
    stats_dict=self.watchmode_stats,  # Share stats dict
    watchmode_client=self.watchmode_client,
    enrichment_enabled=self.enrichment_enabled
)

# Inject cache references into enrichment service
self.enrichment.set_cache_references(
    self.watch_links_cache,
    self.watch_links_overrides,
    self.watch_link_overrides
)
```

### Step 3: Method Call Replacements

#### Phase 1 - Storage (23 occurrences)
- `self.load_cache(` → `self.storage.load_cache(`
- `self.save_cache(` → `self.storage.save_cache(`
- `self.atomic_write_json(` → `self.storage.atomic_write_json(`
- `self.atomic_move_to_archive(` → `self.storage.atomic_move_to_archive(`
- `self.load_all_movies(` → `self.storage.load_all_movies(`
- `self.load_json(` → `self.storage.load_json(`

#### Phase 2 - Validation (8 occurrences)
- `self.validate_watch_links_schema(` → `self.validator.validate_watch_links_schema(`
- `self.validate_enrichment_consistency(` → `self.validator.validate_enrichment_consistency(`
- `self.validate_data_json_schema(` → `self.validator.validate_data_json_schema(`

#### Phase 3 - Enrichment (9+ occurrences)
- `self.get_watch_links(` → `self.enrichment.get_watch_links(`
- `self._try_agent_scraper(` → `self.enrichment.try_agent_scraper(`
- `self._try_platform_scraper(` → `self.enrichment.try_platform_scraper(`
- `self._get_platform_deep_link_with_cache(` → `self.enrichment.get_platform_deep_link_with_cache(`
- `self._enforce_platform_scraper_rate_limit(` → `self.enrichment.enforce_platform_scraper_rate_limit(`
- `self._normalize_watch_links_urls(` → `self.enrichment.normalize_watch_links_urls(`
- `self._migrate_legacy_cache_format(` → `self.enrichment.migrate_legacy_cache_format(`
- `self.append_affiliate_tag(` → `self.enrichment.append_affiliate_tag(`
- `self.is_excluded_service(` → `self.enrichment.is_excluded_service(`
- `self.is_actual_amazon_service(` → `self.enrichment.is_actual_amazon_service(`
- `self.is_actual_apple_service(` → `self.enrichment.is_actual_apple_service(`
- `self.validate_service_link_consistency(` → `self.enrichment.validate_service_link_consistency(`

### Step 4: Delete Method Definitions

Methods to delete (with line ranges):

#### Phase 1 - Storage Methods (135 lines total)
- `load_cache`: lines 507-512 (6 lines)
- `save_cache`: lines 513-517 (5 lines)
- `atomic_write_json`: lines 2363-2407 (45 lines)
- `atomic_move_to_archive`: lines 2408-2460 (53 lines)
- `load_all_movies`: lines 2461-2486 (26 lines)

#### Phase 2 - Validation Methods (281 lines total)
- `validate_watch_links_schema`: lines 1215-1310 (96 lines)
- `validate_enrichment_consistency`: lines 2248-2362 (115 lines)
- `validate_data_json_schema`: lines 2487-2556 (70 lines)

#### Phase 3 - Enrichment Methods (962 lines total)
- `get_watch_links`: lines 736-1141 (406 lines)
- `_try_agent_scraper`: lines 1311-1356 (46 lines)
- `_try_platform_scraper`: lines 1465-1619 (155 lines)
- `_get_platform_deep_link_with_cache`: lines 1156-1176 (21 lines)
- `_enforce_platform_scraper_rate_limit`: lines 1142-1155 (14 lines)
- `_normalize_watch_links_urls`: lines 1177-1214 (38 lines)
- `_migrate_legacy_cache_format`: lines 1620-1671 (52 lines)
- `append_affiliate_tag`: lines 357-408 (52 lines)
- `is_excluded_service`: lines 315-329 (15 lines)
- `is_actual_amazon_service`: lines 1357-1383 (27 lines)
- `is_actual_apple_service`: lines 1384-1410 (27 lines)
- `validate_service_link_consistency`: lines 1411-1464 (54 lines)
- `_init_agent_scraper`: lines 409-449 (41 lines) [Note: This is also extracted]

**Total Lines to Delete**: ~1,378 lines

Each deleted method will be replaced with a migration comment:
```python
# method_name - EXTRACTED to pipeline service (2025-11-10)
```

### Step 5: Add Migration Markers

Add documentation marker before class definition:
```python
# ============================================================================
# MIGRATION APPLIED: Pipeline Extraction (2025-11-10)
# - Phase 1: Storage operations → pipeline/storage.py
# - Phase 2: Validation operations → pipeline/validation.py
# - Phase 3: Enrichment operations → pipeline/enrichment.py
# ============================================================================
```

## Expected Results

### Line Count Changes
- **Original**: 3,350 lines
- **Lines Deleted**: ~1,378 lines (method definitions)
- **Lines Added**: ~45 lines (imports + initialization + markers)
- **Expected Final**: ~2,017 lines
- **Reduction**: ~39.8%

### Methods Preserved in generate_data.py
These methods will **NOT** be deleted (they stay in generate_data.py):
- `load_config`
- `_init_rt_scraper`
- `scrape_rt_score`
- `find_wikipedia_url`
- `find_trailer_url`
- `find_rt_url`
- `get_movie_details`
- `simplify_provider_name`
- `generate_google_search_fallback`
- `perform_startup_consistency_check`
- `validate_enrichment_changes`
- `get_excluded_services`
- All discovery methods
- All generation methods
- All main orchestration methods

## Testing Plan

### 1. Syntax Check
```bash
python3 -m py_compile generate_data.py
```

### 2. Import Check
```python
from generate_data import DataGenerator
gen = DataGenerator()
```

### 3. Basic Functionality Test
```bash
python generate_data.py
```

### 4. Run Test Suite
```bash
python test_fixes.py
```

### 5. Manual Tests
- Test storage operations: File I/O, atomic writes
- Test validation: Schema validation, consistency checks
- Test enrichment: Watch link discovery, scraper integration

## Rollback Plan

If issues are encountered:
1. Revert changes: `git checkout generate_data.py`
2. Review errors in logs
3. Fix issues in pipeline services
4. Re-run migration script

## Benefits

1. **Code Organization**: Clear separation of concerns
2. **Maintainability**: Each service is independently testable
3. **Reusability**: Services can be used by other modules
4. **Readability**: generate_data.py focuses on orchestration
5. **Testability**: Services have isolated unit tests

## Migration Script

The migration is automated via `apply_pipeline_extraction.py`:
```bash
python apply_pipeline_extraction.py
```

This script:
1. Adds imports
2. Initializes services
3. Replaces method calls
4. Deletes method definitions
5. Adds migration markers
6. Reports line count changes

## Verification Checklist

After migration:
- [ ] No syntax errors
- [ ] All imports resolve
- [ ] DataGenerator instantiates
- [ ] Storage operations work (load/save cache)
- [ ] Validation operations work (schema validation)
- [ ] Enrichment operations work (watch link discovery)
- [ ] Tests pass
- [ ] No runtime errors in logs
- [ ] Line count matches expected (~2,017 lines)
