#!/usr/bin/env python3
"""Test Google search functionality to see why RT URLs aren't being found."""

from rt_scraper_playwright import RTScraperPlaywright

def test_google_search():
    """Test Google search directly to see what's happening."""

    # Test movies that should have RT pages
    test_movies = [
        {"title": "Dune", "year": 2021},
        {"title": "The Batman", "year": 2022}
    ]

    print("🧪 Testing Google search for RT URLs...")
    print("=" * 60)

    scraper = RTScraperPlaywright()

    # Initialize browser to access the page
    scraper._init_browser()

    for i, movie in enumerate(test_movies, 1):
        title = movie["title"]
        year = movie["year"]

        print(f"\n[{i}/{len(test_movies)}] Testing: {title} ({year})")
        print("-" * 40)

        try:
            # Build search query like the scraper does
            search_query = f'"{title}" {year} "Rotten Tomatoes"'
            print(f"Search query: {search_query}")

            # Navigate to Google
            from urllib.parse import quote_plus
            search_url = f"https://www.google.com/search?q={quote_plus(search_query)}"
            print(f"Search URL: {search_url}")

            scraper.page.goto(search_url, wait_until='domcontentloaded')

            # Wait a moment for the page to load
            import time
            time.sleep(2)

            # Take a screenshot for debugging
            screenshot_path = f"cache/screenshots/google_search_{title.replace(' ', '_')}_{year}.png"
            scraper.page.screenshot(path=screenshot_path)
            print(f"Screenshot saved: {screenshot_path}")

            # Check page title and basic elements
            page_title = scraper.page.title()
            print(f"Page title: {page_title}")

            # Look for search results
            search_results = scraper.page.query_selector_all('div[class*="result"], .g, h3')
            print(f"Found {len(search_results)} search result elements")

            # Look for any rottentomatoes.com links
            rt_links = scraper.page.query_selector_all('a[href*="rottentomatoes.com"]')
            print(f"Found {len(rt_links)} rottentomatoes.com links")

            if rt_links:
                for j, link in enumerate(rt_links[:3]):  # Show first 3
                    href = link.get_attribute('href')
                    text = link.text_content()[:100]
                    print(f"  [{j+1}] {href}")
                    print(f"      Text: {text}")

            # Check if we're being blocked
            page_content = scraper.page.content()
            if 'captcha' in page_content.lower() or 'blocked' in page_content.lower():
                print("⚠️  Possible CAPTCHA or blocking detected")

            if 'unusual traffic' in page_content.lower():
                print("⚠️  'Unusual traffic' message detected")

        except Exception as e:
            print(f"💥 ERROR: {e}")

    scraper.close()
    print("\n" + "=" * 60)
    print("Google search test complete. Check screenshots for visual debugging.")

def _quote_plus(text):
    """Helper method for URL encoding."""
    from urllib.parse import quote_plus
    return quote_plus(text)

# Add quote_plus method to scraper class temporarily
RTScraperPlaywright._quote_plus = _quote_plus

if __name__ == "__main__":
    test_google_search()