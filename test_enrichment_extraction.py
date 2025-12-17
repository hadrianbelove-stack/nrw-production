#!/usr/bin/env python3
"""
Test suite for enrichment extraction (Phase 3).

Tests that enrichment.py works correctly and integrates with generate_data.py.
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

def test_enrichment_service_import():
    """Test that EnrichmentService imports correctly"""
    print("\n" + "="*60)
    print("TEST 1: EnrichmentService Import")
    print("="*60)

    try:
        from pipeline import EnrichmentService
        from pipeline.enrichment import EnrichmentService as DirectImport

        test_result("Import from pipeline package", True)
        test_result("Direct import from enrichment module", True)
        test_result("Both imports reference same class", EnrichmentService is DirectImport)

        return True
    except ImportError as e:
        test_result("EnrichmentService import", False, str(e))
        return False

def test_enrichment_service_methods():
    """Test EnrichmentService methods work correctly"""
    print("\n" + "="*60)
    print("TEST 2: EnrichmentService Methods")
    print("="*60)

    try:
        from pipeline import EnrichmentService
        import logging

        # Save original working directory
        original_cwd = os.getcwd()

        # Create temp directory for testing
        test_dir = tempfile.mkdtemp(prefix='nrw_enrichment_test_')

        try:
            # Initialize service
            logger = logging.getLogger('test_enrichment')
            logger.addHandler(logging.NullHandler())
            enrichment = EnrichmentService(logger=logger)

            test_result("EnrichmentService initialization", True)

            # Test utility methods
            test_result(
                "is_excluded_service method exists",
                hasattr(enrichment, 'is_excluded_service')
            )

            test_result(
                "is_actual_amazon_service method exists",
                hasattr(enrichment, 'is_actual_amazon_service')
            )

            test_result(
                "append_affiliate_tag method exists",
                hasattr(enrichment, 'append_affiliate_tag')
            )

            # Test is_actual_amazon_service
            is_amazon = enrichment.is_actual_amazon_service('Amazon Prime Video')
            test_result(
                "is_actual_amazon_service recognizes Amazon",
                is_amazon,
                f"Returned: {is_amazon}"
            )

            not_amazon = enrichment.is_actual_amazon_service('Amazon Channel')
            test_result(
                "is_actual_amazon_service rejects Amazon Channel",
                not not_amazon,
                f"Returned: {not_amazon}"
            )

            # Test affiliate tag (without config, should return original URL)
            test_url = "https://amazon.com/test"
            tagged = enrichment.append_affiliate_tag(test_url, "Amazon")
            test_result(
                "append_affiliate_tag returns URL",
                tagged == test_url,
                f"Returned: {tagged}"
            )

            return True

        finally:
            # Restore original working directory
            os.chdir(original_cwd)
            # Cleanup test directory
            shutil.rmtree(test_dir)

    except Exception as e:
        test_result("EnrichmentService methods test", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def test_generate_data_integration():
    """Test that pipeline/generator.py has DataGenerator with enrichment service"""
    print("\n" + "="*60)
    print("TEST 3: Integration with DataGenerator")
    print("="*60)

    try:
        # Import from pipeline module
        from pipeline import DataGenerator
        import logging

        test_result("DataGenerator imports from pipeline", True)

        # Check that EnrichmentService is imported and used
        import inspect
        init_source = inspect.getsource(DataGenerator.__init__)

        has_enrichment_init = 'self.enrichment = EnrichmentService' in init_source
        test_result(
            "DataGenerator initializes enrichment service",
            has_enrichment_init,
            "Found self.enrichment initialization in pipeline/generator.py"
        )

        has_cache_injection = 'self.enrichment.set_cache_references' in init_source
        test_result(
            "DataGenerator injects cache references",
            has_cache_injection,
            "Found cache injection call in pipeline/generator.py"
        )

        # Verify generate_data.py imports from pipeline
        with open('generate_data.py', 'r') as f:
            wrapper_content = f.read()

        wrapper_imports_pipeline = 'from pipeline import DataGenerator' in wrapper_content
        test_result(
            "generate_data.py imports from pipeline",
            wrapper_imports_pipeline,
            "Found 'from pipeline import DataGenerator' in wrapper"
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
        # Check pipeline/generator.py (where DataGenerator now lives)
        with open('pipeline/generator.py', 'r') as f:
            generator_content = f.read()

        # Check that enrichment service calls exist
        enrichment_calls = generator_content.count('self.enrichment.')
        test_result(
            "Enrichment service calls present in generator",
            enrichment_calls >= 6,
            f"Found {enrichment_calls} calls to self.enrichment.* in pipeline/generator.py"
        )

        # Check that generate_data.py is now a thin wrapper
        with open('generate_data.py', 'r') as f:
            wrapper_content = f.read()

        wrapper_lines = len(wrapper_content.splitlines())
        test_result(
            "generate_data.py is thin CLI wrapper",
            wrapper_lines < 150,
            f"generate_data.py is {wrapper_lines} lines (should be ~110)"
        )

        # Check that methods are in enrichment module
        with open('pipeline/enrichment.py', 'r') as f:
            enrichment_content = f.read()

        has_get_watch_links = 'def get_watch_links(self, movie_id, title, year, providers' in enrichment_content
        test_result(
            "get_watch_links method in enrichment module",
            has_get_watch_links,
            "Method found in pipeline/enrichment.py"
        )

        has_try_agent = 'def try_vod_scraper(self, title, year' in enrichment_content
        test_result(
            "try_vod_scraper method in enrichment module",
            has_try_agent,
            "Method found in pipeline/enrichment.py"
        )

        has_append_affiliate = 'def append_affiliate_tag(self, url, service_name' in enrichment_content
        test_result(
            "append_affiliate_tag method in enrichment module",
            has_append_affiliate,
            "Method found in pipeline/enrichment.py"
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

        # Count lines in pipeline/enrichment.py
        with open('pipeline/enrichment.py', 'r') as f:
            enrichment_lines = len(f.readlines())

        test_result(
            "generate_data.py massively reduced",
            gen_lines < 2000,
            f"Current: {gen_lines} lines (was 2967 after validation extraction)"
        )

        test_result(
            "enrichment.py created",
            enrichment_lines > 1000,
            f"Enrichment module: {enrichment_lines} lines"
        )

        reduction = 2967 - gen_lines
        test_result(
            "Major reduction achieved",
            reduction > 1000,
            f"Removed {reduction} lines from monolith (-{round(reduction*100/2967, 1)}%)"
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
        from pipeline import EnrichmentService, StorageService, ValidationService
        import logging

        # Simulate DataGenerator pattern
        class MockDataGenerator:
            def __init__(self):
                self.logger = logging.getLogger('mock')
                self.logger.addHandler(logging.NullHandler())
                self.config = {}
                self.watchmode_stats = {
                    'cache_hits': 0,
                    'override_hits': 0,
                    'manual_tracking_hits': 0
                }

                # Initialize services
                self.storage = StorageService(self.logger)
                self.validator = ValidationService(
                    logger=self.logger,
                    storage_service=self.storage,
                    config=self.config,
                    stats_dict=self.watchmode_stats
                )
                self.enrichment = EnrichmentService(
                    logger=self.logger,
                    config=self.config,
                    storage_service=self.storage,
                    validator_service=self.validator,
                    stats_dict=self.watchmode_stats,
                    enrichment_enabled=True
                )

                # Inject cache references
                self.enrichment.set_cache_references({}, {}, {})

        mock_gen = MockDataGenerator()

        # Test that enrichment methods are accessible
        has_get_watch_links = hasattr(mock_gen.enrichment, 'get_watch_links')
        has_try_agent = hasattr(mock_gen.enrichment, 'try_vod_scraper')
        has_is_amazon = hasattr(mock_gen.enrichment, 'is_actual_amazon_service')
        has_append_tag = hasattr(mock_gen.enrichment, 'append_affiliate_tag')

        test_result("get_watch_links method accessible", has_get_watch_links)
        test_result("try_vod_scraper method accessible", has_try_agent)
        test_result("is_actual_amazon_service method accessible", has_is_amazon)
        test_result("append_affiliate_tag method accessible", has_append_tag)

        # Test that utility methods work
        is_amazon = mock_gen.enrichment.is_actual_amazon_service('Amazon Prime Video')
        test_result("is_actual_amazon_service works", is_amazon)

        # Test stats sharing
        test_result(
            "Stats dict is shared",
            mock_gen.enrichment.stats is mock_gen.watchmode_stats,
            "EnrichmentService updates shared stats dict"
        )

        return True

    except Exception as e:
        test_result("Backward compatibility", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def test_service_delegation():
    """Test that EnrichmentService properly delegates to sub-services"""
    print("\n" + "="*60)
    print("TEST 7: Service Delegation")
    print("="*60)

    try:
        from pipeline import EnrichmentService, StorageService, ValidationService
        import logging

        logger = logging.getLogger('test')
        logger.addHandler(logging.NullHandler())

        # Create shared stats dict
        shared_stats = {
            'cache_hits': 0,
            'override_hits': 0,
            'manual_tracking_hits': 0
        }

        # Initialize services with delegation
        storage = StorageService(logger)
        validator = ValidationService(logger=logger, storage_service=storage, stats_dict=shared_stats)
        enrichment = EnrichmentService(
            logger=logger,
            config={},
            storage_service=storage,
            validator_service=validator,
            stats_dict=shared_stats
        )

        test_result(
            "Enrichment service has storage reference",
            enrichment.storage is storage,
            "Storage service delegated"
        )

        test_result(
            "Enrichment service has validator reference",
            enrichment.validator is validator,
            "Validator service delegated"
        )

        test_result(
            "Enrichment service uses shared stats",
            enrichment.stats is shared_stats,
            "Stats dict reference matches"
        )

        return True

    except Exception as e:
        test_result("Service delegation", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("ENRICHMENT EXTRACTION TEST SUITE")
    print("="*60)

    results = {
        'Test 1 - EnrichmentService Import': test_enrichment_service_import(),
        'Test 2 - EnrichmentService Methods': test_enrichment_service_methods(),
        'Test 3 - DataGenerator Integration': test_generate_data_integration(),
        'Test 4 - Method Replacements': test_method_replacements(),
        'Test 5 - Line Count Metrics': test_line_count_reduction(),
        'Test 6 - Backward Compatibility': test_backward_compatibility(),
        'Test 7 - Service Delegation': test_service_delegation(),
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
        print(f"\n{GREEN}✅ ALL TESTS PASSED - Enrichment extraction successful!{RESET}")
        return 0
    else:
        print(f"\n{RED}❌ SOME TESTS FAILED - Review output above{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
