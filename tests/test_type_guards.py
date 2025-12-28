#!/usr/bin/env python3
"""
Test type guards in StorageService
"""
import json
import os
import tempfile
import logging
from pipeline.storage import StorageService

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_type_guards():
    """Test that type guards catch and handle type mismatches"""
    storage = StorageService(logger)

    # Test 1: Create a corrupt cache file (string instead of dict)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump("This is a string, not a dict!", f)
        corrupt_file = f.name

    try:
        print("\n🧪 Test 1: Loading corrupt cache (string instead of dict)")
        result = storage.load_cache(corrupt_file)
        print(f"   Result type: {type(result).__name__}")
        print(f"   Result value: {result}")
        assert isinstance(result, dict), "Should return empty dict"
        assert result == {}, "Should return empty dict"
        print("   ✅ Test passed - returned empty dict")

        # Check that corrupt file was moved to backups
        assert not os.path.exists(corrupt_file), "Corrupt file should be moved"
        print("   ✅ Corrupt file moved to backups/")

    finally:
        if os.path.exists(corrupt_file):
            os.unlink(corrupt_file)

    # Test 2: Create a corrupt cache file (list instead of dict)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump([1, 2, 3], f)
        corrupt_file = f.name

    try:
        print("\n🧪 Test 2: Loading corrupt cache (list instead of dict)")
        result = storage.load_cache(corrupt_file)
        print(f"   Result type: {type(result).__name__}")
        print(f"   Result value: {result}")
        assert isinstance(result, dict), "Should return empty dict"
        assert result == {}, "Should return empty dict"
        print("   ✅ Test passed - returned empty dict")

        # Check that corrupt file was moved to backups
        assert not os.path.exists(corrupt_file), "Corrupt file should be moved"
        print("   ✅ Corrupt file moved to backups/")

    finally:
        if os.path.exists(corrupt_file):
            os.unlink(corrupt_file)

    # Test 3: Test load_json with expected_type
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump("wrong type", f)
        corrupt_file = f.name

    try:
        print("\n🧪 Test 3: Loading with expected_type=dict")
        result = storage.load_json(corrupt_file, default={"key": "value"}, expected_type=dict)
        print(f"   Result type: {type(result).__name__}")
        print(f"   Result value: {result}")
        assert isinstance(result, dict), "Should return default dict"
        assert result == {"key": "value"}, "Should return default dict"
        print("   ✅ Test passed - returned default dict")

    finally:
        if os.path.exists(corrupt_file):
            os.unlink(corrupt_file)

    # Test 4: Valid cache file should load normally
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"valid": "data"}, f)
        valid_file = f.name

    try:
        print("\n🧪 Test 4: Loading valid cache file")
        result = storage.load_cache(valid_file)
        print(f"   Result type: {type(result).__name__}")
        print(f"   Result value: {result}")
        assert isinstance(result, dict), "Should return dict"
        assert result == {"valid": "data"}, "Should return original data"
        print("   ✅ Test passed - loaded valid data")

    finally:
        if os.path.exists(valid_file):
            os.unlink(valid_file)

    print("\n✅ All type guard tests passed!\n")

if __name__ == "__main__":
    test_type_guards()
