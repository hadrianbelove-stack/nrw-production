#!/usr/bin/env python3
"""Health check for NRW system"""

import json
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse

def validate_watch_links_data(data_file='data.json'):
    """Validate watch links in data.json and return validation statistics

    Returns:
        dict: {'total_movies': int, 'validation_warnings': int, 'validation_passes': int, 'failure_rate': float}
    """
    if not os.path.exists(data_file):
        return {'total_movies': 0, 'validation_warnings': 0, 'validation_passes': 0, 'failure_rate': 0.0}

    with open(data_file, 'r') as f:
        data = json.load(f)

    movies = data.get('movies', [])
    total_movies = len(movies)
    validation_warnings = 0
    validation_passes = 0

    valid_categories = ['streaming', 'rent', 'buy']

    for movie in movies:
        watch_links = movie.get('watch_links', {})
        movie_title = movie.get('title', 'Unknown')
        had_warnings = False

        for category, category_data in watch_links.items():
            # Category validation
            if category not in valid_categories:
                had_warnings = True
                continue

            # Structure validation
            if not isinstance(category_data, dict):
                had_warnings = True
                continue

            if 'service' not in category_data or 'link' not in category_data:
                had_warnings = True
                continue

            # Service validation
            if not isinstance(category_data['service'], str) or not category_data['service'].strip():
                had_warnings = True
                continue

            # Link validation
            link = category_data['link']
            if link is not None:
                if not isinstance(link, str):
                    had_warnings = True
                    continue

                try:
                    parsed = urlparse(link)
                    if not parsed.scheme or parsed.scheme not in ['http', 'https']:
                        had_warnings = True
                        continue
                    if not parsed.netloc:
                        had_warnings = True
                        continue
                except Exception:
                    had_warnings = True
                    continue

        if had_warnings:
            validation_warnings += 1
        else:
            validation_passes += 1

    failure_rate = (validation_warnings / total_movies * 100) if total_movies > 0 else 0.0

    return {
        'total_movies': total_movies,
        'validation_warnings': validation_warnings,
        'validation_passes': validation_passes,
        'failure_rate': failure_rate
    }

def check_system_health():
    issues = []
    
    # Check tracking database exists and is recent
    if not os.path.exists('movie_tracking.json'):
        issues.append("❌ No tracking database found")
    else:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)
            last_update = datetime.fromisoformat(db.get('last_update', '2000-01-01'))
            if (datetime.now() - last_update).days > 2:
                issues.append(f"⚠️ Database stale: last updated {last_update}")
    
    # Check data.json exists and has content
    if not os.path.exists('data.json'):
        issues.append("❌ No display data found")
    else:
        with open('data.json', 'r') as f:
            data = json.load(f)
            if len(data.get('movies', [])) < 10:
                issues.append(f"⚠️ Only {len(data['movies'])} movies in display")
    
    # Check cache directory
    if not os.path.exists('cache'):
        issues.append("❌ Cache directory missing")

    # Check validation failure rates
    validation_stats = validate_watch_links_data()
    VALIDATION_FAILURE_THRESHOLD = 5.0  # 5% threshold

    if validation_stats['total_movies'] > 0:
        if validation_stats['failure_rate'] > VALIDATION_FAILURE_THRESHOLD:
            issues.append(f"❌ High validation failure rate: {validation_stats['failure_rate']:.1f}% "
                         f"({validation_stats['validation_warnings']}/{validation_stats['total_movies']} movies)")
        elif validation_stats['validation_warnings'] > 0:
            issues.append(f"⚠️ Validation warnings: {validation_stats['failure_rate']:.1f}% "
                         f"({validation_stats['validation_warnings']}/{validation_stats['total_movies']} movies)")

    # Determine if we should fail CI
    critical_failure = any("❌" in issue for issue in issues)

    if issues:
        print("System Health Issues:")
        for issue in issues:
            print(f"  {issue}")
        return not critical_failure  # Return False for critical failures
    else:
        print("✅ System healthy")
        return True

if __name__ == "__main__":
    healthy = check_system_health()
    if not healthy:
        sys.exit(1)  # Exit with error code for CI