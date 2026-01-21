#!/usr/bin/env python3 -u
"""
Enrich Wikipedia URLs for movies missing them in data.json.
Uses the updated WikipediaScraperPlaywright with:
- Plain title fallback in REST API
- Click-through approach in Playwright
- Never returns search URLs
"""

import json
import sys
import os
from datetime import datetime

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wikipedia_scraper_playwright import WikipediaScraperPlaywright


def load_json(path):
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    """Save JSON file with backup."""
    # Create backup
    if os.path.exists(path):
        backup_path = f"{path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(path, 'r') as f:
            backup_data = f.read()
        with open(backup_path, 'w') as f:
            f.write(backup_data)
        print(f"Backup created: {backup_path}")

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    # Paths
    data_path = 'data.json'
    tracking_path = 'movie_tracking.json'

    print("=" * 60)
    print("Wikipedia URL Enrichment Script")
    print("=" * 60)

    # Load data
    print("\nLoading data.json...")
    data = load_json(data_path)
    movies = data['movies']
    print(f"Total movies: {len(movies)}")

    # Find movies needing Wikipedia URLs
    needs_wiki = []
    for movie in movies:
        wiki_url = movie.get('links', {}).get('wikipedia')
        if not wiki_url:
            needs_wiki.append(movie)
        elif 'index.php?search=' in wiki_url:
            needs_wiki.append(movie)

    print(f"Movies needing Wikipedia URLs: {len(needs_wiki)}")

    if not needs_wiki:
        print("All movies have Wikipedia URLs!")
        return

    # Initialize scraper
    print("\nInitializing Wikipedia scraper...")
    scraper = WikipediaScraperPlaywright(
        cache_file='cache/wikipedia_cache.json',
        config={},
        logger=None
    )

    # Process movies
    print(f"\nProcessing {len(needs_wiki)} movies...")
    print("-" * 60)

    success_count = 0
    not_found_count = 0

    for i, movie in enumerate(needs_wiki):
        title = movie['title']
        year = str(movie.get('year', ''))
        imdb_id = movie.get('imdb_id')

        print(f"[{i+1}/{len(needs_wiki)}] {title} ({year})...", end=' ')

        try:
            wiki_url = scraper.find_wikipedia_url(
                title=title,
                year=year,
                imdb_id=imdb_id,
                use_api=True,
                use_wikidata=True
            )

            if wiki_url and '/wiki/' in wiki_url:
                # Update movie links
                if 'links' not in movie:
                    movie['links'] = {}
                movie['links']['wikipedia'] = wiki_url
                print(f"✓ {wiki_url.split('/wiki/')[-1][:40]}")
                success_count += 1
            else:
                print("✗ Not found")
                not_found_count += 1

        except Exception as e:
            print(f"✗ Error: {e}")
            not_found_count += 1

    # Summary
    print("-" * 60)
    print(f"\nResults:")
    print(f"  Found: {success_count}")
    print(f"  Not found: {not_found_count}")
    print(f"  Success rate: {success_count}/{len(needs_wiki)} ({100*success_count/len(needs_wiki):.1f}%)")

    # Show scraper stats
    stats = scraper.get_stats()
    print(f"\nScraper stats:")
    print(f"  Cache hits: {stats['cache_hits']}")
    print(f"  API successes: {stats['api_successes']}")
    print(f"  Wikidata successes: {stats['wikidata_successes']}")
    print(f"  Playwright successes: {stats['scraper_successes']}")

    # Save updated data
    if success_count > 0:
        print(f"\nSaving updated data.json...")
        data['movies'] = movies
        save_json(data_path, data)
        print("Done!")

    # Close scraper
    scraper.close()

    print("\n" + "=" * 60)
    print("Enrichment complete!")


if __name__ == '__main__':
    main()
