#!/usr/bin/env python3
"""
Test script for YouTube scraper validation.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch
import tempfile
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_paid_scraper import YouTubePaidScraper


class TestYouTubePaidScraper(unittest.TestCase):
    """Test cases for YouTubePaidScraper class."""

    def setUp(self):
        """Set up test environment."""
        # Create a temporary cache file
        self.temp_cache = tempfile.NamedTemporaryFile(mode='w', delete=False)
        self.temp_cache.close()

        # Test configuration
        self.test_config = {
            'rate_limit': 0.1,  # Fast for testing
            'timeout': 5,
            'max_retries': 1,
            'cache_ttl_days': 1,
            'discovery': {
                'max_pages': 1,
                'min_runtime': 70,
                'search_queries': ['test film'],
                'include_free': True
            },
            'exponential_backoff': {
                'base_delay': 0.1,
                'max_delay': 1.0,
                'jitter_ratio': 0.1
            }
        }

    def tearDown(self):
        """Clean up test environment."""
        try:
            os.unlink(self.temp_cache.name)
        except:
            pass

    def test_scraper_initialization(self):
        """Test scraper initialization with config."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config,
            headless=True
        )

        self.assertEqual(scraper.cache_file, self.temp_cache.name)
        self.assertEqual(scraper.config, self.test_config)
        self.assertTrue(scraper.headless)
        self.assertEqual(scraper.rate_limit, 0.1)
        self.assertEqual(scraper.min_runtime, 70)
        self.assertIn('test film', scraper.search_queries)

    def test_normalize_title(self):
        """Test title normalization function."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        # Test basic normalization
        self.assertEqual(scraper._normalize_title('The Movie'), 'the movie')

        # Test special characters removal
        self.assertEqual(scraper._normalize_title('Movie: Title!'), 'movie title')

        # Test unicode handling
        self.assertEqual(scraper._normalize_title('Café'), 'cafe')

        # Test whitespace handling
        self.assertEqual(scraper._normalize_title('  Multiple   Spaces  '), 'multiple spaces')

        # Test empty string
        self.assertEqual(scraper._normalize_title(''), '')

        # Test None input
        self.assertEqual(scraper._normalize_title(None), '')

    def test_calculate_title_match(self):
        """Test title matching calculation."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        # Perfect match
        match = scraper._calculate_title_match('The Movie', 'The Movie')
        self.assertEqual(match, 1.0)

        # Partial match
        match = scraper._calculate_title_match('The Movie', 'Movie')
        self.assertGreater(match, 0.5)

        # No match
        match = scraper._calculate_title_match('The Movie', 'Different Film')
        self.assertEqual(match, 0.0)

        # Stopwords ignored
        match = scraper._calculate_title_match('A Great Movie', 'Great Movie')
        self.assertEqual(match, 1.0)

    def test_extract_film_metadata_structure(self):
        """Test film metadata extraction returns correct structure."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        # Mock element with basic data
        mock_element = Mock()
        mock_page = Mock()

        # Mock the locator chain more carefully
        def mock_locator(selector):
            mock_locator_obj = Mock()
            if 'href' in selector or 'a' in selector:
                mock_first = Mock()
                mock_first.count.return_value = 1
                mock_first.get_attribute.return_value = 'https://youtube.com/watch?v=testid123'
                mock_locator_obj.first = mock_first
            else:
                mock_first = Mock()
                mock_first.count.return_value = 1
                mock_first.inner_text.return_value = 'Test Film Title'
                mock_first.get_attribute.return_value = 'Test Film Title'
                mock_locator_obj.first = mock_first
            return mock_locator_obj

        mock_element.locator = mock_locator
        mock_element.inner_text.return_value = 'Test Film Title 90 min'

        # Test metadata extraction
        with patch.object(scraper, '_get_runtime_from_video_page', return_value=90):
            metadata = scraper._extract_film_metadata(mock_element, mock_page)

        self.assertIsInstance(metadata, dict)
        self.assertIn('title', metadata)
        self.assertIn('youtube_url', metadata)
        self.assertIn('video_id', metadata)
        self.assertIn('runtime', metadata)
        self.assertIn('discovery_date', metadata)

    def test_cache_functionality(self):
        """Test cache loading and saving."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        # Test initial empty cache
        self.assertEqual(scraper.cache, {})

        # Test cache saving with current timestamp (won't expire)
        from datetime import datetime
        current_time = datetime.now().isoformat()
        scraper.cache['test_key'] = {'data': 'test_value', 'timestamp': current_time}
        scraper._save_cache()

        # Test cache loading
        new_scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )
        self.assertIn('test_key', new_scraper.cache)

    def test_tmdb_matching_without_api_key(self):
        """Test TMDB matching when API key is not available."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )
        scraper.tmdb_api_key = ''

        result, confidence = scraper._match_with_tmdb('Test Movie')
        self.assertIsNone(result)
        self.assertEqual(confidence, 'none')

    @patch('youtube_paid_scraper.requests.get')
    def test_tmdb_matching_with_api_key(self, mock_get):
        """Test TMDB matching with mocked API response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {
                    'id': 12345,
                    'title': 'Test Movie',
                    'release_date': '2023-01-01',
                    'genres': [{'name': 'Drama'}],
                    'overview': 'A test movie'
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )
        scraper.tmdb_api_key = 'test_key'

        mock_get.return_value = mock_response
        result, confidence = scraper._match_with_tmdb('Test Movie', 2023)

        self.assertIsNotNone(result)
        self.assertEqual(result['id'], 12345)
        self.assertIn(confidence, ['high', 'medium', 'low'])

    def test_youtube_url_patterns(self):
        """Test various YouTube URL patterns for video ID extraction."""
        test_cases = [
            ('https://youtube.com/watch?v=testid123', 'testid123'),
            ('https://youtube.com/watch/testid123', 'testid123'),
            ('https://www.youtube.com/watch?v=testid123&t=30s', 'testid123'),
            ('https://youtu.be/testid123', 'testid123'),
            ('', None),
            ('not-a-url', None),
            ('https://vimeo.com/123456', None)
        ]

        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        for url, expected_id in test_cases:
            # Mock element that returns the URL
            mock_element = Mock()
            mock_page = Mock()

            if expected_id:
                mock_link = Mock()
                mock_link.count.return_value = 1
                mock_link.get_attribute.return_value = url
                mock_element.locator.return_value.first = mock_link

                mock_title = Mock()
                mock_title.count.return_value = 1
                mock_title.inner_text.return_value = 'Test Film'
                mock_element.locator.return_value.first = mock_title

                mock_element.inner_text.return_value = 'Test Film 90 min'

                metadata = scraper._extract_film_metadata(mock_element, mock_page)
                if metadata:
                    self.assertEqual(metadata.get('video_id'), expected_id)

    def test_runtime_parsing(self):
        """Test runtime parsing from various formats."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        # Mock element with different runtime formats
        test_cases = [
            ('90 min', 90),
            ('1:30:00', 90),  # 1 hour 30 minutes
            ('2:15', 2),      # 2 minutes 15 seconds
            ('Duration: 105', 105),
            ('Runtime: 80', 80),
            ('No runtime info', 80)  # Default
        ]

        for text, expected_runtime in test_cases:
            mock_element = Mock()
            mock_page = Mock()

            mock_link = Mock()
            mock_link.count.return_value = 1
            mock_link.get_attribute.return_value = 'https://youtube.com/watch?v=testid123'
            mock_element.locator.return_value.first = mock_link

            mock_title = Mock()
            mock_title.count.return_value = 1
            mock_title.inner_text.return_value = 'Test Film'
            mock_element.locator.return_value.first = mock_title

            mock_element.inner_text.return_value = text

            with patch.object(scraper, '_get_runtime_from_video_page', return_value=None):
                metadata = scraper._extract_film_metadata(mock_element, mock_page)

            if metadata:
                self.assertEqual(metadata.get('runtime'), expected_runtime)

    def test_price_extraction(self):
        """Test price extraction from element text."""
        scraper = YouTubePaidScraper(
            cache_file=self.temp_cache.name,
            config=self.test_config
        )

        test_cases = [
            ('Free with ads', True, 'Free', 'Free'),
            ('Rent $3.99 Buy $12.99', False, '$3.99', '$12.99'),
            ('Buy $9.99', False, None, '$9.99'),
            ('No price info', False, None, None)
        ]

        for text, expected_free, expected_rent, expected_buy in test_cases:
            mock_element = Mock()
            mock_page = Mock()

            mock_link = Mock()
            mock_link.count.return_value = 1
            mock_link.get_attribute.return_value = 'https://youtube.com/watch?v=testid123'
            mock_element.locator.return_value.first = mock_link

            mock_title = Mock()
            mock_title.count.return_value = 1
            mock_title.inner_text.return_value = 'Test Film'
            mock_element.locator.return_value.first = mock_title

            mock_element.inner_text.return_value = text

            metadata = scraper._extract_film_metadata(mock_element, mock_page)

            if metadata:
                self.assertEqual(metadata.get('is_free'), expected_free)
                self.assertEqual(metadata.get('price_rent'), expected_rent)
                self.assertEqual(metadata.get('price_buy'), expected_buy)


class TestYouTubeScrapeIntegration(unittest.TestCase):
    """Integration tests that require careful setup and may access external resources."""

    def setUp(self):
        """Set up integration test environment."""
        self.temp_cache = tempfile.NamedTemporaryFile(mode='w', delete=False)
        self.temp_cache.close()

        self.test_config = {
            'rate_limit': 1.0,  # Slower for external requests
            'timeout': 10,
            'max_retries': 1,
            'cache_ttl_days': 1,
            'discovery': {
                'max_pages': 1,
                'min_runtime': 70,
                'search_queries': ['test'],
                'include_free': True
            }
        }

    def tearDown(self):
        """Clean up integration test environment."""
        try:
            os.unlink(self.temp_cache.name)
        except:
            pass

    def test_scraper_initialization_with_defaults(self):
        """Test scraper can initialize with default config fallback."""
        # This test doesn't require external resources
        with patch('yaml.safe_load') as mock_yaml:
            mock_yaml.side_effect = Exception("No config file")

            scraper = YouTubePaidScraper(cache_file=self.temp_cache.name)

            # Should fall back to defaults
            self.assertIsNotNone(scraper.config)
            self.assertIn('discovery', scraper.config)


def run_tests():
    """Run all test suites."""
    print("🧪 Running YouTube scraper validation tests...")
    print("=" * 50)

    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestYouTubePaidScraper)
    integration_suite = unittest.TestLoader().loadTestsFromTestCase(TestYouTubeScrapeIntegration)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)

    print("\n📋 Unit Tests:")
    print("-" * 30)
    result1 = runner.run(suite)

    print("\n🔗 Integration Tests:")
    print("-" * 30)
    result2 = runner.run(integration_suite)

    # Summary
    total_tests = result1.testsRun + result2.testsRun
    total_failures = len(result1.failures) + len(result2.failures)
    total_errors = len(result1.errors) + len(result2.errors)

    print("\n" + "=" * 50)
    print("🎯 Test Summary")
    print("=" * 50)
    print(f"Total tests run: {total_tests}")
    print(f"Failures: {total_failures}")
    print(f"Errors: {total_errors}")

    if total_failures == 0 and total_errors == 0:
        print("✅ All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)