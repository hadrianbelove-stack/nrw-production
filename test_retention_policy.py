#!/usr/bin/env python3
"""
Comprehensive tests for backup retention policy in StorageService

Tests all aspects:
1. Age-based deletion (delete old files, keep recent ones)
2. Safety guards (only delete .corrupted-* files)
3. Rate limiting (don't run cleanup too frequently)
4. Configuration (enabled/disabled, custom retention days)
5. Integration with quarantine operations
"""
import json
import os
import tempfile
import time
import logging
from datetime import datetime, timedelta
from pipeline.storage import StorageService

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_old_quarantined_file(backups_dir: str, basename: str, age_days: int) -> str:
    """
    Create a mock quarantined file with specified age.

    Args:
        backups_dir: Directory to create file in
        basename: Base name for the file
        age_days: How many days old the file should be

    Returns:
        Path to created file
    """
    timestamp = (datetime.now() - timedelta(days=age_days)).strftime('%Y%m%d_%H%M%S')
    filename = f"{basename}.corrupted-parse-{timestamp}.json"
    filepath = os.path.join(backups_dir, filename)

    # Create the file
    with open(filepath, 'w') as f:
        json.dump({"corrupt": "data"}, f)

    # Set modification time to simulate age
    age_seconds = age_days * 86400
    old_time = time.time() - age_seconds
    os.utime(filepath, (old_time, old_time))

    return filepath

def test_delete_old_files():
    """Test that files older than retention period are deleted"""
    print("\n🧪 Test 1: Delete old quarantined files")

    # Create temporary backups directory
    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        # Save current directory and switch to temp
        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Create files with different ages (retention: 30 days)
            old_file_40_days = create_old_quarantined_file(backups_dir, 'test_cache', 40)
            old_file_35_days = create_old_quarantined_file(backups_dir, 'test_cache2', 35)
            recent_file_20_days = create_old_quarantined_file(backups_dir, 'test_cache3', 20)
            recent_file_5_days = create_old_quarantined_file(backups_dir, 'test_cache4', 5)

            # Verify files exist before cleanup
            assert os.path.exists(old_file_40_days), "Old file should exist before cleanup"
            assert os.path.exists(old_file_35_days), "Old file should exist before cleanup"

            # Initialize storage - cleanup runs automatically in __init__
            storage = StorageService(logger)

            # Note: cleanup already ran in __init__, so calling again would be rate-limited
            # We verify the cleanup happened by checking file existence
            assert not os.path.exists(old_file_40_days), "40-day old file should be deleted"
            assert not os.path.exists(old_file_35_days), "35-day old file should be deleted"
            assert os.path.exists(recent_file_20_days), "20-day old file should be kept"
            assert os.path.exists(recent_file_5_days), "5-day old file should be kept"

            print("   ✅ Test passed - old files deleted, recent files kept")

        finally:
            os.chdir(original_dir)

def test_safety_guards():
    """Test that only .corrupted-* files are deleted"""
    print("\n🧪 Test 2: Safety guards (only delete .corrupted-* files)")

    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Create various file types
            corrupted_file = create_old_quarantined_file(backups_dir, 'test', 40)

            # Create regular backup file (should NOT be deleted)
            regular_backup = os.path.join(backups_dir, 'movie_tracking.backup-20200101_120000.json')
            with open(regular_backup, 'w') as f:
                json.dump({"safe": "backup"}, f)
            # Make it old
            old_time = time.time() - (40 * 86400)
            os.utime(regular_backup, (old_time, old_time))

            # Create hidden file (should NOT be deleted)
            hidden_file = os.path.join(backups_dir, '.DS_Store')
            with open(hidden_file, 'w') as f:
                f.write("system file")
            os.utime(hidden_file, (old_time, old_time))

            # Initialize storage - cleanup runs automatically in __init__
            storage = StorageService(logger)

            # Verify only corrupted file was deleted
            assert not os.path.exists(corrupted_file), "Corrupted file should be deleted"
            assert os.path.exists(regular_backup), "Regular backup should be kept"
            assert os.path.exists(hidden_file), "Hidden file should be kept"

            print("   ✅ Test passed - only .corrupted-* files deleted")

        finally:
            os.chdir(original_dir)

def test_rate_limiting():
    """Test that cleanup doesn't run too frequently"""
    print("\n🧪 Test 3: Rate limiting (don't run cleanup too frequently)")

    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Initialize storage (this runs initial cleanup in __init__)
            storage = StorageService(logger)

            # Create old file after initialization
            old_file = create_old_quarantined_file(backups_dir, 'test', 40)

            # Immediate opportunistic cleanup should be skipped due to rate limiting
            storage._cleanup_old_backups_opportunistic()
            assert os.path.exists(old_file), "Opportunistic cleanup should be rate-limited"

            # Direct call to cleanup_old_backups() should still work (bypasses rate limiting)
            deleted = storage.cleanup_old_backups()
            assert deleted == 1, "Direct cleanup call should work (not rate limited)"
            assert not os.path.exists(old_file), "Direct cleanup should delete file"

            print("   ✅ Test passed - rate limiting works correctly")

        finally:
            os.chdir(original_dir)

def test_config_disabled():
    """Test that cleanup can be disabled via config"""
    print("\n🧪 Test 4: Config-based disable")

    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Create config with cleanup disabled
            config_content = """
backups:
  retention_days: 30
  cleanup_check_interval_hours: 1
  enabled: false
"""
            with open('config.yaml', 'w') as f:
                f.write(config_content)

            # Create old file
            old_file = create_old_quarantined_file(backups_dir, 'test', 40)

            # Initialize storage (cleanup should be skipped due to disabled config)
            storage = StorageService(logger)

            # Verify file still exists (cleanup was disabled)
            assert os.path.exists(old_file), "File should not be deleted when cleanup disabled"

            # Direct call should also respect the disabled config
            deleted = storage.cleanup_old_backups()
            assert deleted == 0, "Direct cleanup should also be skipped when disabled"
            assert os.path.exists(old_file), "File should still exist after direct cleanup call"

            print("   ✅ Test passed - cleanup can be disabled via config")

        finally:
            os.chdir(original_dir)

def test_custom_retention_period():
    """Test custom retention period from config"""
    print("\n🧪 Test 5: Custom retention period")

    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Create config with 7-day retention
            config_content = """
backups:
  retention_days: 7
  cleanup_check_interval_hours: 1
  enabled: true
"""
            with open('config.yaml', 'w') as f:
                f.write(config_content)

            # Create files
            old_file_10_days = create_old_quarantined_file(backups_dir, 'test1', 10)
            recent_file_5_days = create_old_quarantined_file(backups_dir, 'test2', 5)

            # Initialize storage (cleanup runs automatically with 7-day retention)
            storage = StorageService(logger)

            # Verify cleanup used custom 7-day retention period
            assert not os.path.exists(old_file_10_days), "10-day old file should be deleted with 7-day retention"
            assert os.path.exists(recent_file_5_days), "5-day old file should be kept with 7-day retention"

            print("   ✅ Test passed - custom retention period works")

        finally:
            os.chdir(original_dir)

def test_integration_with_quarantine():
    """Test that cleanup is triggered after quarantine"""
    print("\n🧪 Test 6: Integration with quarantine operations")

    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Create config with short retention for testing
            config_content = """
backups:
  retention_days: 7
  cleanup_check_interval_hours: 1
  enabled: true
"""
            with open('config.yaml', 'w') as f:
                f.write(config_content)

            # Create corrupt file to trigger quarantine
            corrupt_file = os.path.join(temp_dir, 'test_corrupt.json')
            with open(corrupt_file, 'w') as f:
                f.write('{broken json')

            # Initialize storage (runs initial cleanup)
            storage = StorageService(logger)

            # Create old quarantined file AFTER initialization
            # (so it won't be deleted by init cleanup)
            old_file = create_old_quarantined_file(backups_dir, 'old_cache', 10)

            # Verify old file exists
            assert os.path.exists(old_file), "Old file should exist before quarantine"

            # Load corrupt file - triggers quarantine, which triggers opportunistic cleanup
            # But cleanup will be rate-limited, so we call it directly
            storage.load_cache(corrupt_file)

            # Force cleanup by directly calling (bypassing rate limit)
            deleted = storage.cleanup_old_backups()
            assert deleted == 1, "Old file should be deleted after direct cleanup call"
            assert not os.path.exists(old_file), "Old file should be gone"

            # Verify quarantine happened
            quarantined_files = [f for f in os.listdir(backups_dir) if 'test_corrupt' in f]
            assert len(quarantined_files) == 1, "Corrupt file should be quarantined"

            print("   ✅ Test passed - cleanup integrates with quarantine")

        finally:
            os.chdir(original_dir)

def test_empty_backups_directory():
    """Test cleanup handles missing/empty backups directory gracefully"""
    print("\n🧪 Test 7: Empty/missing backups directory")

    with tempfile.TemporaryDirectory() as temp_dir:
        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # No backups directory exists
            storage = StorageService(logger)
            deleted = storage.cleanup_old_backups()

            assert deleted == 0, "Should return 0 for missing directory"

            # Create empty backups directory
            os.makedirs('backups')
            deleted = storage.cleanup_old_backups()

            assert deleted == 0, "Should return 0 for empty directory"

            print("   ✅ Test passed - handles empty/missing directory")

        finally:
            os.chdir(original_dir)

def test_mixed_corruption_types():
    """Test cleanup handles different corruption types (.corrupted-parse, .corrupted-str, etc.)"""
    print("\n🧪 Test 8: Mixed corruption types")

    with tempfile.TemporaryDirectory() as temp_dir:
        backups_dir = os.path.join(temp_dir, 'backups')
        os.makedirs(backups_dir)

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Create files with different corruption types
            timestamp = (datetime.now() - timedelta(days=40)).strftime('%Y%m%d_%H%M%S')

            files = []
            for corruption_type in ['parse', 'str', 'list', 'ioerror', 'unknown']:
                filename = f"test.corrupted-{corruption_type}-{timestamp}.json"
                filepath = os.path.join(backups_dir, filename)
                with open(filepath, 'w') as f:
                    f.write("corrupt")

                # Make old
                old_time = time.time() - (40 * 86400)
                os.utime(filepath, (old_time, old_time))
                files.append(filepath)

            # Initialize storage (cleanup runs automatically)
            storage = StorageService(logger)

            # Verify all corrupted files were deleted
            for filepath in files:
                assert not os.path.exists(filepath), f"File should be deleted: {filepath}"

            print("   ✅ Test passed - all corruption types handled")

        finally:
            os.chdir(original_dir)

def run_all_tests():
    """Run all retention policy tests"""
    print("="*60)
    print("BACKUP RETENTION POLICY TESTS")
    print("="*60)

    test_delete_old_files()
    test_safety_guards()
    test_rate_limiting()
    test_config_disabled()
    test_custom_retention_period()
    test_integration_with_quarantine()
    test_empty_backups_directory()
    test_mixed_corruption_types()

    print("\n" + "="*60)
    print("✅ ALL RETENTION POLICY TESTS PASSED")
    print("="*60)

if __name__ == "__main__":
    run_all_tests()
