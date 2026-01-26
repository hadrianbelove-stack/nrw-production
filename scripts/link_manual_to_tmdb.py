#!/usr/bin/env python3
"""
Link manual entries in data.json to their real TMDB IDs from movie_tracking.json.
Then mark them for re-enrichment.
"""

import json
from datetime import datetime

def link_manual_entries():
    """Find and link manual entries to real TMDB IDs."""

    # Load data
    with open('data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    with open('movie_tracking.json', 'r', encoding='utf-8') as f:
        tracking = json.load(f)

    # Build title -> TMDB ID lookup from tracking
    title_to_tmdb = {}
    for tmdb_id, movie_data in tracking.get('movies', {}).items():
        title = movie_data.get('title', '')
        if title:
            title_to_tmdb[title.lower()] = {
                'tmdb_id': tmdb_id,
                'status': movie_data.get('status'),
                'providers': movie_data.get('providers', {})
            }

    # Find manual entries with placeholder IDs
    linked = []
    not_found = []
    already_linked = []

    for movie in data.get('movies', []):
        movie_id = str(movie.get('id', ''))
        title = movie.get('title', '')

        # Check if it's a manual placeholder ID
        if movie_id.startswith('manual_'):
            lookup = title_to_tmdb.get(title.lower())

            if lookup:
                old_id = movie_id
                new_id = lookup['tmdb_id']

                # Update the movie
                movie['id'] = new_id
                movie['_old_manual_id'] = old_id
                movie['_enrichment_status'] = 'pending'  # Mark for re-enrichment
                movie['_linked_at'] = datetime.now().isoformat()

                linked.append({
                    'title': title,
                    'old_id': old_id,
                    'new_id': new_id,
                    'tracking_status': lookup['status'],
                    'has_providers': bool(lookup['providers'])
                })
            else:
                not_found.append({
                    'title': title,
                    'manual_id': movie_id
                })
        elif movie.get('manually_added') and not movie_id.startswith('manual_'):
            already_linked.append({
                'title': title,
                'id': movie_id
            })

    # Save updated data
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Report
    print(f"\n{'='*60}")
    print("Manual Entry Linking Report")
    print(f"{'='*60}")

    print(f"\n✅ LINKED ({len(linked)}):")
    for item in linked:
        providers = "has providers" if item['has_providers'] else "no providers"
        print(f"  {item['title']}")
        print(f"    {item['old_id']} → {item['new_id']} ({item['tracking_status']}, {providers})")

    if not_found:
        print(f"\n❌ NOT FOUND IN TRACKING ({len(not_found)}):")
        for item in not_found:
            print(f"  {item['title']} ({item['manual_id']})")

    if already_linked:
        print(f"\n📌 ALREADY HAS REAL ID ({len(already_linked)}):")
        for item in already_linked:
            print(f"  {item['title']} ({item['id']})")

    print(f"\n{'='*60}")
    print(f"Summary: {len(linked)} linked, {len(not_found)} not found, {len(already_linked)} already linked")
    print(f"{'='*60}")

    return {
        'linked': linked,
        'not_found': not_found,
        'already_linked': already_linked
    }


if __name__ == '__main__':
    link_manual_entries()
