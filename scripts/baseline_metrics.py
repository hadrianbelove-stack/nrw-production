#!/usr/bin/env python3
"""
Compute 3-day baseline metrics for discovery and newly-digital counts
"""

import json
import os
from datetime import datetime, timedelta

def compute_baseline():
    """Compute and display 3-day baseline metrics"""
    metrics_file = 'metrics/daily.jsonl'

    if not os.path.exists(metrics_file):
        print("❌ No metrics file found at metrics/daily.jsonl")
        print("   Run 'python3 generate_data.py --discover' first to collect data")
        return

    # Read all metrics
    metrics = []
    try:
        with open(metrics_file, 'r') as f:
            for line in f:
                if line.strip():
                    metrics.append(json.loads(line))
    except Exception as e:
        print(f"❌ Error reading metrics file: {e}")
        return

    if not metrics:
        print("❌ No metrics data found")
        return

    print(f"📊 Baseline Metrics Report")
    print("=" * 50)

    # Show all available data
    print(f"Total data points: {len(metrics)}")
    if metrics:
        first_date = metrics[0]['date']
        last_date = metrics[-1]['date']
        print(f"Date range: {first_date} to {last_date}")

    # Compute 3-day baseline if we have enough data
    if len(metrics) >= 3:
        last_3 = metrics[-3:]

        discovery_avg = sum(m['discovered'] for m in last_3) / 3
        newly_digital_avg = sum(m['newly_digital'] for m in last_3) / 3

        print(f"\n📈 3-Day Baseline (last 3 days):")
        print(f"  Discovery average: {discovery_avg:.1f} movies/day")
        print(f"  Newly digital average: {newly_digital_avg:.1f} movies/day")
        print(f"  Based on: {', '.join(m['date'] for m in last_3)}")

        # Show individual daily values
        print(f"\n📅 Daily Breakdown:")
        for metric in last_3:
            print(f"  {metric['date']}: {metric['discovered']} discovered, {metric['newly_digital']} newly digital")
    else:
        print(f"\n⚠️  Need at least 3 days of data for baseline")
        print(f"   Currently have {len(metrics)} day(s)")

    # Show recent trends (last 7 days)
    if len(metrics) >= 2:
        recent = metrics[-min(7, len(metrics)):]
        print(f"\n📊 Recent Trends (last {len(recent)} days):")

        total_discovered = sum(m['discovered'] for m in recent)
        total_newly_digital = sum(m['newly_digital'] for m in recent)

        print(f"  Total discovered: {total_discovered}")
        print(f"  Total newly digital: {total_newly_digital}")
        print(f"  Discovery rate: {total_discovered/len(recent):.1f}/day")
        print(f"  Digital rate: {total_newly_digital/len(recent):.1f}/day")

    # Show current tracking status
    if metrics:
        latest = metrics[-1]
        print(f"\n📋 Current Status (as of {latest['date']}):")
        print(f"  Movies tracking: {latest['total_tracking']}")
        print(f"  Movies available: {latest['total_available']}")
        print(f"  Total in database: {latest['total_tracking'] + latest['total_available']}")

if __name__ == "__main__":
    compute_baseline()