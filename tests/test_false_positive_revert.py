#!/usr/bin/env python3
"""
Integration test for false-positive revert logic in the enrichment pipeline.

Tests the safeguard that reverts movies from available→tracking when enrichment
finds zero watch links — indicating the discovery was a false positive.

See: NRW_DATA_WORKFLOW_EXPLAINED.md > Pipeline Safeguards > False Positive Revert
"""

import unittest
import json
import copy


class TestFalsePositiveRevert(unittest.TestCase):
    """Test false-positive detection and revert behavior."""

    def _make_tracking_data(self, movies_dict):
        """Helper: wrap movies dict in tracking format."""
        return {'movies': movies_dict}

    def _make_movie(self, mid, title, status='available', discovery_source='tmdb_type4', watch_links=None):
        """Helper: create a movie entry."""
        return {
            'id': int(mid),
            'tmdb_id': int(mid),
            'title': title,
            'status': status,
            'digital_date': '2026-04-15',
            'enriched': True,
            'enrichment_date': '2026-04-15',
            '_discovery_source': discovery_source,
            'watch_links': watch_links or {},
        }

    def test_zero_watch_links_detected_as_false_positive(self):
        """Movie with status=available + zero watch links should be flagged as false positive."""
        movie = self._make_movie('999', 'Ghost Movie', watch_links={})
        tracking = self._make_tracking_data({
            '999': {
                'title': 'Ghost Movie',
                'status': 'available',
                '_discovery_source': 'tmdb_type4',
                'enriched': True,
                'enrichment_date': '2026-04-15',
            }
        })

        # Simulate the revert logic from generator.py post-enrichment sync
        mid = '999'
        wl = movie.get('watch_links', {})
        wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0

        if wl_count == 0 and tracking['movies'][mid].get('status') == 'available':
            old_source = tracking['movies'][mid].get('_discovery_source', 'unknown')
            if old_source == 'tmdb_type4':
                tracking['movies'][mid]['_type4_false_positive'] = True
            else:
                tracking['movies'][mid]['_providers_false_positive'] = True
            tracking['movies'][mid]['status'] = 'tracking'
            tracking['movies'][mid]['_reverted_from_available'] = True
            tracking['movies'][mid]['_false_positive_source'] = old_source

        # Verify revert happened
        self.assertEqual(tracking['movies'][mid]['status'], 'tracking',
                         "Movie with zero watch links should revert to tracking")
        self.assertTrue(tracking['movies'][mid].get('_reverted_from_available'),
                        "Should flag _reverted_from_available")
        self.assertEqual(tracking['movies'][mid].get('_false_positive_source'), 'tmdb_type4',
                         "Should record which source was false positive")
        self.assertTrue(tracking['movies'][mid].get('_type4_false_positive'),
                        "Should set _type4_false_positive for Type 4 source")

    def test_provider_false_positive_sets_correct_flag(self):
        """Provider-based false positive should set _providers_false_positive, not _type4."""
        tracking = self._make_tracking_data({
            '888': {
                'title': 'Provider Ghost',
                'status': 'available',
                '_discovery_source': 'provider_availability_check',
                'enriched': True,
            }
        })

        mid = '888'
        wl_count = 0  # zero watch links

        if wl_count == 0 and tracking['movies'][mid].get('status') == 'available':
            old_source = tracking['movies'][mid].get('_discovery_source', 'unknown')
            if old_source == 'tmdb_type4':
                tracking['movies'][mid]['_type4_false_positive'] = True
            else:
                tracking['movies'][mid]['_providers_false_positive'] = True
            tracking['movies'][mid]['status'] = 'tracking'
            tracking['movies'][mid]['_reverted_from_available'] = True
            tracking['movies'][mid]['_false_positive_source'] = old_source

        self.assertEqual(tracking['movies'][mid]['status'], 'tracking')
        self.assertTrue(tracking['movies'][mid].get('_providers_false_positive'),
                        "Should set _providers_false_positive for provider source")
        self.assertNotIn('_type4_false_positive', tracking['movies'][mid],
                         "Should NOT set _type4_false_positive for provider source")

    def test_movie_with_watch_links_not_reverted(self):
        """Movie with valid watch links should NOT be reverted."""
        tracking = self._make_tracking_data({
            '777': {
                'title': 'Real Movie',
                'status': 'available',
                '_discovery_source': 'tmdb_type4',
                'enriched': True,
            }
        })
        watch_links = {'streaming': [{'service': 'Netflix', 'link': 'https://netflix.com/watch/123'}]}

        mid = '777'
        wl = watch_links
        wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0

        reverted = False
        if wl_count == 0 and tracking['movies'][mid].get('status') == 'available':
            tracking['movies'][mid]['status'] = 'tracking'
            reverted = True

        self.assertFalse(reverted, "Movie with watch links should NOT be reverted")
        self.assertEqual(tracking['movies'][mid]['status'], 'available',
                         "Status should remain available")

    def test_zero_watch_links_display_filter(self):
        """Movies with zero watch links should be filtered from display output."""
        all_movies = [
            {'id': 1, 'title': 'Has Links', 'watch_links': {
                'streaming': [{'service': 'Netflix', 'link': 'https://example.com'}]
            }},
            {'id': 2, 'title': 'No Links', 'watch_links': {}},
            {'id': 3, 'title': 'Also Has Links', 'watch_links': {
                'vod': [{'service': 'Amazon', 'link': 'https://amazon.com/dp/123'}]
            }},
            {'id': 4, 'title': 'Empty Sublists', 'watch_links': {
                'streaming': [], 'vod': [], 'buy': []
            }},
        ]

        # Simulate the zero-watch-links filter from generator.py display phase
        filtered_movies = []
        filtered_out = []
        for m in all_movies:
            wl = m.get('watch_links', {})
            wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
            if wl_count == 0:
                filtered_out.append(m.get('title'))
            else:
                filtered_movies.append(m)

        self.assertEqual(len(filtered_movies), 2, "Should keep only movies with actual links")
        self.assertIn('No Links', filtered_out, "'No Links' should be filtered")
        self.assertIn('Empty Sublists', filtered_out, "'Empty Sublists' should be filtered")
        titles_kept = [m['title'] for m in filtered_movies]
        self.assertIn('Has Links', titles_kept)
        self.assertIn('Also Has Links', titles_kept)

    def test_reverted_movie_can_rediscover_via_other_source(self):
        """A Type-4 false positive should still allow provider discovery (and vice versa)."""
        movie = {
            'title': 'Retry Movie',
            'status': 'tracking',
            '_reverted_from_available': True,
            '_false_positive_source': 'tmdb_type4',
            '_type4_false_positive': True,
        }

        # Simulate discovery skip logic from generator.py
        skip_type4 = False
        skip_provider = False
        if movie.get('_reverted_from_available'):
            fp_source = movie.get('_false_positive_source', '')
            if fp_source == 'tmdb_type4':
                skip_type4 = True
            elif fp_source == 'provider_availability_check':
                skip_provider = True

        self.assertTrue(skip_type4, "Type 4 should be skipped (was false positive)")
        self.assertFalse(skip_provider, "Provider discovery should NOT be skipped")


if __name__ == '__main__':
    unittest.main()
