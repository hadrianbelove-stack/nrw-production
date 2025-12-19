#!/usr/bin/env python3
"""Test RT scraper score extraction with known RT URLs."""

from rt_scraper_playwright import RTScraperPlaywright

def test_score_extraction():
    """Test the enhanced RT scraper's score extraction on known RT pages."""

    # Test cases with known RT URLs that should have scores
    test_cases = [
        {
            "title": "Dune",
            "year": 2021,
            "expected_url": "https://www.rottentomatoes.com/m/dune_2021",
            "expect_score": True
        },
        {
            "title": "Spider-Man: No Way Home",
            "year": 2021,
            "expected_url": "https://www.rottentomatoes.com/m/spider_man_no_way_home",
            "expect_score": True
        },
        {
            "title": "The Batman",
            "year": 2022,
            "expected_url": "https://www.rottentomatoes.com/m/the_batman",
            "expect_score": True
        },
    ]

    print("🧪 Testing RT scraper score extraction...")
    print("=" * 60)

    scraper = RTScraperPlaywright()

    for i, test in enumerate(test_cases, 1):
        title = test["title"]
        year = test["year"]
        expected_url = test["expected_url"]

        print(f"\n[{i}/{len(test_cases)}] Testing: {title} ({year})")
        print(f"Expected URL: {expected_url}")
        print("-" * 40)

        try:
            # Test the full scraper (should find the URL via Google search)
            result = scraper.scrape_rt_score(title, year)

            if result:
                url = result.get('url', '')
                score = result.get('score', '')
                print(f"✅ SUCCESS:")
                print(f"   URL: {url}")
                print(f"   Score: {score}")

                if expected_url in url:
                    print("   ✓ URL matches expected")
                else:
                    print(f"   ⚠️  URL different from expected: {expected_url}")

                if score and score != 'N/A':
                    print("   ✓ Score extracted successfully")
                else:
                    print("   ⚠️  No score extracted")
            else:
                print("❌ FAILED: No RT data found")

        except Exception as e:
            print(f"💥 ERROR: {e}")

    scraper.close()
    print("\n" + "=" * 60)
    print("Score extraction test complete.")

if __name__ == "__main__":
    test_score_extraction()