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

                if result and result.get('url') and result.get('score'):
                    successes += 1
                    status = "✓ SUCCESS"
                    score_text = f"Score: {result.get('score')}%"
                else:
                    status = "✗ FAILED"
                    score_text = "No url/score found"

                results.append({
                    'title': title,
                    'year': year,
                    'success': bool(result and result.get('url') and result.get('score')),
                    'result': result
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
        print(f"Successes: {successes}/10 ({successes*10}%)")
        print(f"Failures:  {10-successes}/10 ({(10-successes)*10}%)")
        print()

        if successes < 7:  # Less than 70% success rate
            print("⚠️  LOW SUCCESS RATE - Consider investigating failures")
        elif successes >= 9:  # 90%+ success rate
            print("✅ EXCELLENT SUCCESS RATE")
        else:
            print("👍 GOOD SUCCESS RATE")

        print()
        print("Detailed Results:")
        print("-" * 40)
        for result in results:
            success_icon = "✓" if result['success'] else "✗"
            print(f"{success_icon} {result['title']} ({result['year']})")
            if not result['success'] and 'error' in result:
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