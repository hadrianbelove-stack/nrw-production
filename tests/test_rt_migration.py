#!/usr/bin/env python3
"""
Test script for RT scraper migration from Selenium to Playwright
Tests with a sample of movies from the tracking database
"""

import json
import os
from rt_scraper_playwright import RTScraperPlaywright
import yaml


def load_config():
    """Load configuration from config.yaml"""
    if os.path.exists('config.yaml'):
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    return {}


def load_tracking_data():
    """Load enriched data with years from data.json"""
    if os.path.exists('data.json'):
        with open('data.json', 'r') as f:
            data = json.load(f)
            # data.json has a dict with 'movies' key containing the list
            if isinstance(data, dict) and 'movies' in data:
                return data['movies']
            # Fallback for older format
            if isinstance(data, list):
                return data
    return []


def main():
    print("🧪 RT Scraper Migration Test")
    print("=" * 60)

    # Load config
    config = load_config()

    # Load tracking data
    tracking_data = load_tracking_data()

    if not tracking_data:
        print("❌ No tracking data found in data.json")
        return

    # Select a sample of movies (first 30 with years)
    sample_movies = []
    for movie in tracking_data:
        if movie.get('year') and len(sample_movies) < 30:
            sample_movies.append(movie)

    print(f"\n📊 Testing with {len(sample_movies)} movies")
    print("=" * 60)

    # Initialize RT scraper
    print("\n🚀 Initializing RT scraper with Playwright...")
    with RTScraperPlaywright(cache_file='cache/rt_cache.json', config=config) as scraper:
        print("✅ RT scraper initialized successfully\n")

        # Test each movie
        results = {
            'success': [],
            'failure': [],
            'cache_hit': []
        }

        for i, movie in enumerate(sample_movies, 1):
            title = movie.get('title', 'Unknown')
            year = movie.get('year')

            if not year:
                print(f"{i}/{len(sample_movies)} ⏭️  Skipping {title} (no year)")
                continue

            print(f"{i}/{len(sample_movies)} 🔍 Testing: {title} ({year})")

            # Get initial cache stats
            initial_cache_hits = scraper.stats['cache_hits']

            # Scrape RT score
            result = scraper.scrape_rt_score(title, year)

            # Check if it was a cache hit
            was_cache_hit = scraper.stats['cache_hits'] > initial_cache_hits

            if result:
                url = result.get('url')
                score = result.get('score', 'N/A')
                status = '💾' if was_cache_hit else '✅'
                print(f"   {status} Found: {url}")
                print(f"      Score: {score}")

                if was_cache_hit:
                    results['cache_hit'].append((title, year, url, score))
                else:
                    results['success'].append((title, year, url, score))
            else:
                print(f"   ❌ Not found")
                results['failure'].append((title, year))

            print()

        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        total = len(results['success']) + len(results['failure']) + len(results['cache_hit'])
        print(f"\nTotal movies tested: {total}")
        print(f"✅ New scrapes successful: {len(results['success'])}")
        print(f"💾 Cache hits: {len(results['cache_hit'])}")
        print(f"❌ Failures: {len(results['failure'])}")

        if total > 0:
            success_rate = ((len(results['success']) + len(results['cache_hit'])) / total) * 100
            print(f"\n📈 Success rate: {success_rate:.1f}%")

        # Print scraper stats
        stats = scraper.get_stats()
        print(f"\n📊 Scraper Statistics:")
        print(f"   Attempts: {stats['attempts']}")
        print(f"   Successes: {stats['successes']}")
        print(f"   Cache hits: {stats['cache_hits']}")
        print(f"   Failures: {stats['failures']}")

        # Print failures if any
        if results['failure']:
            print(f"\n❌ Failed movies:")
            for title, year in results['failure']:
                print(f"   - {title} ({year})")

        print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
