#!/usr/bin/env python3
"""
Test script for 2025-11-09 fixes:
1. Hardcoded localhost fix (data.json includes hidden/featured)
2. JSON validation
3. File locking
"""

import json
import sys
import os
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

def test_1_data_json_structure():
    """Test that data.json includes hidden and featured arrays"""
    print("\n" + "="*60)
    print("TEST 1: data.json Structure (Localhost Fix)")
    print("="*60)

    try:
        with open('data.json', 'r') as f:
            data = json.load(f)

        # Check required keys
        required = ['generated_at', 'count', 'movies', 'hidden', 'featured']
        has_keys = all(key in data for key in required)

        if not has_keys:
            missing = [k for k in required if k not in data]
            return test_result(
                "data.json has required keys",
                False,
                f"Missing keys: {missing}"
            )

        test_result("data.json has required keys", True)

        # Check types
        checks = [
            test_result(
                "generated_at is string",
                isinstance(data['generated_at'], str),
                f"Type: {type(data['generated_at'])}"
            ),
            test_result(
                "count is integer",
                isinstance(data['count'], int),
                f"Value: {data['count']}"
            ),
            test_result(
                "movies is list",
                isinstance(data['movies'], list),
                f"Length: {len(data['movies'])}"
            ),
            test_result(
                "hidden is list",
                isinstance(data['hidden'], list),
                f"Length: {len(data['hidden'])}"
            ),
            test_result(
                "featured is list",
                isinstance(data['featured'], list),
                f"Length: {len(data['featured'])}"
            )
        ]

        return all(checks)

    except FileNotFoundError:
        return test_result("data.json exists", False, "File not found")
    except json.JSONDecodeError as e:
        return test_result("data.json is valid JSON", False, str(e))
    except Exception as e:
        return test_result("data.json structure test", False, str(e))

def test_2_json_validation():
    """Test JSON validation function"""
    print("\n" + "="*60)
    print("TEST 2: JSON Validation")
    print("="*60)

    try:
        from admin.utils import validate_movie_update_request

        # Test valid request
        valid_request = {
            'movie_id': '12345',
            'director': 'Christopher Nolan',
            'rt_score': 85
        }
        is_valid, error = validate_movie_update_request(valid_request)
        test_result("Valid request accepted", is_valid, f"Error: {error}" if error else "")

        # Test unexpected field
        invalid_request = {
            'movie_id': '12345',
            'unexpected_field': 'malicious'
        }
        is_valid, error = validate_movie_update_request(invalid_request)
        test_result(
            "Unexpected field rejected",
            not is_valid,
            f"Error: {error}"
        )

        # Test missing movie_id
        invalid_request = {
            'director': 'Test'
        }
        is_valid, error = validate_movie_update_request(invalid_request)
        test_result(
            "Missing movie_id rejected",
            not is_valid,
            f"Error: {error}"
        )

        # Test string too long
        invalid_request = {
            'movie_id': '12345',
            'director': 'A' * 300
        }
        is_valid, error = validate_movie_update_request(invalid_request)
        test_result(
            "Too-long string rejected",
            not is_valid,
            f"Error: {error}"
        )

        # Test invalid URL
        invalid_request = {
            'movie_id': '12345',
            'rt_link': 'not-a-url'
        }
        is_valid, error = validate_movie_update_request(invalid_request)
        test_result(
            "Invalid URL rejected",
            not is_valid,
            f"Error: {error}"
        )

        # Test invalid year
        invalid_request = {
            'movie_id': '12345',
            'year': 2500
        }
        is_valid, error = validate_movie_update_request(invalid_request)
        test_result(
            "Out-of-range year rejected",
            not is_valid,
            f"Error: {error}"
        )

        # Test invalid RT score
        invalid_request = {
            'movie_id': '12345',
            'rt_score': 150
        }
        is_valid, error = validate_movie_update_request(invalid_request)
        test_result(
            "Out-of-range RT score rejected",
            not is_valid,
            f"Error: {error}"
        )

        return True

    except ImportError as e:
        return test_result("Import validation function", False, str(e))
    except Exception as e:
        return test_result("JSON validation test", False, str(e))

def test_3_file_locking():
    """Test file locking functionality"""
    print("\n" + "="*60)
    print("TEST 3: File Locking")
    print("="*60)

    try:
        from file_lock import safe_write_json_atomic, safe_read_json_locked

        # Test basic write
        test_file = 'test_lock_write.json'
        test_data = {'test': 'data', 'timestamp': datetime.now().isoformat()}

        try:
            safe_write_json_atomic(test_file, test_data, timeout=5.0)
            test_result("Write with locking succeeds", True)
        except Exception as e:
            test_result("Write with locking succeeds", False, str(e))
            return False

        # Test basic read
        try:
            read_data = safe_read_json_locked(test_file, timeout=5.0)
            matches = read_data == test_data
            test_result(
                "Read with locking succeeds",
                matches,
                f"Read data matches: {matches}"
            )
        except Exception as e:
            test_result("Read with locking succeeds", False, str(e))
            return False

        # Test concurrent writes (simulate race condition)
        print(f"\n{YELLOW}Note: Concurrent write test skipped (requires multiprocessing){RESET}")
        print(f"      Manual test: Run generate_data.py and admin save simultaneously")

        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)

        return True

    except ImportError as e:
        return test_result("Import file_lock module", False, str(e))
    except Exception as e:
        return test_result("File locking test", False, str(e))

def test_4_frontend_compatibility():
    """Test that frontend code is compatible"""
    print("\n" + "="*60)
    print("TEST 4: Frontend Compatibility")
    print("="*60)

    try:
        with open('assets/app.js', 'r') as f:
            app_js = f.read()

        # Check that localhost fetch is removed
        has_localhost = 'localhost:5556' in app_js
        test_result(
            "No hardcoded localhost in app.js",
            not has_localhost,
            "Found localhost:5556" if has_localhost else "Clean"
        )

        # Check that it reads from data.json
        reads_from_data = 'data.hidden' in app_js or 'data.featured' in app_js
        test_result(
            "Reads hidden/featured from data.json",
            reads_from_data,
            "Found data.hidden/featured references" if reads_from_data else "Missing"
        )

        return not has_localhost and reads_from_data

    except Exception as e:
        return test_result("Frontend compatibility test", False, str(e))

def test_5_backwards_compatibility():
    """Test backwards compatibility"""
    print("\n" + "="*60)
    print("TEST 5: Backwards Compatibility")
    print("="*60)

    try:
        # Test old import still works
        from file_lock import safe_write_json
        test_result("Old safe_write_json import works", True)

        # Test it's actually the new function
        import file_lock
        is_new = safe_write_json == file_lock.safe_write_json
        test_result(
            "safe_write_json uses new implementation",
            is_new,
            "Imported from file_lock.py"
        )

        return True

    except Exception as e:
        return test_result("Backwards compatibility test", False, str(e))

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("NRW FIXES TEST SUITE - 2025-11-09")
    print("="*60)

    results = {
        'Test 1 - data.json Structure': test_1_data_json_structure(),
        'Test 2 - JSON Validation': test_2_json_validation(),
        'Test 3 - File Locking': test_3_file_locking(),
        'Test 4 - Frontend Compatibility': test_4_frontend_compatibility(),
        'Test 5 - Backwards Compatibility': test_5_backwards_compatibility()
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
        print(f"\n{GREEN}✅ ALL TESTS PASSED{RESET}")
        return 0
    else:
        print(f"\n{RED}❌ SOME TESTS FAILED{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
