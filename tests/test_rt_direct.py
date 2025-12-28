#!/usr/bin/env python3
"""Test RT scraper score extraction directly on known RT URLs."""

from rt_scraper_playwright import RTScraperPlaywright

def test_direct_extraction():
    """Test the _extract_score_from_rt_page method directly."""

    # Known RT URLs that should have scores
    test_urls = [
        "https://www.rottentomatoes.com/m/dune_2021",
        "https://www.rottentomatoes.com/m/spider_man_no_way_home",
        "https://www.rottentomatoes.com/m/the_batman",
    ]

    print("🧪 Testing direct RT score extraction...")
    print("=" * 60)

    scraper = RTScraperPlaywright()

    # Initialize browser
    scraper._init_browser()

    for i, url in enumerate(test_urls, 1):
        print(f"\n[{i}/{len(test_urls)}] Testing URL: {url}")
        print("-" * 40)

        try:
            # Test the direct score extraction method
            score = scraper._extract_score_from_rt_page(url)

            if score:
                print(f"✅ SUCCESS: Score = {score}")
            else:
                print("❌ FAILED: No score found")

        except Exception as e:
            print(f"💥 ERROR: {e}")

    scraper.close()
    print("\n" + "=" * 60)
    print("Direct extraction test complete.")

if __name__ == "__main__":
    test_direct_extraction()