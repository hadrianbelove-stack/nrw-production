#!/bin/bash

# sync_daily_updates.sh - Merge automation data from bot
#
# Usage:
#   ./sync_daily_updates.sh
#
# What it does:
# 1. Fetches automation-updates branch
# 2. Shows what changed
# 3. Merges into current branch (main)
# 4. Shows latest movies added
#
# When to run:
# - Daily after automation completes (check GitHub Actions)
# - Before starting work (ensures you have latest data)
# - After making local changes (merge automation before committing)
#
# Troubleshooting:
# - "Branch not found": Run GitHub Actions workflow first
# - "Merge conflicts": Run `git merge --abort`, then `python3 generate_data.py` to regenerate
# - "Permission denied": Run `chmod +x sync_daily_updates.sh`

set -e  # Exit on error
set -u  # Exit on undefined variable

echo "🔄 Syncing daily automation updates..."

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: Not in a git repository"
    echo "   Run this script from the project root directory"
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --staged --quiet; then
    echo "❌ Error: Uncommitted changes detected"
    echo "   You have uncommitted changes that could conflict with automation data."
    echo ""
    echo "   To fix:"
    echo "   1. Commit your changes: git add -A && git commit -m \"...\""
    echo "   2. Or stash them: git stash"
    echo "   3. Run this script again"
    echo "   4. If stashed: git stash pop"
    exit 1
fi

# Check if we're on main branch
current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    echo "❌ Error: Not on main branch"
    echo "   Current branch: $current_branch"
    echo "   This script merges into the current branch, which should be 'main'."
    echo ""
    echo "   To fix:"
    echo "   1. Switch to main: git checkout main"
    echo "   2. Run this script again"
    echo "   3. Or add --force flag to allow merging into $current_branch (advanced)"
    exit 1
fi

# Fetch from origin and check if local main is up to date
echo "📡 Fetching from origin..."
git fetch origin

# Check if local main is behind origin/main
local_main=$(git rev-parse HEAD)
origin_main=$(git rev-parse origin/main)
if [ "$local_main" != "$origin_main" ]; then
    echo "❌ Error: Local main is not up to date with origin/main"
    echo "   Your local main branch is behind the remote."
    echo ""
    echo "   To fix:"
    echo "   1. Run: git pull --ff-only origin main"
    echo "   2. Run this script again"
    exit 1
fi

# Fetch automation branch
echo "📡 Fetching automation-updates branch..."
if ! git fetch origin automation-updates 2>/dev/null; then
    echo "❌ Error: automation-updates branch not found"
    echo "   The automation hasn't run yet, or the branch was deleted."
    echo ""
    echo "   To fix:"
    echo "   1. Go to GitHub Actions → Daily Update → Run workflow"
    echo "   2. Wait for workflow to complete (~5 minutes)"
    echo "   3. Run this script again"
    exit 1
fi

# Check if already up to date
if git diff --quiet HEAD origin/automation-updates; then
    echo "✅ Already up to date"
    echo "   No new automation changes to merge"
    exit 0
fi

# Show what changed
echo ""
echo "📊 Changes from automation:"
echo "=========================="
git diff --stat HEAD origin/automation-updates
echo ""

# Show commit messages from automation branch
echo "📝 Automation commits:"
echo "====================="
git log --oneline HEAD..origin/automation-updates
echo ""

# Merge automation branch
echo "🔀 Merging automation updates..."
if ! git merge origin/automation-updates -m "Sync automation updates - $(date +%Y-%m-%d)"; then
    echo ""
    echo "❌ Error: Merge conflicts detected"
    echo "   The automation changes conflict with your local work."
    echo ""
    echo "   To fix:"
    echo "   1. Run: git merge --abort"
    echo "   2. Review conflicts in: data.json, movie_tracking.json"
    echo "   3. Option A: Regenerate data.json: python3 generate_data.py --full"
    echo "   4. Option B: Manually resolve conflicts"
    echo "   5. Run this script again"
    exit 1
fi

echo "✅ Automation data synced!"

# Show latest movies
echo ""
echo "🎬 Latest movies added:"
echo "======================"
python3 -c "
import json
import sys
from datetime import datetime, timedelta

try:
    with open('data.json', 'r') as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f'❌ Could not read data.json: {e}')
    sys.exit(0)  # Don't fail the script, just skip movie display

movies = data.get('movies', [])
if not movies:
    print('No movies found in data.json')
    sys.exit(0)

# Filter movies from last 2 days
cutoff_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
recent_movies = [
    m for m in movies
    if m.get('digital_date', '') >= cutoff_date
]

# Sort by date descending
recent_movies.sort(key=lambda x: x.get('digital_date', ''), reverse=True)

# Show top 5 recent movies
count = 0
for movie in recent_movies[:5]:
    title = movie.get('title', 'Unknown Title')
    date = movie.get('digital_date', 'Unknown Date')
    print(f'• {title} - {date}')
    count += 1

if count == 0:
    print('No movies added in the last 2 days')
else:
    print(f'')
    print(f'Showing {count} most recent movies (last 2 days)')
    if len(recent_movies) > 5:
        print(f'({len(recent_movies) - 5} more recent movies not shown)')
"

echo ""
echo "🎯 Summary:"
echo "=========="
echo "• Automation data has been merged into your main branch"
echo "• You can now continue working normally"
echo "• Next automation run: Check GitHub Actions for schedule"
echo "• To see all changes: git log --oneline -10"