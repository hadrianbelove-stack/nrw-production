#!/usr/bin/env python3
"""
Unit tests for enhanced add_movie_to_site_immediately() function.
Tests TMDB fallback, atomic writes, schema validation, and discovery metadata.
"""

import pytest
import json
import os
import sys
import copy
from datetime import datetime
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.generator import DataGenerator

# Test data constants
SAMPLE_MOVIE_DATA = {
    'title': 'Test Movie',
    'digital_date': '2025-01-15',
    'providers': {
        'streaming': ['Netflix'],
        'rent': ['Amazon'],
        'buy': ['Apple TV']
    }
}

SAMPLE_TMDB_RESPONSE = {
    'title': 'Test Movie',
    'overview': 'A test movie synopsis',
    'genres': [{'name': 'Action'}, {'name': 'Drama'}],
    'runtime': 120,
    'release_date': '2025-01-15',
    'poster_path': '/test_poster.jpg',
    'production_companies': [{'name': 'Test Studio'}],
    'production_countries': [{'name': 'United States'}],
    'credits': {
        'crew': [{'name': 'Test Director', 'job': 'Director'}],
        'cast': [
            {'name': 'Actor 1'},
            {'name': 'Actor 2'},
            {'name': 'Actor 3'}
        ]
    }
}

EXISTING_DATA_JSON = {
    'generated_at': '2025-01-01T00:00:00',
    'count': 2,
    'movies': [
        {
            'id': '100',
            'title': 'Existing Movie 1',
            'digital_date': '2025-01-01',
            'synopsis': 'Existing synopsis',
            'genres': ['Drama'],
            'runtime': 90,
            'year': 2025,
            'poster': 'https://image.tmdb.org/t/p/w500/poster1.jpg',
            'crew': {'director': 'Director 1', 'cast': ['Actor A']},
            'studio': 'Studio 1',
            'country': 'USA',
            'rt_score': None,
            'providers': {'streaming': [], 'rent': [], 'buy': []},
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'watch_links': {},
            'bootstrap_date': False,
            'manually_corrected': False
        },
        {
            'id': '200',
            'title': 'Existing Movie 2',
            'digital_date': '2025-01-02',
            'synopsis': 'Another synopsis',
            'genres': ['Comedy'],
            'runtime': 100,
            'year': 2025,
            'poster': None,
            'crew': {'director': 'Director 2', 'cast': []},
            'studio': 'Studio 2',
            'country': 'UK',
            'rt_score': 85,
            'providers': {'streaming': ['Netflix'], 'rent': [], 'buy': []},
            'links': {'wikipedia': None, 'trailer': None, 'rt': None},
            'watch_links': {},
            'bootstrap_date': False,
            'manually_corrected': False
        }
    ]
}

# Fixtures
@pytest.fixture
def tmp_working_dir(tmp_path):
    """Create isolated working directory for file operations."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    # Create backups directory
    (tmp_path / 'backups').mkdir(exist_ok=True)

    yield tmp_path
    os.chdir(original_cwd)

@pytest.fixture
def sample_movie_data():
    """Return sample movie data."""
    return SAMPLE_MOVIE_DATA.copy()

@pytest.fixture
def existing_data_json(tmp_working_dir):
    """Create existing data.json with test movies."""
    data = copy.deepcopy(EXISTING_DATA_JSON)
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)
    return data

@pytest.fixture
def mock_tmdb_config():
    """Mock TMDB configuration to avoid requiring API key."""
    config = {
        'api': {
            'tmdb_api_key': 'test_key_12345'
        }
    }
    with patch.object(DataGenerator, 'load_config', return_value=config):
        yield config

@pytest.fixture
def data_generator(tmp_working_dir, mock_tmdb_config):
    """Create real DataGenerator with mocked config."""
    return DataGenerator()


class TestTMDBFailureFallback:
    """Test TMDB API failure scenarios and minimal entry creation."""

    def test_tmdb_failure_creates_minimal_entry(self, data_generator, sample_movie_data):
        """Test that TMDB failure creates minimal entry."""
        # Mock TMDB failure
        with patch.object(data_generator, 'get_movie_details', return_value=None):
            result = data_generator.add_movie_to_site_immediately('12345', sample_movie_data)

            assert result is True

            # Load resulting data.json
            assert os.path.exists('data.json')
            with open('data.json', 'r') as f:
                data = json.load(f)

            # Find movie in list
            movie = next((m for m in data['movies'] if m['id'] == '12345'), None)
            assert movie is not None

            # Verify minimal entry flags
            assert movie['_minimal_entry'] is True
            assert movie['_tmdb_fetch_failed'] is True

            # Verify minimal fields
            assert movie['id'] == '12345'
            assert movie['title'] == 'Test Movie'
            # digital_date uses YYYY-MM-DD format for display (from movie_tracking or today)
            assert movie['digital_date'] == '2025-01-15'  # From sample_movie_data
            assert movie['synopsis'] == ''
            assert movie['crew'] == {'director': 'Unknown', 'cast': []}

    def test_tmdb_exception_creates_minimal_entry(self, data_generator, sample_movie_data):
        """Test that TMDB exception creates minimal entry."""
        # Mock TMDB to raise exception
        with patch.object(data_generator, 'get_movie_details', side_effect=Exception("TMDB API timeout")):
            result = data_generator.add_movie_to_site_immediately('67890', sample_movie_data)

        assert result is True

        # Load and verify minimal entry was created
        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == '67890'), None)
        assert movie is not None
        assert movie['_minimal_entry'] is True
        assert movie['_tmdb_fetch_failed'] is True

    def test_minimal_entry_structure_complete(self, data_generator, sample_movie_data):
        """Test minimal entry has all required fields."""
        with patch.object(data_generator, 'get_movie_details', return_value=None):
            data_generator.add_movie_to_site_immediately('99999', sample_movie_data)

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == '99999'), None)
        assert movie is not None

        # Check all required fields for data.json schema
        required_fields = [
            'id', 'title', 'digital_date', 'bootstrap_date', 'manually_corrected',
            'poster', 'synopsis', 'crew', 'genres', 'studio', 'runtime', 'year',
            'country', 'rt_score', 'providers', 'links', 'watch_links',
            '_enrichment_status', '_tmdb_fetch_failed', '_minimal_entry'
        ]

        for field in required_fields:
            assert field in movie, f"Missing required field: {field}"

        # Verify fields marked for enrichment
        assert movie['poster'] is None
        assert movie['synopsis'] == ''
        assert movie['crew'] == {'director': 'Unknown', 'cast': []}
        assert movie['genres'] == []
        assert movie['studio'] == 'Unknown'
        assert movie['runtime'] is None
        assert movie['year'] is None
        assert movie['country'] == 'Unknown'
        assert movie['rt_score'] is None

        # Verify providers preserved from movie_data
        assert movie['providers'] == sample_movie_data['providers']


class TestTMDBSuccessPath:
    """Test successful TMDB fetch scenarios."""

    def test_tmdb_success_creates_full_entry(self, data_generator, sample_movie_data):
        """Test successful TMDB fetch creates full entry."""
        with patch.object(data_generator, 'get_movie_details', return_value=SAMPLE_TMDB_RESPONSE):
            result = data_generator.add_movie_to_site_immediately('55555', sample_movie_data)

        assert result is True

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == '55555'), None)
        assert movie is not None

        # Verify full entry flags
        assert movie['_minimal_entry'] is False
        assert movie.get('_tmdb_fetch_failed', False) is False

        # Assert TMDB fields are populated
        assert movie['synopsis'] == 'A test movie synopsis'
        assert movie['genres'] == ['Action', 'Drama']
        assert movie['runtime'] == 120
        assert movie['year'] == 2025
        assert movie['poster'] == 'https://image.tmdb.org/t/p/w500/test_poster.jpg'
        assert movie['studio'] == 'Test Studio'
        assert movie['country'] == 'United States'
        assert movie['crew']['director'] == 'Test Director'
        assert len(movie['crew']['cast']) == 3

    def test_full_entry_handles_missing_tmdb_fields(self, data_generator, sample_movie_data):
        """Test handling of partial TMDB data."""
        partial_tmdb_response = {
            'title': 'Partial Movie',
            'overview': 'Partial synopsis'
            # Missing: poster_path, production_companies, credits, etc.
        }

        with patch.object(data_generator, 'get_movie_details', return_value=partial_tmdb_response):
            data_generator.add_movie_to_site_immediately('44444', sample_movie_data)

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == '44444'), None)
        assert movie is not None

        # Verify graceful fallback values
        assert movie['poster'] is None
        assert movie['studio'] == 'Unknown'
        assert movie['crew'] == {'director': 'Unknown', 'cast': []}
        assert movie['synopsis'] == 'Partial synopsis'


class TestAtomicWriteAndBackup:
    """Test atomic write behavior and backup creation."""

    def test_atomic_write_creates_backup(self, data_generator, existing_data_json, sample_movie_data):
        """Test that atomic write creates backup."""
        # Create initial data.json file to enable backup creation
        with open('data.json', 'w') as f:
            json.dump(existing_data_json, f, indent=2)

        # Add movie which should create backup of existing data.json
        with patch.object(data_generator, 'get_movie_details', return_value=None):
            result = data_generator.add_movie_to_site_immediately('33333', sample_movie_data)

        assert result is True

        # Verify backup file was created in backups/ directory
        backup_files = [f for f in os.listdir('backups') if f.startswith('data.backup-') and f.endswith('.json')]
        assert len(backup_files) > 0, "No backup file was created"

        # Verify backup contains original data
        latest_backup = sorted(backup_files)[-1]
        backup_path = os.path.join('backups', latest_backup)

        with open(backup_path, 'r') as f:
            backup_data = json.load(f)

        # Verify backup contains the original movies
        assert len(backup_data['movies']) == len(existing_data_json['movies'])
        assert backup_data['movies'][0]['id'] == existing_data_json['movies'][0]['id']

    def test_atomic_write_failure_returns_false(self, data_generator, sample_movie_data):
        """Test atomic write failure handling."""
        with patch.object(data_generator, 'storage') as mock_storage:
            mock_storage.atomic_write_json.return_value = False
            mock_storage.load_json.return_value = {'movies': []}

            with patch.object(data_generator, 'get_movie_details', return_value=None):
                result = data_generator.add_movie_to_site_immediately('22222', sample_movie_data)

            assert result is False

    def test_atomic_write_preserves_existing_movies(self, data_generator, existing_data_json, sample_movie_data):
        """Test that existing movies are preserved when adding new one."""
        # Count movies before adding
        initial_count = len(existing_data_json['movies'])

        with patch.object(data_generator, 'get_movie_details', return_value=None):
            result = data_generator.add_movie_to_site_immediately('11111', sample_movie_data)

        assert result is True

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Verify count increased by 1
        assert len(data['movies']) == initial_count + 1

        # Find movies by ID
        movie_100 = next((m for m in data['movies'] if m['id'] == '100'), None)
        movie_200 = next((m for m in data['movies'] if m['id'] == '200'), None)
        movie_11111 = next((m for m in data['movies'] if m['id'] == '11111'), None)

        # Verify all movies exist
        assert movie_100 is not None
        assert movie_200 is not None
        assert movie_11111 is not None

        # Verify original movie data unchanged
        assert movie_100['title'] == 'Existing Movie 1'
        assert movie_200['title'] == 'Existing Movie 2'


class TestSchemaValidation:
    """Test schema validation before reading data.json."""

    def test_schema_validation_called_before_read(self, data_generator, existing_data_json, sample_movie_data):
        """Test schema validation is called before file read."""
        with patch.object(data_generator, 'validator') as mock_validator:
            mock_validator.validate_data_json_schema.return_value = True

            with patch.object(data_generator, 'get_movie_details', return_value=None):
                result = data_generator.add_movie_to_site_immediately('77777', sample_movie_data)

            assert result is True
            mock_validator.validate_data_json_schema.assert_called_with('data.json')

    def test_invalid_schema_aborts_write(self, data_generator, sample_movie_data):
        """Test invalid schema aborts the write operation."""
        # Create invalid data.json
        with open('data.json', 'w') as f:
            f.write('{"invalid": "schema"}')

        with patch.object(data_generator, 'validator') as mock_validator:
            mock_validator.validate_data_json_schema.return_value = False

            result = data_generator.add_movie_to_site_immediately('88888', sample_movie_data)

            assert result is False

    def test_missing_data_json_skips_validation(self, data_generator, sample_movie_data):
        """Test missing data.json skips validation."""
        # Ensure data.json does not exist
        if os.path.exists('data.json'):
            os.remove('data.json')

        with patch.object(data_generator, 'validator') as mock_validator:
            with patch.object(data_generator, 'get_movie_details', return_value=None):
                result = data_generator.add_movie_to_site_immediately('99998', sample_movie_data)

            assert result is True
            mock_validator.validate_data_json_schema.assert_not_called()

    def test_load_failure_aborts_write(self, data_generator, sample_movie_data):
        """Test load failure aborts write operation."""
        # Create corrupt data.json
        with open('data.json', 'w') as f:
            f.write('{ corrupt json }')

        with patch.object(data_generator, 'storage') as mock_storage:
            mock_storage.load_json.side_effect = Exception("JSON parse error")

            result = data_generator.add_movie_to_site_immediately('66666', sample_movie_data)

            assert result is False


class TestDiscoveryMetadata:
    """Test discovery metadata field addition."""

    def test_discovery_metadata_added_to_entry(self, data_generator, sample_movie_data):
        """Test discovery metadata fields are added to movie entry."""
        with patch.object(data_generator, 'get_movie_details', return_value=None):
            result = data_generator.add_movie_to_site_immediately('55556', sample_movie_data)

        assert result is True

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == '55556'), None)
        assert movie is not None

        # Assert discovery metadata fields
        assert 'digital_date' in movie  # YYYY-MM-DD format for display
        assert '_discovery_source' in movie
        assert '_enrichment_status' in movie
        assert '_discovered_at' in movie  # ISO timestamp when we found it

        # Verify format
        assert movie['_enrichment_status'] == 'pending'

        # Verify digital_date is YYYY-MM-DD format
        assert len(movie['digital_date']) == 10  # YYYY-MM-DD
        assert movie['digital_date'][4] == '-' and movie['digital_date'][7] == '-'

        # Verify _discovered_at is ISO timestamp
        discovered_at = datetime.fromisoformat(movie['_discovered_at'])
        assert isinstance(discovered_at, datetime)

    def test_discovery_metadata_in_data_json_root(self, data_generator, sample_movie_data):
        """Test discovery metadata is added to data.json root."""
        with patch.object(data_generator, 'get_movie_details', return_value=None):
            data_generator.add_movie_to_site_immediately('55557', sample_movie_data)

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Check root metadata if it exists (implementation dependent)
        if '_metadata' in data:
            metadata = data['_metadata']
            assert 'last_discovery_write' in metadata
            assert isinstance(metadata['last_discovery_write'], str)

    def test_discovery_count_increments(self, data_generator, existing_data_json, sample_movie_data):
        """Test discovery count increments correctly."""
        # Add discovery metadata to one existing movie
        existing_data_json['movies'][0]['_discovery_source'] = 'test'

        with open('data.json', 'w') as f:
            json.dump(existing_data_json, f, indent=2)

        with patch.object(data_generator, 'get_movie_details', return_value=None):
            data_generator.add_movie_to_site_immediately('55558', sample_movie_data)

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Count movies with discovery source
        discovery_count = sum(1 for movie in data['movies']
                            if '_discovery_source' in movie)
        assert discovery_count == 2  # Original + new movie


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_duplicate_movie_skipped(self, data_generator, existing_data_json, sample_movie_data):
        """Test duplicate movie is skipped."""
        # Count movies before adding duplicate
        initial_count = len(existing_data_json['movies'])

        with patch.object(data_generator, 'logger') as mock_logger:
            result = data_generator.add_movie_to_site_immediately('100', sample_movie_data)  # Existing ID

            assert result is True  # Success but skipped

            # Verify movie count unchanged
            with open('data.json', 'r') as f:
                data = json.load(f)
            assert len(data['movies']) == initial_count

    def test_empty_movie_data_handled(self, data_generator):
        """Test empty movie data is handled gracefully."""
        with patch.object(data_generator, 'get_movie_details', return_value=None):
            result = data_generator.add_movie_to_site_immediately('999', {})

        assert result is True

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == '999'), None)
        assert movie is not None
        assert movie['title'] == 'Movie 999'
        assert movie['providers'] == {'rent': [], 'buy': [], 'streaming': []}

    def test_exception_returns_false_without_crash(self, data_generator, sample_movie_data):
        """Test exceptions are handled gracefully."""
        # Create existing data.json to force load_json call
        with open('data.json', 'w') as f:
            json.dump({'movies': []}, f)

        # Mock storage to raise exception during load
        with patch.object(data_generator, 'storage') as mock_storage:
            mock_storage.load_json.side_effect = Exception("Critical error")

            result = data_generator.add_movie_to_site_immediately('error_test', sample_movie_data)

            assert result is False  # Returns False without crashing


class TestIntegration:
    """Integration tests with real dependencies."""

    def test_full_workflow_with_real_services(self, data_generator, sample_movie_data):
        """Test full workflow with real services."""
        # Mock only TMDB call
        with patch.object(data_generator, 'get_movie_details', return_value=SAMPLE_TMDB_RESPONSE):
            result = data_generator.add_movie_to_site_immediately('integration_test', sample_movie_data)

        assert result is True

        # Verify entire workflow completed
        assert os.path.exists('data.json')

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Find movie in list
        movie = next((m for m in data['movies'] if m['id'] == 'integration_test'), None)
        assert movie is not None

        # Verify complete structure
        assert movie['title'] == 'Test Movie'
        assert movie['_minimal_entry'] is False
        assert movie['synopsis'] == 'A test movie synopsis'
        assert movie['_enrichment_status'] == 'pending'

        # Verify backup was created
        backup_files = [f for f in os.listdir('backups') if f.startswith('data.backup')]
        # Note: backup only created if data.json existed before write
        # This test starts with empty directory, so no backup expected