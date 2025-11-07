#!/usr/bin/env python3
"""
Test Wikipedia scraper with known movies that SHOULD have Wikipedia pages
"""

import yaml
import os
from wikipedia_scraper_playwright import WikipediaScraperPlaywright


def load_config():
    if os.path.exists('config.yaml'):
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    return {}


# Test with recent released movies that should have Wikipedia pages
TEST_MOVIES = [
    {"title": "The Substance", "year": "2024"},
    {"title": "Wicked", "year": "2024"},
    {"title": "Gladiator II", "year": "2024"},
    {"title": "Moana 2", "year": "2024"},
    {"title": "Red One", "year": "2024"},
    {"title": "Venom: The Last Dance", "year": "2024"},
    {"title": "Heretic", "year": "2024"},
    {"title": "Terrifier 3", "year": "2024"},
    {"title": "The Wild Robot", "year": "2024"},
    {"title": "Smile 2", "year": "2024"},
]


def main():
    print("🧪 Wikipedia Scraper Test - Known Movies")
    print("=" * 60)
    print(f"\nTesting with {len(TEST_MOVIES)} recent movies that SHOULD have Wikipedia pages")
    print("=" * 60)

    config = load_config()

    with WikipediaScraperPlaywright(cache_file='wikipedia_cache_known.json', config=config) as scraper:
        print("✅ Wikipedia scraper initialized\n")

        results = {'success': [], 'failure': []}

        for i, movie in enumerate(TEST_MOVIES, 1):
            title = movie['title']
            year = movie['year']

            print(f"{i}/{len(TEST_MOVIES)} 🔍 {title} ({year})")

            # Test scraper only (no API/Wikidata to test scraper directly)
            wiki_url = scraper.find_wikipedia_url(title, year, use_api=False, use_wikidata=False)

            if wiki_url and 'index.php?search=' not in wiki_url:
                print(f"   ✅ {wiki_url}")
                results['success'].append((title, year, wiki_url))
            else:
                print(f"   ❌ Not found")
                results['failure'].append((title, year))

        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        total = len(results['success']) + len(results['failure'])
        print(f"\nTotal: {total}")
        print(f"✅ Success: {len(results['success'])}")
        print(f"❌ Failure: {len(results['failure'])}")

        if total > 0:
            success_rate = (len(results['success']) / total) * 100
            print(f"\n📈 Success rate: {success_rate:.1f}%")

        stats = scraper.get_stats()
        print(f"\n📊 Scraper Stats:")
        print(f"   Attempts: {stats['attempts']}")
        print(f"   Successes: {stats['successes']}")
        print(f"   Failures: {stats['failures']}")


if __name__ == "__main__":
    main()
