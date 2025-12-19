#!/usr/bin/env python3
"""Test Wikipedia scraper with IMDb IDs to check Wikidata lookup."""

from wikipedia_scraper_playwright import WikipediaScraperPlaywright

def test_with_imdb():
    """Test Wikipedia scraper with known IMDb IDs."""

    # Test cases with known IMDb IDs that should work
    test_cases = [
        {"title": "Dune", "year": 2021, "imdb_id": "tt1160419"},
        {"title": "Spider-Man: No Way Home", "year": 2021, "imdb_id": "tt10872600"},
        {"title": "The Batman", "year": 2022, "imdb_id": "tt1877830"},
        # These 2025 movies likely won't have IMDb IDs yet
        {"title": "Now You See Me: Now You Don't", "year": 2025, "imdb_id": None},
        {"title": "Misfits", "year": 2025, "imdb_id": None},
    ]

    print("🧪 Testing Wikipedia scraper with IMDb IDs...")
    print("=" * 60)

    scraper = WikipediaScraperPlaywright()

    for i, test in enumerate(test_cases, 1):
        title = test["title"]
        year = test["year"]
        imdb_id = test["imdb_id"]

        print(f"\n[{i}/5] Testing: {title} ({year})")
        print(f"IMDb ID: {imdb_id or 'None'}")
        print("-" * 40)

        try:
            result = scraper.find_wikipedia_url(title, year, imdb_id)

            if result:
                print(f"✅ SUCCESS: {result}")
                if imdb_id:
                    print("   ^^ Should use Wikidata (Tier 2) if available")
                else:
                    print("   ^^ Using Playwright scraping (Tier 4)")
            else:
                print("❌ FAILED: No URL found")

        except Exception as e:
            print(f"💥 ERROR: {e}")

    scraper.close()
    print("\n" + "=" * 60)
    print("Test complete. Check which tier was used for each result.")

if __name__ == "__main__":
    test_with_imdb()