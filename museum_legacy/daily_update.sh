#!/bin/bash
cd ~/Downloads/nrw-production || exit 1

echo "=== NRW Daily Update - $(date) ==="
python movie_tracker.py daily

# echo "Updating Rotten Tomatoes data..."
# python update_rt_data.py  # ARCHIVED - RT scraping now automatic in generate_data.py

# python date_verification.py  # ARCHIVED - date_verification.py moved to museum_legacy/
python generate_data.py

echo "=== Summary ==="
python -c "
import json
d = json.load(open('movie_tracking.json'))
tracking = len([m for m in d['movies'].values() if m['status']=='tracking'])
digital = len([m for m in d['movies'].values() if m['status']=='available'])
total = len(d['movies'])
print(f'Total tracked: {total}')
print(f'Still tracking: {tracking}')
print(f'Now digital: {digital}')
"

if git diff --quiet movie_tracking.json data.json; then
    echo "No changes to commit"
else
    git add -A
    git commit -m "Daily update - $(date +%Y-%m-%d)"
    git push
    echo "Changes committed"
fi
