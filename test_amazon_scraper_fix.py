#!/usr/bin/env python3
"""
Test script for Amazon scraper fixes
Tests with specific movies that were failing before
"""

import sys
from streaming_platform_scraper import StreamingPlatformScraper

def test_amazon_scraper():
    """Test Amazon scraper with known failing movies"""

    # Test cases from user's examples
    test_cases = [
        {
            'title': 'The Bitter Taste',
            'year': '2025',
            'expected_asin': 'B0FPMV1CJ6',
            'expected_url': 'https://www.amazon.com/gp/video/detail/B0FPMV1CJ6'
        },
        {
            'title': 'Armed Only With a Camera',
            'year': '2025',
            'expected_asin': 'B0FVHK69SH',
            'expected_url': 'https://www.amazon.com/gp/video/detail/B0FVHK69SH'
        }
    ]

    print("=" * 80)
    print("Amazon Scraper Fix Test")
    print("=" * 80)
    print()

    # Initialize scraper
    print("Initializing scraper...")
    scraper = StreamingPlatformScraper()

    results = []

    for i, test_case in enumerate(test_cases, 1):
        title = test_case['title']
        year = test_case['year']
        expected_asin = test_case['expected_asin']
        expected_url = test_case['expected_url']

        print(f"\n{'='*80}")
        print(f"Test {i}/{len(test_cases)}: {title} ({year})")
        print(f"Expected ASIN: {expected_asin}")
        print(f"{'='*80}\n")

        try:
            # Try to find the link
            result = scraper.get_platform_deep_link(title, year, "Amazon Video")

            if result:
                print(f"\n✅ SUCCESS: Found link!")
                print(f"   URL: {result}")

                # Check if it has the expected ASIN
                if expected_asin in result:
                    print(f"   ✅ ASIN MATCH: Contains expected ASIN {expected_asin}")
                    results.append({
                        'title': title,
                        'status': 'PASS',
                        'found_url': result
                    })
                else:
                    print(f"   ⚠️  ASIN MISMATCH: Expected {expected_asin}, got different ASIN")
                    results.append({
                        'title': title,
                        'status': 'PARTIAL',
                        'found_url': result,
                        'note': f'Expected ASIN {expected_asin} not found'
                    })
            else:
                print(f"\n❌ FAILED: No link found")
                results.append({
                    'title': title,
                    'status': 'FAIL',
                    'found_url': None
                })

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'title': title,
                'status': 'ERROR',
                'error': str(e)
            })

    # Clean up
    print("\n\nCleaning up...")
    scraper.close()

    # Print summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}\n")

    passed = sum(1 for r in results if r['status'] == 'PASS')
    partial = sum(1 for r in results if r['status'] == 'PARTIAL')
    failed = sum(1 for r in results if r['status'] in ['FAIL', 'ERROR'])

    print(f"Total tests: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"⚠️  Partial: {partial}")
    print(f"❌ Failed: {failed}")
    print()

    for result in results:
        status_icon = {
            'PASS': '✅',
            'PARTIAL': '⚠️',
            'FAIL': '❌',
            'ERROR': '💥'
        }.get(result['status'], '❓')

        print(f"{status_icon} {result['title']}: {result['status']}")
        if result.get('found_url'):
            print(f"   URL: {result['found_url']}")
        if result.get('note'):
            print(f"   Note: {result['note']}")
        if result.get('error'):
            print(f"   Error: {result['error']}")

    print(f"\n{'='*80}")

    # Return exit code
    if failed > 0:
        return 1
    elif partial > 0:
        return 2
    else:
        return 0


if __name__ == "__main__":
    exit_code = test_amazon_scraper()
    sys.exit(exit_code)
