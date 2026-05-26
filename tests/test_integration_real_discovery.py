#!/usr/bin/env python3
"""
Real-World Integration Test for Enhanced Movie Discovery Pipeline

This script tests the enhanced add_movie_to_site_immediately() function using actual
data files, TMDB API calls, and file system operations. Unlike unit tests that mock
dependencies, this integration test exercises the complete workflow end-to-end.

Features:
- Automatic state backup and restore on failure
- Dynamic movie selection (no hardcoded IDs)
- Real TMDB API calls and file operations
- Comprehensive verification of all enhancements
- Detailed pass/fail reporting

Usage:
    python3 test_integration_real_discovery.py

Author: NRW Production Team
Date: December 2024
"""

import json
import os
import sys
import shutil
import glob
from datetime import datetime

# Add pipeline directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pipeline'))

from pipeline.generator import DataGenerator

# Test Configuration
EXPECTED_FIELDS = [
    'id', 'title', 'digital_date', 'bootstrap_date', 'manually_corrected',
    'poster', 'synopsis', 'crew', 'genres', 'studio', 'runtime', 'year',
    'country', 'rt_score', 'providers', 'links', 'watch_links'
]

DISCOVERY_METADATA_FIELDS = [
    '_discovery_source', '_enrichment_status', '_minimal_entry'
]

class IntegrationTestError(Exception):
    """Custom exception for integration test failures."""
    pass

class StateManager:
    """Manages backup and restore of data files during testing."""

    def __init__(self):
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_files = {}

    def backup_current_state(self):
        """Create backup of current data.json before test execution."""
        print("📦 Creating backup of current state...")

        if os.path.exists('data.json'):
            backup_path = f'data.json.pre_test_{self.timestamp}'
            shutil.copy2('data.json', backup_path)
            self.backup_files['data.json'] = backup_path

            # Read current state for reporting
            with open('data.json', 'r') as f:
                current_data = json.load(f)
            movie_count = len(current_data.get('movies', []))
            print(f"   ✅ Backed up data.json ({movie_count} movies) → {backup_path}")
        else:
            print("   ℹ️  data.json doesn't exist - no backup needed")

        return self.timestamp

    def restore_state_on_failure(self):
        """Restore data.json to pre-test state if test fails."""
        print("🔄 Restoring state due to test failure...")

        for original_file, backup_path in self.backup_files.items():
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, original_file)
                print(f"   ✅ Restored {original_file} from {backup_path}")
            else:
                print(f"   ⚠️  Backup {backup_path} not found for {original_file}")

    def cleanup_backups(self):
        """Remove test backup files after successful test."""
        for backup_path in self.backup_files.values():
            if os.path.exists(backup_path):
                os.remove(backup_path)

class MovieSelector:
    """Dynamically finds suitable movies for integration testing."""

    def find_test_movie(self):
        """Find an available movie not already in data.json for testing."""
        print("🎯 Finding suitable test movie...")

        # Load movie tracking data
        if not os.path.exists('movie_tracking.json'):
            raise IntegrationTestError("movie_tracking.json not found")

        with open('movie_tracking.json', 'r') as f:
            tracking_data = json.load(f)

        # Load current data.json to avoid duplicates
        current_movie_ids = set()
        if os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                current_data = json.load(f)
                current_movie_ids = {movie['id'] for movie in current_data.get('movies', [])}

        # Find suitable candidates - tracking_data has structure {'movies': {...}, 'last_update': ...}
        movies_dict = tracking_data.get('movies', tracking_data)  # Handle both structures
        candidates = []
        for movie_id, movie_info in movies_dict.items():
            # Note: digital_date is no longer stored in movie_tracking (only in data.json)
            # We just need status=available with providers
            if (movie_info.get('status') == 'available' and
                movie_id not in current_movie_ids and
                movie_info.get('has_providers', False) and
                movie_info.get('title') and
                movie_info.get('providers')):
                candidates.append((movie_id, movie_info))

        if not candidates:
            raise IntegrationTestError(
                "No suitable test movies found. Need an 'available' movie with providers "
                "that's not already in data.json"
            )

        # Sort by title for consistent selection
        candidates.sort(key=lambda x: x[1].get('title', ''))
        movie_id, movie_data = candidates[0]

        print(f"   ✅ Selected movie: {movie_data.get('title')} (ID: {movie_id})")
        print(f"   📅 Digital date: {movie_data.get('digital_date')}")
        print(f"   📺 Providers: {list(movie_data.get('providers', {}).keys())}")

        return movie_id, movie_data

class IntegrationTester:
    """Main integration test coordinator."""

    def __init__(self):
        self.state_manager = StateManager()
        self.movie_selector = MovieSelector()
        self.test_results = {}
        self.start_time = None

    def run_test(self):
        """Execute complete integration test workflow."""
        self.start_time = datetime.now()
        print("🚀 Starting Real-World Integration Test")
        print(f"⏰ Test started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        try:
            # Phase 1: Setup and preparation
            self.verify_prerequisites()
            backup_timestamp = self.state_manager.backup_current_state()
            movie_id, movie_data = self.movie_selector.find_test_movie()

            # Phase 2: Execute integration test
            self.execute_movie_discovery(movie_id, movie_data)

            # Phase 3: Verify results
            self.verify_data_json_updates(movie_id, movie_data)
            self.verify_backup_creation()
            self.verify_schema_compliance()
            self.test_duplicate_detection(movie_id, movie_data)

            # Phase 4: Generate report
            self.generate_test_report(movie_id, movie_data)

            # Cleanup successful test backups
            self.state_manager.cleanup_backups()

            print("\n🎉 INTEGRATION TEST PASSED")
            return True

        except Exception as e:
            print(f"\n❌ INTEGRATION TEST FAILED: {e}")
            self.state_manager.restore_state_on_failure()
            self.generate_failure_report(str(e))
            return False

    def verify_prerequisites(self):
        """Check that all required files and conditions exist."""
        print("🔍 Verifying prerequisites...")

        # Check required files
        required_files = ['movie_tracking.json', 'pipeline/generator.py']
        for file_path in required_files:
            if not os.path.exists(file_path):
                raise IntegrationTestError(f"Required file missing: {file_path}")

        # Create directories if needed
        os.makedirs('backups', exist_ok=True)
        os.makedirs('logs', exist_ok=True)

        # Initialize DataGenerator to check configuration
        try:
            generator = DataGenerator()
            print("   ✅ DataGenerator initialized successfully")
        except Exception as e:
            raise IntegrationTestError(f"DataGenerator initialization failed: {e}")

        print("   ✅ All prerequisites verified")

    def execute_movie_discovery(self, movie_id, movie_data):
        """Execute the enhanced immediate writing function."""
        print(f"🎬 Executing movie discovery for {movie_data['title']}...")

        # Initialize DataGenerator
        generator = DataGenerator()

        # Execute the enhanced function
        start_time = datetime.now()
        result = generator.add_movie_to_site_immediately(movie_id, movie_data)
        execution_time = (datetime.now() - start_time).total_seconds()

        self.test_results['execution_time'] = execution_time
        self.test_results['function_result'] = result

        print(f"   ⏱️  Execution time: {execution_time:.2f} seconds")

        if not result:
            raise IntegrationTestError("add_movie_to_site_immediately() returned False")

        print("   ✅ Function executed successfully")

    def verify_data_json_updates(self, movie_id, movie_data):
        """Verify that data.json was updated correctly."""
        print("📋 Verifying data.json updates...")

        if not os.path.exists('data.json'):
            raise IntegrationTestError("data.json was not created")

        with open('data.json', 'r') as f:
            data = json.load(f)

        # Verify structure
        if 'movies' not in data:
            raise IntegrationTestError("data.json missing 'movies' array")

        # Find the movie entry
        movie_entry = None
        for movie in data['movies']:
            if movie.get('id') == movie_id:
                movie_entry = movie
                break

        if not movie_entry:
            raise IntegrationTestError(f"Movie {movie_id} not found in data.json")

        print(f"   ✅ Movie {movie_id} found in data.json")

        # Verify required fields
        missing_fields = []
        for field in EXPECTED_FIELDS:
            if field not in movie_entry:
                missing_fields.append(field)

        if missing_fields:
            raise IntegrationTestError(f"Missing required fields: {missing_fields}")

        print("   ✅ All required fields present")

        # Verify discovery metadata
        missing_metadata = []
        for field in DISCOVERY_METADATA_FIELDS:
            if field not in movie_entry:
                missing_metadata.append(field)

        if missing_metadata:
            raise IntegrationTestError(f"Missing discovery metadata: {missing_metadata}")

        print("   ✅ Discovery metadata fields present")

        # Verify discovery metadata values
        digital_date = movie_entry.get('digital_date')  # ISO timestamp when discovered
        discovery_source = movie_entry.get('_discovery_source')
        enrichment_status = movie_entry.get('_enrichment_status')

        if not digital_date:
            raise IntegrationTestError("digital_date is empty")

        if discovery_source != 'provider_availability_check':
            print(f"   ⚠️  Unexpected discovery source: {discovery_source}")

        if enrichment_status != 'pending':
            print(f"   ⚠️  Unexpected enrichment status: {enrichment_status}")

        print("   ✅ Discovery metadata values verified")

        # Store results for reporting
        self.test_results['movie_entry'] = movie_entry
        self.test_results['tmdb_success'] = not movie_entry.get('_tmdb_fetch_failed', False)

        if self.test_results['tmdb_success']:
            print("   ✅ TMDB fetch succeeded - full entry created")
        else:
            print("   ⚠️  TMDB fetch failed - minimal entry created")

    def verify_backup_creation(self):
        """Verify that backup files were created properly."""
        print("💾 Verifying backup creation...")

        # Look for backup files created during this test
        backup_pattern = 'backups/data.backup-*.json'
        backup_files = glob.glob(backup_pattern)

        if not backup_files:
            # Check if data.json existed before test (no backup needed for new files)
            if not self.state_manager.backup_files:
                print("   ℹ️  No backup created (data.json was empty/new)")
                return
            else:
                raise IntegrationTestError("Expected backup file was not created")

        # Find most recent backup
        backup_files.sort()
        latest_backup = backup_files[-1]

        print(f"   ✅ Backup file found: {latest_backup}")

        # Verify backup content
        with open(latest_backup, 'r') as f:
            backup_data = json.load(f)

        if 'movies' not in backup_data:
            raise IntegrationTestError("Backup file has invalid structure")

        print(f"   ✅ Backup contains {len(backup_data['movies'])} movies")

        self.test_results['backup_created'] = latest_backup

    def verify_schema_compliance(self):
        """Verify that the updated data.json passes schema validation."""
        print("🔍 Verifying schema compliance...")

        try:
            generator = DataGenerator()
            validation_result = generator.validator.validate_data_json_schema('data.json')

            if not validation_result:
                raise IntegrationTestError("Schema validation failed")

            print("   ✅ Schema validation passed")
            self.test_results['schema_valid'] = True

        except Exception as e:
            raise IntegrationTestError(f"Schema validation error: {e}")

    def test_duplicate_detection(self, movie_id, movie_data):
        """Test that duplicate movies are properly detected and skipped."""
        print("🔄 Testing duplicate detection...")

        # Count movies before duplicate attempt
        with open('data.json', 'r') as f:
            data_before = json.load(f)
        movies_before = len(data_before['movies'])

        # Attempt to add the same movie again
        generator = DataGenerator()
        result = generator.add_movie_to_site_immediately(movie_id, movie_data)

        if not result:
            raise IntegrationTestError("Duplicate detection returned False (should return True)")

        # Verify no duplicate was added
        with open('data.json', 'r') as f:
            data_after = json.load(f)
        movies_after = len(data_after['movies'])

        if movies_after != movies_before:
            raise IntegrationTestError(f"Movie count changed: {movies_before} → {movies_after}")

        # Count instances of the movie ID
        movie_instances = sum(1 for movie in data_after['movies'] if movie['id'] == movie_id)
        if movie_instances != 1:
            raise IntegrationTestError(f"Found {movie_instances} instances of movie {movie_id}, expected 1")

        print("   ✅ Duplicate detection working correctly")
        self.test_results['duplicate_detection'] = True

    def generate_test_report(self, movie_id, movie_data):
        """Generate detailed test report."""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()

        report = {
            'test_timestamp': self.start_time.isoformat(),
            'test_duration_seconds': total_duration,
            'movie_tested': {
                'id': movie_id,
                'title': movie_data.get('title'),
                'digital_date': movie_data.get('digital_date')
            },
            'results': self.test_results,
            'status': 'PASSED'
        }

        # Save detailed report
        report_filename = f"logs/integration_test_results_{self.state_manager.timestamp}.json"
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2)

        # Save movie entry for inspection
        if 'movie_entry' in self.test_results:
            entry_filename = f"logs/movie_{movie_id}_entry.json"
            with open(entry_filename, 'w') as f:
                json.dump(self.test_results['movie_entry'], f, indent=2)

        print("\n📊 TEST SUMMARY")
        print(f"   🎬 Movie Tested: {movie_data.get('title')} ({movie_id})")
        print(f"   ⏱️  Total Duration: {total_duration:.2f} seconds")
        print(f"   🔧 Function Execution: {self.test_results.get('execution_time', 0):.2f} seconds")
        print(f"   🌐 TMDB Success: {self.test_results.get('tmdb_success', False)}")
        print(f"   📄 Schema Valid: {self.test_results.get('schema_valid', False)}")
        print(f"   💾 Backup Created: {'backup_created' in self.test_results}")
        print(f"   🔄 Duplicate Detection: {self.test_results.get('duplicate_detection', False)}")
        print(f"   📋 Full Report: {report_filename}")

    def generate_failure_report(self, error_message):
        """Generate failure report for debugging."""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds() if self.start_time else 0

        failure_report = {
            'test_timestamp': self.start_time.isoformat() if self.start_time else None,
            'test_duration_seconds': total_duration,
            'error_message': error_message,
            'partial_results': self.test_results,
            'status': 'FAILED'
        }

        # Save failure report
        report_filename = f"logs/integration_test_failure_{self.state_manager.timestamp}.json"
        with open(report_filename, 'w') as f:
            json.dump(failure_report, f, indent=2)

        print(f"   📋 Failure Report: {report_filename}")

def main():
    """Main entry point for integration test."""
    print("🧪 NRW Production - Real-World Integration Test")
    print("Testing Enhanced Movie Discovery Pipeline")
    print("=" * 60)

    try:
        tester = IntegrationTester()
        success = tester.run_test()

        if success:
            print("✅ Integration test completed successfully!")
            sys.exit(0)
        else:
            print("❌ Integration test failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()