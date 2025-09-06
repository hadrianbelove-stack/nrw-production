#!/bin/bash
# NRW — make the dynamic page work with your current repo layout
set -euo pipefail
cd "${REPO:-$PWD}"

echo "Setting up New Release Wall dynamic page..."

# Create assets directory if it doesn't exist
mkdir -p assets

# Use the freshest data file you have
if [ -f output/data.json ]; then
  echo "Using output/data.json as data source"
  cp -f output/data.json assets/data.json
elif [ -f _resume_tmp/current_releases.json ]; then
  echo "Using _resume_tmp/current_releases.json as data source"  
  cp -f _resume_tmp/current_releases.json assets/data.json
elif [ -f current_releases.json ]; then
  echo "Using current_releases.json as data source"
  cp -f current_releases.json assets/data.json
elif [ -f data/current_releases.json ]; then
  echo "Using data/current_releases.json as data source"
  cp -f data/current_releases.json assets/data.json
else
  echo "No data file found in expected locations"; exit 1
fi

# Copy the site.html template to root for direct access
if [ -f templates/site.html ]; then
  echo "Copying templates/site.html to root"
  cp -f templates/site.html site.html
else
  echo "Warning: templates/site.html not found"
fi

# Ensure the runtime script is where site.html expects it
if [ -f render_approved.js ]; then
  echo "Copying render_approved.js to assets/"
  cp -f render_approved.js assets/render_approved.js
else
  echo "Warning: render_approved.js not found"
fi

# Create a simple style override file if it doesn't exist
if [ ! -f assets/style_overrides.css ]; then
  echo "Creating basic style overrides"
  cat > assets/style_overrides.css << 'EOF'
/* Dynamic page style overrides */
.movie-grid {
    justify-content: center;
}

.movie-card {
    width: 180px;
    height: 320px;
}
EOF
fi

# Check if server is already running on port 5500
if lsof -i :5500 >/dev/null 2>&1; then
  echo "Server already running on port 5500"
else
  echo "Starting HTTP server on port 5500..."
  python3 -m http.server 5500 >/dev/null 2>&1 &
  SERVER_PID=$!
  echo $SERVER_PID > .nrw_http_pid
  echo "Server started with PID $SERVER_PID"
  sleep 2
fi

# Open the dynamic page
if command -v open >/dev/null 2>&1; then
  echo "Opening dynamic page in Safari..."
  open -a Safari "http://localhost:5500/site.html"
else
  echo "Open manually: http://localhost:5500/site.html"
fi

echo "Dynamic page setup complete!"
echo "Access at: http://localhost:5500/site.html"
echo "Data source: assets/data.json"
echo "To stop server: kill \$(cat .nrw_http_pid 2>/dev/null || echo 'PID file not found')"