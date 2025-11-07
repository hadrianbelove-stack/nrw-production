#!/usr/bin/env python3
"""
Standalone test script for agent scraper functionality.
Tests the agent scraper in isolation before integration testing.
"""

import sys
import os
import json
from agent_link_scraper import AgentLinkScraper

def test_agent_scraper():
    """Test the agent scraper with various streaming platforms."""
    print("=" * 60)
    print("AGENT LINK SCRAPER STANDALONE TEST")
    print("=" * 60)

    # Test with headless=False to see browser (helps debugging)
    headless = '--headless' in sys.argv
    debug_selectors = '--debug-selectors' in sys.argv

    print(f"\nRunning in {'headless' if headless else 'visible'} mode")
    if debug_selectors:
        print("Selector debugging enabled (will show which selectors matched)")
    print("(Use --headless flag to run without browser window)")
    print("(Use --debug-selectors flag to show selector details)\n")

    try:
        import time
        start_time = time.time()

        # Create config for scraper
        config = {
            'headless': headless,
            'rate_limit': 2.0,
            'timeout': 10,
            'max_retries': 3,
            'screenshots_enabled': True,
            'cache_ttl_days': 30
        }
        scraper = AgentLinkScraper(config=config)

        # Test cases from actual data.json movies with null links
        test_cases = [
            ('1302318', 'A Woman with No Filter', '2025', 'Netflix'),
            ('1156594', 'Our Fault', '2025', 'Netflix'),
            ('1072699', 'Inside Furioza', '2025', 'Netflix'),
            ('1254624', 'Night Always Comes', '2025', 'Netflix'),
            # Test unsupported platform
            ('1156594', 'Our Fault', '2025', 'Amazon Prime Video'),
        ]

        results = []
        for movie_id, title, year, service in test_cases:
            print(f"\nTest: {title} ({year}) on {service}")
            print("-" * 60)

            try:
                result = scraper.find_watch_link(movie_id, title, year, service)
                results.append((title, service, result))

                if result.get('link'):
                    print(f"✅ SUCCESS: {result['link']}")
                    if debug_selectors and result.get('selector_used'):
                        print(f"   Selector: {result['selector_used']}")
                    if result.get('cached'):
                        print("   (from cache)")
                else:
                    print(f"❌ FAILED: No link found")
                    if debug_selectors and result.get('last_error'):
                        print(f"   Error: {result['last_error']}")
                    if service not in ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max', 'Hulu']:
                        print(f"   (Expected: {service} is not supported)")

            except Exception as e:
                print(f"❌ ERROR: {e}")
                results.append((title, service, {'error': str(e)}))

        # Cleanup
        scraper.close()
        end_time = time.time()

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        successes = [r for r in results if r[2].get('link')]
        failures = [r for r in results if not r[2].get('link') and not r[2].get('error')]
        errors = [r for r in results if r[2].get('error')]

        print(f"Total tests: {len(results)}")
        print(f"Successes: {len(successes)}")
        print(f"Failures: {len(failures)}")
        print(f"Errors: {len(errors)}")
        print(f"\n⏱️  Total time: {end_time - start_time:.1f} seconds")
        print(f"   Average per movie: {(end_time - start_time) / len(results):.1f} seconds")
        if successes:
            print(f"   Success rate: {len(successes) / len(results) * 100:.1f}%")

        if successes:
            print("\n✅ Successful scrapes:")
            for title, service, result in successes:
                cached = " (cached)" if result.get('cached') else ""
                print(f"   {title} on {service}: {result['link']}{cached}")

        if failures:
            print("\n❌ Failed scrapes:")
            for title, service, result in failures:
                print(f"   {title} on {service}")

        if errors:
            print("\n💥 Errors:")
            for title, service, result in errors:
                print(f"   {title} on {service}: {result['error']}")

        # Check cache
        cache_file = 'cache/agent_links_cache.json'
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                cache = json.load(f)
            print(f"\n💾 Cache file created: {len(cache.get('movies', {}))} entries")
            print(f"   Location: {os.path.abspath(cache_file)}")

            # Show cache contents
            if cache.get('movies'):
                print("   Cache contents:")
                for movie_id, data in cache['movies'].items():
                    streaming = data.get('streaming', {})
                    service = streaming.get('service')
                    link = streaming.get('link')
                    success = data.get('success', False)
                    print(f"     {movie_id}: {service} -> {'SUCCESS' if success else 'FAILED'}")
        else:
            print("\n⚠️  Cache file NOT created")
            print(f"   Expected location: {os.path.abspath(cache_file)}")

        # Check for screenshots
        screenshot_dir = 'cache/screenshots'
        if os.path.exists(screenshot_dir):
            screenshots = [f for f in os.listdir(screenshot_dir) if f.endswith('.png')]
            if screenshots:
                print(f"\n📸 Screenshots captured: {len(screenshots)}")
                print(f"   Location: {os.path.abspath(screenshot_dir)}")
                print("   Recent failures:")
                for screenshot in sorted(screenshots)[-5:]:  # Show last 5
                    print(f"     {screenshot}")
            else:
                print("\n✅ No failure screenshots (all scrapes succeeded)")
        else:
            print("\n📸 No screenshot directory (no failures or screenshots disabled)")

        # Test recommendations
        print("\n" + "=" * 60)
        print("NEXT STEPS")
        print("=" * 60)

        if len(successes) > 0:
            print("✅ Agent scraper is working! You can now test integration:")
            print("   python3 generate_data.py --full --debug")
            print("\n💡 To update selectors for failing platforms:")
            print("   1. Run test in visible mode (no --headless flag)")
            print("   2. Manually inspect platform search pages in browser")
            print("   3. Update selector arrays in agent_link_scraper.py")
            print("   4. Re-run test to verify fixes")
        else:
            print("❌ Agent scraper is not working. Check the issues:")
            print("   1. Is playwright installed?")
            print("      pip install playwright && playwright install chromium")
            print("   2. Are Playwright browsers installed?")
            print("      playwright install chromium")
            print("   3. Are the CSS selectors outdated?")
            print("      (Streaming sites frequently change their HTML)")
            print("      Check cache/screenshots/ for visual evidence")
            print("   4. Network connectivity issues?")
            print("   5. Rate limiting or blocking from streaming sites?")

        if errors:
            print("\n💡 Error troubleshooting:")
            print("   - ImportError: Install missing dependencies")
            print("   - PlaywrightTimeoutError: Check network or CSS selectors")
            print("   - PermissionError: Check cache directory permissions")
            print("   - Browser launch errors: Run 'playwright install chromium'")

        return len(successes) > 0

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_dependencies():
    """Check if required dependencies are available."""
    print("🔍 Checking dependencies...")

    try:
        from playwright.sync_api import sync_playwright
        print("✅ playwright is installed")
    except ImportError:
        print("❌ playwright is NOT installed")
        print("   Install with: pip install playwright")
        return False

    # Check if Playwright browsers are installed
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try to launch chromium
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                print("✅ Playwright chromium browser is installed")
            except Exception as e:
                print("❌ Playwright chromium browser is NOT installed")
                print("   Install with: playwright install chromium")
                return False
    except Exception as e:
        print(f"❌ Error checking Playwright browsers: {e}")
        return False

    # Check if cache directory exists
    if os.path.exists('cache'):
        print("✅ cache directory exists")
    else:
        print("⚠️  cache directory does not exist (will be created)")

    return True

def main():
    """Main test function."""
    print("🧪 AGENT SCRAPER STANDALONE TEST")
    print("This script tests the agent scraper in isolation\n")

    # Check dependencies first
    if not check_dependencies():
        print("\n❌ Dependencies missing. Please install them first.")
        return False

    print()  # Add spacing

    # Run the test
    success = test_agent_scraper()

    if success:
        print("\n🎉 Test completed successfully!")
    else:
        print("\n💔 Test failed. Check the errors above.")

    return success

if __name__ == "__main__":
    main()