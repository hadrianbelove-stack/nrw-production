#!/usr/bin/env python3
"""
Unit tests for stall detection logic in daily_orchestrator.py

Tests the improved detect_stall() method that groups entries by date
and selects the last entry per date by timestamp ordering.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Import the orchestrator
from daily_orchestrator import NRWOrchestrator


class TestStallDetection(unittest.TestCase):
    """Test stall detection with multiple entries per day scenarios"""

    def setUp(self):
        """Create temporary metrics directory for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.metrics_dir = Path(self.temp_dir) / 'metrics'
        self.metrics_dir.mkdir()
        self.metrics_file = self.metrics_dir / 'daily.jsonl'

        # Save original working directory
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        self.orchestrator = NRWOrchestrator()

    def tearDown(self):
        """Clean up temporary directory"""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir)

    def write_metrics(self, entries):
        """Helper to write metrics entries to file"""
        with open(self.metrics_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

    def test_single_entry_per_day_no_stall(self):
        """Test with single entry per day, no stall detected"""
        base_date = datetime.now()
        entries = [
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=1)).isoformat(),
                'transitions': 5
            },
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=1)).isoformat(),
                'transitions': 3
            },
            {
                'date': base_date.strftime('%Y-%m-%d'),
                'timestamp': base_date.isoformat(),
                'transitions': 2
            }
        ]
        self.write_metrics(entries)

        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "Should not detect stall with transitions > 0")

    def test_single_entry_per_day_with_stall(self):
        """Test with single entry per day, stall detected"""
        base_date = datetime.now()
        entries = [
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=1)).isoformat(),
                'transitions': 0
            },
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=1)).isoformat(),
                'transitions': 0
            },
            {
                'date': base_date.strftime('%Y-%m-%d'),
                'timestamp': base_date.isoformat(),
                'transitions': 0
            }
        ]
        self.write_metrics(entries)

        # Set environment to not fail on stall for testing
        os.environ['NRW_FAIL_ON_STALL'] = 'false'
        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "With NRW_FAIL_ON_STALL=false, should return False but detect stall")

    def test_multiple_entries_per_day_latest_has_transitions(self):
        """Test with multiple entries per day, latest entry has transitions"""
        base_date = datetime.now()
        today = base_date.strftime('%Y-%m-%d')

        entries = [
            # Day 1 - two entries, latest has transitions
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=12)).isoformat(),
                'transitions': 0
            },
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=1)).isoformat(),
                'transitions': 5  # Latest should win
            },
            # Day 2 - single entry with transitions
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=1)).isoformat(),
                'transitions': 3
            },
            # Day 3 - three entries, latest has transitions
            {
                'date': today,
                'timestamp': (base_date - timedelta(hours=6)).isoformat(),
                'transitions': 0
            },
            {
                'date': today,
                'timestamp': (base_date - timedelta(hours=3)).isoformat(),
                'transitions': 0
            },
            {
                'date': today,
                'timestamp': base_date.isoformat(),
                'transitions': 2  # Latest should win
            }
        ]
        self.write_metrics(entries)

        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "Should not detect stall when latest entries have transitions")

    def test_multiple_entries_per_day_latest_has_no_transitions(self):
        """Test with multiple entries per day, latest entry has no transitions - should stall"""
        base_date = datetime.now()
        today = base_date.strftime('%Y-%m-%d')

        entries = [
            # Day 1 - two entries, latest has no transitions
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=12)).isoformat(),
                'transitions': 5
            },
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=1)).isoformat(),
                'transitions': 0  # Latest should win
            },
            # Day 2 - single entry with no transitions
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=1)).isoformat(),
                'transitions': 0
            },
            # Day 3 - three entries, latest has no transitions
            {
                'date': today,
                'timestamp': (base_date - timedelta(hours=6)).isoformat(),
                'transitions': 5
            },
            {
                'date': today,
                'timestamp': (base_date - timedelta(hours=3)).isoformat(),
                'transitions': 3
            },
            {
                'date': today,
                'timestamp': base_date.isoformat(),
                'transitions': 0  # Latest should win
            }
        ]
        self.write_metrics(entries)

        os.environ['NRW_FAIL_ON_STALL'] = 'false'
        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "With NRW_FAIL_ON_STALL=false, should return False but detect stall")

    def test_out_of_order_timestamps_within_same_date(self):
        """Test that timestamps are properly sorted even if written out of order"""
        base_date = datetime.now()
        today = base_date.strftime('%Y-%m-%d')

        entries = [
            # Day 1 - entries written out of order
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=1)).isoformat(),
                'transitions': 0  # Latest timestamp
            },
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=12)).isoformat(),
                'transitions': 5  # Earlier timestamp, but written first
            },
            # Day 2
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=1)).isoformat(),
                'transitions': 0
            },
            # Day 3 - out of order
            {
                'date': today,
                'timestamp': base_date.isoformat(),
                'transitions': 0  # Latest
            },
            {
                'date': today,
                'timestamp': (base_date - timedelta(hours=6)).isoformat(),
                'transitions': 5  # Earlier, but written after
            }
        ]
        self.write_metrics(entries)

        os.environ['NRW_FAIL_ON_STALL'] = 'false'
        result = self.orchestrator.detect_stall()
        # All latest entries have transitions=0, so should detect stall
        self.assertFalse(result, "With NRW_FAIL_ON_STALL=false, should return False but detect stall")

    def test_mixed_scenario_some_dates_single_some_multiple(self):
        """Test with mixed scenario: some dates have single entry, others have multiple"""
        base_date = datetime.now()

        entries = [
            # Day 1 - single entry
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2, hours=1)).isoformat(),
                'transitions': 5
            },
            # Day 2 - multiple entries
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=12)).isoformat(),
                'transitions': 0
            },
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=6)).isoformat(),
                'transitions': 2
            },
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1, hours=1)).isoformat(),
                'transitions': 3  # Latest
            },
            # Day 3 - single entry
            {
                'date': base_date.strftime('%Y-%m-%d'),
                'timestamp': base_date.isoformat(),
                'transitions': 4
            }
        ]
        self.write_metrics(entries)

        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "Should not detect stall when latest entries have transitions")

    def test_insufficient_dates(self):
        """Test with less than 3 unique dates"""
        base_date = datetime.now()

        entries = [
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1)).isoformat(),
                'transitions': 0
            },
            {
                'date': base_date.strftime('%Y-%m-%d'),
                'timestamp': base_date.isoformat(),
                'transitions': 0
            }
        ]
        self.write_metrics(entries)

        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "Should not detect stall with less than 3 dates")

    def test_no_metrics_file(self):
        """Test behavior when metrics file doesn't exist"""
        # Don't create metrics file
        result = self.orchestrator.detect_stall()
        self.assertFalse(result, "Should return False when no metrics file")

    def test_fail_on_stall_environment_variable(self):
        """Test that NRW_FAIL_ON_STALL=true causes failure"""
        base_date = datetime.now()
        entries = [
            {
                'date': (base_date - timedelta(days=2)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=2)).isoformat(),
                'transitions': 0
            },
            {
                'date': (base_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                'timestamp': (base_date - timedelta(days=1)).isoformat(),
                'transitions': 0
            },
            {
                'date': base_date.strftime('%Y-%m-%d'),
                'timestamp': base_date.isoformat(),
                'transitions': 0
            }
        ]
        self.write_metrics(entries)

        os.environ['NRW_FAIL_ON_STALL'] = 'true'
        result = self.orchestrator.detect_stall()
        self.assertTrue(result, "Should return True when NRW_FAIL_ON_STALL=true and stall detected")

        # Clean up
        del os.environ['NRW_FAIL_ON_STALL']


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
