#!/usr/bin/env python3
"""Test RT scraper standalone with 10 movie titles."""

import json
from rt_scraper_playwright import RTScraperPlaywright

def test_rt_scraper():
    """Test RT scraper with 10 movie titles."""

    # Test movies from current data.json
    test_movies = [
        {"title": "The Cure: The Show of a Lost World", "year": 2025},
        {"title": "Wizard of Oz: Dead Walk", "year": 2025},
        {"title": "Murder in Monaco", "year": 2025},
        {"title": "Suffer", "year": 2025},
        {"title": "Music City Mistletoe", "year": 2025},
        {"title": "Wrong Package", "year": 2025},
        {"title": "A Town Called Purgatory", "year": 2025},
        {"title": "Now You See Me: Now You Don't", "year": 2025},
        {"title": "Misfits", "year": 2025},
        {"title": "The Boulet Brothers' Holiday of Horrors", "year": 2025}
    ]

    print(f"🧪 Testing RT scraper with {len(test_movies)} movies...")
    print("=" * 60)

    # Initialize scraper
    scraper = RTScraperPlaywright()

    results = []
    successes = 0
    failures = 0

    for i, movie in enumerate(test_movies, 1):
        title = movie["title"]
        year = movie["year"]

        print(f"\n[{i}/10] Testing: {title} ({year})")
        print("-" * 40)

        try:
            # Test the scraper
            result = scraper.scrape_rt_score(title, year)

            if result:
                print(f"✅ SUCCESS: Found RT data")
                print(f"   URL: {result.get('url', 'N/A')}")
                print(f"   Score: {result.get('score', 'N/A')}")
                print(f"   Rating: {result.get('rating', 'N/A')}")
                successes += 1
                results.append({"title": title, "year": year, "result": result, "status": "success"})
            else:
                print(f"❌ FAILED: No RT data found")
                failures += 1
                results.append({"title": title, "year": year, "result": None, "status": "failed"})

        except Exception as e:
            print(f"💥 ERROR: {str(e)}")
            failures += 1
            results.append({"title": title, "year": year, "result": None, "status": "error", "error": str(e)})

    # Cleanup
    try:
        scraper.close()
    except:
        pass

    # Summary
    print("\n" + "=" * 60)
    print("🏁 RT SCRAPER TEST SUMMARY")
    print("=" * 60)
    print(f"Total movies tested: {len(test_movies)}")
    print(f"✅ Successes: {successes}")
    print(f"❌ Failures: {failures}")
    print(f"📊 Success rate: {(successes/len(test_movies)*100):.1f}%")

    # Detailed results
    print(f"\n📋 Detailed Results:")
    for result in results:
        status_emoji = "✅" if result["status"] == "success" else "❌"
        print(f"  {status_emoji} {result['title']} - {result['status']}")
        if result.get("error"):
            print(f"     Error: {result['error']}")
        elif result.get("result"):
            rt_result = result["result"]
            print(f"     URL: {rt_result.get('url', 'N/A')}")
            print(f"     Score: {rt_result.get('score', 'N/A')}")

    return results

if __name__ == "__main__":
    test_rt_scraper()