# Change Detection Troubleshooting

## Overview

This document covers troubleshooting issues with the intake and provider detection workflows, specifically focusing on correct status transitions and digital_date handling.

## Contract Requirements

### Intake Workflow Contract
When new titles are ingested via `--intake`:
- **Status**: Must be `'tracking'`
- **Digital Date**: Must be `None` (not set during intake)
- **Enriched**: Must be `false`
- **Added Date**: Set to intake date

### Provider Detection Contract
When provider availability is detected via `--discover`:
- **Status**: Transitions from `'tracking'` → `'available'`
- **Digital Date**: Set to **today's date** (detection date, not release date)
- **Enriched**: Remains `false` (enrichment happens separately)

## Common Issues

### Issue 1: Intake Sets digital_date Incorrectly

**Symptoms:**
- New movies have `digital_date` set immediately after intake
- Movies transition directly to `available` status during `--intake`
- Contract test failures: `digital_date` should be `None` for intake movies

**Root Cause:**
Intake logic incorrectly setting `digital_date` based on release dates or availability data.

**Solution:**
```bash
# 1. Check recent intakes
python3 -c "
import json
with open('movie_tracking.json') as f:
    db = json.load(f)
    recent = [(id, m) for id, m in db['movies'].items()
             if m.get('added_date', '') >= '2024-11-01']

    for movie_id, movie in recent[:5]:
        print(f'{movie[\"title\"]}: status={movie[\"status\"]}, digital_date={movie.get(\"digital_date\")}, added={movie.get(\"added_date\")}')
"

# 2. Run contract tests to identify violations
python3 -m pytest tests/test_discovery_contract.py::TestDiscoveryContract::test_discovery_creates_tracking_movies -v

# 3. If violations found, check intake logic in generate_data.py
# Look for lines that set digital_date during intake phase
```

### Issue 2: Provider Detection Sets Wrong Date

**Symptoms:**
- `digital_date` set to release date instead of detection date
- Movies appear "available" with dates in the past
- Historical availability not reflected correctly

**Root Cause:**
Provider detection using movie release date or other historical date instead of current date.

**Solution:**
```bash
# 1. Test provider detection contract
python3 -m pytest tests/test_discovery_contract.py::TestProviderDetectionContract::test_provider_detection_sets_correct_digital_date -v

# 2. Check for movies with digital_date in the past
python3 -c "
import json
from datetime import datetime, timedelta
with open('movie_tracking.json') as f:
    db = json.load(f)

today = datetime.now().strftime('%Y-%m-%d')
cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

suspicious = []
for movie_id, movie in db['movies'].items():
    if (movie.get('status') == 'available' and
        movie.get('digital_date', '') < cutoff):
        suspicious.append((movie_id, movie))

print(f'Found {len(suspicious)} movies with digital_date older than 7 days:')
for movie_id, movie in suspicious[:5]:
    print(f'  {movie[\"title\"]}: digital_date={movie[\"digital_date\"]} (should be recent)')
"

# 3. Fix: Provider detection should use today's date
# Ensure provider check logic sets digital_date = datetime.now().strftime('%Y-%m-%d')
```

### Issue 3: Status Transition Violations

**Symptoms:**
- Movies skip `tracking` status and go directly to `available`
- Movies remain `tracking` despite provider availability
- Inconsistent status transitions

**Root Cause:**
Workflow logic not properly implementing the tracking → available transition.

**Solution:**
```bash
# 1. Run full contract integration test
python3 -m pytest tests/test_discovery_contract.py::TestDiscoveryContract::test_discovery_provider_integration_workflow -v

# 2. Check for status transition anomalies
python3 -c "
import json
from datetime import datetime, timedelta
with open('movie_tracking.json') as f:
    db = json.load(f)

# Find movies that should be tracking but are available (without provider check)
recent = datetime.now() - timedelta(days=1)
recent_str = recent.strftime('%Y-%m-%d')

anomalies = []
for movie_id, movie in db['movies'].items():
    # Movies added recently but immediately available (suspicious)
    if (movie.get('added_date', '') >= recent_str and
        movie.get('status') == 'available' and
        movie.get('digital_date') == movie.get('added_date')):
        anomalies.append(movie)

print(f'Found {len(anomalies)} movies with suspicious immediate availability:')
for movie in anomalies[:3]:
    print(f'  {movie[\"title\"]}: added={movie[\"added_date\"]}, digital_date={movie[\"digital_date\"]}')
"

# 3. Manually verify workflow steps
# Discovery should ONLY create tracking movies
# Provider check should ONLY transition tracking → available
```

## Testing Commands

### Run All Contract Tests
```bash
# Full contract test suite
python3 -m pytest tests/test_discovery_contract.py -v

# Specific contract tests
python3 -m pytest tests/test_discovery_contract.py::TestDiscoveryContract::test_discovery_creates_tracking_movies -v
python3 -m pytest tests/test_discovery_contract.py::TestProviderDetectionContract::test_provider_detection_sets_correct_digital_date -v
```

### Manual Workflow Testing
```bash
# 1. Test intake (should create tracking movies)
python3 generate_data.py --intake

# Check that new movies have status=tracking, digital_date=None
python3 -c "
import json
with open('movie_tracking.json') as f:
    db = json.load(f)
    tracking = [m for m in db['movies'].values() if m.get('status') == 'tracking']
    print(f'Tracking movies: {len(tracking)}')
    for movie in tracking[:3]:
        print(f'  {movie[\"title\"]}: digital_date={movie.get(\"digital_date\")}')
"

# 2. Test provider detection (should transition to available)
python3 generate_data.py --discover

# Check that available movies have digital_date=today
python3 -c "
import json
from datetime import datetime
with open('movie_tracking.json') as f:
    db = json.load(f)
    available = [m for m in db['movies'].values() if m.get('status') == 'available']
    today = datetime.now().strftime('%Y-%m-%d')
    recent_available = [m for m in available if m.get('digital_date') == today]
    print(f'Available movies: {len(available)}, Available today: {len(recent_available)}')
"
```

## Prevention

1. **Always run contract tests** before merging discovery/provider changes:
   ```bash
   python3 -m pytest tests/test_discovery_contract.py -v
   ```

2. **Monitor status transition patterns** in daily runs:
   ```bash
   # Check for unusual patterns
   grep -E "(status|digital_date)" logs/admin.log | tail -20
   ```

3. **Use separate phases**: Keep intake and provider detection in separate workflow steps to maintain clear contracts.

4. **Validate dates**: Ensure `digital_date` is always current date when set by provider detection, never historical.

## Related Documentation

- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - General workflow troubleshooting
- [SYSTEM_ARCHITECTURE.md](../../SYSTEM_ARCHITECTURE.md) - System design overview
- Contract tests: `tests/test_discovery_contract.py`