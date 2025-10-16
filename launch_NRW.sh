#!/bin/bash
# launch_NRW.sh - One-command daily startup for New Release Wall

set -e

# Cleanup function for server process
cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 $SERVER_PID 2>/dev/null; then
        echo ''
        echo '🛑 Shutting down server...'
        kill $SERVER_PID 2>/dev/null
    fi
}

# Register cleanup for all exit paths
trap cleanup EXIT INT TERM

echo "🎬 NEW RELEASE WALL - Daily Startup"
echo "===================================="
echo ""

# Step 0: Check dependencies
echo "🔍 Step 0: Checking dependencies..."
command -v python3 >/dev/null || { echo "   ❌ Python 3 not found. Install with: brew install python3 (macOS) or apt-get install python3 (Linux)"; exit 1; }
command -v git >/dev/null || { echo "   ❌ Git not found. Install with: brew install git (macOS) or apt-get install git (Linux)"; exit 1; }
if command -v open >/dev/null; then
    BROWSER_CMD="open"
elif command -v xdg-open >/dev/null; then
    BROWSER_CMD="xdg-open"
else
    BROWSER_CMD=""
    echo "   ⚠️ No browser opener found. Will skip auto-opening browser."
fi
echo "   ✅ All dependencies available"
echo ""

# Step 1: Pull latest data from GitHub automation
echo "📥 Step 1: Pulling latest data from automation..."
set +e  # Temporarily disable exit on error for git operations
if git fetch origin --quiet 2>/dev/null; then
    # Capture git pull output and exit status separately
    PULL_OUTPUT=$(git pull origin main 2>&1)
    PULL_EXIT_CODE=$?

    if [ $PULL_EXIT_CODE -eq 0 ]; then
        # Pull succeeded, check if there were updates
        if echo "$PULL_OUTPUT" | grep -q "Already up to date"; then
            echo "   ✅ Data is current"
        else
            echo "   ✅ New data pulled from GitHub"
        fi
    else
        echo "   ⚠️ Git pull failed (exit code: $PULL_EXIT_CODE). Using local data."
    fi
else
    echo "   ⚠️ Git fetch failed (offline?). Using local data."
fi
set -e  # Re-enable exit on error
echo ""

# Step 2: Brief status report
echo "📊 Step 2: Quick Status Report"

# Validate data.json exists and is readable
if [ ! -f data.json ]; then
    echo "   ❌ data.json not found. Run 'python3 generate_data.py' first."
    exit 1
fi

# Quick JSON validation
if ! python3 -c "import json; json.load(open('data.json'))" 2>/dev/null; then
    echo "   ❌ data.json is corrupted. Regenerate with: python3 generate_data.py"
    exit 1
fi
python3 << 'PYTHON'
import json
import os
from datetime import datetime, timedelta

with open('data.json') as f:
    data = json.load(f)

movies = data['movies']
today = datetime.now().date()
yesterday = today - timedelta(days=1)

today_str = today.isoformat()
yesterday_str = yesterday.isoformat()

today_count = len([m for m in movies if m.get('digital_date', '').startswith(today_str)])
yesterday_count = len([m for m in movies if m.get('digital_date', '').startswith(yesterday_str)])

# Check for movie_tracking.json and get tracked total
tracked_total = None
if os.path.exists('movie_tracking.json'):
    try:
        with open('movie_tracking.json') as f:
            tracking_db = json.load(f)
        tracked_total = len(tracking_db.get('movies', {}))
    except (json.JSONDecodeError, KeyError):
        print("   ⚠️ Warning: movie_tracking.json found but corrupted")

print(f"   Total movies on wall: {len(movies)}")
if tracked_total is not None:
    print(f"   Tracked: {tracked_total} / Displayed: {len(movies)}")
else:
    print("   ⚠️ movie_tracking.json not found, skipping tracked count")
print(f"   New today ({today.strftime('%b %d')}): {today_count}")
print(f"   New yesterday ({yesterday.strftime('%b %d')}): {yesterday_count}")
print(f"   Last generated: {data.get('generated_at', 'unknown')[:19]}")
PYTHON
echo ""

# Step 3: Assistant context reminder
echo "📋 Step 3: Context Files for AI Assistants"
echo "   When working with AI assistants, read these files in order:"
echo "   1. DAILY_CONTEXT.md (current state, recent changes, active issues) ⭐ PRIMARY"
echo "   2. PROJECT_CHARTER.md (governance & amendments)"
echo "   3. NRW_DATA_WORKFLOW_EXPLAINED.md (technical pipeline)"
echo ""

# Step 4: Start server and open browser
echo "🚀 Step 4: Starting local server..."

# Check for port conflicts
PORT=8000
if command -v lsof >/dev/null; then
    # lsof is available, check for port conflicts
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "   ⚠️ Port 8000 in use, trying 8001..."
        PORT=8001
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo "   ❌ Ports 8000 and 8001 both in use. Stop other servers first."
            echo "   Try: lsof -ti:8000 | xargs kill"
            exit 1
        fi
    fi
else
    # lsof not available, show warning and continue
    echo "   ⚠️ Port conflict detection skipped (lsof not found)."
    echo "   Install lsof for better port management: brew install lsof (macOS) or apt-get install lsof (Linux)"
    echo "   If server fails to start, manually check for port conflicts."
fi

echo "   Starting server on port $PORT"
echo "   Press Ctrl+C to stop the server when done"
echo "===================================="
echo ""

# Start server in background
python3 -m http.server $PORT &
SERVER_PID=$!

# Wait for server to be ready with retry loop
echo -n "   Waiting for server to start"
RETRY_COUNT=0
MAX_RETRIES=10
SERVER_READY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Check if server process is still alive
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo ""
        echo "   ❌ Server failed to start (process died)"
        exit 1
    fi

    # Try to connect to server
    if command -v curl >/dev/null && curl --silent --fail --connect-timeout 1 http://localhost:$PORT >/dev/null 2>&1; then
        SERVER_READY=true
        break
    elif command -v lsof >/dev/null && lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        SERVER_READY=true
        break
    fi

    echo -n "."
    sleep 0.5
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

echo ""

if [ "$SERVER_READY" = false ]; then
    echo "   ❌ Server failed to start on port $PORT after $MAX_RETRIES attempts"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

# Open browser if available
if [ -n "$BROWSER_CMD" ]; then
    echo "   Opening browser at http://localhost:$PORT"
    $BROWSER_CMD http://localhost:$PORT
else
    echo "   Visit: http://localhost:$PORT"
fi

# Wait for user to stop (Ctrl+C)
wait $SERVER_PID
