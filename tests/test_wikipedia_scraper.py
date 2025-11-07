#!/usr/bin/env python3
"""
Test script for Wikipedia scraper with Playwright
Tests with movies that currently have failed lookups (search fallbacks)
"""

import json
import os
from wikipedia_scraper_playwright import WikipediaScraperPlaywright
import yaml


def load_config():
    """Load configuration from config.yaml"""
    if os.path.exists('config.yaml'):
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    return {}


def load_failed_lookups():
    """Load movies with failed Wikipedia lookups from cache"""
    if os.path.exists('wikipedia_cache.json'):
        with open('wikipedia_cache.json', 'r') as f:
            cache = json.load(f)

            failed = []
            for key, value in cache.items():
                if isinstance(value, dict):
                    url = value.get('url', '')
                    source = value.get('source', '')
                    # Find search fallbacks (failed lookups)
                    if source == 'search_fallback' or 'index.php?search=' in url:
                        title = value.get('title')
                        if title and '_' in key:
                            year = key.split('_')[-1]
                            failed.append({'title': title, 'year': year, 'cache_key': key})

            return failed
    return []


def main():
    print("🧪 Wikipedia Scraper Playwright Test")
    print("=" * 60)

    # Load config
    config = load_config()

    # Load failed lookups
    failed_lookups = load_failed_lookups()

    if not failed_lookups:
        print("❌ No failed lookups found in cache")
        return

    # Test with first 15 failed lookups
    test_movies = failed_lookups[:15]
    print(f"\n📊 Testing with {len(test_movies)} movies that previously failed")
    print("=" * 60)

    # Initialize Wikipedia scraper
    print("\n🚀 Initializing Wikipedia scraper with Playwright...")
    with WikipediaScraperPlaywright(cache_file='wikipedia_cache_test.json', config=config) as scraper:
        print("✅ Wikipedia scraper initialized successfully\n")

        # Test each movie
        results = {
            'success': [],
            'failure': []
        }

        for i, movie in enumerate(test_movies, 1):
            title = movie['title']
            year = movie['year']

            print(f"{i}/{len(test_movies)} 🔍 Testing: {title} ({year})")

            # Scrape Wikipedia URL (skip cache and API to test scraper directly)
            wiki_url = scraper.find_wikipedia_url(title, year, use_api=False, use_wikidata=False)

            if wiki_url and 'index.php?search=' not in wiki_url:
                print(f"   ✅ Found: {wiki_url}")
                results['success'].append((title, year, wiki_url))
            else:
                print(f"   ❌ Not found")
                results['failure'].append((title, year))

            print()

        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        total = len(results['success']) + len(results['failure'])
        print(f"\nTotal movies tested: {total}")
        print(f"✅ New scrapes successful: {len(results['success'])}")
        print(f"❌ Failures: {len(results['failure'])}")

        if total > 0:
            success_rate = (len(results['success']) / total) * 100
            print(f"\n📈 Success rate: {success_rate:.1f}%")

        # Print scraper stats
        stats = scraper.get_stats()
        print(f"\n📊 Scraper Statistics:")
        print(f"   Attempts: {stats['attempts']}")
        print(f"   Successes: {stats['successes']}")
        print(f"   Scraper successes: {stats['scraper_successes']}")
        print(f"   Failures: {stats['failures']}")

        # Print successful finds
        if results['success']:
            print(f"\n✅ Successfully found Wikipedia pages:")
            for title, year, url in results['success']:
                print(f"   - {title} ({year})")
                print(f"     {url}")

        print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
