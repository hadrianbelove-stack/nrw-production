#!/bin/bash

# NRW Production Site Launcher
# Regenerates data and launches local web server

set -e  # Exit on error

echo "🎬 NRW Production Site Launcher"
echo "================================"
echo ""

# Parse arguments
SKIP_REGEN=false
FULL_REGEN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-regen)
            SKIP_REGEN=true
            shift
            ;;
        --full)
            FULL_REGEN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-regen] [--full]"
            echo "  --skip-regen: Skip data regeneration, just launch server"
            echo "  --full: Do full data regeneration (slower but complete)"
            exit 1
            ;;
    esac
done

# Kill any existing server on port 8001
echo "🧹 Checking for existing server..."
if lsof -ti:8001 > /dev/null 2>&1; then
    echo "   Stopping existing server on port 8001..."
    lsof -ti:8001 | xargs kill
    sleep 1
fi

# Regenerate data (unless skipped)
if [ "$SKIP_REGEN" = false ]; then
    echo ""
    echo "🔄 Regenerating data..."

    if [ "$FULL_REGEN" = true ]; then
        echo "   Running FULL regeneration (this may take 30+ minutes)..."
        TMDB_API_KEY="99b122ce7fa3e9065d7b7dc6e660772d" \
        WATCHMODE_API_KEY="bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp" \
        python3 generate_data.py --full
    else
        echo "   Running incremental update (recent movies only)..."
        TMDB_API_KEY="99b122ce7fa3e9065d7b7dc6e660772d" \
        WATCHMODE_API_KEY="bBMpVr31lRfUsSFmgoQp0jixDrQt8DIKCVg7EFdp" \
        python3 generate_data.py
    fi

    if [ $? -eq 0 ]; then
        echo "   ✅ Data regeneration complete!"
    else
        echo "   ⚠️  Data regeneration had errors, but continuing..."
    fi
else
    echo ""
    echo "⏭️  Skipping data regeneration (using existing data.json)"
fi

# Start server
echo ""
echo "🚀 Starting web server on port 8001..."
python3 -m http.server 8001 --bind 127.0.0.1 > /dev/null 2>&1 &
SERVER_PID=$!

sleep 1

# Verify server started
if lsof -ti:8001 > /dev/null 2>&1; then
    echo "   ✅ Server running at http://localhost:8001 (PID: $SERVER_PID)"
    echo ""
    echo "🌐 Opening browser..."
    open http://localhost:8001
    echo ""
    echo "✨ Site is live!"
    echo ""
    echo "To stop the server:"
    echo "   kill $SERVER_PID"
    echo "   OR run: lsof -ti:8001 | xargs kill"
else
    echo "   ❌ Failed to start server"
    exit 1
fi
