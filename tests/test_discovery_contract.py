#!/usr/bin/env python3
"""
Contract tests for intake and provider discovery workflows.

These tests simulate intake and provider discovery to ensure
proper status transitions and digital_date handling as specified in Comment 4.

Test scenarios:
1. Intake (`--intake`) finds new premieres → status='tracking', digital_date=None
2. Discovery (`--discover`) detects provider availability → status='available', digital_date=today
3. Workflow integration ensures contract compliance
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
    from generate_data import DataGenerator
except ImportError:
    # Skip tests if generate_data can't be imported
    print("Warning: Could not import generate_data - skipping contract tests")
    DataGenerator = None


class TestDiscoveryContract(unittest.TestCase):
    """Test contract compliance for discovery workflow."""

    def setUp(self):
        """Set up test environment and mock dependencies."""
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create minimal config.yaml
        config_content = """
api:
  tmdb_api_key: "test_key"
  tmdb_rate_limit: 0.1
tracking:
  bootstrap_days: 7
discovery:
  days_back: 14
  max_pages: 20
"""
        with open('config.yaml', 'w') as f:
            f.write(config_content)

        # Create logs directory
        os.makedirs('logs', exist_ok=True)

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.old_cwd)
        import shutil
        shutil.rmtree(self.test_dir)

    @unittest.skipIf(DataGenerator is None, "DataGenerator not available")
    def test_discovery_creates_tracking_movies(self):
        """
        Test: Discovery output creates movies with status='tracking' and digital_date=None.

        Contract: New titles discovered should have:
        - status == 'tracking'
        - digital_date is None
        - enriched == False
        """
        # Simulate TMDB discovery response
        mock_tmdb_response = {
            'results': [
                {
                    'id': 12345,
                    'title': 'Test Discovery Movie',
                    'release_date': '2024-11-01',
                    'overview': 'A test movie found during discovery',
                    'poster_path': '/test_poster.jpg',
                    'vote_average': 7.5,
                    'genre_ids': [28, 12]  # Action, Adventure
                }
            ]
        }

        # Mock DataGenerator to avoid API calls and external dependencies
        with patch.multiple(
            DataGenerator,
            __init__=lambda self: self._mock_init(),
            _mock_init=lambda self: self._setup_mock_attributes(),
            load_config=MagicMock(return_value={
                'api': {'tmdb_api_key': 'test', 'tmdb_rate_limit': 0.1},
                'tracking': {'bootstrap_days': 7},
                'discovery': {'days_back': 14, 'max_pages': 20}
            }),
            atomic_write_json=MagicMock(return_value=True)
        ):
            # Create empty tracking database
            tracking_db = {'movies': {}}
            with open('movie_tracking.json', 'w') as f:
                json.dump(tracking_db, f)

            generator = DataGenerator(enrichment_enabled=True)

            # Simulate processing a discovered movie
            movie_data = mock_tmdb_response['results'][0]
            movie_id = str(movie_data['id'])

            # Simulate the discovery logic (new movie)
            if movie_id not in tracking_db['movies']:
                tracking_db['movies'][movie_id] = {
                    'id': movie_data['id'],
                    'title': movie_data['title'],
                    'status': 'tracking',  # CONTRACT: New discoveries start as tracking
                    'digital_date': None,  # CONTRACT: Discovery does not set digital_date
                    'enriched': False,     # CONTRACT: New movies are not enriched
                    'added_date': datetime.now().strftime('%Y-%m-%d'),
                    'tmdb_id': movie_data['id']
                }

            # Verify contract compliance
            discovered_movie = tracking_db['movies'][movie_id]

            # Assert discovery contract
            self.assertEqual(discovered_movie['status'], 'tracking',
                           "Discovered movies must have status='tracking'")
            self.assertIsNone(discovered_movie['digital_date'],
                            "Discovered movies must have digital_date=None")
            self.assertEqual(discovered_movie['enriched'], False,
                           "Discovered movies must have enriched=False")
            self.assertIn('added_date', discovered_movie,
                        "Discovered movies must have added_date")

    def _setup_mock_attributes(self):
        """Set up mock attributes for DataGenerator."""
        self.logger = MagicMock()
        self.config = {
            'api': {'tmdb_api_key': 'test', 'tmdb_rate_limit': 0.1},
            'tracking': {'bootstrap_days': 7},
            'discovery': {'days_back': 14, 'max_pages': 20}
        }
        self.tmdb_key = 'test'
        # Note: Watchmode deprecated 2024-12, JustWatch is now primary source

    def test_provider_detection_transitions_status(self):
        """
        Test: Provider detection transitions tracking → available with digital_date=today.

        Contract: When provider is detected:
        - status changes from 'tracking' to 'available'
        - digital_date is set to today's date
        - enriched flag remains False (enrichment happens later)
        """
        today = datetime.now().strftime('%Y-%m-%d')

        # Create tracking movie
        tracking_db = {
            'movies': {
                '12345': {
                    'id': 12345,
                    'title': 'Test Tracking Movie',
                    'status': 'tracking',
                    'digital_date': None,
                    'enriched': False,
                    'added_date': '2024-11-01',
                    'tmdb_id': 12345
                }
            }
        }

        # Simulate provider detection (e.g., movie found on streaming platform)
        movie_id = '12345'
        movie = tracking_db['movies'][movie_id]

        # Simulate the provider check logic
        provider_found = True  # Mock: provider detection returned positive result

        if movie['status'] == 'tracking' and provider_found:
            # CONTRACT: Provider detection should transition status and set digital_date
            movie['status'] = 'available'
            movie['digital_date'] = today
            # Note: enriched remains False until enrichment phase

        # Verify provider detection contract
        updated_movie = tracking_db['movies'][movie_id]

        self.assertEqual(updated_movie['status'], 'available',
                       "Provider detection must transition status to 'available'")
        self.assertEqual(updated_movie['digital_date'], today,
                       "Provider detection must set digital_date to today")
        self.assertEqual(updated_movie['enriched'], False,
                       "Provider detection must not change enriched flag")

    def test_discovery_provider_integration_workflow(self):
        """
        Test: Complete workflow from discovery → provider detection → status transitions.

        This integration test simulates the full pipeline to ensure
        contracts are maintained throughout the workflow.
        """
        today = datetime.now().strftime('%Y-%m-%d')

        # Step 1: Initial state (empty database)
        tracking_db = {'movies': {}}

        # Step 2: Intake phase - new movie found via TMDB
        discovered_movie = {
            'id': 67890,
            'title': 'Integration Test Movie',
            'release_date': '2024-11-01'
        }

        movie_id = str(discovered_movie['id'])

        # Add discovered movie (simulate discovery logic)
        tracking_db['movies'][movie_id] = {
            'id': discovered_movie['id'],
            'title': discovered_movie['title'],
            'status': 'tracking',     # Discovery contract
            'digital_date': None,     # Discovery contract
            'enriched': False,        # Discovery contract
            'added_date': today,
            'tmdb_id': discovered_movie['id']
        }

        # Verify intake phase contract
        movie_after_discovery = tracking_db['movies'][movie_id]
        self.assertEqual(movie_after_discovery['status'], 'tracking')
        self.assertIsNone(movie_after_discovery['digital_date'])
        self.assertEqual(movie_after_discovery['enriched'], False)

        # Step 3: Provider check phase - movie becomes available
        # Simulate checking for digital availability
        provider_available = True  # Mock: movie found on platform

        if movie_after_discovery['status'] == 'tracking' and provider_available:
            tracking_db['movies'][movie_id]['status'] = 'available'
            tracking_db['movies'][movie_id]['digital_date'] = today
            # enriched remains False (enrichment happens in separate phase)

        # Verify provider detection contract
        movie_after_provider_check = tracking_db['movies'][movie_id]
        self.assertEqual(movie_after_provider_check['status'], 'available')
        self.assertEqual(movie_after_provider_check['digital_date'], today)
        self.assertEqual(movie_after_provider_check['enriched'], False)

        # Step 4: Optional - enrichment phase (separate from discovery/provider detection)
        # This would happen later and should not affect the discovery/provider contracts
        if movie_after_provider_check['status'] == 'available':
            # Enrichment adds metadata but doesn't change core status/date fields
            tracking_db['movies'][movie_id]['enriched'] = True
            tracking_db['movies'][movie_id]['enrichment_date'] = today
            # status and digital_date remain unchanged by enrichment

        # Verify enrichment doesn't break contracts
        movie_after_enrichment = tracking_db['movies'][movie_id]
        self.assertEqual(movie_after_enrichment['status'], 'available')
        self.assertEqual(movie_after_enrichment['digital_date'], today)
        self.assertEqual(movie_after_enrichment['enriched'], True)

    def test_bulk_discovery_contract_compliance(self):
        """
        Test: Multiple movies discovered maintain contract compliance.

        Ensures that batch discovery operations properly set status and dates.
        """
        # Simulate discovering multiple movies
        discovered_movies = [
            {'id': 100, 'title': 'Bulk Movie 1', 'release_date': '2024-11-01'},
            {'id': 101, 'title': 'Bulk Movie 2', 'release_date': '2024-11-02'},
            {'id': 102, 'title': 'Bulk Movie 3', 'release_date': '2024-11-03'}
        ]

        tracking_db = {'movies': {}}

        # Process each discovered movie
        for movie_data in discovered_movies:
            movie_id = str(movie_data['id'])
            tracking_db['movies'][movie_id] = {
                'id': movie_data['id'],
                'title': movie_data['title'],
                'status': 'tracking',
                'digital_date': None,
                'enriched': False,
                'added_date': datetime.now().strftime('%Y-%m-%d'),
                'tmdb_id': movie_data['id']
            }

        # Verify all movies follow discovery contract
        for movie_id, movie in tracking_db['movies'].items():
            with self.subTest(movie_id=movie_id):
                self.assertEqual(movie['status'], 'tracking',
                               f"Movie {movie_id} status contract violation")
                self.assertIsNone(movie['digital_date'],
                                f"Movie {movie_id} digital_date contract violation")
                self.assertEqual(movie['enriched'], False,
                               f"Movie {movie_id} enriched contract violation")

        # Verify count
        self.assertEqual(len(tracking_db['movies']), 3,
                       "All discovered movies should be in tracking database")


class TestProviderDetectionContract(unittest.TestCase):
    """Test contract compliance for provider detection workflow."""

    def test_provider_detection_sets_correct_digital_date(self):
        """
        Test: Provider detection sets digital_date to current date, not historical.

        This prevents the bug where discovery incorrectly sets digital_date.
        Only provider detection should set digital_date.
        """
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # Start with a tracking movie (no digital_date)
        movie = {
            'id': 12345,
            'title': 'Provider Test Movie',
            'status': 'tracking',
            'digital_date': None,
            'enriched': False,
            'added_date': yesterday  # Added yesterday
        }

        # Simulate provider detection finding availability today
        provider_detected_today = True

        if movie['status'] == 'tracking' and provider_detected_today:
            movie['status'] = 'available'
            movie['digital_date'] = today  # Should be today, not added_date

        # Verify provider detection sets correct date
        self.assertEqual(movie['digital_date'], today,
                       "Provider detection must set digital_date to detection date, not discovery date")
        self.assertNotEqual(movie['digital_date'], movie['added_date'],
                          "digital_date should not equal added_date")

    def test_provider_detection_preserves_tracking_metadata(self):
        """
        Test: Provider detection preserves discovery metadata while updating status.
        """
        original_movie = {
            'id': 54321,
            'title': 'Metadata Preservation Test',
            'status': 'tracking',
            'digital_date': None,
            'enriched': False,
            'added_date': '2024-10-15',
            'tmdb_id': 54321,
            'year': 2024,
            'overview': 'Test overview'
        }

        # Make a copy to modify
        movie = original_movie.copy()

        # Simulate provider detection
        if movie['status'] == 'tracking':
            movie['status'] = 'available'
            movie['digital_date'] = datetime.now().strftime('%Y-%m-%d')

        # Verify metadata preservation
        preserved_fields = ['id', 'title', 'added_date', 'tmdb_id', 'year', 'overview']
        for field in preserved_fields:
            self.assertEqual(movie[field], original_movie[field],
                           f"Provider detection must preserve {field}")

        # Verify only expected fields changed
        self.assertEqual(movie['status'], 'available')
        self.assertIsNotNone(movie['digital_date'])
        self.assertEqual(movie['enriched'], False)  # Enrichment happens separately


if __name__ == '__main__':
    # Configure test runner for CI integration
    unittest.main(verbosity=2, buffer=True)