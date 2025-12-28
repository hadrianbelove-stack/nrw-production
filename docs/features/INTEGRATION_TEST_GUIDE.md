# Integration Test Guide - Enhanced Movie Discovery Pipeline

## Overview

This integration test validates the enhanced `add_movie_to_site_immediately()` function using real data files, TMDB API calls, and file system operations. It provides comprehensive end-to-end testing of your movie discovery pipeline.

## What This Test Does

The integration test:
1. **Automatically finds a suitable movie** from your tracking data (no hardcoded IDs)
2. **Backs up your current data.json** before making any changes
3. **Executes real movie discovery** using TMDB API and file operations
4. **Verifies all enhancements work correctly**: atomic writes, TMDB fallback, schema validation, discovery metadata
5. **Tests duplicate detection** by attempting to add the same movie twice
6. **Generates detailed reports** with pass/fail status
7. **Automatically restores backups** if anything goes wrong

## Prerequisites

### Required Files
- `movie_tracking.json` - Must contain at least one movie with status "available"
- `pipeline/generator.py` - Enhanced discovery pipeline code
- `config.yaml` or `TMDB_API_KEY` environment variable - For TMDB API access

### System Requirements
- Python 3.6+
- All pipeline dependencies installed
- Write permissions in project directory

## How to Run the Test

### Option 1: Quick Test (Recommended)
```bash
./run_integration_test.sh
```

This wrapper script:
- ✅ Checks all prerequisites
- ✅ Shows current state before testing
- ✅ Asks for confirmation
- ✅ Runs the test with safety checks
- ✅ Shows detailed results summary

### Option 2: Direct Execution
```bash
python3 test_integration_real_discovery.py
```

Direct execution without safety wrapper.

## What to Expect

### Successful Test Output
```
🚀 Starting Real-World Integration Test
⏰ Test started at: 2024-12-17 14:30:15
============================================================
🔍 Verifying prerequisites...
   ✅ All prerequisites verified
📦 Creating backup of current state...
   ✅ Backed up data.json (536 movies) → data.json.pre_test_20241217_143015
🎯 Finding suitable test movie...
   ✅ Selected movie: A Suite Holiday Romance (ID: 1547925)
   📅 Digital date: 2024-12-15
   📺 Providers: ['streaming']
🎬 Executing movie discovery for A Suite Holiday Romance...
   ⏱️  Execution time: 1.23 seconds
   ✅ Function executed successfully
📋 Verifying data.json updates...
   ✅ Movie 1547925 found in data.json
   ✅ All required fields present
   ✅ Discovery metadata fields present
   ✅ Discovery metadata values verified
   ✅ TMDB fetch succeeded - full entry created
💾 Verifying backup creation...
   ✅ Backup file found: backups/data.backup-20241217_143016.json
   ✅ Backup contains 536 movies
🔍 Verifying schema compliance...
   ✅ Schema validation passed
🔄 Testing duplicate detection...
   ✅ Duplicate detection working correctly

📊 TEST SUMMARY
   🎬 Movie Tested: A Suite Holiday Romance (1547925)
   ⏱️  Total Duration: 3.45 seconds
   🔧 Function Execution: 1.23 seconds
   🌐 TMDB Success: True
   📄 Schema Valid: True
   💾 Backup Created: True
   🔄 Duplicate Detection: True
   📋 Full Report: logs/integration_test_results_20241217_143015.json

🎉 INTEGRATION TEST PASSED
✅ Integration test completed successfully!
```

### If TMDB Fails (Still Success)
```
🎬 Executing movie discovery for Test Movie...
   ⏱️  Execution time: 0.45 seconds
   ✅ Function executed successfully
📋 Verifying data.json updates...
   ✅ Movie found in data.json
   ✅ All required fields present
   ✅ Discovery metadata fields present
   ⚠️  TMDB fetch failed - minimal entry created
```

Even if TMDB fails, the test should still pass because the enhanced pipeline creates minimal entries as a fallback.

## What Gets Created

### Backup Files
```
backups/
├── data.backup-20241217_143016.json    # Automatic backup of data.json
└── data.json.pre_test_20241217_143015   # Manual backup from test
```

### Log Files
```
logs/
├── integration_test_results_20241217_143015.json  # Detailed test report
└── movie_1547925_entry.json                       # Copy of movie entry added
```

## Understanding Test Results

### Test Report Structure
```json
{
  "test_timestamp": "2024-12-17T14:30:15",
  "test_duration_seconds": 3.45,
  "movie_tested": {
    "id": "1547925",
    "title": "A Suite Holiday Romance",
    "digital_date": "2024-12-15"
  },
  "results": {
    "execution_time": 1.23,
    "function_result": true,
    "tmdb_success": true,
    "schema_valid": true,
    "duplicate_detection": true,
    "backup_created": "backups/data.backup-20241217_143016.json"
  },
  "status": "PASSED"
}
```

### Key Metrics to Watch
- **Execution Time**: Should be < 5 seconds
- **TMDB Success**: True means full entry, False means minimal fallback (both are fine)
- **Schema Valid**: Must be True
- **Duplicate Detection**: Must be True
- **Backup Created**: Should show backup file path

## When to Run This Test

### Recommended Timing
- **Before major releases**: Verify everything works before deployment
- **After code changes**: Confirm enhancements still function correctly
- **Monthly health checks**: Ensure ongoing system reliability
- **When investigating issues**: Diagnose discovery pipeline problems
- **New engineer onboarding**: Verify development environment setup

### Not Recommended
- **During production deployments**: Could interfere with live operations
- **When data.json is actively being updated**: Wait for quiet periods
- **Without recent backups**: Always have recent production backups

## Troubleshooting

### Common Issues

#### "No suitable test movies found"
**Cause**: All available movies are already in data.json or movie_tracking.json has no "available" movies.

**Solution**:
```bash
# Check available movies not in data.json
python3 -c "
import json
with open('movie_tracking.json') as f: tracking = json.load(f)
with open('data.json') as f: current = json.load(f)
existing_ids = {m['id'] for m in current.get('movies', [])}
available = [mid for mid, info in tracking.items()
            if info.get('status') == 'available' and mid not in existing_ids]
print(f'Available movies for testing: {len(available)}')
if available: print(f'Examples: {available[:3]}')
"
```

#### "TMDB API key not found"
**Cause**: TMDB configuration is missing.

**Solution**: The test will still pass with TMDB fallback, but to test full functionality:
```bash
export TMDB_API_KEY="your_api_key_here"
```

#### "Schema validation failed"
**Cause**: data.json structure is corrupted.

**Solution**: The test automatically restores from backup. Check the failure report for details.

#### "Permission denied"
**Cause**: Insufficient file permissions.

**Solution**:
```bash
chmod 755 .
chmod 644 data.json movie_tracking.json
chmod 755 backups logs
```

### Emergency Recovery

If the test fails and leaves your data in a bad state:
```bash
# Find the latest backup
ls -t data.json.pre_test_* | head -1

# Restore manually
cp data.json.pre_test_YYYYMMDD_HHMMSS data.json
```

## Advanced Usage

### Running with Specific Conditions
```bash
# Test with no existing data.json
mv data.json data.json.backup
python3 test_integration_real_discovery.py
mv data.json.backup data.json

# Test with corrupted data.json
echo "invalid json" > data.json
python3 test_integration_real_discovery.py  # Should restore from backup
```

### Integration with CI/CD
```bash
# Run test and capture result
if python3 test_integration_real_discovery.py; then
    echo "Integration test passed - safe to deploy"
else
    echo "Integration test failed - deployment blocked"
    exit 1
fi
```

## File Locations Reference

| File | Purpose | When Created |
|------|---------|--------------|
| `test_integration_real_discovery.py` | Main test script | Manual creation |
| `run_integration_test.sh` | Safety wrapper script | Manual creation |
| `data.json.pre_test_*` | State backup before test | Every test run |
| `backups/data.backup-*.json` | Automatic pipeline backups | When data.json exists |
| `logs/integration_test_results_*.json` | Detailed test reports | Every test run |
| `logs/integration_test_failure_*.json` | Failure analysis | On test failure |
| `logs/movie_*_entry.json` | Copy of added movie entry | Successful tests |

## Safety Features

### Automatic State Management
- ✅ Creates backup before any changes
- ✅ Automatically restores on failure
- ✅ Preserves original data integrity

### Dynamic Movie Selection
- ✅ No hardcoded movie IDs
- ✅ Adapts to current data state
- ✅ Multiple fallback candidates

### Comprehensive Verification
- ✅ Tests all enhanced features
- ✅ Validates schema compliance
- ✅ Verifies error handling

This integration test gives you confidence that your enhanced movie discovery pipeline works correctly in real-world conditions.