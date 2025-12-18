#!/usr/bin/env python3
"""
RT Scraper Success Rate Spot Check
10-title harness to measure RT success rate before/after tweaks
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rt_scraper_playwright import RTScraperPlaywright


def test_rt_success_rate():
    """
    Test RT scraper success rate with 10 known titles.
    Success = both url and score are non-null.
    """

    # Mix of popular/new titles with known RT pages
    test_titles = [
        ("The Dark Knight", 2008),
        ("Inception", 2010),
        ("Parasite", 2019),
        ("Everything Everywhere All at Once", 2022),
        ("Top Gun: Maverick", 2022),
        ("The Batman", 2022),
        ("Dune", 2021),
        ("No Time to Die", 2021),
        ("Spider-Man: No Way Home", 2021),
        ("Oppenheimer", 2023)
    ]

    print("RT Scraper Success Rate Test")
    print("=" * 40)
    print(f"Testing {len(test_titles)} titles...")
    print()

    scraper = RTScraperPlaywright()

    try:
        scraper._init_browser()

        successes = 0
        results = []

        for i, (title, year) in enumerate(test_titles, 1):
            print(f"[{i:2d}/10] Testing: {title} ({year})")

            try:
                result = scraper._scrape_rt_page(title, year)

                # Success criterion: RT URL found AND score extracted from RT page
                # With the improved scraper, we should get scores consistently when URLs are found
                has_rt_url = result and result.get('url') and 'rottentomatoes.com' in result.get('url', '')
                has_score = result and result.get('score') is not None

                if has_rt_url and has_score:
                    successes += 1
                    status = "✓ SUCCESS"
                    score_text = f"Score: {result.get('score')}"
                elif has_rt_url and not has_score:
                    status = "⚠ PARTIAL"
                    score_text = "RT URL found but no score extracted"
                else:
                    status = "✗ FAILED"
                    score_text = "No RT URL found"

                results.append({
                    'title': title,
                    'year': year,
                    'success': has_rt_url and has_score,  # Full success requires both URL and score
                    'partial_success': has_rt_url and not has_score,  # Track partial successes separately
                    'result': result,
                    'has_rt_url': has_rt_url,
                    'has_score': has_score
                })

                print(f"         {status} - {score_text}")

            except Exception as e:
                print(f"         ✗ ERROR - {str(e)}")
                results.append({
                    'title': title,
                    'year': year,
                    'success': False,
                    'error': str(e)
                })

        print()
        print("=" * 40)
        print("RESULTS SUMMARY")
        print("=" * 40)

        # Calculate different success metrics
        full_successes = successes  # URL + score
        partial_successes = sum(1 for r in results if r.get('partial_success', False))
        total_rt_urls = full_successes + partial_successes
        total_failures = 10 - total_rt_urls

        print(f"Full success (URL + score): {full_successes}/10 ({full_successes*10}%)")
        print(f"Partial success (URL only): {partial_successes}/10 ({partial_successes*10}%)")
        print(f"Total RT URLs found:        {total_rt_urls}/10 ({total_rt_urls*10}%)")
        print(f"Complete failures:          {total_failures}/10 ({total_failures*10}%)")
        print()

        # Score extraction rate (when URLs are found)
        if total_rt_urls > 0:
            score_extraction_rate = (full_successes / total_rt_urls) * 100
            print(f"Score extraction rate: {score_extraction_rate:.1f}% ({full_successes}/{total_rt_urls} URLs with scores)")
        else:
            print("Score extraction rate: N/A (no RT URLs found)")
        print()

        # Overall assessment based on full success rate
        if full_successes < 7:  # Less than 70% full success rate
            print("⚠️  LOW SUCCESS RATE - Consider investigating failures")
        elif full_successes >= 9:  # 90%+ full success rate
            print("✅ EXCELLENT SUCCESS RATE")
        else:
            print("👍 GOOD SUCCESS RATE")

        print()
        print("Detailed Results:")
        print("-" * 40)
        for result in results:
            if result['success']:
                icon = "✓"
                score_info = f" (score: {result['result'].get('score')})"
            elif result.get('partial_success', False):
                icon = "⚠"
                score_info = " (URL only, no score)"
            else:
                icon = "✗"
                score_info = ""

            print(f"{icon} {result['title']} ({result['year']}){score_info}")
            if not result['success'] and not result.get('partial_success', False) and 'error' in result:
                print(f"    Error: {result['error']}")

        return successes, results

    finally:
        scraper._cleanup_browser()


if __name__ == "__main__":
    successes, results = test_rt_success_rate()

    # Exit with non-zero code if success rate is too low
    if successes < 5:  # Less than 50% success rate
        sys.exit(1)
    else:
        sys.exit(0)