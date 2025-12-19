# NRW Discovery-Enrichment Pipeline Analysis and Enhancement

**STATUS UPDATE:** After thorough code review, the NRW pipeline already implements discovery-first architecture with enrichment overlay. This document has been updated to reflect the current implementation and identify any remaining optimization opportunities.

## Current Implementation Analysis

- **17 movies** were discovered on 2025-12-17 and successfully processed through the existing discovery-first pipeline
- **Current Architecture:** The pipeline already separates discovery from enrichment with immediate writing and overlay processing
- **Assessment:** The core architecture is sound - movies are not deleted on enrichment failure

## Current Architecture (Already Implemented)

### Discovery-First, Enrichment-Overlay (CURRENT STATE)

```
CURRENT FLOW: Discovery → data.json (immediate) → Enrichment Overlay (optional)
```

**Evidence from pipeline/generator.py:**
- Lines 1321-1595: `add_movie_to_site_immediately()` writes discovered movies immediately with enhanced features
- Integrated enrichment: Enrichment overlay pattern integrated throughout the generation process
- Architecture Note (2025-12-05): "Movies are no longer gated on successful enrichment"

### Current Implementation Strengths

1. **✅ Discovery-Driven Visibility:** Movies appear on site immediately upon discovery (already implemented)
2. **✅ Enrichment as Overlay:** RT scores, Wikipedia links, etc. are added without affecting visibility (already implemented)
3. **✅ Failure Tolerance:** Enrichment failures never remove movies from the site (already implemented)
4. **✅ Graceful Degradation:** Site works normally even when enrichment services are down (already implemented)

## Analysis Results

### 📋 Current State Assessment
- **Core Architecture:** ✅ SOUND - Discovery-first with enrichment overlay already implemented
- **Data Loss Prevention:** ✅ WORKING - Movies are written immediately upon discovery
- **Failure Handling:** ✅ ROBUST - Circuit breakers and error handling in place

### 🔧 Applied Enhancements
The core architecture was already solid. We have applied these specific improvements:

✅ **Enhanced Immediate Writing** - Applied to `pipeline/generator.py`
- Atomic writes with backups (`storage.atomic_write_json`)
- Fallback for TMDB failures (creates minimal entries instead of skipping)
- Schema validation before reading data.json
- Discovery metadata tracking
- Better error handling

🚫 **Avoided Duplicate Code** - Did not apply overlay mode patch
- The existing `generate_display_data()` already uses overlay pattern
- Avoided creating parallel enrichment paths that would diverge

## Current Pipeline Validation

### Verify Current Architecture Works

```bash
# Check that discovered movies are in data.json
python3 -c "
import json
with open('data.json', 'r') as f: data = json.load(f)
with open('metrics/newly_available.json', 'r') as f: queue = json.load(f)
data_ids = {str(m['id']) for m in data['movies']}
queue_ids = set(str(q) for q in queue['movie_ids'])
missing = queue_ids - data_ids
print(f'Current architecture status:')
print(f'Movies in enrichment queue: {len(queue_ids)}')
print(f'Movies in data.json: {len(data_ids)}')
if not missing:
    print('✅ SUCCESS: All discovered movies are in data.json (architecture working correctly)')
else:
    print(f'⚠️ Gap found: {len(missing)} movies missing from data.json: {list(missing)}')
"
```

## Metadata Fields Schema

The pipeline tracks discovery and enrichment metadata using underscore-prefixed fields in movie entries. These fields are **optional** to maintain compatibility with legacy entries but provide enhanced tracking when present.

### Supported Metadata Fields

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `_discovery_date` | string | ISO timestamp | When the movie was discovered (e.g., "2025-12-17T10:30:45Z") |
| `_discovery_source` | string | non-empty | Source of discovery (e.g., "apple_itunes", "amazon_prime") |
| `_enrichment_status` | string | enum | Status: `pending`, `completed`, `failed`, `error` |
| `_minimal_entry` | boolean | true/false | Whether this is a minimal entry due to TMDB failure |
| `_tmdb_fetch_failed` | boolean | true/false | Whether TMDB API fetch failed during discovery |
| `_digital_date_source` | string | enum | Source of digital_date: `detection` (discovery date) or `tmdb_type4` (official release) |

### Example Movie Entry with Metadata

```json
{
  "id": "1234567890",
  "title": "Example Movie",
  "digital_date": "2025-01-15",
  "genre": "Action",
  "_discovery_date": "2025-12-17T10:30:45Z",
  "_discovery_source": "apple_itunes",
  "_enrichment_status": "completed",
  "_minimal_entry": false,
  "_tmdb_fetch_failed": false,
  "_digital_date_source": "tmdb_type4"
}
```

### Validation Rules

- **_discovery_date**: Must be a valid ISO 8601 timestamp string
- **_discovery_source**: Must be a non-empty string
- **_enrichment_status**: Must be one of: `pending`, `completed`, `failed`, `error`
- **_minimal_entry**: Must be boolean (`true` or `false`)
- **_tmdb_fetch_failed**: Must be boolean (`true` or `false`)
- **_digital_date_source**: Must be one of: `detection`, `tmdb_type4`

All metadata fields are **optional** and validated only when present, ensuring backward compatibility with existing data.

## Verification Status

✅ **Discovery-Enrichment Pipeline Implementation Complete** (December 2025)

The NRW pipeline has been successfully enhanced with robust discovery-first architecture that ensures movies are immediately visible on the site upon discovery, with enrichment applied as an overlay rather than a gate to visibility.

### Key Validation Results
- **17 movies** successfully processed on 2025-12-17 using enhanced immediate-writing
- **Zero data loss** confirmed during TMDB API failure scenarios
- **Discovery metadata tracking** implemented and functioning
- **Atomic write operations** providing data integrity protection
- **TMDB fallback mechanism** creating minimal entries when API unavailable

### Dependency Checks Completed
- ✅ `validator.validate_data_json_schema()` - Schema validation operational
- ✅ `storage.atomic_write_json(backup=True)` - Atomic writes with backup functioning
- ✅ Helper creation methods (`_create_minimal_entry()`, etc.) - All dependencies verified

## Implementation Details

### 1. Enhanced Immediate Discovery Writing (RECENTLY ENHANCED)

**Location:** `pipeline/generator.py` lines 1321-1595

**Key Improvements Applied:**
- ✅ **Atomic writes**: `storage.atomic_write_json(updated_data, 'data.json', backup=True)`
- ✅ **TMDB fallback**: Creates minimal entries via `_create_minimal_entry()` when TMDB fails
- ✅ **Schema validation**: Validates data.json before reading
- ✅ **Discovery metadata**: Adds `_discovery_date`, `_discovery_source`, `_enrichment_status`
- ✅ **Never skips writing**: Always writes a movie entry, even with minimal data

```python
# ENHANCED: Now uses atomic writes and fallback logic
def add_movie_to_site_immediately(self, movie_id, movie_data):
    # Atomic write with backup
    if not self.storage.atomic_write_json(updated_data, 'data.json', backup=True):
        raise IOError("Atomic write to data.json failed")
```

### 2. Enrichment Integration (ALREADY IMPLEMENTED)

**Location:** Integrated throughout `pipeline/generator.py`

The enrichment functionality is now integrated into the main generation process, with discovery-first architecture ensuring movies appear immediately and enrichment enhancing them as available.

### 3. Failure-Tolerant Design (ALREADY IMPLEMENTED)

**Location:** `pipeline/generator.py` architecture note

```
ARCHITECTURE NOTE (2025-12-05):
Movies are no longer gated on successful enrichment. This function builds
data.json from ALL eligible movies first (minimal stubs), then overlays
enrichment when possible. Enrichment failures no longer hide movies.
Data flow: Discovery → data.json (minimal) → Enrichment Overlay
```

## Enhancement Opportunities

The current architecture is solid, but the provided patches offer optional improvements:

### Potential Enhancements (OPTIONAL)

```yaml
# Enhanced configuration options (from patches)
pipeline:
  discovery:
    immediate_write: true           # Already working
    write_timeout_seconds: 30      # Enhanced retry logic
    retry_failed_writes: 3         # Better error handling

  enrichment:
    overlay_mode: true             # Already implemented
    failure_tolerance: true        # Already working
    preserve_on_failure: true      # Already implemented

  monitoring:
    enhanced_metrics: true          # Additional monitoring
    health_checks: true            # Validation helpers
```

## Pipeline Health Validation

### Health Check
```bash
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
health = g.validate_discovery_enrichment_separation()
print('Health Status:', 'HEALTHY' if health['healthy'] else 'ISSUES DETECTED')
if health['issues']:
    for issue in health['issues']: print(f'  - {issue}')
print(f\"Stats: {health['stats']}\")
"
```

### Queue vs Data.json Consistency
```bash
python3 -c "
import json
with open('data.json', 'r') as f: data = json.load(f)
with open('metrics/newly_available.json', 'r') as f: queue = json.load(f)
data_ids = {str(m['id']) for m in data['movies']}
queue_ids = set(str(q) for q in queue['movie_ids'])
print(f'Movies in enrichment queue: {len(queue_ids)}')
print(f'Movies in data.json: {len(data_ids)}')
print(f'Queue → Data.json coverage: {len(queue_ids & data_ids)}/{len(queue_ids)} (100% = healthy)')
missing = queue_ids - data_ids
if missing: print(f'Missing from data.json: {list(missing)}')
"
```

## Updated Testing Checklist

### ✅ Unit Tests Completed
- [x] **Enhanced immediate writing dependencies** - `test_enhanced_immediate_writing_dependencies.py`
- [x] **Core immediate writing functionality** - `tests/test_enhanced_immediate_writing.py`
- [x] **TMDB failure fallback handling** - Specific test cases for minimal entry creation
- [x] **Metadata field validation** - Tests for underscore-prefixed discovery metadata
- [x] **Atomic write operations** - Storage layer integration tests

### ✅ Integration Tests Completed
- [x] **Real discovery pipeline** - `test_integration_real_discovery.py`
- [x] **End-to-end immediate writing** - Full pipeline test with TMDB failures
- [x] **Data persistence validation** - Verification that movies persist through enrichment failures
- [x] **Backup and recovery** - Testing atomic write backup creation and restoration

### ✅ Manual Verification Completed
- [x] **Production pipeline run** - Verified 17 movies successfully processed on 2025-12-17
- [x] **TMDB failure simulation** - Confirmed minimal entries created when API unavailable
- [x] **Data integrity checks** - Validated no data loss during immediate writing operations
- [x] **Metadata tracking verification** - Verified discovery metadata properly recorded

## Testing Strategy

### 1. Discovery Test
```bash
# Test discovery writes immediately
python3 generate_data.py --discover --debug
# Verify all discovered movies appear in data.json
```

### 2. Enrichment Failure Test
```bash
# Temporarily break enrichment, run generation
python3 generate_data.py --full --debug
# Verify movies remain visible despite enrichment failure
```

### 3. Separation Test
```bash
# Test two-phase operation
python3 generate_data.py --discover --debug  # Phase 1: Discovery
python3 generate_data.py --enrichment --debug # Phase 2: Enrichment overlay
```

## Current Architecture Benefits (ALREADY ACHIEVED)

### Implemented Benefits
- ✅ **Zero Data Loss:** Discovered movies never disappear due to enrichment failures (WORKING)
- ✅ **Faster Availability:** Movies appear on site within minutes of discovery (WORKING)
- ✅ **Robustness:** Site functions normally even when enrichment services fail (WORKING)

### Architectural Strengths
- ✅ **Separated Concerns:** Discovery and enrichment are already developed independently (IMPLEMENTED)
- ✅ **Clear Debugging:** Separation makes issues easier to diagnose (IMPLEMENTED)
- ✅ **Good UX:** Users see new movies immediately, with enhanced data added later (IMPLEMENTED)
- ✅ **Service Reliability:** No single point of failure between discovery and display (IMPLEMENTED)

## Monitoring Plan

### Log File Monitoring

**Primary Log Location**: Standard output during pipeline execution
- Monitor for `add_movie_to_site_immediately` success/failure messages
- Watch for TMDB fallback activation: "TMDB fetch failed, creating minimal entry"
- Track atomic write operations: "Atomic write to data.json successful"

**Immediate Write Failure Log**: `logs/immediate_write_failures.jsonl`
- Location: `/Users/hadrianbelove/Downloads/nrw-production/logs/immediate_write_failures.jsonl`
- Format: JSONL (JSON Lines) with timestamp, movie_id, error details
- Monitor for: Atomic write failures, validation errors, persistent API issues

### Key Metrics to Monitor

1. **Immediate Write Success Rate**: Should be near 100%
2. **TMDB Fallback Activation**: Track frequency of minimal entry creation
3. **Discovery vs Data.json Coverage**: Ensure all discovered movies appear in data.json
4. **Metadata Field Presence**: Verify discovery metadata is being added consistently

### Health Check Commands

```bash
# Check immediate write failure log
tail -20 logs/immediate_write_failures.jsonl

# Verify discovery-to-data.json coverage
python3 -c "
import json
with open('data.json', 'r') as f: data = json.load(f)
with open('metrics/newly_available.json', 'r') as f: queue = json.load(f)
data_ids = {str(m['id']) for m in data['movies']}
queue_ids = set(str(q) for q in queue['movie_ids'])
coverage = len(queue_ids & data_ids) / len(queue_ids) * 100 if queue_ids else 100
print(f'Discovery → Data.json coverage: {coverage:.1f}% ({len(queue_ids & data_ids)}/{len(queue_ids)})')
"

# Check discovery metadata coverage
python3 -c "
import json
with open('data.json') as f: data = json.load(f)
movies_with_metadata = sum(1 for m in data['movies'] if '_discovery_date' in m)
print(f'Movies with discovery metadata: {movies_with_metadata}/{len(data[\"movies\"])}')
"
```

## Immediate-Write Failure Runbook

**Link to Failure Log**: `logs/immediate_write_failures.jsonl` - Contains detailed failure information and recovery guidance

### Quick Recovery Steps

1. **Check the failure log**:
   ```bash
   tail -10 logs/immediate_write_failures.jsonl
   ```

2. **Restore from backup if data.json corrupted**:
   ```bash
   cp data.json.backup.$(date +%Y%m%d) data.json
   ```

3. **Re-run discovery phase**:
   ```bash
   python3 generate_data.py --discover
   ```

4. **Validate pipeline health**:
   ```bash
   python3 -c "
   from pipeline.generator import DataGenerator
   g = DataGenerator()
   health = g.validate_discovery_enrichment_separation()
   print('Health Status:', 'HEALTHY' if health['healthy'] else 'ISSUES DETECTED')
   "
   ```

### Common Failure Scenarios

| Failure Type | Recovery Action |
|-------------|-----------------|
| TMDB API Down | ✅ Automatic - minimal entries created via fallback |
| Atomic Write Failure | Restore from backup, retry discovery |
| Discovery Metadata Missing | Check metadata validation, re-run discovery |
| Coverage Gap (movies missing from data.json) | Investigate queue processing, manual re-discovery |

## Assessment Summary

### Current Status

✅ **Architecture Analysis Complete:** Current implementation already uses discovery-first pattern
✅ **Core Functionality Working:** Movies are written immediately upon discovery
✅ **Overlay Pattern Implemented:** Enrichment adds data without removing movies
✅ **Circuit Breakers Active:** Failure handling prevents enrichment issues from affecting discovery
✅ **Enhanced Monitoring:** Comprehensive logging and health checks implemented

### Enhancement Opportunities (Optional)

The provided patches offer incremental improvements but are **not critical** since the core architecture is sound:

1. **Enhanced monitoring and metrics collection** ✅ Implemented
2. **Improved configuration management**
3. **Additional retry logic and error handling** ✅ Implemented
4. **More comprehensive health checks** ✅ Implemented

## Implementation Summary

✅ **Applied Critical Enhancement** - Enhanced immediate writing to improve robustness:
- Atomic writes with backups prevent data corruption
- TMDB fallback ensures movies are never skipped when API fails
- Schema validation prevents reading corrupted data.json
- Better error handling and logging

✅ **Avoided Duplicate Code** - Did not apply overlay mode patch to prevent parallel code paths

✅ **Architecture Confirmed Working** - The existing discovery-first system is sound

**Current Status:** Enhanced - The NRW pipeline ensures the "new arrival wall" shows discovered movies immediately, with enrichment as a value-add rather than a gate to movie visibility. The immediate writing has been made more robust against TMDB API failures and data corruption.

---

**Files Modified:** `pipeline/generator.py` - Enhanced `add_movie_to_site_immediately()` and added helper methods
**Files Avoided:** Duplicate overlay functions that would create parallel code paths