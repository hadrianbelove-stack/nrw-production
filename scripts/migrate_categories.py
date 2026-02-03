#!/usr/bin/env python3
"""
Migration Script: Add categories to existing movies in data.json

This script reads the current data.json and adds a 'categories' object to each movie
based on the auto-categorization logic (studio matching + budget fallback).

Run with: python scripts/migrate_categories.py
"""

import json
import os
from datetime import datetime


def load_category_config():
    """Load the category configuration"""
    config_path = 'admin/category_config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {
        'big_time_studios': [],
        'budget_threshold': 10000000
    }


def load_staff_picks():
    """Load staff picks list"""
    # Try new file first, fall back to old
    if os.path.exists('admin/staff_picks.json'):
        with open('admin/staff_picks.json', 'r') as f:
            return json.load(f)
    elif os.path.exists('admin/featured_movies.json'):
        with open('admin/featured_movies.json', 'r') as f:
            return json.load(f)
    return []


def categorize_movie(movie, category_config, staff_picks):
    """
    Categorize a movie as 'big_time' or 'niche' based on studio and budget.

    Returns:
        dict: Categories object
    """
    big_time_studios = category_config.get('big_time_studios', [])
    budget_threshold = category_config.get('budget_threshold', 10000000)

    # Get movie properties
    studio = movie.get('studio', '') or ''
    budget = movie.get('budget', 0) or 0
    original_language = movie.get('original_language', 'en')
    movie_id = str(movie.get('id', ''))

    # Determine tier
    tier = 'niche'  # Default
    auto_categorized = True

    # Check studio against big time list (case-insensitive partial match)
    if studio:
        for bs in big_time_studios:
            if bs.lower() in studio.lower():
                tier = 'big_time'
                break

    # If no studio match, check budget
    if tier == 'niche' and budget >= budget_threshold:
        tier = 'big_time'

    # Determine foreign status
    is_foreign = bool(original_language and original_language != 'en')

    # Check if staff pick
    is_staff_pick = movie_id in staff_picks

    return {
        'tier': tier,
        'is_foreign': is_foreign,
        'is_staff_pick': is_staff_pick,
        'auto_categorized': auto_categorized,
        'manual_override': None
    }


def migrate():
    """Main migration function"""
    print("=" * 60)
    print("Category Migration Script")
    print("=" * 60)

    # Load configuration
    print("\n1. Loading configuration...")
    category_config = load_category_config()
    staff_picks = load_staff_picks()

    print(f"   - Big Time studios: {len(category_config.get('big_time_studios', []))}")
    print(f"   - Budget threshold: ${category_config.get('budget_threshold', 0):,}")
    print(f"   - Staff picks: {len(staff_picks)}")

    # Load data.json
    print("\n2. Loading data.json...")
    if not os.path.exists('data.json'):
        print("   ERROR: data.json not found!")
        return

    with open('data.json', 'r') as f:
        data = json.load(f)

    movies = data.get('movies', [])
    print(f"   - Found {len(movies)} movies")

    # Categorize each movie
    print("\n3. Categorizing movies...")
    stats = {
        'big_time': 0,
        'niche': 0,
        'foreign': 0,
        'staff_picks': 0,
        'already_categorized': 0
    }

    for movie in movies:
        # Skip if already has categories (unless you want to recategorize)
        if movie.get('categories') and not movie.get('_force_recategorize'):
            stats['already_categorized'] += 1
            continue

        categories = categorize_movie(movie, category_config, staff_picks)
        movie['categories'] = categories

        # Also set featured flag for backwards compatibility
        if categories['is_staff_pick']:
            movie['featured'] = True

        # Count stats
        if categories['tier'] == 'big_time':
            stats['big_time'] += 1
        else:
            stats['niche'] += 1
        if categories['is_foreign']:
            stats['foreign'] += 1
        if categories['is_staff_pick']:
            stats['staff_picks'] += 1

    print(f"   - Big Time: {stats['big_time']}")
    print(f"   - Niche: {stats['niche']}")
    print(f"   - Foreign: {stats['foreign']}")
    print(f"   - Staff Picks: {stats['staff_picks']}")
    print(f"   - Already categorized (skipped): {stats['already_categorized']}")

    # Update data structure
    data['movies'] = movies
    data['staff_picks'] = staff_picks
    data['generated_at'] = datetime.now().isoformat()

    # Backup original
    print("\n4. Creating backup...")
    backup_path = f"data.json.backup.pre_categories_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(backup_path, 'w') as f:
        with open('data.json', 'r') as original:
            f.write(original.read())
    print(f"   - Backup saved to: {backup_path}")

    # Save updated data.json
    print("\n5. Saving updated data.json...")
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)
    print("   - Done!")

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"\nCategorized {stats['big_time'] + stats['niche']} movies:")
    print(f"  - {stats['big_time']} Big Time ({stats['big_time'] / len(movies) * 100:.1f}%)")
    print(f"  - {stats['niche']} Niche ({stats['niche'] / len(movies) * 100:.1f}%)")
    print(f"  - {stats['foreign']} Foreign films")
    print(f"  - {stats['staff_picks']} Staff Picks")

    if stats['already_categorized'] > 0:
        print(f"\n  Note: {stats['already_categorized']} movies were already categorized and skipped.")
        print("  To force re-categorization, set '_force_recategorize': true on each movie.")


if __name__ == '__main__':
    migrate()
