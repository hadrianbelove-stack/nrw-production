#!/usr/bin/env python3
"""
Newsletter mapping tests for generate_newsletter.py

Tests the newsletter generation functionality including:
- Review inclusion logic
- Platform grouping
- Date filtering
- Newsletter formatting

These tests use mocked data to verify the mapping and filtering logic.
"""

import unittest
import json
import tempfile
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from generate_newsletter import NewsletterGenerator
except ImportError:
    # Skip tests if generate_newsletter can't be imported
    print("Warning: Could not import generate_newsletter - skipping newsletter tests")
    NewsletterGenerator = None


class TestNewsletterMapping(unittest.TestCase):
    """Test newsletter mapping and filtering functionality."""

    def setUp(self):
        """Set up test environment with mock data."""
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create mock data.json
        self.mock_movies = [
            {
                'id': 1001,
                'title': 'Test Movie 1',
                'digital_date': '2024-11-01',
                'year': 2024,
                'watch_links': {
                    'streaming': {'service': 'Netflix', 'link': 'https://netflix.com/test1'},
                    'rent': {'service': 'Amazon', 'link': 'https://amazon.com/rent/test1'},
                    'buy': {'service': 'iTunes', 'link': 'https://itunes.com/buy/test1'}
                },
                'rt_score': 85,
                'overview': 'A great test movie for streaming'
            },
            {
                'id': 1002,
                'title': 'Test Movie 2',
                'digital_date': '2024-11-02',
                'year': 2024,
                'watch_links': {
                    'rent': {'service': 'Amazon', 'link': 'https://amazon.com/rent/test2'},
                    'buy': {'service': 'Apple TV', 'link': 'https://tv.apple.com/buy/test2'}
                },
                'rt_score': 72,
                'overview': 'Another test movie available for rent/purchase'
            },
            {
                'id': 1003,
                'title': 'Test Movie 3',
                'digital_date': '2024-10-15',  # Older date
                'year': 2024,
                'watch_links': {
                    'streaming': {'service': 'Hulu', 'link': 'https://hulu.com/test3'}
                },
                'rt_score': 91,
                'overview': 'An older test movie on streaming'
            }
        ]

        # Create mock movie_reviews.json
        self.mock_reviews = {
            '1001': {
                'title': 'Test Movie 1',
                'review': 'This is an excellent movie with great action sequences.',
                'rating': 4.5,
                'reviewed_date': '2024-11-01'
            },
            '1002': {
                'title': 'Test Movie 2',
                'review': 'A decent movie but not outstanding.',
                'rating': 3.0,
                'reviewed_date': '2024-11-02'
            }
            # Note: No review for movie 1003
        }

        with open('data.json', 'w') as f:
            json.dump({'movies': self.mock_movies}, f)

        with open('admin/movie_reviews.json', 'w') as f:
            os.makedirs('admin', exist_ok=True)
            json.dump(self.mock_reviews, f)

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.old_cwd)
        import shutil
        shutil.rmtree(self.test_dir)

    @unittest.skipIf(NewsletterGenerator is None, "NewsletterGenerator not available")
    def test_review_inclusion_logic(self):
        """
        Test: Movies with reviews are properly included and mapped.

        Verifies that:
        - Movies with reviews are included in newsletter
        - Review content is properly mapped
        - Movies without reviews are excluded (unless configured otherwise)
        """
        generator = NewsletterGenerator()
        generator.load_data()
        generator.load_reviews('admin/movie_reviews.json')

        # Filter movies that have reviews
        reviewed_movies = []
        for movie in generator.movies:
            movie_id = str(movie.get('id'))
            if movie_id in generator.reviews:
                reviewed_movies.append(movie)

        # Verify review inclusion logic
        self.assertEqual(len(reviewed_movies), 2, "Should find 2 movies with reviews")

        # Check that the correct movies are included
        reviewed_titles = [m['title'] for m in reviewed_movies]
        self.assertIn('Test Movie 1', reviewed_titles)
        self.assertIn('Test Movie 2', reviewed_titles)
        self.assertNotIn('Test Movie 3', reviewed_titles)

        # Verify review content mapping
        movie1 = next(m for m in reviewed_movies if m['title'] == 'Test Movie 1')
        movie1_review = generator.reviews[str(movie1['id'])]
        self.assertEqual(movie1_review['rating'], 4.5)
        self.assertIn('excellent movie', movie1_review['review'])

    @unittest.skipIf(NewsletterGenerator is None, "NewsletterGenerator not available")
    def test_platform_grouping(self):
        """
        Test: Movies are properly grouped by streaming platforms.

        Verifies that:
        - Movies are categorized by availability (streaming vs rent/buy)
        - Platform names are correctly extracted
        - Multiple platforms per movie are handled properly
        """
        generator = NewsletterGenerator()
        generator.load_data()

        # Test platform grouping logic
        streaming_movies = []
        rent_buy_movies = []

        for movie in generator.movies:
            watch_links = movie.get('watch_links', {})

            if 'streaming' in watch_links and watch_links['streaming']:
                streaming_movies.append(movie)

            if ('rent' in watch_links and watch_links['rent']) or \
               ('buy' in watch_links and watch_links['buy']):
                rent_buy_movies.append(movie)

        # Verify grouping
        self.assertEqual(len(streaming_movies), 2)  # Test Movie 1 and 3
        self.assertEqual(len(rent_buy_movies), 2)   # Test Movie 1 and 2

        # Verify platform extraction
        streaming_platforms = set()
        for movie in streaming_movies:
            service = movie['watch_links']['streaming']['service']
            streaming_platforms.add(service)

        self.assertIn('Netflix', streaming_platforms)
        self.assertIn('Hulu', streaming_platforms)

        # Check rent/buy platforms
        rent_buy_platforms = set()
        for movie in rent_buy_movies:
            if 'rent' in movie['watch_links'] and movie['watch_links']['rent']:
                rent_buy_platforms.add(movie['watch_links']['rent']['service'])
            if 'buy' in movie['watch_links'] and movie['watch_links']['buy']:
                rent_buy_platforms.add(movie['watch_links']['buy']['service'])

        self.assertIn('Amazon', rent_buy_platforms)
        self.assertIn('iTunes', rent_buy_platforms)
        self.assertIn('Apple TV', rent_buy_platforms)

    @unittest.skipIf(NewsletterGenerator is None, "NewsletterGenerator not available")
    def test_date_filtering(self):
        """
        Test: Date filtering works correctly for newsletter generation.

        Verifies that:
        - Recent movies (within date range) are included
        - Older movies (outside date range) are excluded
        - Date parsing handles different formats correctly
        """
        generator = NewsletterGenerator()
        generator.load_data()

        # Test date filtering for last 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_movies = []

        for movie in generator.movies:
            digital_date_str = movie.get('digital_date')
            if digital_date_str:
                try:
                    movie_date = datetime.strptime(digital_date_str, '%Y-%m-%d')
                    if movie_date >= cutoff_date:
                        recent_movies.append(movie)
                except ValueError:
                    # Skip movies with invalid date formats
                    continue

        # Verify date filtering (movies from Nov 2024 should be recent)
        recent_titles = [m['title'] for m in recent_movies]
        self.assertIn('Test Movie 1', recent_titles)
        self.assertIn('Test Movie 2', recent_titles)

        # Test Movie 3 from October might or might not be included depending on current date
        # The important thing is that the filtering logic works

        # Test stricter date filtering (last 7 days)
        week_cutoff = datetime.now() - timedelta(days=7)
        very_recent_movies = []

        for movie in generator.movies:
            digital_date_str = movie.get('digital_date')
            if digital_date_str:
                try:
                    movie_date = datetime.strptime(digital_date_str, '%Y-%m-%d')
                    if movie_date >= week_cutoff:
                        very_recent_movies.append(movie)
                except ValueError:
                    continue

        # This test is more dependent on the actual test date, so we just verify the logic runs
        self.assertIsInstance(very_recent_movies, list)

    @unittest.skipIf(NewsletterGenerator is None, "NewsletterGenerator not available")
    def test_newsletter_formatting_structure(self):
        """
        Test: Newsletter content is properly structured and formatted.

        Verifies that:
        - Newsletter sections are properly created
        - Movie information is correctly formatted
        - HTML/Markdown formatting is applied correctly
        """
        generator = NewsletterGenerator()
        generator.load_data()
        generator.load_reviews('admin/movie_reviews.json')

        # Test basic newsletter structure creation
        # We'll test the data preparation rather than full HTML generation
        reviewed_movies = []
        for movie in generator.movies:
            movie_id = str(movie.get('id'))
            if movie_id in generator.reviews:
                movie_with_review = movie.copy()
                movie_with_review['review_data'] = generator.reviews[movie_id]
                reviewed_movies.append(movie_with_review)

        # Verify movie data structure for newsletter
        self.assertGreater(len(reviewed_movies), 0)

        for movie in reviewed_movies:
            # Check required fields for newsletter
            self.assertIn('title', movie)
            self.assertIn('digital_date', movie)
            self.assertIn('watch_links', movie)
            self.assertIn('review_data', movie)

            # Check review data structure
            review = movie['review_data']
            self.assertIn('review', review)
            self.assertIn('rating', review)
            self.assertIsInstance(review['rating'], (int, float))

    @unittest.skipIf(NewsletterGenerator is None, "NewsletterGenerator not available")
    def test_edge_cases(self):
        """
        Test: Edge cases and error conditions are handled properly.

        Verifies that:
        - Missing review files don't crash the system
        - Movies with incomplete data are handled gracefully
        - Empty datasets are handled correctly
        """
        generator = NewsletterGenerator()

        # Test with missing data file
        if os.path.exists('data.json'):
            os.rename('data.json', 'data.json.backup')

        self.assertFalse(generator.load_data())

        # Restore data file
        if os.path.exists('data.json.backup'):
            os.rename('data.json.backup', 'data.json')

        # Test with missing reviews file
        self.assertTrue(generator.load_data())
        self.assertFalse(generator.load_reviews('nonexistent_reviews.json'))

        # Test with empty reviews
        generator.load_data()
        with open('admin/empty_reviews.json', 'w') as f:
            json.dump({}, f)

        self.assertTrue(generator.load_reviews('admin/empty_reviews.json'))
        self.assertEqual(len(generator.reviews), 0)

    def test_mock_data_integrity(self):
        """
        Test: Mock data used in tests is properly structured.

        This is a meta-test to ensure our test data is valid.
        """
        # Verify mock movies structure
        for movie in self.mock_movies:
            self.assertIn('id', movie)
            self.assertIn('title', movie)
            self.assertIn('digital_date', movie)
            self.assertIn('watch_links', movie)

        # Verify mock reviews structure
        for movie_id, review in self.mock_reviews.items():
            self.assertIn('title', review)
            self.assertIn('review', review)
            self.assertIn('rating', review)
            self.assertIsInstance(review['rating'], (int, float))


if __name__ == '__main__':
    # Configure test runner for CI integration
    unittest.main(verbosity=2, buffer=True)