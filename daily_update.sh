#!/bin/bash
# Daily Update Script - Canonical workflow for NRW updates

# Navigate to correct repository location
cd ~/Downloads/nrw-production || exit 1

echo "=== NRW Daily Update - $(date) ==="

# Step 1: Check for new digital releases
echo "Checking for new digital releases..."
python movie_tracker.py check

# Step 2: Generate display data
echo "Generating data.json..."
python generate_data.py

# Step 3: Show summary
echo "=== Summary ==="
python -c "
import json
d = json.load(open('movie_tracking.json'))
tracking = len([m for m in d['movies'].values() if m['status']=='tracking'])
digital = len([m for m in d['movies'].values() if m['status']=='available'])
today = len([m for m in d['movies'].values() if m.get('digital_date')=='$(date +%Y-%m-%d)'])
bootstrap = len([m for m in d['movies'].values() if m.get('digital_date')=='2025-09-05'])
print(f'Tracking: {tracking} movies')
print(f'Digital: {digital} movies')
print(f'New today: {today} movies')
print(f'Bootstrap batch: {bootstrap} movies')
"

# Step 4: Git commit if changes
if git diff --quiet movie_tracking.json data.json; then
    echo "No changes to commit"
else
    git add movie_tracking.json data.json
    git commit -m "Daily update - $(date +%Y-%m-%d)"
    git push
    echo "Changes committed and pushed"
fi

echo "=== Update complete ==="
