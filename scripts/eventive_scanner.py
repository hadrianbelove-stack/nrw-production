#!/usr/bin/env python3
"""
Eventive Virtual Screening Scanner — Standalone Report

Scans Eventive's festival directory for active virtual screenings,
cross-references against NRW tracking/wall movies, and prints a report.

Report-only — does NOT modify cache or tracking files.
For pipeline integration (auto-caching), use: python3 generate_data.py --scan-eventive

Usage:
    python3 scripts/eventive_scanner.py
"""

import json
import os
import sys
from datetime import datetime

# Add project root to path so pipeline imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.eventive import (
    scan_all_festivals,
    build_title_indexes,
    match_film,
    format_date,
)


def load_nrw_data():
    """Load tracking and wall data for matching."""
    from pipeline.tracking_db import get_tracking_db
    tracking_movies = get_tracking_db().load_all().get('movies', {})

    wall_movies = []
    if os.path.exists('data.json'):
        with open('data.json') as f:
            data = json.load(f)
        wall_movies = data.get('movies', []) if isinstance(data, dict) else data

    return tracking_movies, wall_movies


def main():
    print("=" * 70)
    print("EVENTIVE VIRTUAL SCREENING SCANNER")
    print("=" * 70)
    print()

    # Load NRW data
    tracking_movies, wall_movies = load_nrw_data()
    tier1_index, tier2_index = build_title_indexes(tracking_movies, wall_movies)
    print(f"NRW data loaded: {len(tracking_movies)} tracking, {len(wall_movies)} on wall")
    print()

    # Scan all festivals
    try:
        scan_result = scan_all_festivals()
    except Exception as e:
        print(f"ERROR: Scan failed: {e}")
        return

    unique_films = scan_result['films']
    stats = scan_result['stats']

    # Match against NRW
    tracking_matches = []
    wall_matches = []
    unmatched = []

    for film in unique_films:
        match = match_film(film, tier1_index, tier2_index)
        if match:
            for mid, orig_title, source, status in match['matches']:
                entry = {
                    'movie_id': mid,
                    'nrw_title': orig_title,
                    'eventive_title': film['name'],
                    'festival': film.get('festival_name', film['slug']),
                    'link': film['link'],
                    'start': film.get('start_time', ''),
                    'end': film.get('end_time', ''),
                    'status': film['status'],
                    'match_tier': match['tier'],
                    'nrw_status': status,
                }
                if source == 'wall':
                    wall_matches.append(entry)
                else:
                    tracking_matches.append(entry)
        else:
            unmatched.append({
                'eventive_title': film['name'],
                'festival': film.get('festival_name', film['slug']),
                'link': film['link'],
                'start': film.get('start_time', ''),
                'end': film.get('end_time', ''),
                'status': film['status'],
            })

    # -----------------------------------------------------------------------
    # Print Report
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("SCAN RESULTS")
    print("=" * 70)

    # Section 1: Tracking matches
    print(f"\n{'─' * 70}")
    print(f"MATCHES IN NRW TRACKING — {len(tracking_matches)} films")
    print(f"{'─' * 70}")
    if tracking_matches:
        for m in sorted(tracking_matches, key=lambda x: x['festival']):
            status_tag = f"[{m['status'].upper()}]"
            tier_tag = f"(tier {m['match_tier']})" if m['match_tier'] > 1 else ""
            print(f"  {m['nrw_title']:<45} {status_tag:<10} {tier_tag}")
            print(f"    Festival: {m['festival']}")
            print(f"    Link: {m['link']}")
            print(f"    Dates: {format_date(m['start'])} — {format_date(m['end'])}")
            print(f"    TMDB ID: {m['movie_id']} | NRW status: {m['nrw_status']}")
            print()
    else:
        print("  None")

    # Section 2: Wall matches
    print(f"\n{'─' * 70}")
    print(f"MATCHES ALREADY ON WALL — {len(wall_matches)} films")
    print(f"{'─' * 70}")
    if wall_matches:
        for m in sorted(wall_matches, key=lambda x: x['festival']):
            status_tag = f"[{m['status'].upper()}]"
            print(f"  {m['nrw_title']:<45} {status_tag}")
            print(f"    Festival: {m['festival']}")
            print(f"    Link: {m['link']}")
            print(f"    Dates: {format_date(m['start'])} — {format_date(m['end'])}")
            print()
    else:
        print("  None")

    # Section 3: Unmatched
    print(f"\n{'─' * 70}")
    print(f"UNMATCHED ACTIVE FILMS (not in NRW) — {len(unmatched)} films")
    print(f"{'─' * 70}")
    if unmatched:
        by_festival = {}
        for u in unmatched:
            by_festival.setdefault(u['festival'], []).append(u)
        for fest in sorted(by_festival.keys()):
            films_list = by_festival[fest]
            print(f"\n  {fest} ({len(films_list)} films):")
            for u in sorted(films_list, key=lambda x: x['eventive_title']):
                status_tag = f"[{u['status'].upper()}]"
                dates = f"{format_date(u['start'])} — {format_date(u['end'])}"
                print(f"    {u['eventive_title']:<40} {status_tag:<10} {dates}")
    else:
        print("  None")

    # Section 4: Summary
    print(f"\n{'─' * 70}")
    print("SUMMARY")
    print(f"{'─' * 70}")
    print(f"  Festivals scanned:     {stats['festivals_scanned']}")
    print(f"  Festivals with films:  {stats['festivals_with_films']}")
    print(f"  Festivals failed:      {stats['festivals_failed']}")
    print(f"  Total films indexed:   {stats['total_films_indexed']}")
    print(f"  Expired (filtered):    {stats['expired_filtered']}")
    print(f"  Unique active films:   {stats['unique_active']}")
    print(f"  Matched (tracking):    {len(tracking_matches)}")
    print(f"  Matched (wall):        {len(wall_matches)}")
    print(f"  Unmatched:             {len(unmatched)}")

    # Save results to metrics
    results = {
        'timestamp': datetime.now().isoformat(),
        'operation': 'eventive_scan',
        'stats': {
            **stats,
            'tracking_matches': len(tracking_matches),
            'wall_matches': len(wall_matches),
            'unmatched': len(unmatched),
        },
        'tracking_matches': tracking_matches,
        'wall_matches': wall_matches,
        'unmatched_sample': unmatched[:50],
    }

    metrics_path = 'metrics/eventive_scan_run.json'
    os.makedirs('metrics', exist_ok=True)
    with open(metrics_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Full results saved to {metrics_path}")
    print("=" * 70)


if __name__ == '__main__':
    main()
