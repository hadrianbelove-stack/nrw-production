#!/bin/bash
# NRW Local Daily Script
# Runs via launchd every 30 min; sentinel file ensures it only runs once per day.
# 1. Pulls latest data from GitHub
# 2. Uploads new trailers to B2 (CI stamps URLs into data.json next morning)

PROJECT_DIR="/Users/hadrianbelove/Downloads/nrw-production"
LOG="$PROJECT_DIR/logs/launchagent.log"

# Already ran today? Skip.
SENTINEL="/var/tmp/nrw_daily_$(date +%Y%m%d)"
if [ -f "$SENTINEL" ]; then
    exit 0
fi

echo "" >> "$LOG"
echo "=== NRW Local Daily: $(date) ===" >> "$LOG"

cd "$PROJECT_DIR" || { echo "ERROR: Cannot cd to $PROJECT_DIR" >> "$LOG"; exit 1; }

# Step 1: Pull latest from GitHub
# Strategy: discard local data.json changes (CI version is authoritative),
# stash everything else, pull, then restore stash.
echo "Pulling latest from GitHub..." >> "$LOG"

# Always reset CI-regenerated files before pulling (CI versions are authoritative)
/usr/bin/git checkout -- data.json movie_tracking.json metrics/ >> "$LOG" 2>&1

# Stash any other local changes
STASHED=false
if ! /usr/bin/git diff --quiet || ! /usr/bin/git diff --cached --quiet; then
    /usr/bin/git stash >> "$LOG" 2>&1
    STASHED=true
    echo "  Stashed local changes" >> "$LOG"
fi

/usr/bin/git pull --ff-only origin main >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
    echo "WARNING: git pull failed" >> "$LOG"
fi

if [ "$STASHED" = true ]; then
    /usr/bin/git stash pop >> "$LOG" 2>&1 || echo "WARNING: stash pop had conflicts — resolve manually" >> "$LOG"
    echo "  Restored local changes" >> "$LOG"
fi

# Step 2: Upload new trailers to B2 (download from YouTube + upload, no data.json writes)
echo "Hosting new trailers..." >> "$LOG"
/opt/homebrew/bin/python3.11 scripts/trailer_pipeline.py host >> "$LOG" 2> >(grep -v "Cookies.binarycookies" >> "$LOG")

touch "$SENTINEL"
echo "=== Done: $(date) ===" >> "$LOG"
