#!/usr/bin/env python3
"""Batch enrichment script to avoid memory issues"""
import sys
import subprocess
import json

def get_unenriched_count():
    """Count movies that need enrichment"""
    with open('enrichment_state.json') as f:
        enriched = json.load(f)
    with open('movie_tracking.json') as f:
        tracking = json.load(f)

    enriched_ids = set(enriched.keys())
    needs_enrichment = [
        mid for mid, movie in tracking['movies'].items()
        if movie['status'] == 'available' and mid not in enriched_ids
    ]
    return len(needs_enrichment)

def run_batch(batch_size=20):
    """Run one batch of enrichment"""
    print(f"\n{'='*60}")
    print(f"Running batch enrichment (max {batch_size} movies)")
    print(f"{'='*60}\n")

    # Run generate_data.py which will enrich unenriched movies
    result = subprocess.run(
        ['python3', 'generate_data.py'],
        capture_output=False,
        text=True
    )

    return result.returncode == 0

if __name__ == '__main__':
    batch_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    remaining = get_unenriched_count()
    print(f"Batch #{batch_num}: {remaining} movies remaining to enrich")

    if remaining == 0:
        print("✅ All movies enriched!")
        sys.exit(0)

    success = run_batch(batch_size)

    if success:
        new_remaining = get_unenriched_count()
        enriched = remaining - new_remaining
        print(f"\n✅ Batch #{batch_num} complete: enriched {enriched} movies")
        print(f"📊 Remaining: {new_remaining} movies")
    else:
        print(f"\n❌ Batch #{batch_num} failed")
        sys.exit(1)
