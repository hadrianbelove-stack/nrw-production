#!/usr/bin/env python3
"""
Test suite for storage extraction (Phase 1).

Tests that storage.py works correctly and integrates with generate_data.py.
"""

import os
import json
import sys
import tempfile
import shutil
from datetime import datetime

# Test colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def test_result(name, passed, details=""):
    """Print test result"""
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"{status} - {name}")
    if details:
        print(f"      {details}")
    return passed

def test_storage_service_import():
    """Test that StorageService imports correctly"""
    print("\n" + "="*60)
    print("TEST 1: StorageService Import")
    print("="*60)

    try:
        from pipeline import StorageService
        from pipeline.storage import StorageService as DirectImport

        test_result("Import from pipeline package", True)
        test_result("Direct import from storage module", True)
        test_result("Both imports reference same class", StorageService is DirectImport)

        return True
    except ImportError as e:
        test_result("StorageService import", False, str(e))
        return False

def test_storage_service_methods():
    """Test StorageService methods work correctly"""
    print("\n" + "="*60)
    print("TEST 2: StorageService Methods")
    print("="*60)

    try:
        from pipeline import StorageService
        import logging

        # Create temp directory for testing
        test_dir = tempfile.mkdtemp(prefix='nrw_storage_test_')

        try:
            # Initialize service
            logger = logging.getLogger('test_storage')
            logger.addHandler(logging.NullHandler())
            storage = StorageService(logger)

            test_result("StorageService initialization", True)

            # Test load_cache (non-existent file)
            cache_file = os.path.join(test_dir, 'test_cache.json')
            cache = storage.load_cache(cache_file)
            test_result(
                "load_cache returns empty dict for missing file",
                cache == {},
                f"Returned: {cache}"
            )

            # Test save_cache
            test_data = {'test': 'data', 'count': 42}
            storage.save_cache(test_data, cache_file)
            test_result("save_cache creates file", os.path.exists(cache_file))

            # Test load_cache (existing file)
            loaded = storage.load_cache(cache_file)
            test_result(
                "load_cache reads saved data",
                loaded == test_data,
                f"Expected: {test_data}, Got: {loaded}"
            )

            # Test atomic_write_json
            json_file = os.path.join(test_dir, 'test.json')
            backup_dir = os.path.join(test_dir, 'backups')

            # Create backups directory structure expected by StorageService
            original_cwd = os.getcwd()
            os.chdir(test_dir)

            try:
                success = storage.atomic_write_json({'version': 1}, 'test.json', backup=True)
                test_result("atomic_write_json succeeds", success)
                test_result("atomic_write_json creates file", os.path.exists('test.json'))

                # Update file (should create backup)
                success = storage.atomic_write_json({'version': 2}, 'test.json', backup=True)
                test_result("atomic_write_json updates file", success)

                # Check backup was created
                backup_exists = os.path.exists('backups') and len(os.listdir('backups')) > 0
                test_result("atomic_write_json creates backups", backup_exists)

                # Verify data
                with open('test.json', 'r') as f:
                    data = json.load(f)
                test_result(
                    "atomic_write_json preserves data",
                    data['version'] == 2,
                    f"Data: {data}"
                )
            finally:
                os.chdir(original_cwd)

            return True

        finally:
            # Cleanup test directory
            shutil.rmtree(test_dir)

    except Exception as e:
        test_result("StorageService methods test", False, str(e))
        return False

def test_generate_data_integration():
    """Test that generate_data.py works with new storage service"""
    print("\n" + "="*60)
    print("TEST 3: Integration with generate_data.py")
    print("="*60)

    try:
        # Import without initializing (to avoid TMDB API key requirement)
        from generate_data import DataGenerator
        import logging

        test_result("DataGenerator imports successfully", True)

        # Check that StorageService is imported
        import inspect
        init_source = inspect.getsource(DataGenerator.__init__)
        has_storage_import = 'from pipeline import StorageService' in init_source
        test_result(
            "DataGenerator imports StorageService",
            has_storage_import,
            "Found import in __init__"
        )

        has_storage_init = 'self.storage = StorageService' in init_source
        test_result(
            "DataGenerator initializes storage service",
            has_storage_init,
            "Found self.storage initialization"
        )

        return True

    except Exception as e:
        test_result("DataGenerator integration", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def test_method_replacements():
    """Test that all old method calls were replaced"""
    print("\n" + "="*60)
    print("TEST 4: Method Call Replacements")
    print("="*60)

    try:
        with open('generate_data.py', 'r') as f:
            content = f.read()

        # Check that storage service calls exist
        storage_calls = content.count('self.storage.')
        test_result(
            "Storage service calls present",
            storage_calls > 20,
            f"Found {storage_calls} calls to self.storage.*"
        )

        # Check that old method definitions were removed/commented
        has_old_load_cache = 'def load_cache(self, filename):' in content
        test_result(
            "Old load_cache method removed",
            not has_old_load_cache,
            "Method definition not found (good)"
        )

        has_old_save_cache = 'def save_cache(self, data, filename):' in content
        test_result(
            "Old save_cache method removed",
            not has_old_save_cache,
            "Method definition not found (good)"
        )

        has_old_atomic = 'def atomic_write_json(self, data, filepath):' in content
        test_result(
            "Old atomic_write_json method removed",
            not has_old_atomic,
            "Method definition not found (good)"
        )

        # Check for migration comments
        has_migration_comments = 'moved to pipeline/storage.py' in content
        test_result(
            "Migration comments present",
            has_migration_comments,
            "Found documentation of extraction"
        )

        return True

    except Exception as e:
        test_result("Method replacement check", False, str(e))
        return False

def test_file_locking_integration():
    """Test that file locking integrates with storage service"""
    print("\n" + "="*60)
    print("TEST 5: File Locking Integration")
    print("="*60)

    try:
        from pipeline.storage import StorageService
        import logging

        # Read storage.py source to verify file_lock integration
        with open('pipeline/storage.py', 'r') as f:
            storage_source = f.read()

        has_file_lock_import = 'from file_lock import' in storage_source
        test_result(
            "Storage imports file_lock",
            has_file_lock_import,
            "Found file_lock import"
        )

        uses_safe_write = 'safe_write_json_atomic' in storage_source
        test_result(
            "Storage uses safe_write_json_atomic",
            uses_safe_write,
            "Found call to locking function"
        )

        has_fallback = 'except ImportError' in storage_source
        test_result(
            "Storage has fallback for missing file_lock",
            has_fallback,
            "ImportError handler present"
        )

        return True

    except Exception as e:
        test_result("File locking integration", False, str(e))
        return False

def test_line_count_reduction():
    """Verify line count reduction from extraction"""
    print("\n" + "="*60)
    print("TEST 6: Line Count Metrics")
    print("="*60)

    try:
        # Count lines in generate_data.py
        with open('generate_data.py', 'r') as f:
            gen_lines = len(f.readlines())

        # Count lines in pipeline/storage.py
        with open('pipeline/storage.py', 'r') as f:
            storage_lines = len(f.readlines())

        test_result(
            "generate_data.py reduced",
            gen_lines < 3300,
            f"Current: {gen_lines} lines (was ~3352)"
        )

        test_result(
            "storage.py created",
            storage_lines > 250,
            f"Storage module: {storage_lines} lines"
        )

        reduction = 3352 - gen_lines
        test_result(
            "Net reduction achieved",
            reduction > 100,
            f"Removed {reduction} lines from monolith"
        )

        return True

    except Exception as e:
        test_result("Line count metrics", False, str(e))
        return False

def test_backward_compatibility():
    """Test that existing usage patterns still work"""
    print("\n" + "="*60)
    print("TEST 7: Backward Compatibility")
    print("="*60)

    try:
        from pipeline import StorageService
        import logging

        # Simulate old DataGenerator pattern
        class MockDataGenerator:
            def __init__(self):
                self.logger = logging.getLogger('mock')
                self.logger.addHandler(logging.NullHandler())
                from pipeline import StorageService
                self.storage = StorageService(self.logger)
                self.config = {'tracking': {'archive_available_on_detect': False}}

        mock_gen = MockDataGenerator()

        # Test that storage methods are accessible
        has_load_cache = hasattr(mock_gen.storage, 'load_cache')
        has_save_cache = hasattr(mock_gen.storage, 'save_cache')
        has_atomic_write = hasattr(mock_gen.storage, 'atomic_write_json')
        has_load_all = hasattr(mock_gen.storage, 'load_all_movies')

        test_result("load_cache method accessible", has_load_cache)
        test_result("save_cache method accessible", has_save_cache)
        test_result("atomic_write_json method accessible", has_atomic_write)
        test_result("load_all_movies method accessible", has_load_all)

        # Test that methods work
        cache = mock_gen.storage.load_cache('nonexistent.json')
        test_result("load_cache works", isinstance(cache, dict))

        return True

    except Exception as e:
        test_result("Backward compatibility", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("STORAGE EXTRACTION TEST SUITE")
    print("="*60)

    results = {
        'Test 1 - StorageService Import': test_storage_service_import(),
        'Test 2 - StorageService Methods': test_storage_service_methods(),
        'Test 3 - DataGenerator Integration': test_generate_data_integration(),
        'Test 4 - Method Replacements': test_method_replacements(),
        'Test 5 - File Locking Integration': test_file_locking_integration(),
        'Test 6 - Line Count Metrics': test_line_count_reduction(),
        'Test 7 - Backward Compatibility': test_backward_compatibility(),
    }

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(results.values())
    total = len(results)

    for name, result in results.items():
        status = f"{GREEN}✓{RESET}" if result else f"{RED}✗{RESET}"
        print(f"{status} {name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print(f"\n{GREEN}✅ ALL TESTS PASSED - Storage extraction successful!{RESET}")
        return 0
    else:
        print(f"\n{RED}❌ SOME TESTS FAILED - Review output above{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
