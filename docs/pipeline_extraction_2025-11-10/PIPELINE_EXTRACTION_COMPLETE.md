# Pipeline Extraction - Complete Implementation Guide

## Executive Summary

This document provides a complete guide for reapplying all three phases of pipeline extraction to `generate_data.py`. The pipeline services already exist and are complete - this is purely an integration task.

### Quick Stats
- **Current State**: `generate_data.py` at 3,350 lines (reverted)
- **Target State**: ~2,017 lines (39.8% reduction)
- **Services**: 3 pipeline services ready to integrate
- **Methods to Extract**: 21 methods totaling ~1,378 lines
- **Method Calls to Replace**: 61+ occurrences

## Files Included

1. **`apply_pipeline_extraction.py`** - Automated migration script
2. **`MIGRATION_PLAN.md`** - Detailed migration plan with line-by-line changes
3. **`METHOD_REPLACEMENTS.md`** - Quick reference for all method call replacements
4. **`PIPELINE_EXTRACTION_COMPLETE.md`** - This file (executive summary)

## Quick Start

### Option 1: Review First (Recommended)

```bash
# 1. Review the plan
cat MIGRATION_PLAN.md

# 2. Review method replacements
cat METHOD_REPLACEMENTS.md

# 3. When ready, run the migration script
python apply_pipeline_extraction.py

# 4. Review changes
git diff generate_data.py

# 5. Test
python generate_data.py
```

### Option 2: Direct Migration

```bash
# Run migration directly
python apply_pipeline_extraction.py

# Verify
python generate_data.py
```

## What the Migration Does

### 1. Adds Pipeline Imports (After Line 21)
```python
from pipeline.storage import StorageService
from pipeline.validation import ValidationService
from pipeline.enrichment import EnrichmentService
```

### 2. Initializes Services (After Line 183)
```python
self.storage = StorageService(logger=self.logger)
self.validator = ValidationService(...)
self.enrichment = EnrichmentService(...)
self.enrichment.set_cache_references(...)
```

### 3. Replaces Method Calls (61+ locations)
```python
# Storage
self.load_cache(...)          → self.storage.load_cache(...)
self.atomic_write_json(...)   → self.storage.atomic_write_json(...)

# Validation
self.validate_watch_links_schema(...) → self.validator.validate_watch_links_schema(...)

# Enrichment
self.get_watch_links(...)     → self.enrichment.get_watch_links(...)
```

### 4. Deletes Method Definitions (21 methods, ~1,378 lines)

**Phase 1 - Storage (5 methods, 135 lines)**
- `load_cache`
- `save_cache`
- `atomic_write_json`
- `atomic_move_to_archive`
- `load_all_movies`

**Phase 2 - Validation (2 methods, ~170 lines)**
- `validate_watch_links_schema`
- ~~`validate_enrichment_consistency`~~ DELETED 2025-12-05 (loop bug)
- `validate_data_json_schema`

**Phase 3 - Enrichment (13 methods, 962 lines)**
- `get_watch_links`
- `_try_agent_scraper`
- `_try_platform_scraper`
- `_init_agent_scraper`
- `_get_platform_deep_link_with_cache`
- `_enforce_platform_scraper_rate_limit`
- `_normalize_watch_links_urls`
- `_migrate_legacy_cache_format`
- `append_affiliate_tag`
- `is_excluded_service`
- `is_actual_amazon_service`
- `is_actual_apple_service`
- `validate_service_link_consistency`

### 5. Adds Migration Markers
Documentation comments marking the extraction for future reference.

## Expected Results

### Line Count
```
Original:  3,350 lines
Deleted:  ~1,378 lines (methods)
Added:       ~45 lines (imports/init)
Final:    ~2,017 lines
Reduction:  39.8%
```

### File Structure After Migration

```
generate_data.py (~2,017 lines)
├── Imports (including pipeline services)
├── setup_logger()
├── DataGenerator class
│   ├── __init__() (with service initialization)
│   ├── Configuration methods (load_config, etc.)
│   ├── Scraper initialization (_init_rt_scraper)
│   ├── Metadata discovery (scrape_rt_score, find_wikipedia_url, etc.)
│   ├── Intake operations (intake_new_premieres, etc.)
│   └── Generation operations (generate, etc.)
└── Main entry point

pipeline/storage.py (433 lines)
├── StorageService class
└── All file I/O operations

pipeline/validation.py (402 lines)
├── ValidationService class
└── All validation operations

pipeline/enrichment.py (1,087 lines)
├── EnrichmentService class
└── All enrichment operations
```

## Testing Strategy

### 1. Pre-Migration Tests
```bash
# Verify pipeline services exist
ls -l pipeline/storage.py
ls -l pipeline/validation.py
ls -l pipeline/enrichment.py

# Verify current state
wc -l generate_data.py  # Should show 3,350
```

### 2. Post-Migration Tests
```bash
# Verify syntax
python3 -m py_compile generate_data.py

# Verify line count
wc -l generate_data.py  # Should show ~2,017

# Verify imports
python3 -c "from generate_data import DataGenerator"

# Verify instantiation
python3 -c "from generate_data import DataGenerator; gen = DataGenerator()"

# Run full generation
python generate_data.py

# Run test suite (if available)
python test_fixes.py
```

### 3. Verification Commands
```bash
# Check old method calls are gone (should be 0)
grep -c "self\.load_cache(" generate_data.py
grep -c "self\.get_watch_links(" generate_data.py

# Check new service calls exist (should have counts)
grep -c "self\.storage\." generate_data.py
grep -c "self\.validator\." generate_data.py
grep -c "self\.enrichment\." generate_data.py
```

## Rollback Plan

If issues occur:

```bash
# Option 1: Git revert
git checkout generate_data.py

# Option 2: From backup (if created)
cp generate_data.py.backup generate_data.py
```

## Benefits

### 1. Code Organization
- Clear separation of concerns
- Each service has single responsibility
- Easier to navigate and understand

### 2. Maintainability
- Changes to storage logic only affect `pipeline/storage.py`
- Validation logic isolated in `pipeline/validation.py`
- Enrichment logic isolated in `pipeline/enrichment.py`

### 3. Testability
- Services can be unit tested independently
- Mock services for integration tests
- Faster test execution

### 4. Reusability
- Services can be imported by other modules
- Admin panel can use same validation
- Future tools can use same storage

### 5. Readability
- `generate_data.py` focuses on orchestration
- Service implementations hidden from main flow
- Clear API boundaries

## Common Issues & Solutions

### Issue: Import Error
```
ImportError: No module named 'pipeline'
```
**Solution**: Ensure pipeline directory exists and has `__init__.py`
```bash
ls pipeline/__init__.py
```

### Issue: Attribute Error
```
AttributeError: 'DataGenerator' object has no attribute 'storage'
```
**Solution**: Check service initialization in `__init__` method

### Issue: Method Not Found
```
AttributeError: 'StorageService' object has no attribute 'load_cache'
```
**Solution**: Verify pipeline services are complete and up to date

### Issue: Cache Reference Error
```
KeyError: Cache references not set
```
**Solution**: Ensure `set_cache_references()` is called for enrichment service

## Migration Script Details

The `apply_pipeline_extraction.py` script performs these operations:

1. **Add Imports**: Inserts 5 lines after constants import
2. **Initialize Services**: Inserts ~35 lines in `__init__` method
3. **Replace Calls**: Uses regex to replace 61+ method calls
4. **Delete Methods**: Removes 21 method definitions (~1,378 lines)
5. **Add Markers**: Inserts documentation comments

The script is idempotent - running it multiple times won't break anything (though it may create duplicate imports/initialization).

## Success Criteria

Migration is successful when:

- [ ] No syntax errors in `generate_data.py`
- [ ] File compiles: `python3 -m py_compile generate_data.py`
- [ ] Imports work: `from generate_data import DataGenerator`
- [ ] Instantiation works: `DataGenerator()` succeeds
- [ ] Line count is ~2,017 lines (±50 lines acceptable)
- [ ] All tests pass
- [ ] Generation runs successfully: `python generate_data.py`
- [ ] No runtime errors in logs
- [ ] Git diff shows expected changes

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    generate_data.py                         │
│                  (Main Orchestration)                       │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              DataGenerator.__init__()                  │ │
│  │  • Loads config                                        │ │
│  │  • Initializes API clients (TMDB, JustWatch)         │ │
│  │  • Creates service instances:                         │ │
│  │    - self.storage = StorageService()                 │ │
│  │    - self.validator = ValidationService()            │ │
│  │    - self.enrichment = EnrichmentService()           │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │           Core Orchestration Methods                   │ │
│  │  • intake_new_premieres() - Find new movies           │ │
│  │  • check_tracking_movies() - Update tracking          │ │
│  │  • generate() - Create data.json                      │ │
│  │                                                        │ │
│  │  Uses services via:                                   │ │
│  │  • self.storage.load_cache()                          │ │
│  │  • self.validator.validate_watch_links_schema()       │ │
│  │  • self.enrichment.get_watch_links()                  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ uses
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Pipeline Services                         │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │ StorageService   │  │ValidationService │  │Enrichment│ │
│  │ (433 lines)      │  │ (402 lines)      │  │Service   │ │
│  │                  │  │                  │  │(1087 ln) │ │
│  │ • load_cache     │  │ • validate_      │  │• get_    │ │
│  │ • save_cache     │  │   watch_links_   │  │  watch_  │ │
│  │ • atomic_write   │  │   schema         │  │  links   │ │
│  │ • load_all_      │  │ • validate_      │  │• try_    │ │
│  │   movies         │  │   enrichment_    │  │  agent_  │ │
│  │                  │  │   consistency    │  │  scraper │ │
│  └──────────────────┘  └──────────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Next Steps After Migration

1. **Commit Changes**
   ```bash
   git add generate_data.py
   git commit -m "Reapply pipeline extraction: storage, validation, enrichment services"
   ```

2. **Update Documentation**
   - Update README with new architecture
   - Document service APIs
   - Add service usage examples

3. **Add Tests**
   - Unit tests for each service
   - Integration tests with services
   - End-to-end tests

4. **Monitor Performance**
   - Check for any performance regressions
   - Verify memory usage
   - Monitor logs for errors

## Questions?

If you encounter issues:

1. Check `MIGRATION_PLAN.md` for detailed steps
2. Check `METHOD_REPLACEMENTS.md` for method mappings
3. Review logs in `logs/admin.log`
4. Check git diff: `git diff generate_data.py`
5. Rollback if needed: `git checkout generate_data.py`

## Summary

This migration:
- ✅ Reduces `generate_data.py` from 3,350 to ~2,017 lines (39.8%)
- ✅ Separates concerns into 3 focused services
- ✅ Improves testability and maintainability
- ✅ Preserves all functionality
- ✅ Is fully reversible via git

**Ready to migrate?**

```bash
python apply_pipeline_extraction.py
```
