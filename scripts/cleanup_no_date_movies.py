#!/usr/bin/env python3
"""
Cleanup script to remove movies without digital_date from data.json
and reset their status in movie_tracking.json.

These movies have status='available' but no digital_date, which is
an inconsistent state. This script:
1. Removes them from data.json (shouldn't be displayed without dates)
2. Resets status to 'tracking' in movie_tracking.json (so they get
   properly re-discovered when actually released)
"""

import json
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from file_lock import safe_write_json

def main():
    print("=" * 60)
    print("Cleanup: Movies without digital_date")
    print("=" * 60)

    # Load data.json
    print("\nLoading data.json...")
    with open('data.json', 'r') as f:
        data = json.load(f)

    original_count = len(data['movies'])

    # Find movies without dates
    no_date_ids = set()
    for m in data['movies']:
        if not m.get('digital_date'):
            no_date_ids.add(str(m.get('id')))

    print(f"Found {len(no_date_ids)} movies without digital_date in data.json")

    if not no_date_ids:
        print("Nothing to clean up!")
        return

    # Remove from data.json
    data['movies'] = [m for m in data['movies'] if m.get('digital_date')]
    new_count = len(data['movies'])

    print(f"Removing {original_count - new_count} movies from data.json")

    # Update metadata
    data['generated_at'] = datetime.now().isoformat()
    data['count'] = new_count

    # Save data.json
    safe_write_json('data.json', data)
    print(f"✓ data.json updated: {original_count} -> {new_count} movies")

    # Load movie_tracking.json
    print("\nLoading movie_tracking.json...")
    with open('movie_tracking.json', 'r') as f:
        tracking = json.load(f)

    # Reset status for movies with available but no date
    reset_count = 0
    for movie_id, movie in tracking.get('movies', {}).items():
        if movie.get('status') == 'available' and not movie.get('digital_date'):
            movie['status'] = 'tracking'
            movie['_reset_from_cleanup'] = datetime.now().isoformat()
            reset_count += 1

    print(f"Resetting {reset_count} movies from 'available' to 'tracking' status")

    # Save movie_tracking.json
    safe_write_json('movie_tracking.json', tracking)
    print(f"✓ movie_tracking.json updated: {reset_count} movies reset to tracking")

    print("\n" + "=" * 60)
    print("Cleanup complete!")
    print(f"  - Removed {original_count - new_count} movies from data.json")
    print(f"  - Reset {reset_count} movies to 'tracking' status")
    print("\nThese movies will be re-discovered when they actually become available.")

if __name__ == '__main__':
    main()
