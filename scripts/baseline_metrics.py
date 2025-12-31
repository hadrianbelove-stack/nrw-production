#!/usr/bin/env python3
"""
Compute 3-day baseline metrics for intake and newly-digital counts
"""

import json
import os
from datetime import datetime, timedelta

def compute_baseline():
    """Compute and display 3-day baseline metrics"""
    metrics_file = 'metrics/daily.jsonl'

    if not os.path.exists(metrics_file):
        print("❌ No metrics file found at metrics/daily.jsonl")
        print("   Run 'python3 daily_orchestrator.py' first to collect data")
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

    # Helper functions for legacy key compatibility
    def get_intake_count(m):
        """Handle legacy key names: intaked_today > discovered_today > discovered"""
        return m.get('intaked_today') or m.get('discovered_today') or m.get('discovered') or 0
    def get_transition_count(m):
        """Handle legacy key names: transitions > newly_digital"""
        return m.get('transitions') or m.get('newly_digital') or 0

    # Compute 3-day baseline if we have enough data
    if len(metrics) >= 3:
        last_3 = metrics[-3:]

        intake_avg = sum(get_intake_count(m) for m in last_3) / 3
        newly_digital_avg = sum(get_transition_count(m) for m in last_3) / 3

        print(f"\n📈 3-Day Baseline (last 3 days):")
        print(f"  Intake average: {intake_avg:.1f} movies/day")
        print(f"  Newly digital average: {newly_digital_avg:.1f} movies/day")
        print(f"  Based on: {', '.join(m['date'] for m in last_3)}")

        # Show individual daily values
        print(f"\n📅 Daily Breakdown:")
        for metric in last_3:
            print(f"  {metric['date']}: {get_intake_count(metric)} intaked, {get_transition_count(metric)} newly digital")
    else:
        print(f"\n⚠️  Need at least 3 days of data for baseline")
        print(f"   Currently have {len(metrics)} day(s)")

    # Show recent trends (last 7 days)
    if len(metrics) >= 2:
        recent = metrics[-min(7, len(metrics)):]
        print(f"\n📊 Recent Trends (last {len(recent)} days):")

        total_intaked = sum(get_intake_count(m) for m in recent)
        total_newly_digital = sum(get_transition_count(m) for m in recent)

        print(f"  Total intaked: {total_intaked}")
        print(f"  Total newly digital: {total_newly_digital}")
        print(f"  Intake rate: {total_intaked/len(recent):.1f}/day")
        print(f"  Digital rate: {total_newly_digital/len(recent):.1f}/day")

    # Show current tracking status (optional fields)
    if metrics:
        latest = metrics[-1]
        print(f"\n📋 Current Status (as of {latest['date']}):")
        total_tracking = latest.get('total_tracking')
        total_available = latest.get('total_available')
        if total_tracking is not None and total_available is not None:
            print(f"  Movies tracking: {total_tracking}")
            print(f"  Movies available: {total_available}")
            print(f"  Total in database: {total_tracking + total_available}")
        else:
            print(f"  Tracking status not available in current metrics format")

if __name__ == "__main__":
    compute_baseline()