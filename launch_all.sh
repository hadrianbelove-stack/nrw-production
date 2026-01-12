#!/bin/bash

# NRW Unified Launcher - Single Command Launch
# Per Amendment 031: Launch both admin panel and public site
# Admin in background, site in foreground, with port conflict handling

set -e
cd "$(dirname "$0")"

# Sync with remote before launching
git pull --ff-only origin main 2>/dev/null || true

# Port configuration
ADMIN_PORT=${ADMIN_PORT:-5556}
SITE_PORT=${SITE_PORT:-3000}

# Check if a port is available
check_port() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        if lsof -ti:$port >/dev/null 2>&1; then
            return 1  # Port is in use
        fi
    fi
    return 0  # Port available or can't check
}

# Handle port conflicts
if ! check_port $ADMIN_PORT; then
    echo "⚠️  Port $ADMIN_PORT in use, trying 5557..."
    ADMIN_PORT=5557
fi

if ! check_port $SITE_PORT; then
    echo "⚠️  Port $SITE_PORT in use, trying 3001..."
    SITE_PORT=3001
fi

echo "🎬 NRW Production Launcher"
echo "=========================="
echo "Admin: http://localhost:$ADMIN_PORT (background)"
echo "Site:  http://localhost:$SITE_PORT (foreground)"
echo ""

# Launch admin in background
echo "🚀 Starting admin panel..."
ADMIN_PORT=$ADMIN_PORT python3 admin.py &
ADMIN_PID=$!

# Setup cleanup with graceful shutdown
cleanup() {
    echo ""
    echo "🛑 Shutting down..."

    # Send SIGTERM to both processes
    echo "Sending SIGTERM to processes..."
    kill -TERM $ADMIN_PID 2>/dev/null || true
    [ -n "$SITE_PID" ] && kill -TERM $SITE_PID 2>/dev/null || true

    # Wait up to 5 seconds for graceful shutdown
    for i in {1..5}; do
        if ! kill -0 $ADMIN_PID 2>/dev/null && ! kill -0 $SITE_PID 2>/dev/null; then
            echo "✓ Clean shutdown"
            exit 0
        fi
        sleep 1
    done

    # Force kill if still running
    echo "⚠️  Force killing remaining processes..."
    kill -KILL $ADMIN_PID 2>/dev/null || true
    [ -n "$SITE_PID" ] && kill -KILL $SITE_PID 2>/dev/null || true
    exit 0
}

trap cleanup INT TERM

# Poll admin port for readiness with timeout
echo "Waiting for admin to be ready..."
TIMEOUT=30
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$ADMIN_PORT 2>/dev/null | grep -q "200"; then
        echo "✓ Admin ready"
        break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "⚠️  Admin did not respond after ${TIMEOUT}s, continuing anyway..."
fi

# Auto-open browsers if available
if command -v open >/dev/null 2>&1; then
    echo "Opening browsers..."
    open http://localhost:$ADMIN_PORT
    open http://localhost:$SITE_PORT
fi

# Launch site in foreground
echo "🚀 Starting site (Ctrl+C to stop both)..."
python3 -m http.server $SITE_PORT &
SITE_PID=$!
wait $SITE_PID