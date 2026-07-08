"""Golden-case validation for the restoration-on-VOD catch finder.

Hits the LIVE Gemini API (grounded), so it is a manual validation script, not a CI
unit test. Asserts the catch DECISION (on_vod) matches the hand-labeled truth on the
four cases that broke the structured-signal approach. Run:

    /usr/bin/python3 scripts/validate_restoration_vod.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemini_scraper.restoration_vod import GeminiRestorationVODFinder

# (title, year, restoration_note, expected_on_vod, why)
GOLDEN = [
    ("The Gold Rush", 1925,
     "2025 4K restoration (Cineteca di Bologna/mk2), premiered Cannes Classics 2025, theatrical",
     False, "restoration is theatrical-only; only the old transfer streams"),
    ("Fight Club", 1999,
     "2026 Fincher-supervised 4K restoration, Dolby Vision, theatrical re-release Apr 2026",
     True, "new 4K Dolby Vision restoration on Apple TV since 2026-05"),
    ("Yi Yi", 2000,
     "2025 4K restoration (Cannes Classics 2025), Criterion 4K UHD Jan 2026",
     True, "restoration on Apple TV 4K; Criterion Channel still the old HD transfer"),
    ("Sorcerer", 1977,
     "2025 Criterion 4K restoration (released June 2025)",
     False, "restoration is disc-only; every digital listing is HD from the old master"),
]


def main() -> int:
    finder = GeminiRestorationVODFinder()
    passed = 0
    for title, year, note, expected, why in GOLDEN:
        v = finder.find_restoration_vod_status(title, year, restoration_note=note)
        if v is None:
            print(f"!! API failed for {title} ({year}) — cannot validate")
            continue
        ok = (v["on_vod"] == expected)
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"\n=== {title} ({year})  [{mark}] ===")
        print(f"  expected on_vod={expected}  ({why})")
        print(f"  got:      available={v['available']}  version={v['is_restoration_version']}  "
              f"on_vod={v['on_vod']}  conf={v['confidence']}")
        print(f"  platforms={v['platforms']}  since={v['since_date']}")
        print(f"  basis: {v['basis']}")
        for s in v['sources'][:3]:
            print(f"    - {s}")

    total = len(GOLDEN)
    print(f"\n{'='*50}\nGOLDEN CASES: {passed}/{total} passed")
    print("Stats:", json.dumps(finder.get_stats()))
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
