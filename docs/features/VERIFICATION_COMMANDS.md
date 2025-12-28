# Enhanced Immediate Writing - Verification Commands

## Quick Verification

```bash
# Run full dependency verification
python3 verify_enhanced_dependencies.py

# Run with JSON output for automated parsing
python3 verify_enhanced_dependencies.py --format json > verification_report.json

# Run end-to-end functional tests
python3 test_enhanced_immediate_writing_dependencies.py

# Check for verification artifacts and backups
ls -lh verification_report.* backups/data.json.backup-*
```

## Manual Dependency Checks

### Validator Service Check
```bash
# Check validator method exists and is accessible
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
print('Validator available:', hasattr(g, 'validator'))
if hasattr(g, 'validator'):
    print('Schema validation method:', hasattr(g.validator, 'validate_data_json_schema'))

    # Test validation
    result = g.validator.validate_data_json_schema('data.json')
    print('Validation test result:', result)
"
```

### Storage Service Check
```bash
# Check storage atomic write and signature
python3 -c "
from pipeline.generator import DataGenerator
import inspect
g = DataGenerator()
print('Storage available:', hasattr(g, 'storage'))
if hasattr(g, 'storage'):
    print('Atomic write method:', hasattr(g.storage, 'atomic_write_json'))
    sig = inspect.signature(g.storage.atomic_write_json)
    print('Method signature:', sig)
    print('Has backup parameter:', 'backup' in sig.parameters)
"
```

### Helper Methods Check
```bash
# Check helper methods exist and are callable
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
print('_create_minimal_entry:', hasattr(g, '_create_minimal_entry'))
print('_create_full_basic_entry:', hasattr(g, '_create_full_basic_entry'))
print('Both callable:',
      callable(getattr(g, '_create_minimal_entry', None)) and
      callable(getattr(g, '_create_full_basic_entry', None)))
"
```

## Test Data Creation

### Create Test Movie Entry
```bash
# Add a test movie using the enhanced function
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()

movie_id = 'test_12345'
movie_data = {
    'title': 'Test Movie',
    'digital_date': '2024-12-16',
    'providers': {'streaming': ['Test Platform'], 'rent': [], 'buy': []}
}

result = g.add_movie_to_site_immediately(movie_id, movie_data)
print(f'Movie addition result: {result}')
print(f'Check data.json for movie {movie_id}')
"
```

### Verify Test Movie Added
```bash
# Check if test movie was added correctly
python3 -c "
import json
with open('data.json') as f:
    data = json.load(f)

if 'test_12345' in data.get('movies', {}):
    movie = data['movies']['test_12345']
    print('Test movie found!')
    print(f'Title: {movie.get(\"title\")}')
    print(f'Minimal entry: {movie.get(\"_minimal_entry\")}')
    print(f'Enrichment status: {movie.get(\"_enrichment_status\")}')
    print(f'Discovery date: {movie.get(\"_discovered_at\")}')
else:
    print('Test movie not found in data.json')
"
```

## Backup Verification

### Check Backup Creation
```bash
# List recent backups
ls -lt backups/data.json.backup-* | head -5

# Check backup content (latest backup)
latest_backup=$(ls -t backups/data.json.backup-* | head -1)
echo "Latest backup: $latest_backup"
python3 -c "
import json
with open('$latest_backup') as f:
    backup = json.load(f)
print(f'Backup contains {len(backup.get(\"movies\", {}))} movies')
print(f'Backup timestamp: {backup.get(\"last_updated\")}')
"
```

### Verify Atomic Write Safety
```bash
# Test atomic write behavior (safe interruption)
python3 -c "
import json
from pipeline.generator import DataGenerator

# Count movies before
with open('data.json') as f:
    before_count = len(json.load(f).get('movies', {}))

g = DataGenerator()
result = g.add_movie_to_site_immediately('atomic_test', {
    'title': 'Atomic Test', 'digital_date': '2024-12-16',
    'providers': {'streaming': [], 'rent': [], 'buy': []}
})

# Count movies after
with open('data.json') as f:
    after_count = len(json.load(f).get('movies', {}))

print(f'Before: {before_count} movies, After: {after_count} movies')
print(f'Addition successful: {result and after_count > before_count}')
"
```

## Schema Validation Testing

### Test Valid Schema
```bash
# Test schema validation with current data.json
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
result = g.validator.validate_data_json_schema('data.json')
print(f'Current data.json schema valid: {result}')
"
```

### Test Invalid Schema Handling
```bash
# Create invalid JSON and test handling
echo '{ "invalid": json }' > test_invalid.json
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
result = g.validator.validate_data_json_schema('test_invalid.json')
print(f'Invalid JSON handled correctly: {not result}')
"
rm test_invalid.json
```

## Performance Benchmarking

### Measure Write Performance
```bash
# Time a single movie addition
time python3 -c "
from pipeline.generator import DataGenerator
import random
g = DataGenerator()
movie_id = f'perf_test_{random.randint(1000, 9999)}'
result = g.add_movie_to_site_immediately(movie_id, {
    'title': f'Performance Test {movie_id}',
    'digital_date': '2024-12-16',
    'providers': {'streaming': ['Test'], 'rent': [], 'buy': []}
})
print(f'Performance test result: {result}')
"
```

### Measure Schema Validation Performance
```bash
# Time schema validation
time python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
for i in range(10):
    result = g.validator.validate_data_json_schema('data.json')
print(f'10 validations completed, result: {result}')
"
```

## Error Testing

### Test TMDB Failure Path
```bash
# Test with definitely non-existent movie ID
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()
result = g.add_movie_to_site_immediately('999999999', {
    'title': 'Nonexistent Movie',
    'digital_date': '2024-12-16',
    'providers': {'streaming': ['Test'], 'rent': [], 'buy': []}
})
print(f'TMDB failure handled: {result}')

# Check if minimal entry was created
import json
with open('data.json') as f:
    data = json.load(f)
    if '999999999' in data.get('movies', {}):
        movie = data['movies']['999999999']
        print(f'Minimal entry created: {movie.get(\"_minimal_entry\")}')
        print(f'TMDB fetch failed: {movie.get(\"_tmdb_fetch_failed\")}')
"
```

### Test Duplicate Prevention
```bash
# Test duplicate movie handling
python3 -c "
from pipeline.generator import DataGenerator
g = DataGenerator()

# Add movie twice
movie_id = 'duplicate_test_123'
movie_data = {
    'title': 'Duplicate Test',
    'digital_date': '2024-12-16',
    'providers': {'streaming': ['Test'], 'rent': [], 'buy': []}
}

result1 = g.add_movie_to_site_immediately(movie_id, movie_data)
result2 = g.add_movie_to_site_immediately(movie_id, movie_data)

print(f'First addition: {result1}')
print(f'Second addition (should skip): {result2}')

import json
with open('data.json') as f:
    data = json.load(f)
    count = sum(1 for k in data.get('movies', {}) if k == movie_id)
    print(f'Movie appears {count} time(s) in data.json')
"
```

## Cleanup Commands

### Remove Test Movies
```bash
# Remove test movies from data.json
python3 -c "
import json
with open('data.json') as f:
    data = json.load(f)

# Remove test movies
test_prefixes = ['test_', 'perf_test_', 'duplicate_test_', 'atomic_test']
movies_to_remove = [
    movie_id for movie_id in data.get('movies', {})
    if any(movie_id.startswith(prefix) for prefix in test_prefixes)
]

for movie_id in movies_to_remove:
    del data['movies'][movie_id]
    print(f'Removed test movie: {movie_id}')

data['total_count'] = len(data['movies'])

with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f'Cleanup complete. {len(movies_to_remove)} test movies removed.')
"
```

### Clean Old Backups
```bash
# Remove backups older than 7 days (optional)
find backups/ -name "data.json.backup-*" -mtime +7 -exec rm {} \;
echo "Old backups cleaned up"
```

## Integration Testing Commands

### Real-World Integration Test
```bash
# Run comprehensive integration test (recommended)
./run_integration_test.sh

# Direct execution without wrapper
python3 test_integration_real_discovery.py

# Check integration test results
ls -la logs/integration_test_results_*.json

# View latest test report
cat $(ls -t logs/integration_test_results_*.json | head -1)

# Clean up integration test artifacts
rm -f data.json.pre_test_*
find logs -name "integration_test_*" -mtime +30 -delete
```

### Integration Test Monitoring
```bash
# Watch test progress in real time
tail -f logs/integration_test_results_$(date +%Y%m%d)*.json

# Check for any integration test failures
find logs -name "integration_test_failure_*.json" -mtime -7

# Verify integration test backup creation
ls -la backups/data.backup-$(date +%Y%m%d)*.json
```

## Verification Checklist

### Unit Testing (Development)
Run these commands to verify individual components:

```bash
# 1. Full dependency verification
python3 verify_enhanced_dependencies.py
echo "✅ Dependency verification: Check all tests pass"

# 2. End-to-end functional tests
python3 test_enhanced_immediate_writing_dependencies.py
echo "✅ Functional tests: Check all scenarios pass"

# 3. Manual dependency checks
python3 -c "from pipeline.generator import DataGenerator; g=DataGenerator(); print('✅ Generator loads:', bool(g.validator and g.storage))"

# 4. Performance check
time python3 -c "from pipeline.generator import DataGenerator; g=DataGenerator(); print('✅ Performance acceptable:', g.add_movie_to_site_immediately('perf_check', {'title':'Test','digital_date':'2024-12-16','providers':{'streaming':[],'rent':[],'buy':[]}}))"

# 5. Backup verification
ls -la backups/data.json.backup-* | tail -1
echo "✅ Backups: Check recent backup exists"

# 6. Schema validation check
python3 -c "from pipeline.generator import DataGenerator; g=DataGenerator(); print('✅ Schema validation:', g.validator.validate_data_json_schema('data.json'))"
```

### Integration Testing (Pre-Production)
Run these commands before major releases:

```bash
# 1. Real-world integration test
./run_integration_test.sh
echo "✅ Integration test: Check all components work together"

# 2. Verify real movie addition
python3 -c "
import json
if os.path.exists('logs/integration_test_results_$(date +%Y%m%d)*.json'):
    with open(glob.glob('logs/integration_test_results_*.json')[-1]) as f:
        report = json.load(f)
    print(f'✅ Integration result: {report[\"status\"]}')
    print(f'✅ Movie tested: {report[\"movie_tested\"][\"title\"]}')
else:
    print('❌ No recent integration test results found')
"

# 3. Check production readiness
python3 -c "
import json, glob, os
# Check unit tests passed
if os.path.exists('verification_report.json'):
    with open('verification_report.json') as f:
        unit_report = json.load(f)
    unit_passed = unit_report.get('summary', {}).get('failed', 1) == 0
else:
    unit_passed = False

# Check integration tests passed
integration_files = glob.glob('logs/integration_test_results_*.json')
if integration_files:
    with open(max(integration_files)) as f:
        integration_report = json.load(f)
    integration_passed = integration_report.get('status') == 'PASSED'
else:
    integration_passed = False

print(f'✅ Unit tests: {\"PASSED\" if unit_passed else \"FAILED\"}')
print(f'✅ Integration tests: {\"PASSED\" if integration_passed else \"FAILED\"}')
print(f'✅ Production ready: {\"YES\" if unit_passed and integration_passed else \"NO\"}')
"
```

**Expected output:** All checks should show ✅ with successful results.

## Monitoring Immediate Write Failures

### Check Recent Failures
```bash
# Show last 10 immediate write failures
python scripts/check_immediate_write_failures.py

# Show last 5 failures only
python scripts/check_immediate_write_failures.py --last 5

# Show summary for last 48 hours
python scripts/check_immediate_write_failures.py --hours 48

# Check if failure log exists
ls -la logs/immediate_write_failures.jsonl
```

### Manual Failure Log Analysis
```bash
# View raw failure log
cat logs/immediate_write_failures.jsonl

# Count total failures
wc -l logs/immediate_write_failures.jsonl

# Get failure types in the last day
python3 -c "
import json
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=1)
with open('logs/immediate_write_failures.jsonl') as f:
    recent_errors = []
    for line in f:
        failure = json.loads(line.strip())
        timestamp = datetime.fromisoformat(failure['timestamp'])
        if timestamp >= cutoff:
            recent_errors.append(failure['error_type'])

from collections import Counter
print('Error types in last 24h:')
for error, count in Counter(recent_errors).items():
    print(f'  {error}: {count}')
"

# Check TMDB availability correlation
python3 -c "
import json
with open('logs/immediate_write_failures.jsonl') as f:
    failures = [json.loads(line.strip()) for line in f]

tmdb_available = sum(1 for f in failures if f.get('tmdb_available'))
tmdb_unavailable = len(failures) - tmdb_available
print(f'Failures with TMDB available: {tmdb_available}')
print(f'Failures with TMDB unavailable: {tmdb_unavailable}')
"
```

### Cleanup Failure Logs
```bash
# Archive old failure logs (optional)
if [ -f logs/immediate_write_failures.jsonl ]; then
    cp logs/immediate_write_failures.jsonl logs/immediate_write_failures.$(date +%Y%m%d).jsonl
    > logs/immediate_write_failures.jsonl  # Clear current log
    echo "Failure log archived and cleared"
fi

# Remove old archived logs (older than 30 days)
find logs -name "immediate_write_failures.*.jsonl" -mtime +30 -delete
```

## Troubleshooting

### If verification fails:
1. Check Python path: `python3 -c "import sys; print(sys.path)"`
2. Verify pipeline imports: `python3 -c "from pipeline.generator import DataGenerator"`
3. Check file permissions: `ls -la data.json backups/`
4. Verify dependencies: `pip3 list | grep -E "(tmdb|requests)"`

### If tests fail:
1. Check test directory permissions: `ls -la /tmp/`
2. Verify disk space: `df -h .`
3. Run with verbose output: `python3 verify_enhanced_dependencies.py 2>&1 | grep -E "(ERROR|FAIL|Exception)"`

### If performance is slow:
1. Check data.json size: `ls -lh data.json`
2. Monitor system resources: `top -p $(pgrep python3)`
3. Profile validation: `time python3 -c "from pipeline.generator import DataGenerator; g=DataGenerator(); g.validator.validate_data_json_schema('data.json')"`