#!/bin/bash
# NRW Local Daily Script
# Runs via launchd every 30 min; keeps retrying until today's CI data is pulled.
# 1. Pulls latest data from GitHub
# 2. Uploads new trailers to B2
# 3. Stamps hosted trailer URLs into data.json and pushes to GitHub
# Sentinel is only created after we confirm CI has run today (via run_diagnostics.json).

export PATH="/opt/homebrew/bin:$PATH"
PROJECT_DIR="/Users/hadrianbelove/Downloads/nrw-production"
LOG="$PROJECT_DIR/logs/launchagent.log"

# Already pulled today's CI data? Done.
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
/usr/bin/git checkout -- data.json data_archive.json movie_tracking.json metrics/ >> "$LOG" 2>&1
# Clean untracked files in metrics/ so they don't block git pull
/usr/bin/git clean -f metrics/ >> "$LOG" 2>&1

# Stash any other local changes
STASHED=false
if ! /usr/bin/git diff --quiet || ! /usr/bin/git diff --cached --quiet; then
    /usr/bin/git stash >> "$LOG" 2>&1
    STASHED=true
    echo "  Stashed local changes" >> "$LOG"
fi

/usr/bin/git pull --rebase origin main >> "$LOG" 2>&1
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

# Step 3: Stamp hosted trailer URLs into data.json and push to GitHub
# This eliminates the ~19-hour gap where trailers show as YouTube fallbacks.
# Safe: CI finishes 5+ hours before this runs. Stamp is idempotent.
echo "Stamping hosted trailer URLs..." >> "$LOG"
/opt/homebrew/bin/python3.11 scripts/trailer_pipeline.py stamp >> "$LOG" 2>&1

if ! /usr/bin/git diff --quiet data.json 2>/dev/null; then
    echo "  Pushing stamped trailers to GitHub..." >> "$LOG"
    if NRW_ALLOW_DATA_COMMIT=1 /usr/bin/git commit data.json -m "Local trailer stamp — APPROVED: DELETE" >> "$LOG" 2>&1; then
        if /usr/bin/git push origin main >> "$LOG" 2>&1; then
            echo "  Pushed successfully" >> "$LOG"
        else
            echo "  WARNING: Push failed — CI will stamp tomorrow" >> "$LOG"
        fi
    else
        echo "  WARNING: Commit failed — CI will stamp tomorrow" >> "$LOG"
    fi
else
    echo "  No new trailers to stamp" >> "$LOG"
fi

# Only create sentinel if we have today's CI data
CI_DATE=$(/usr/bin/python3 -c "import json; print(json.load(open('metrics/run_diagnostics.json'))['timestamp'][:10])" 2>/dev/null)
TODAY=$(date +%Y-%m-%d)
if [ "$CI_DATE" = "$TODAY" ]; then
    touch "$SENTINEL"
    echo "  CI data is current ($CI_DATE) — sentinel created, done for today" >> "$LOG"
else
    echo "  CI data is stale ($CI_DATE) — will retry next cycle" >> "$LOG"
fi
echo "=== Done: $(date) ===" >> "$LOG"
