#!/bin/bash
# NRW Daily Wrapper - Runs once per day, catches up if missed
# Runs at 4 AM OR on wake/login if today's run was missed

set -e
cd "$(dirname "$0")/.."

LOG_FILE="$HOME/Library/Logs/nrw_daily.out"
TODAY=$(date +%Y-%m-%d)

# Check if today's run already happened by looking at metrics/daily.jsonl
if [ -f "metrics/daily.jsonl" ]; then
    LAST_RUN=$(tail -1 metrics/daily.jsonl 2>/dev/null | grep -o '"date": "[^"]*"' | cut -d'"' -f4)
    if [ "$LAST_RUN" = "$TODAY" ]; then
        echo "$(date): Already ran today ($TODAY), skipping" >> "$LOG_FILE"
        exit 0
    fi
fi

echo "$(date): Starting daily run for $TODAY" >> "$LOG_FILE"

# Pull latest from remote
git pull --ff-only origin main 2>/dev/null || true

# Run the orchestrator
source ~/.nrw.env 2>/dev/null || true
/usr/bin/python3 daily_orchestrator.py >> "$LOG_FILE" 2>&1

echo "$(date): Daily run complete" >> "$LOG_FILE"
