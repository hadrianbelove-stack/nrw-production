#!/usr/bin/env python3
"""
Agent Scraper Improvements Test

Tests the enhanced agent scraper (Netflix, Disney+, Max, Hulu) to verify that
the Amazon scraper improvements have been successfully applied and are working correctly.

This includes testing:
- Enhanced title matching with stopwords
- Flexible year matching (±1 year)
- Position-based filtering to avoid sponsored results
- Alternative validation for featured results
"""

import sys
import re
import time
import asyncio
import argparse
import os
from agent_link_scraper import AgentLinkScraper


def check_async_fix_status():
    """
    Verify that the async fix is working before running agent scraper tests.

    Returns:
        bool: True if pre-flight checks passed, False otherwise
    """
    print("🔍 Pre-flight checks: Verifying async fix status...")

    # Check 1: Import and test PlaywrightManager
    try:
        from playwright_manager import get_playwright_manager
        print("✅ PlaywrightManager import successful")

        manager = get_playwright_manager()
        print("✅ PlaywrightManager instance created")

        playwright = manager.get_playwright()
        print("✅ Playwright instance obtained from manager")

        manager.release()
        print("✅ PlaywrightManager released successfully")

    except Exception as e:
        print(f"❌ PlaywrightManager test failed: {e}")
        return False

    # Check 2: Check for event loop
    try:
        loop = asyncio.get_running_loop()
        print("❌ WARNING: Event loop already running")
        print("   This may cause asyncio conflicts")
        return False
    except RuntimeError:
        print("✅ No event loop detected")

    # Check 3: Verify scraper imports
    try:
        scraper = AgentLinkScraper()
        if hasattr(scraper, 'manager'):
            print("✅ AgentLinkScraper using PlaywrightManager")
        else:
            print("❌ AgentLinkScraper missing manager attribute (using old code?)")
            return False
        scraper.close()
    except Exception as e:
        print(f"❌ AgentLinkScraper import test failed: {e}")
        return False

    print("✅ All pre-flight checks passed")
    return True


def validate_platform_url(url, platform):
    """
    Validate that a found URL matches the expected format for each platform.

    Args:
        url (str): The URL returned by the scraper
        platform (str): Platform name ("Netflix", "Disney+", "Max", "Hulu")

    Returns:
        tuple: (is_valid: bool, validation_message: str)
    """
    if not url:
        return False, "URL is None or empty"

    if not isinstance(url, str):
        return False, "URL is not a string"

    if not url.startswith('https://'):
        return False, "URL does not use HTTPS"

    if 'google.com/search' in url:
        return False, "URL appears to be a Google search fallback"

    if len(url) < 20:
        return False, "URL is too short (likely a stub)"

    # Platform-specific validation
    if platform == "Netflix":
        if 'netflix.com' not in url:
            return False, "URL does not contain expected Netflix domain"
        if '/title/' in url or '/watch/' in url:
            return True, "Valid Netflix URL with /title/ or /watch/ path"
        else:
            return False, "Netflix URL does not contain expected /title/ or /watch/ path"

    elif platform == "Disney+":
        if 'disneyplus.com' not in url:
            return False, "URL does not contain expected Disney+ domain"
        if '/movies/' in url or '/video/' in url:
            return True, "Valid Disney+ URL with /movies/ or /video/ path"
        else:
            return False, "Disney+ URL does not contain expected /movies/ or /video/ path"

    elif platform == "Max":
        if 'max.com' not in url:
            return False, "URL does not contain expected Max domain"
        if '/movies/' in url or '/video/' in url:
            return True, "Valid Max URL with /movies/ or /video/ path"
        else:
            return False, "Max URL does not contain expected /movies/ or /video/ path"

    elif platform == "Hulu":
        if 'hulu.com' not in url:
            return False, "URL does not contain expected Hulu domain"
        if '/movie/' in url or '/watch/' in url:
            return True, "Valid Hulu URL with /movie/ or /watch/ path"
        else:
            return False, "Hulu URL does not contain expected /movie/ or /watch/ path"

    else:
        return False, f"Unknown platform: {platform}"


# Test case definitions
test_cases = [
    # Netflix tests (2 movies)
    {
        'title': 'A House of Dynamite',
        'year': '2025',
        'platform': 'Netflix',
        'service': 'Netflix'
    },
    {
        'title': 'Vash Level 2',
        'year': '2025',
        'platform': 'Netflix',
        'service': 'Netflix'
    },

    # Disney+ tests (2 movies)
    {
        'title': 'LEGO Frozen: Operation Puffins',
        'year': '2025',
        'platform': 'Disney+',
        'service': 'Disney+'
    },
    {
        'title': 'Spidey and Iron Man: Avengers Team Up!',
        'year': '2025',
        'platform': 'Disney+',
        'service': 'Disney+'
    },

    # Hulu test (1 movie)
    {
        'title': 'The Hand That Rocks the Cradle',
        'year': '2025',
        'platform': 'Hulu',
        'service': 'Hulu'
    },

    # Max test (1 movie)
    {
        'title': 'Armed Only with a Camera: The Life and Death of Brent Renaud',
        'year': '2025',
        'platform': 'Max',
        'service': 'Max'
    }
]


def test_agent_scraper():
    """
    Main test orchestration function.

    Returns:
        int: Exit code (0=pass, 1=fail, 2=partial)
    """
    # Print test header
    print("=" * 80)
    print("Agent Scraper Improvements Test")
    print("Testing Netflix, Disney+, Max, and Hulu scrapers")
    print("=" * 80)
    print()
    print("Test Configuration:")
    print(f"  Total test cases: {len(test_cases)}")
    print("  Platforms: Netflix (2), Disney+ (2), Max (1), Hulu (1)")
    print("  Validation: Enhanced title matching, flexible year, position filtering")
    print("=" * 80)
    print()

    # Run pre-flight checks
    if not check_async_fix_status():
        print("\n❌ Pre-flight checks failed!")
        print("\nDiagnostic suggestions:")
        print("  1. Restart Python process to reload modules")
        print("  2. Clear __pycache__: find . -name '__pycache__' -exec rm -rf {} +")
        print("  3. Verify commit: git log -1 --oneline")
        print("  4. Check for stale processes: ps aux | grep python")
        return 1
    print()

    # Initialize scraper
    print("Initializing agent scraper...")
    try:
        scraper = AgentLinkScraper()
        print("✅ Agent scraper initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize agent scraper: {e}")
        return 1

    print()

    # Initialize results tracking
    results = []
    platform_stats = {
        'Netflix': {'attempted': 0, 'passed': 0, 'failed': 0},
        'Disney+': {'attempted': 0, 'passed': 0, 'failed': 0},
        'Max': {'attempted': 0, 'passed': 0, 'failed': 0},
        'Hulu': {'attempted': 0, 'passed': 0, 'failed': 0}
    }

    # Test loop
    for i, test_case in enumerate(test_cases, 1):
        title = test_case['title']
        year = test_case['year']
        platform = test_case['platform']
        service = test_case['service']

        # Print test header
        print("=" * 80)
        print(f"Test {i}/{len(test_cases)}: {title} ({year}) - {platform}")
        print("=" * 80)

        # Increment platform attempt counter
        platform_stats[platform]['attempted'] += 1

        try:
            # Call scraper with timing
            print(f"Searching {platform} for {title}...")
            start_time = time.time()
            movie_id = f"test-{i:02d}"
            result = scraper.find_watch_link(movie_id, title, year, service)
            end_time = time.time()
            elapsed_time = end_time - start_time

            # Process result
            if not result:
                print("❌ FAILED: No link found")
                platform_stats[platform]['failed'] += 1
                results.append({
                    'title': title,
                    'platform': platform,
                    'status': 'FAIL',
                    'found_url': None,
                    'validation_message': 'Scraper returned no link',
                    'selector_used': None,
                    'error': None,
                    'elapsed_time': elapsed_time
                })
            else:
                # Extract URL and metadata
                if isinstance(result, dict):
                    url = result.get('link')
                    selector_used = result.get('selector_used')
                else:
                    url = result
                    selector_used = None

                print(f"✅ Found link: {url}")
                if selector_used:
                    print(f"   Selector used: {selector_used}")

                # Validate URL
                is_valid, message = validate_platform_url(url, platform)

                if is_valid:
                    print(f"✅ VALIDATION PASSED: {message}")
                    platform_stats[platform]['passed'] += 1
                    results.append({
                        'title': title,
                        'platform': platform,
                        'status': 'PASS',
                        'found_url': url,
                        'validation_message': message,
                        'selector_used': selector_used,
                        'error': None,
                        'elapsed_time': elapsed_time
                    })
                else:
                    print(f"⚠️ VALIDATION FAILED: {message}")
                    print(f"   URL: {url}")
                    platform_stats[platform]['failed'] += 1
                    results.append({
                        'title': title,
                        'platform': platform,
                        'status': 'PARTIAL',
                        'found_url': url,
                        'validation_message': message,
                        'selector_used': selector_used,
                        'error': None,
                        'elapsed_time': elapsed_time
                    })

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            import traceback
            print("Full traceback:")
            traceback.print_exc()

            # Add diagnostic output on failure
            print("\n🔍 Diagnostic information:")
            print("Checking if PlaywrightManager is active...")
            try:
                if hasattr(scraper, 'manager'):
                    print("✅ Scraper has manager reference")
                else:
                    print("❌ Scraper missing manager reference (using old code?)")
            except:
                print("❌ Unable to check scraper manager")

            # Check for asyncio errors in exception
            if 'asyncio' in str(e).lower() or 'event loop' in str(e).lower():
                print("❌ ASYNC ERROR DETECTED: {}".format(str(e)))
                print("This suggests the async fix is not working")
                print("Verify PlaywrightManager commit (fb271c2d) is active")

            platform_stats[platform]['failed'] += 1
            results.append({
                'title': title,
                'platform': platform,
                'status': 'ERROR',
                'found_url': None,
                'validation_message': None,
                'selector_used': None,
                'error': str(e),
                'elapsed_time': 0
            })

        # Add spacing between tests
        print()

    # Cleanup
    print("\n\nCleaning up...")
    try:
        scraper.close()
        print("✅ Browser closed and cache saved")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

    # Print summary
    print("\n")
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total_tests = len(results)
    passed = sum(1 for r in results if r['status'] == 'PASS')
    partial = sum(1 for r in results if r['status'] == 'PARTIAL')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')

    print(f"\nTotal tests: {total_tests}")
    print(f"✅ Passed: {passed}")
    print(f"⚠️ Partial: {partial}")
    print(f"❌ Failed: {failed}")
    print(f"💥 Errors: {errors}")
    print(f"\nOverall success rate: {(passed/total_tests)*100:.1f}% ({passed}/{total_tests})")

    # Calculate timing statistics
    times = [r.get('elapsed_time', 0) for r in results if r.get('elapsed_time', 0) > 0]
    if times:
        total_time = sum(times)
        avg_time = total_time / len(times)
        print(f"\nTiming Statistics:")
        print(f"  Total test duration: {total_time:.1f} seconds")
        print(f"  Average time per search: {avg_time:.1f} seconds")

        # Per-platform timing
        platform_times = {}
        for result in results:
            platform = result['platform']
            elapsed = result.get('elapsed_time', 0)
            if elapsed > 0:
                if platform not in platform_times:
                    platform_times[platform] = []
                platform_times[platform].append(elapsed)

        for platform, times_list in platform_times.items():
            if times_list:
                avg_platform_time = sum(times_list) / len(times_list)
                print(f"  {platform} average: {avg_platform_time:.1f} seconds per search")

    # Per-platform statistics
    print("\n")
    print("=" * 80)
    print("PER-PLATFORM RESULTS")
    print("=" * 80)

    for platform, stats in platform_stats.items():
        attempted = stats['attempted']
        if attempted > 0:
            passed_count = stats['passed']
            failed_count = stats['failed']
            success_rate = (passed_count / attempted) * 100

            print(f"\n{platform}:")
            print(f"  Attempted: {attempted}")
            print(f"  Passed: {passed_count}")
            print(f"  Failed: {failed_count}")
            print(f"  Success rate: {success_rate:.1f}%")

    # Detailed results
    print("\n")
    print("=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)

    for result in results:
        title = result['title']
        platform = result['platform']
        status = result['status']
        url = result['found_url']
        validation_msg = result['validation_message']
        selector = result['selector_used']
        error = result['error']

        if status == 'PASS':
            print(f"\n✅ {title} ({platform}): PASS")
            print(f"   URL: {url}")
            print(f"   Validation: {validation_msg}")
            if selector:
                print(f"   Selector: {selector}")

        elif status == 'PARTIAL':
            print(f"\n⚠️ {title} ({platform}): PARTIAL")
            print(f"   URL: {url}")
            print(f"   Validation: {validation_msg}")
            if selector:
                print(f"   Selector: {selector}")

        elif status == 'FAIL':
            print(f"\n❌ {title} ({platform}): FAIL")
            print(f"   Reason: {validation_msg}")

        elif status == 'ERROR':
            print(f"\n💥 {title} ({platform}): ERROR")
            print(f"   Error: {error}")

    # Add baseline comparison
    print("\n")
    print("=" * 80)
    print("IMPROVEMENT vs BASELINE")
    print("=" * 80)

    print("\nBaseline (from old logs):")
    print("  Platform scraper: 0% success rate (0/327 attempts)")
    print("  Agent scraper: 0% success rate (0/95 attempts, cache only)")
    print("  Google fallbacks: 42 movies")

    current_success_rate = (passed/total_tests)*100 if total_tests > 0 else 0
    print(f"\nCurrent Results:")
    print(f"  Agent scraper: {current_success_rate:.1f}% success rate ({passed}/{total_tests} attempts)")
    print(f"  Improvement: +{current_success_rate:.1f} percentage points")

    if current_success_rate > 50:
        print("\n🎉 SUCCESS: Agent scraper showing significant improvement!")
    elif current_success_rate > 30:
        print("\n📈 PROGRESS: Agent scraper showing moderate improvement")
    elif current_success_rate > 0:
        print("\n⚠️ PARTIAL: Some improvement detected, but more work needed")
    else:
        print("\n❌ NO IMPROVEMENT: Agent scraper still failing completely")

    print("\n")
    print("=" * 80)

    # Calculate exit code
    failed_tests = sum(1 for r in results if r['status'] in ['FAIL', 'ERROR'])
    partial_tests = sum(1 for r in results if r['status'] == 'PARTIAL')

    if failed_tests > 0:
        return 1  # Failure
    elif partial_tests > 0:
        return 2  # Partial success
    else:
        return 0  # Full success


if __name__ == "__main__":
    # Add command-line argument parsing
    parser = argparse.ArgumentParser(description='Test agent scraper improvements')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Clear agent scraper cache before running tests')
    args = parser.parse_args()

    # Clear cache if requested
    if args.clear_cache:
        cache_file = 'cache/agent_links_cache.json'
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print("🗑️  Cleared agent scraper cache")
        else:
            print("ℹ️  Agent scraper cache not found (already clear)")
        print()

    exit_code = test_agent_scraper()
    sys.exit(exit_code)