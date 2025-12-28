#!/bin/bash

# NRW Production - Integration Test Runner
# Executes real-world integration test with safety checks

set -e  # Exit on any error

echo "🧪 NRW Production - Integration Test Runner"
echo "==========================================="

# Check if we're in the right directory
if [ ! -f "test_integration_real_discovery.py" ]; then
    echo "❌ Error: Must be run from project root directory"
    echo "Expected files: test_integration_real_discovery.py"
    exit 1
fi

# Check for required files
echo "🔍 Checking prerequisites..."

REQUIRED_FILES=("movie_tracking.json" "pipeline/generator.py")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Error: Required file missing: $file"
        exit 1
    fi
done

# Check Python environment
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found"
    exit 1
fi

# Check TMDB API key (optional warning)
if [ -z "$TMDB_API_KEY" ] && [ ! -f "config.yaml" ]; then
    echo "⚠️  Warning: TMDB_API_KEY not set and config.yaml not found"
    echo "   TMDB calls will fail, but test will still verify fallback behavior"
fi

echo "✅ Prerequisites check passed"

# Create necessary directories
mkdir -p logs backups

# Show current state
echo ""
echo "📊 Current State:"
if [ -f "data.json" ]; then
    MOVIE_COUNT=$(python3 -c "import json; data=json.load(open('data.json')); print(len(data.get('movies', [])))" 2>/dev/null || echo "unknown")
    echo "   📄 data.json exists with $MOVIE_COUNT movies"
else
    echo "   📄 data.json does not exist (will be created)"
fi

TRACKING_COUNT=$(python3 -c "import json; data=json.load(open('movie_tracking.json')); print(len(data))" 2>/dev/null || echo "unknown")
echo "   📋 movie_tracking.json contains $TRACKING_COUNT entries"

# Ask for confirmation
echo ""
read -p "🚀 Ready to run integration test? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Test cancelled by user"
    exit 0
fi

# Run the test
echo ""
echo "🎬 Executing integration test..."
echo "================================="

# Execute test and capture exit code
if python3 test_integration_real_discovery.py; then
    echo ""
    echo "🎉 Integration test completed successfully!"

    # Show results
    echo ""
    echo "📊 Results Summary:"
    if [ -f "data.json" ]; then
        NEW_COUNT=$(python3 -c "import json; data=json.load(open('data.json')); print(len(data.get('movies', [])))" 2>/dev/null || echo "unknown")
        echo "   📄 data.json now contains $NEW_COUNT movies"
    fi

    BACKUP_COUNT=$(find backups -name "data.backup-*.json" 2>/dev/null | wc -l)
    echo "   💾 Total backup files: $BACKUP_COUNT"

    LOG_FILES=$(find logs -name "integration_test_results_*.json" 2>/dev/null | wc -l)
    echo "   📋 Test reports: $LOG_FILES"

    # Show latest log
    LATEST_LOG=$(find logs -name "integration_test_results_*.json" -print0 2>/dev/null | xargs -0 ls -t | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "   📄 Latest report: $LATEST_LOG"
    fi

    echo ""
    echo "✅ Integration test PASSED - Enhanced discovery pipeline is working correctly!"

else
    echo ""
    echo "❌ Integration test FAILED!"

    # Show failure information
    LATEST_FAILURE=$(find logs -name "integration_test_failure_*.json" -print0 2>/dev/null | xargs -0 ls -t | head -1)
    if [ -n "$LATEST_FAILURE" ]; then
        echo "   📄 Failure report: $LATEST_FAILURE"
        echo ""
        echo "🔍 Error details:"
        python3 -c "
import json
try:
    with open('$LATEST_FAILURE') as f:
        report = json.load(f)
    print(f\"   Error: {report.get('error_message', 'Unknown error')}\")
except:
    print('   Unable to read failure report')
"
    fi

    echo ""
    echo "💡 Troubleshooting tips:"
    echo "   1. Check TMDB API key configuration"
    echo "   2. Verify movie_tracking.json has available movies"
    echo "   3. Ensure data.json is not corrupted"
    echo "   4. Check file permissions"

    exit 1
fi