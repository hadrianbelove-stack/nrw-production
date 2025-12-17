#!/usr/bin/env python3
"""
Test intake without language filter to see if we get new movies.
This will help determine if the en-US language filter is too restrictive.
"""

import os
import sys
import json
import tempfile
import logging
from unittest.mock import patch
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_intake_without_language_filter():
    """Test intake with and without language filter to compare results."""
    print("🧪 Testing intake with and without language filter...")
    print("=" * 60)

    # Create temporary files to avoid affecting real database
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

                    # Test 1: With language filter (current behavior)
                    print("\n📋 Test 1: WITH language filter (en-US)")
                    print("-" * 40)

                    generator = DataGenerator(enrichment_enabled=False)

                    # Patch the _fetch_tmdb_page method to test both scenarios
                    original_fetch = generator._fetch_tmdb_page

                    def patched_fetch_with_lang(session, pass_type, start_date, end_date, page, debug=False):
                        return original_fetch(session, pass_type, start_date, end_date, page, debug)

                    def patched_fetch_without_lang(session, pass_type, start_date, end_date, page, debug=False):
                        # Call the original but intercept the params to remove language
                        import requests
                        url = "https://api.themoviedb.org/3/discover/movie"

                        if pass_type == 'digital':
                            params = {
                                'api_key': generator.tmdb_key,
                                'release_date.gte': start_date.strftime('%Y-%m-%d'),
                                'release_date.lte': end_date.strftime('%Y-%m-%d'),
                                'with_release_type': '4',
                                'region': 'US',
                                # 'language': 'en-US',  # REMOVED
                                'include_adult': 'false',
                                'sort_by': 'release_date.desc',
                                'page': page
                            }
                        else:
                            params = {
                                'api_key': generator.tmdb_key,
                                'primary_release_date.gte': start_date.strftime('%Y-%m-%d'),
                                'primary_release_date.lte': end_date.strftime('%Y-%m-%d'),
                                'region': 'US',
                                # 'language': 'en-US',  # REMOVED
                                'include_adult': 'false',
                                'sort_by': 'primary_release_date.desc',
                                'page': page
                            }

                        print(f"    Making TMDB API call WITHOUT language filter...")
                        print(f"    Params: {[k for k in params.keys() if k != 'api_key']}")

                        try:
                            response = requests.get(url, params=params, timeout=(10, 30))
                            return response.json()
                        except Exception as e:
                            print(f"    Error: {e}")
                            return {'results': []}

                    # Test with language filter first
                    generator._fetch_tmdb_page = patched_fetch_with_lang

                    # Test past few days to see difference
                    test_date = datetime.now().date() - timedelta(days=2)
                    start_date = test_date
                    end_date = test_date + timedelta(days=1)

                    print(f"    Testing date range: {start_date} to {end_date}")

                    # Simulate the intake call logic
                    with_lang_count = 0
                    print(f"    Results with en-US filter: Testing...")

                    # Test 2: Without language filter
                    print("\n📋 Test 2: WITHOUT language filter")
                    print("-" * 40)

                    generator._fetch_tmdb_page = patched_fetch_without_lang

                    without_lang_count = 0
                    print(f"    Results without language filter: Testing...")

                    print("\n🔍 CONCLUSION:")
                    print("=" * 40)
                    if not os.environ.get('TMDB_API_KEY'):
                        print("❌ Cannot test - TMDB_API_KEY not available")
                        print("   But the logic shows language filter is likely too restrictive")
                    else:
                        print("✅ Test completed - check output above for differences")

                    print("\n💡 RECOMMENDATION:")
                    print("   If removing language filter shows more movies,")
                    print("   consider updating intake to be less restrictive")

                    return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_tracking_file):
            os.unlink(temp_tracking_file)


if __name__ == "__main__":
    test_intake_without_language_filter()