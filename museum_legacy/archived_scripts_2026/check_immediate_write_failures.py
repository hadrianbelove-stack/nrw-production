#!/usr/bin/env python3
"""
Immediate Write Failures Monitor

This script reads logs/immediate_write_failures.jsonl and provides analysis
of recent failures from the add_movie_to_site_immediately() function.

Usage:
    python scripts/check_immediate_write_failures.py [--last N] [--hours H]

Options:
    --last N    Show last N failures (default: 10)
    --hours H   Show summary for last H hours (default: 24)

Examples:
    python scripts/check_immediate_write_failures.py
    python scripts/check_immediate_write_failures.py --last 5
    python scripts/check_immediate_write_failures.py --hours 48

The script handles missing or empty log files gracefully and provides:
- Recent failure details (timestamp, movie_id, title, error_type)
- Summary counts by error type over specified time window
- Basic statistics on TMDB availability during failures

Reference this script from README_DISCOVERY_ENRICHMENT_FIX.md or
VERIFICATION_COMMANDS.md for operational monitoring.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from collections import Counter, defaultdict


def parse_args():
    parser = argparse.ArgumentParser(
        description='Monitor immediate write failures from JSONL logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--last', '-n',
        type=int,
        default=10,
        help='Show last N failures (default: 10)'
    )
    parser.add_argument(
        '--hours', '-h',
        type=int,
        default=24,
        help='Show summary for last H hours (default: 24)'
    )
    return parser.parse_args()


def load_failures(log_path):
    """Load failures from JSONL file, handle missing/empty files gracefully"""
    if not os.path.exists(log_path):
        return []

    failures = []
    try:
        with open(log_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    failure = json.loads(line)
                    failures.append(failure)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON on line {line_num}: {e}", file=sys.stderr)
                    continue
    except Exception as e:
        print(f"Error reading {log_path}: {e}", file=sys.stderr)
        return []

    return failures


def parse_timestamp(timestamp_str):
    """Parse ISO timestamp, handle various formats gracefully"""
    try:
        # Try parsing with microseconds
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError:
        try:
            # Try without microseconds
            return datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            # Fallback - return None for invalid timestamps
            return None


def print_recent_failures(failures, count):
    """Print details of the last N failures"""
    if not failures:
        print("📊 No immediate write failures recorded")
        return

    # Sort by timestamp (newest first)
    sorted_failures = []
    for failure in failures:
        timestamp = parse_timestamp(failure.get('timestamp', ''))
        if timestamp:
            sorted_failures.append((timestamp, failure))

    sorted_failures.sort(key=lambda x: x[0], reverse=True)

    recent = sorted_failures[:count]

    print(f"📋 Last {len(recent)} immediate write failures:")
    print("=" * 80)

    for i, (timestamp, failure) in enumerate(recent, 1):
        movie_id = failure.get('movie_id', 'unknown')
        title = failure.get('title', 'Unknown Title')
        error_type = failure.get('error_type', 'UnknownError')
        error_msg = failure.get('error_message', '')
        tmdb_available = failure.get('tmdb_available', False)
        data_exists = failure.get('data_json_exists', False)

        print(f"{i:2d}. {timestamp.strftime('%Y-%m-%d %H:%M:%S')} | ID: {movie_id}")
        print(f"    Title: {title}")
        print(f"    Error: {error_type}")
        if error_msg and len(error_msg) < 100:
            print(f"    Message: {error_msg}")
        print(f"    TMDB: {'✓' if tmdb_available else '✗'} | data.json: {'✓' if data_exists else '✗'}")
        if i < len(recent):
            print()


def print_summary(failures, hours):
    """Print summary statistics for failures in the last N hours"""
    if not failures:
        return

    cutoff_time = datetime.now() - timedelta(hours=hours)
    recent_failures = []

    for failure in failures:
        timestamp = parse_timestamp(failure.get('timestamp', ''))
        if timestamp and timestamp >= cutoff_time:
            recent_failures.append(failure)

    if not recent_failures:
        print(f"📈 No failures in the last {hours} hours")
        return

    print(f"📈 Summary for last {hours} hours ({len(recent_failures)} failures):")
    print("=" * 80)

    # Error type breakdown
    error_types = Counter(f.get('error_type', 'Unknown') for f in recent_failures)
    print("Error Types:")
    for error_type, count in error_types.most_common():
        print(f"  {error_type}: {count}")

    print()

    # TMDB availability stats
    tmdb_available = sum(1 for f in recent_failures if f.get('tmdb_available', False))
    tmdb_unavailable = len(recent_failures) - tmdb_available

    print("TMDB Availability during failures:")
    print(f"  Available: {tmdb_available}")
    print(f"  Unavailable: {tmdb_unavailable}")

    print()

    # data.json existence stats
    data_exists = sum(1 for f in recent_failures if f.get('data_json_exists', False))
    data_missing = len(recent_failures) - data_exists

    print("data.json existence during failures:")
    print(f"  Exists: {data_exists}")
    print(f"  Missing: {data_missing}")

    # Hourly breakdown if we have enough data
    if hours >= 24 and len(recent_failures) >= 3:
        print()
        hourly_counts = defaultdict(int)
        for failure in recent_failures:
            timestamp = parse_timestamp(failure.get('timestamp', ''))
            if timestamp:
                hour_key = timestamp.strftime('%Y-%m-%d %H:00')
                hourly_counts[hour_key] += 1

        if hourly_counts:
            print("Hourly breakdown:")
            for hour in sorted(hourly_counts.keys())[-12:]:  # Last 12 hours
                print(f"  {hour}: {hourly_counts[hour]}")


def main():
    args = parse_args()
    log_path = 'logs/immediate_write_failures.jsonl'

    print("🔍 Immediate Write Failures Monitor")
    print(f"📂 Reading from: {log_path}")
    print()

    failures = load_failures(log_path)

    if not failures:
        print("✅ No immediate write failures found!")
        print()
        print("This could mean:")
        print("  • No failures have occurred yet")
        print("  • The log file doesn't exist or is empty")
        print("  • There was an issue reading the log file")
        return

    print_recent_failures(failures, args.last)
    print()
    print_summary(failures, args.hours)


if __name__ == '__main__':
    main()