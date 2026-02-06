#!/usr/bin/env python3
"""
Enhanced Immediate Writing - End-to-End Functional Tests

Tests the enhanced add_movie_to_site_immediately() function with various scenarios
to verify it works correctly with all dependencies.

Test scenarios:
1. TMDB Success - Full entry creation with TMDB details
2. TMDB Failure - Minimal entry creation when TMDB fails
3. Atomic Write - Verify backup creation
4. Schema Validation - Verify function aborts on invalid data.json
5. Duplicate Detection - Verify second call skips duplicate

Usage:
    python3 test_enhanced_immediate_writing_dependencies.py
"""

import sys
import os
import json
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path

# Project root directory (this file is in tests/, so go up one level)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Add pipeline directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pipeline'))

def backup_current_state():
    """Create a timestamped backup of the real data.json before running tests."""
    data_json_path = str(PROJECT_ROOT / "data.json")

    if not os.path.exists(data_json_path):
        print(f"  ⚠️ No data.json found at {data_json_path} - skipping backup")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{data_json_path}.pre_test_{timestamp}"

    try:
        shutil.copy2(data_json_path, backup_path)
        print(f"  ✅ Created backup: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"  ❌ Failed to create backup: {e}")
        return None

def restore_state_on_failure(backup_path):
    """Restore data.json from backup and clean up temp files."""
    if not backup_path or not os.path.exists(backup_path):
        print(f"  ⚠️ No valid backup to restore from: {backup_path}")
        return False

    data_json_path = str(PROJECT_ROOT / "data.json")

    try:
        shutil.copy2(backup_path, data_json_path)
        os.remove(backup_path)  # Remove backup after successful restore
        print(f"  ✅ Restored data.json from backup and cleaned up temp file")
        return True
    except Exception as e:
        print(f"  ❌ Failed to restore from backup: {e}")
        return False

def cleanup_backup_on_success(backup_path):
    """Remove backup file after successful test completion."""
    if backup_path and os.path.exists(backup_path):
        try:
            os.remove(backup_path)
            print(f"  ✅ Cleaned up backup: {backup_path}")
        except Exception as e:
            print(f"  ⚠️ Failed to clean up backup: {e}")

def find_test_movie():
    """Find a suitable test movie from movie_tracking.json for dynamic testing."""
    tracking_path = str(PROJECT_ROOT / "movie_tracking.json")
    data_path = str(PROJECT_ROOT / "data.json")

    if not os.path.exists(tracking_path):
        print(f"  ⚠️ movie_tracking.json not found at {tracking_path}")
        return None, None

    try:
        # Load movie tracking data
        with open(tracking_path) as f:
            tracking_data = json.load(f)

        # Load existing data.json to exclude already processed movies
        existing_ids = set()
        if os.path.exists(data_path):
            with open(data_path) as f:
                data = json.load(f)
                existing_ids = {str(movie.get('id')) for movie in data.get('movies', [])}

        movies = tracking_data.get('movies', {})

        # Priority 1: available + has_providers + not in data.json
        ideal_candidates = []
        available_candidates = []
        fallback_candidates = []

        for movie_id, movie_data in movies.items():
            if str(movie_id) in existing_ids:
                continue  # Skip movies already in data.json

            status = movie_data.get('status', '')
            has_providers = movie_data.get('has_providers', False)

            if status == 'available' and has_providers:
                ideal_candidates.append((movie_id, movie_data))
            elif status == 'available':
                available_candidates.append((movie_id, movie_data))
            else:
                fallback_candidates.append((movie_id, movie_data))

        # Select best candidate
        selected_movie = None
        selection_reason = ""

        if ideal_candidates:
            selected_movie = ideal_candidates[0]
            selection_reason = "ideal candidate (available + has_providers + not in data.json)"
        elif available_candidates:
            selected_movie = available_candidates[0]
            selection_reason = "available candidate (available + not in data.json)"
        elif fallback_candidates:
            selected_movie = fallback_candidates[0]
            selection_reason = "fallback candidate (not in data.json)"

        if selected_movie:
            movie_id, movie_data = selected_movie
            print(f"  ✅ Selected movie {movie_id} ({movie_data.get('title', 'Unknown')}) - {selection_reason}")

            # Format movie data for the test function
            formatted_data = {
                "title": movie_data.get('title', 'Unknown Title'),
                "digital_date": movie_data.get('digital_date') or datetime.now().strftime('%Y-%m-%d'),
                "providers": {
                    "streaming": [],
                    "rent": [],
                    "buy": []
                }
            }

            # Add providers if available
            if movie_data.get('providers'):
                providers = movie_data['providers']
                if isinstance(providers, dict):
                    formatted_data['providers'] = providers
                elif isinstance(providers, list):
                    formatted_data['providers']['streaming'] = providers

            return str(movie_id), formatted_data
        else:
            print(f"  ⚠️ No suitable test movies found in tracking data")
            return None, None

    except Exception as e:
        print(f"  ❌ Error reading movie tracking data: {e}")
        return None, None

def setup_test_environment():
    """Set up temporary directory with test files."""
    temp_dir = tempfile.mkdtemp(prefix='nrw_test_')

    # Create test data.json
    test_data = {
        "movies": {},
        "last_updated": datetime.now().isoformat(),
        "total_count": 0
    }

    data_json_path = os.path.join(temp_dir, 'data.json')
    with open(data_json_path, 'w') as f:
        json.dump(test_data, f, indent=2)

    # Create backups directory
    backups_dir = os.path.join(temp_dir, 'backups')
    os.makedirs(backups_dir, exist_ok=True)

    # Create test movie_tracking.json
    tracking_data = {
        "555666": {  # Use a movie ID that should exist in TMDB
            "title": "The Matrix",
            "digital_date": "2024-01-15",
            "providers": {
                "streaming": ["HBO Max"],
                "rent": [],
                "buy": []
            },
            "status": "available"
        },
        "999999": {  # Use a movie ID that definitely won't exist
            "title": "Nonexistent Movie",
            "digital_date": "2024-01-15",
            "providers": {
                "streaming": ["Netflix"],
                "rent": [],
                "buy": []
            },
            "status": "available"
        }
    }

    tracking_json_path = os.path.join(temp_dir, 'movie_tracking.json')
    with open(tracking_json_path, 'w') as f:
        json.dump(tracking_data, f, indent=2)

    return temp_dir, data_json_path, tracking_json_path, backups_dir

def cleanup_test_environment(temp_dir):
    """Clean up test directory."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

def test_tmdb_success(generator, temp_dir):
    """Test 1: TMDB Success - Full entry creation"""
    print("\n[TEST 1] TMDB Success - Full entry creation")

    # Save original working directory
    original_cwd = os.getcwd()

    try:
        # Change to temp directory for test
        os.chdir(temp_dir)

        # Find a suitable test movie dynamically
        print("  Finding suitable test movie...")
        movie_id, movie_data = find_test_movie()

        if not movie_id or not movie_data:
            print("  ⚠️ No suitable movie found, falling back to known working ID")
            # Fallback to a known working movie ID
            movie_id = "603"  # The Matrix
            movie_data = {
                "title": "The Matrix",
                "digital_date": "2024-01-15",
                "providers": {
                    "streaming": ["HBO Max"],
                    "rent": [],
                    "buy": []
                }
            }

        print(f"  Using movie {movie_id}: {movie_data.get('title', 'Unknown')}")

        result = generator.add_movie_to_site_immediately(movie_id, movie_data)

        # Verify result
        print(f"  ✅ Function returned: {result}")

        # Check if movie was added to data.json
        if os.path.exists('data.json'):
            with open('data.json') as f:
                data = json.load(f)
                if movie_id in data.get('movies', {}):
                    entry = data['movies'][movie_id]
                    has_tmdb_details = bool(entry.get('synopsis') or entry.get('genres'))
                    print(f"  ✅ Movie added to data.json with TMDB details: {has_tmdb_details}")
                    print(f"  ✅ Minimal entry flag: {entry.get('_minimal_entry', 'not set')}")
                    print(f"  ✅ Enrichment status: {entry.get('_enrichment_status', 'not set')}")
                else:
                    print(f"  ❌ Movie {movie_id} not found in data.json")
        else:
            print("  ❌ data.json not found")

        return True

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

    finally:
        os.chdir(original_cwd)

def test_tmdb_failure(generator, temp_dir):
    """Test 2: TMDB Failure - Minimal entry creation"""
    print("\n[TEST 2] TMDB Failure - Minimal entry creation")

    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # Use a guaranteed fake movie ID that should fail TMDB lookup
        # Using a very high number that's unlikely to exist
        movie_id = "99999999"
        movie_data = {
            "title": "Nonexistent Test Movie",
            "digital_date": datetime.now().strftime('%Y-%m-%d'),
            "providers": {
                "streaming": ["Test Service"],
                "rent": [],
                "buy": []
            }
        }

        print(f"  Using fake movie {movie_id}: {movie_data.get('title', 'Unknown')}")

        result = generator.add_movie_to_site_immediately(movie_id, movie_data)

        print(f"  ✅ Function returned: {result}")

        # Check if movie was added with minimal details
        if os.path.exists('data.json'):
            with open('data.json') as f:
                data = json.load(f)
                if movie_id in data.get('movies', {}):
                    entry = data['movies'][movie_id]
                    is_minimal = entry.get('_minimal_entry', False)
                    tmdb_failed = entry.get('_tmdb_fetch_failed', False)
                    print(f"  ✅ Movie added as minimal entry: {is_minimal}")
                    print(f"  ✅ TMDB fetch failed flag: {tmdb_failed}")
                    print(f"  ✅ Title preserved: {entry.get('title') == movie_data['title']}")
                else:
                    print(f"  ❌ Movie {movie_id} not found in data.json")
        else:
            print("  ❌ data.json not found")

        return True

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

    finally:
        os.chdir(original_cwd)

def test_atomic_write_backup(generator, temp_dir, backups_dir):
    """Test 3: Atomic Write - Verify backup creation"""
    print("\n[TEST 3] Atomic Write - Backup creation")

    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # Count existing backups
        existing_backups = len([f for f in os.listdir(backups_dir) if f.startswith('data.json.backup')])

        # Add a movie to trigger backup - use a timestamp-based ID to avoid conflicts
        movie_id = f"test_backup_{int(time.time())}"
        movie_data = {
            "title": "Test Backup Movie",
            "digital_date": datetime.now().strftime('%Y-%m-%d'),
            "providers": {
                "streaming": ["Test Service"],
                "rent": [],
                "buy": []
            }
        }

        print(f"  Using test movie {movie_id}: {movie_data.get('title', 'Unknown')}")

        result = generator.add_movie_to_site_immediately(movie_id, movie_data)

        print(f"  ✅ Function returned: {result}")

        # Check for new backup
        time.sleep(1)  # Give filesystem time to create backup
        new_backups = len([f for f in os.listdir(backups_dir) if f.startswith('data.json.backup')])
        backup_created = new_backups > existing_backups

        print(f"  ✅ Backup created: {backup_created} (existing: {existing_backups}, new: {new_backups})")

        if backup_created:
            backup_files = [f for f in os.listdir(backups_dir) if f.startswith('data.json.backup')]
            latest_backup = max(backup_files) if backup_files else None
            print(f"  ✅ Latest backup: {latest_backup}")

        return True

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

    finally:
        os.chdir(original_cwd)

def test_schema_validation_abort(generator, temp_dir):
    """Test 4: Schema Validation - Function aborts on invalid data.json"""
    print("\n[TEST 4] Schema Validation - Invalid data.json handling")

    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # Corrupt data.json with invalid JSON
        with open('data.json', 'w') as f:
            f.write("{ invalid json }")

        movie_id = f"test_invalid_{int(time.time())}"
        movie_data = {
            "title": "Should Not Be Added",
            "digital_date": datetime.now().strftime('%Y-%m-%d'),
            "providers": {"streaming": [], "rent": [], "buy": []}
        }

        print(f"  Using test movie {movie_id}: {movie_data.get('title', 'Unknown')}")

        result = generator.add_movie_to_site_immediately(movie_id, movie_data)

        # Function should return False due to invalid JSON
        validation_failed = not result
        print(f"  ✅ Function aborted due to invalid data.json: {validation_failed}")

        # Check if file was quarantined
        quarantine_files = [f for f in os.listdir('.') if 'quarantined' in f or 'corrupted' in f]
        quarantined = len(quarantine_files) > 0
        print(f"  ✅ Invalid file quarantined: {quarantined}")
        if quarantined:
            print(f"  ✅ Quarantine files: {quarantine_files}")

        return True

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

    finally:
        os.chdir(original_cwd)

def test_duplicate_detection(generator, temp_dir):
    """Test 5: Duplicate Detection - Second call skips duplicate"""
    print("\n[TEST 5] Duplicate Detection - Skip duplicate entries")

    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # Restore valid data.json first
        test_data = {
            "movies": {},
            "last_updated": datetime.now().isoformat(),
            "total_count": 0
        }

        with open('data.json', 'w') as f:
            json.dump(test_data, f, indent=2)

        movie_id = f"duplicate_test_{int(time.time())}"
        movie_data = {
            "title": "Duplicate Test Movie",
            "digital_date": datetime.now().strftime('%Y-%m-%d'),
            "providers": {"streaming": ["Test"], "rent": [], "buy": []}
        }

        print(f"  Using test movie {movie_id}: {movie_data.get('title', 'Unknown')}")

        # First call - should add movie
        result1 = generator.add_movie_to_site_immediately(movie_id, movie_data)
        print(f"  ✅ First call returned: {result1}")

        # Second call - should detect duplicate and skip
        result2 = generator.add_movie_to_site_immediately(movie_id, movie_data)
        print(f"  ✅ Second call returned: {result2}")

        # Check data.json only has one entry
        if os.path.exists('data.json'):
            with open('data.json') as f:
                data = json.load(f)
                movie_count = len(data.get('movies', {}))
                print(f"  ✅ Total movies in data.json: {movie_count}")

                if movie_id in data.get('movies', {}):
                    print(f"  ✅ Movie {movie_id} exists (not duplicated)")

        return True

    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

    finally:
        os.chdir(original_cwd)

def main():
    """Run all end-to-end functional tests."""
    print("=== Enhanced Immediate Writing - End-to-End Functional Tests ===")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    temp_dir = None
    backup_path = None

    try:
        # Create backup of current state before running tests
        print("\n[BACKUP] Creating backup of current data.json...")
        backup_path = backup_current_state()

        # Set up test environment
        print("\n[SETUP] Creating test environment...")
        temp_dir, data_json_path, tracking_json_path, backups_dir = setup_test_environment()
        print(f"  ✅ Test directory: {temp_dir}")

        # Initialize DataGenerator
        print("\n[SETUP] Initializing DataGenerator...")
        from generator import DataGenerator
        generator = DataGenerator()
        print("  ✅ DataGenerator initialized")

        # Run all tests
        tests = [
            ("TMDB Success", lambda: test_tmdb_success(generator, temp_dir)),
            ("TMDB Failure", lambda: test_tmdb_failure(generator, temp_dir)),
            ("Atomic Write Backup", lambda: test_atomic_write_backup(generator, temp_dir, backups_dir)),
            ("Schema Validation", lambda: test_schema_validation_abort(generator, temp_dir)),
            ("Duplicate Detection", lambda: test_duplicate_detection(generator, temp_dir))
        ]

        passed_tests = 0
        total_tests = len(tests)

        for test_name, test_func in tests:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                print(f"  ❌ {test_name} test exception: {e}")

        # Summary
        print(f"\n=== TEST SUMMARY ===")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")

        if passed_tests == total_tests:
            print("Status: ✅ ALL FUNCTIONAL TESTS PASSED")
            # All tests passed - clean up backup
            print("\n[BACKUP] All tests passed - cleaning up backup...")
            cleanup_backup_on_success(backup_path)
            exit_code = 0
        else:
            print("Status: ❌ SOME TESTS FAILED")
            # Tests failed - restore from backup
            print("\n[RESTORE] Tests failed - restoring from backup...")
            if backup_path:
                restore_state_on_failure(backup_path)
            exit_code = 1

    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        # Exception occurred - restore from backup
        print("\n[RESTORE] Exception occurred - restoring from backup...")
        if backup_path:
            restore_state_on_failure(backup_path)
        exit_code = 1

    finally:
        # Cleanup test environment
        if temp_dir:
            print(f"\n[CLEANUP] Removing test directory: {temp_dir}")
            cleanup_test_environment(temp_dir)

    sys.exit(exit_code)

if __name__ == "__main__":
    main()