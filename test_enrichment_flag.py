#!/usr/bin/env python3
"""
Test enrichment_enabled flag behavior to prevent timing bugs.

Tests that the enrichment_enabled flag is properly propagated from DataGenerator
to EnrichmentService and prevents expensive operations during intake/discovery.
"""

import os
import sys
import json
import tempfile
import logging
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_enrichment_disabled():
    """Test that DataGenerator(enrichment_enabled=False) prevents agent scraper initialization."""
    print("🧪 Testing enrichment_enabled=False behavior...")

    # Create temporary files to avoid TMDB API key requirement
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({'movies': {}}, f)
        temp_tracking_file = f.name

    try:
        # Mock file paths and TMDB key
        with patch.dict(os.environ, {'TMDB_API_KEY': 'test_key'}):
            with patch('os.path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('builtins.open', side_effect=lambda path, *args, **kwargs:
                          open(temp_tracking_file, *args, **kwargs) if 'movie_tracking.json' in path
                          else open('/dev/null', *args, **kwargs)):

                    from pipeline.generator import DataGenerator

                    # Test with enrichment disabled
                    generator = DataGenerator(enrichment_enabled=False)

                    # Verify the flag is set correctly
                    assert generator.enrichment_enabled == False, f"Expected enrichment_enabled=False, got {generator.enrichment_enabled}"
                    assert generator.enrichment.enrichment_enabled == False, f"Expected enrichment service enrichment_enabled=False, got {generator.enrichment.enrichment_enabled}"

                    # Try to trigger agent scraper initialization
                    generator.enrichment._init_vod_scraper()

                    # Verify agent scraper was NOT initialized (should be False, not an object)
                    assert generator.enrichment.vod_scraper == False, f"Expected vod_scraper=False when enrichment disabled, got {generator.enrichment.vod_scraper}"

                    print("✅ enrichment_enabled=False correctly prevents agent scraper initialization")
                    return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_tracking_file):
            os.unlink(temp_tracking_file)


def test_enrichment_enabled():
    """Test that DataGenerator(enrichment_enabled=True) allows agent scraper initialization."""
    print("🧪 Testing enrichment_enabled=True behavior...")

    # Create temporary files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({'movies': {}}, f)
        temp_tracking_file = f.name

    try:
        # Mock file paths and TMDB key
        with patch.dict(os.environ, {'TMDB_API_KEY': 'test_key'}):
            with patch('os.path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('builtins.open', side_effect=lambda path, *args, **kwargs:
                          open(temp_tracking_file, *args, **kwargs) if 'movie_tracking.json' in path
                          else open('/dev/null', *args, **kwargs)):

                    from pipeline.generator import DataGenerator

                    # Test with enrichment enabled
                    generator = DataGenerator(enrichment_enabled=True)

                    # Verify the flag is set correctly
                    assert generator.enrichment_enabled == True, f"Expected enrichment_enabled=True, got {generator.enrichment_enabled}"
                    assert generator.enrichment.enrichment_enabled == True, f"Expected enrichment service enrichment_enabled=True, got {generator.enrichment.enrichment_enabled}"

                    # Mock the AgentLinkScraper to avoid actual browser initialization
                    mock_scraper = MagicMock()
                    with patch('pipeline.enrichment.AgentLinkScraper', return_value=mock_scraper):
                        # Try to trigger agent scraper initialization
                        generator.enrichment._init_vod_scraper()

                        # Verify agent scraper WAS initialized (should be the mock object)
                        assert generator.enrichment.vod_scraper == mock_scraper, f"Expected vod_scraper to be initialized when enrichment enabled, got {generator.enrichment.vod_scraper}"

                    print("✅ enrichment_enabled=True correctly allows agent scraper initialization")
                    return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_tracking_file):
            os.unlink(temp_tracking_file)


def test_constructor_injection():
    """Test that the enrichment flag is properly injected at construction time."""
    print("🧪 Testing constructor injection timing...")

    # Create temporary files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({'movies': {}}, f)
        temp_tracking_file = f.name

    try:
        # Mock file paths and TMDB key
        with patch.dict(os.environ, {'TMDB_API_KEY': 'test_key'}):
            with patch('os.path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('builtins.open', side_effect=lambda path, *args, **kwargs:
                          open(temp_tracking_file, *args, **kwargs) if 'movie_tracking.json' in path
                          else open('/dev/null', *args, **kwargs)):

                    from pipeline.generator import DataGenerator

                    # Test that both generator and enrichment service have the same flag from construction
                    generator_false = DataGenerator(enrichment_enabled=False)
                    generator_true = DataGenerator(enrichment_enabled=True)

                    # Verify flags match between generator and enrichment service
                    assert generator_false.enrichment_enabled == generator_false.enrichment.enrichment_enabled, \
                        "Generator and EnrichmentService flags should match for enrichment_enabled=False"

                    assert generator_true.enrichment_enabled == generator_true.enrichment.enrichment_enabled, \
                        "Generator and EnrichmentService flags should match for enrichment_enabled=True"

                    print("✅ Constructor injection properly synchronizes flags")
                    return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_tracking_file):
            os.unlink(temp_tracking_file)


def main():
    """Run all enrichment flag tests."""
    print("🚀 Running enrichment_enabled flag tests...")
    print("=" * 50)

    tests = [
        ("Enrichment Disabled Test", test_enrichment_disabled),
        ("Enrichment Enabled Test", test_enrichment_enabled),
        ("Constructor Injection Test", test_constructor_injection),
    ]

    results = {}
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        results[test_name] = test_func()

    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Enrichment flag behavior is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the enrichment flag implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)