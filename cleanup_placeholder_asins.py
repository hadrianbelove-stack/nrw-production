#!/usr/bin/env python3
"""
Cleanup script to reset enriched flags for movies with placeholder ASINs
"""

import json
import os
from datetime import datetime
from constants import PLACEHOLDER_ASINS

def cleanup_placeholder_asins():
    """Reset enriched flags for movies with placeholder ASINs"""

    # Backup existing files
    backup_suffix = f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Load data.json to find movies with placeholder ASIN
    affected_movie_ids = set()

    placeholder_list = ', '.join(PLACEHOLDER_ASINS)
    print(f"🔍 Scanning data.json for placeholder ASINs: {placeholder_list}...")

    try:
        with open('data.json', 'r') as f:
            data = json.load(f)

        movies = data.get('movies', [])

        for movie in movies:
            movie_id = str(movie.get('id', ''))
            movie_title = movie.get('title', 'Unknown')
            watch_links = movie.get('watch_links', {})

            # Check each category for placeholder ASIN
            has_placeholder = False
            for category in ['streaming', 'rent', 'buy']:
                category_data = watch_links.get(category, {})
                if isinstance(category_data, dict):
                    link = category_data.get('link', '')
                    if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                        has_placeholder = True
                        detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                        print(f"  🎬 Found placeholder ASIN {detected_asin} in {movie_title} ({category}): {link}")
                        break

            if has_placeholder:
                affected_movie_ids.add(movie_id)

        print(f"📊 Found {len(affected_movie_ids)} movies with placeholder ASINs")

    except Exception as e:
        print(f"❌ Error reading data.json: {e}")
        return False

    # Load movie_tracking.json
    print("\n🔧 Cleaning movie_tracking.json...")

    try:
        with open('movie_tracking.json', 'r') as f:
            tracking_db = json.load(f)

        # Backup movie_tracking.json
        backup_file = f'movie_tracking{backup_suffix}.json'
        with open(backup_file, 'w') as f:
            json.dump(tracking_db, f, indent=2)
        print(f"💾 Backup created: {backup_file}")

        corrected_count = 0

        # Process each movie
        for movie_id, movie in tracking_db.get('movies', {}).items():
            if movie_id in affected_movie_ids:
                print(f"  🔄 Resetting enriched flag for {movie.get('title', 'Unknown')} (ID: {movie_id})")
                # Always set enriched to False for affected IDs to guarantee re-enrichment
                movie['enriched'] = False
                # Remove enrichment_date regardless of current enriched value
                if 'enrichment_date' in movie:
                    del movie['enrichment_date']
                # Remove watch_links regardless of current enriched value
                if 'watch_links' in movie:
                    del movie['watch_links']
                corrected_count += 1

        # Save corrected tracking database
        with open('movie_tracking.json', 'w') as f:
            json.dump(tracking_db, f, indent=2)

        print(f"✅ Corrected {corrected_count} movies in movie_tracking.json")
        print(f"💾 Original file backed up as: {backup_file}")

        return True

    except Exception as e:
        print(f"❌ Error processing movie_tracking.json: {e}")
        return False

if __name__ == "__main__":
    print("🧹 Amazon Placeholder ASINs Cleanup Tool")
    print("=" * 50)

    success = cleanup_placeholder_asins()

    if success:
        print("\n✅ Cleanup completed successfully!")
        print("📝 Next steps:")
        print("   1. Run: python3 generate_data.py")
        print("   2. Verify: grep -c 'B0FMPYFP9W\\|B0FNDR5BW5' data.json (should be 0)")
    else:
        print("\n❌ Cleanup failed. Check error messages above.")