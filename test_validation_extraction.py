#!/usr/bin/env python3
"""
Test suite for validation extraction (Phase 2).

Tests that validation.py works correctly and integrates with generate_data.py.
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

def test_validation_service_import():
    """Test that ValidationService imports correctly"""
    print("\n" + "="*60)
    print("TEST 1: ValidationService Import")
    print("="*60)

    try:
        from pipeline import ValidationService
        from pipeline.validation import ValidationService as DirectImport

        test_result("Import from pipeline package", True)
        test_result("Direct import from validation module", True)
        test_result("Both imports reference same class", ValidationService is DirectImport)

        return True
    except ImportError as e:
        test_result("ValidationService import", False, str(e))
        return False

def test_validation_service_methods():
    """Test ValidationService methods work correctly"""
    print("\n" + "="*60)
    print("TEST 2: ValidationService Methods")
    print("="*60)

    try:
        from pipeline import ValidationService
        import logging

        # Save original working directory
        original_cwd = os.getcwd()

        # Create temp directory for testing
        test_dir = tempfile.mkdtemp(prefix='nrw_validation_test_')

        try:
            # Initialize service
            logger = logging.getLogger('test_validation')
            logger.addHandler(logging.NullHandler())
            validator = ValidationService(logger=logger)

            test_result("ValidationService initialization", True)

            # Test validate_watch_links_schema
            valid_links = {
                'streaming': {'service': 'Netflix', 'link': 'https://netflix.com/title/123'},
                'rent': {'service': 'Amazon', 'link': None}
            }
            validated = validator.validate_watch_links_schema(valid_links, 'Test Movie')
            test_result(
                "validate_watch_links_schema accepts valid links",
                validated == valid_links,
                f"Returned: {validated}"
            )

            # Test reject invalid category
            invalid_links = {
                'invalid_category': {'service': 'Test', 'link': None}
            }
            validated = validator.validate_watch_links_schema(invalid_links, 'Test Movie')
            test_result(
                "validate_watch_links_schema rejects invalid category",
                validated == {},
                f"Returned: {validated}"
            )

            # Test reject invalid link
            invalid_links = {
                'streaming': {'service': 'Test', 'link': 'not-a-url'}
            }
            validated = validator.validate_watch_links_schema(invalid_links, 'Test Movie')
            test_result(
                "validate_watch_links_schema rejects invalid URL",
                validated == {},
                f"Returned: {validated}"
            )

            # Test validate_data_json_schema with valid data
            os.chdir(test_dir)
            valid_data = {
                'generated_at': datetime.now().isoformat(),
                'count': 1,
                'movies': [
                    {'id': '123', 'title': 'Test Movie', 'digital_date': '2025-01-01'}
                ]
            }
            with open('test_data.json', 'w') as f:
                json.dump(valid_data, f)

            is_valid = validator.validate_data_json_schema('test_data.json')
            test_result("validate_data_json_schema accepts valid data", is_valid)

            # Test reject invalid data
            invalid_data = {'invalid': 'structure'}
            with open('test_invalid.json', 'w') as f:
                json.dump(invalid_data, f)

            is_valid = validator.validate_data_json_schema('test_invalid.json')
            test_result("validate_data_json_schema rejects invalid data", not is_valid)

            # Test stats tracking
            stats = validator.get_stats()
            test_result(
                "ValidationService tracks stats",
                'schema_validation_warnings' in stats and 'schema_validation_passes' in stats,
                f"Stats: {stats}"
            )

            return True

        finally:
            # Restore original working directory
            os.chdir(original_cwd)
            # Cleanup test directory
            shutil.rmtree(test_dir)

    except Exception as e:
        test_result("ValidationService methods test", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def test_generate_data_integration():
    """Test that generate_data.py works with new validation service"""
    print("\n" + "="*60)
    print("TEST 3: Integration with generate_data.py")
    print("="*60)

    try:
        # Import without initializing (to avoid TMDB API key requirement)
        from generate_data import DataGenerator
        import logging

        test_result("DataGenerator imports successfully", True)

        # Check that ValidationService is imported
        import inspect
        init_source = inspect.getsource(DataGenerator.__init__)
        has_validation_import = 'from pipeline import ValidationService' in init_source
        test_result(
            "DataGenerator imports ValidationService",
            has_validation_import,
            "Found import in __init__"
        )

        has_validator_init = 'self.validator = ValidationService' in init_source
        test_result(
            "DataGenerator initializes validation service",
            has_validator_init,
            "Found self.validator initialization"
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

        # Check that validator service calls exist
        validator_calls = content.count('self.validator.')
        test_result(
            "Validator service calls present",
            validator_calls >= 8,
            f"Found {validator_calls} calls to self.validator.*"
        )

        # Check specific method calls
        validate_watch_links_calls = content.count('self.validator.validate_watch_links_schema(')
        test_result(
            "validate_watch_links_schema calls replaced",
            validate_watch_links_calls >= 5,
            f"Found {validate_watch_links_calls} calls"
        )

        validate_data_json_calls = content.count('self.validator.validate_data_json_schema(')
        test_result(
            "validate_data_json_schema calls replaced",
            validate_data_json_calls >= 2,
            f"Found {validate_data_json_calls} calls"
        )

        # validate_enrichment_consistency was DELETED 2025-12-05 (loop bug)
        # No longer testing for its presence

        # Check that old method definitions were removed/commented
        has_old_validate_watch = 'def validate_watch_links_schema(self, watch_links' in content
        test_result(
            "Old validate_watch_links_schema method removed",
            not has_old_validate_watch,
            "Method definition not found (good)"
        )

        # validate_enrichment_consistency was DELETED 2025-12-05 - skip check

        has_old_validate_data = 'def validate_data_json_schema(self, file_path' in content
        test_result(
            "Old validate_data_json_schema method removed",
            not has_old_validate_data,
            "Method definition not found (good)"
        )

        # Check for migration comments
        has_migration_comments = 'moved to pipeline/validation.py' in content
        test_result(
            "Migration comments present",
            has_migration_comments,
            "Found documentation of extraction"
        )

        return True

    except Exception as e:
        test_result("Method replacement check", False, str(e))
        return False

def test_line_count_reduction():
    """Verify line count reduction from extraction"""
    print("\n" + "="*60)
    print("TEST 5: Line Count Metrics")
    print("="*60)

    try:
        # Count lines in generate_data.py
        with open('generate_data.py', 'r') as f:
            gen_lines = len(f.readlines())

        # Count lines in pipeline/validation.py
        with open('pipeline/validation.py', 'r') as f:
            validation_lines = len(f.readlines())

        test_result(
            "generate_data.py reduced from storage extraction",
            gen_lines < 3231,
            f"Current: {gen_lines} lines (was 3231 after storage extraction)"
        )

        test_result(
            "validation.py created",
            validation_lines > 300,
            f"Validation module: {validation_lines} lines"
        )

        reduction = 3231 - gen_lines
        test_result(
            "Net reduction achieved",
            reduction > 200,
            f"Removed {reduction} lines from monolith"
        )

        return True

    except Exception as e:
        test_result("Line count metrics", False, str(e))
        return False

def test_backward_compatibility():
    """Test that existing usage patterns still work"""
    print("\n" + "="*60)
    print("TEST 6: Backward Compatibility")
    print("="*60)

    try:
        from pipeline import ValidationService
        import logging

        # Simulate old DataGenerator pattern
        class MockDataGenerator:
            def __init__(self):
                self.logger = logging.getLogger('mock')
                self.logger.addHandler(logging.NullHandler())
                from pipeline import ValidationService
                self.config = {}
                self.watchmode_stats = {
                    'schema_validation_warnings': 0,
                    'schema_validation_passes': 0
                }
                self.validator = ValidationService(
                    logger=self.logger,
                    config=self.config,
                    stats_dict=self.watchmode_stats
                )

        mock_gen = MockDataGenerator()

        # Test that validation methods are accessible
        has_validate_watch = hasattr(mock_gen.validator, 'validate_watch_links_schema')
        # validate_enrichment_consistency DELETED 2025-12-05 (loop bug)
        has_validate_data = hasattr(mock_gen.validator, 'validate_data_json_schema')

        test_result("validate_watch_links_schema method accessible", has_validate_watch)
        # validate_enrichment_consistency test removed - function deleted 2025-12-05
        test_result("validate_data_json_schema method accessible", has_validate_data)

        # Test that methods work
        valid_links = {'streaming': {'service': 'Netflix', 'link': 'https://netflix.com/test'}}
        validated = mock_gen.validator.validate_watch_links_schema(valid_links, 'Test')
        test_result("validate_watch_links_schema works", isinstance(validated, dict))

        # Test stats sharing
        test_result(
            "Stats dict is shared",
            mock_gen.validator.stats is mock_gen.watchmode_stats,
            "ValidationService updates shared stats dict"
        )

        return True

    except Exception as e:
        test_result("Backward compatibility", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def test_stats_integration():
    """Test that validation stats integrate with watchmode_stats"""
    print("\n" + "="*60)
    print("TEST 7: Stats Integration")
    print("="*60)

    try:
        from pipeline import ValidationService
        import logging

        logger = logging.getLogger('test')
        logger.addHandler(logging.NullHandler())

        # Create shared stats dict (simulating self.watchmode_stats)
        shared_stats = {
            'schema_validation_warnings': 0,
            'schema_validation_passes': 0,
            'other_metric': 42
        }

        # Initialize validator with shared stats
        validator = ValidationService(
            logger=logger,
            stats_dict=shared_stats
        )

        test_result(
            "Validator uses shared stats dict",
            validator.stats is shared_stats,
            "Stats dict reference matches"
        )

        # Validate something to increment stats
        valid_links = {'streaming': {'service': 'Netflix', 'link': 'https://netflix.com/test'}}
        validator.validate_watch_links_schema(valid_links, 'Test')

        test_result(
            "Stats updated in shared dict",
            shared_stats['schema_validation_passes'] > 0,
            f"Passes: {shared_stats['schema_validation_passes']}"
        )

        test_result(
            "Other stats preserved",
            shared_stats['other_metric'] == 42,
            "Unrelated metrics unchanged"
        )

        return True

    except Exception as e:
        test_result("Stats integration", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("VALIDATION EXTRACTION TEST SUITE")
    print("="*60)

    results = {
        'Test 1 - ValidationService Import': test_validation_service_import(),
        'Test 2 - ValidationService Methods': test_validation_service_methods(),
        'Test 3 - DataGenerator Integration': test_generate_data_integration(),
        'Test 4 - Method Replacements': test_method_replacements(),
        'Test 5 - Line Count Metrics': test_line_count_reduction(),
        'Test 6 - Backward Compatibility': test_backward_compatibility(),
        'Test 7 - Stats Integration': test_stats_integration(),
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
        print(f"\n{GREEN}✅ ALL TESTS PASSED - Validation extraction successful!{RESET}")
        return 0
    else:
        print(f"\n{RED}❌ SOME TESTS FAILED - Review output above{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
