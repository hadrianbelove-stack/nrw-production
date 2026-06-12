"""
Allow `python -m gemini_scraper` to run a quick diagnostic.

Prints available finder classes and checks Gemini API key availability.
"""

from gemini_scraper import GeminiYouTubeFinder, GeminiRTFinder, GeminiWikipediaFinder, GeminiVODDateFinder, PullQuoteFinder, LetterboxdQuoteScraper, GeminiIMDbFinder, GeminiCapsuleWriter, HybridYouTubeFinder, HybridRTFinder
from gemini_scraper.base import _get_gemini_api_key


def main():
    finders = [
        GeminiYouTubeFinder, GeminiRTFinder, GeminiWikipediaFinder,
        GeminiVODDateFinder, PullQuoteFinder, LetterboxdQuoteScraper,
        GeminiIMDbFinder, GeminiCapsuleWriter,
    ]
    hybrids = [HybridYouTubeFinder, HybridRTFinder]

    print("gemini_scraper package")
    print(f"  {len(finders)} Gemini finders: {', '.join(c.__name__ for c in finders)}")
    print(f"  {len(hybrids)} Hybrid wrappers: {', '.join(c.__name__ for c in hybrids)}")

    key = _get_gemini_api_key()
    if key:
        print(f"  Gemini API key: configured ({key[:6]}...)")
    else:
        print("  Gemini API key: NOT configured")


if __name__ == '__main__':
    main()
