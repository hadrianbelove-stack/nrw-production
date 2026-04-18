#!/usr/bin/env python3
"""
Regression tests for YouTube trailer title matching logic.

Tests the check_title_match() method on YouTubeTrailerScraper to ensure
title verification correctly accepts matching trailers and rejects wrong ones.

History: Added after discovering "BODYCAM" was matched to "Cat Cam" via
substring matching. The fix uses whole-word matching with punctuation
normalization and a 0.75 threshold, validated against 816 real trailers.
"""

import sys
import os
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.youtube_trailer_scraper import YouTubeTrailerScraper


class TestTitleMatching(unittest.TestCase):
    """Test the title matching logic used to verify YouTube search results."""

    def check(self, movie, video):
        """Helper: returns (ratio, passed)."""
        return YouTubeTrailerScraper.check_title_match(movie, video)

    # --- Core: whole-word matching prevents substring false positives ---

    def test_substring_rejected(self):
        """'cam' should NOT match inside 'bodycam' — the original bug."""
        ratio, passed = self.check("Cat Cam", "BODYCAM Official Trailer")
        self.assertFalse(passed)

    def test_exact_match(self):
        """Both words present as whole words should pass."""
        ratio, passed = self.check("Cat Cam", "Cat Cam | Official Trailer")
        self.assertTrue(passed)
        self.assertEqual(ratio, 1.0)

    # --- Punctuation normalization: both sides cleaned equally ---

    def test_colon_in_title(self):
        """Colons should be stripped from both movie and video titles."""
        ratio, passed = self.check("Alien: Romulus", "Alien: Romulus | Final Trailer")
        self.assertTrue(passed)

    def test_apostrophe(self):
        """Apostrophes should be stripped: Father's → father + s."""
        ratio, passed = self.check("A Father's Miracle",
                                    "A Father's Miracle – Official Trailer | Netflix")
        self.assertTrue(passed)

    def test_hyphen(self):
        """Hyphens should be stripped: Self-Help → self + help."""
        ratio, passed = self.check("Self-Help", "Self-Help | Official Trailer | Horror Brains")
        self.assertTrue(passed)

    def test_exclamation_and_comma(self):
        """Mixed punctuation should be handled."""
        ratio, passed = self.check("Blessed: Live, Laugh,Run!",
                                    "Blessed: Live, Laugh, Run! - Trailer")
        self.assertTrue(passed)

    def test_parentheses(self):
        """Parenthetical content should be handled."""
        ratio, passed = self.check("D(e)AD", "D(e)ad | Official Trailer")
        self.assertTrue(passed)

    def test_slash(self):
        """Slashes should split into separate words."""
        ratio, passed = self.check("Space/Time", "Space/Time (2026) Official Trailer")
        self.assertTrue(passed)

    # --- Stop word filtering ---

    def test_stop_words_filtered(self):
        """Common words like 'a' should be filtered out."""
        ratio, passed = self.check("Break a Leg", "Break a Leg - Trailer")
        self.assertTrue(passed)
        # "a" filtered, so only "break" and "leg" matter → 2/2 = 1.0
        self.assertEqual(ratio, 1.0)

    def test_all_stop_words_fallback(self):
        """If all words are stop words, fall back to using all words."""
        ratio, passed = self.check("It Is", "It Is - Trailer")
        self.assertTrue(passed)

    # --- Threshold boundary ---

    def test_threshold_exact(self):
        """Exactly 0.75 should pass (>=, not >)."""
        # 3 of 4 content words = 0.75
        ratio, passed = self.check("One Two Three Four", "One Two Three Trailer")
        self.assertEqual(ratio, 0.75)
        self.assertTrue(passed)

    def test_threshold_below(self):
        """Below 0.75 should fail."""
        # 2 of 4 content words = 0.50
        ratio, passed = self.check("One Two Three Four", "One Two Trailer")
        self.assertEqual(ratio, 0.50)
        self.assertFalse(passed)

    # --- Wrong movie rejection ---

    def test_wrong_movie_zero_overlap(self):
        """Completely different movie should get 0.0."""
        ratio, passed = self.check("Boss", "Good Fortune Official Trailer")
        self.assertFalse(passed)
        self.assertEqual(ratio, 0.0)

    def test_wrong_movie_partial_overlap(self):
        """Different movie with some shared words should still fail."""
        ratio, passed = self.check("The Boy by the Pool", "Boy in the Pool | tvN Movies")
        self.assertFalse(passed)
        # "boy" matches, "pool" matches, but "by" doesn't → 2/3 = 0.67
        self.assertLess(ratio, 0.75)

    # --- Real-world cases that must pass ---

    def test_real_malcolm(self):
        ratio, passed = self.check("Malcolm in the Middle: Life's Still Unfair",
                                    "Malcolm in the Middle: Life's Still Unfair | Official Trailer | Hulu")
        self.assertTrue(passed)

    def test_real_sniper(self):
        ratio, passed = self.check("Sniper: No Nation",
                                    "SNIPER: NO NATION - Official Trailer (HD)")
        self.assertTrue(passed)

    def test_real_untold(self):
        ratio, passed = self.check("Untold: Jail Blazers",
                                    "Untold: Jail Blazers | Official Trailer | Netflix")
        self.assertTrue(passed)

    def test_real_tmnt_long_subtitle(self):
        """Long subtitle difference is an accepted trade-off — should fail at 0.75."""
        ratio, passed = self.check(
            "Teenage Mutant Ninja Turtles: Chrome Alone 2 - Lost in New Jersey",
            "Teenage Mutant Ninja Turtles: Chrome Alone 2 | Official Teaser (2025 Short)")
        # This fails because the subtitle "Lost in New Jersey" adds 4 unmatched words.
        # Accepted trade-off: no trailer is better than a wrong trailer.
        self.assertFalse(passed)

    # --- Case insensitivity ---

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        ratio, passed = self.check("THE FUZZIES", "The Fuzzies Official Trailer")
        self.assertTrue(passed)


def run_tests():
    """Run tests with verbose output."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestTitleMatching)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
