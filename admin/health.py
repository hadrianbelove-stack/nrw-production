"""Admin panel health status and delta summary."""

import os
import json
from datetime import datetime
from typing import Optional

from admin.config import HEALTH_METRICS_FILE, DATA_FILE, FEATURED_FILE
from admin.logging_setup import logger
from admin.utils import load_json


def load_health_status() -> Optional[dict]:
    """Load last run health status for admin banner."""
    try:
        if os.path.exists(HEALTH_METRICS_FILE):
            with open(HEALTH_METRICS_FILE, 'r') as f:
                data = json.load(f)

            # Parse timestamp
            timestamp = data.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%b %d, %I:%M %p')
            except:
                formatted_time = timestamp[:16] if timestamp else 'Unknown'

            # Determine status
            failures = data.get('failures', [])
            warnings = data.get('warnings', [])
            health_issues = data.get('health_issues', [])
            overall_success = data.get('overall_success', True)

            # Build status
            if failures:
                status = 'error'
                status_text = f'Completed with {len(failures)} error(s)'
                status_emoji = '\U0001f534'
            elif warnings or health_issues:
                status = 'warning'
                status_text = f'Completed with {len(warnings) + len(health_issues)} warning(s)'
                status_emoji = '\U0001f7e1'
            elif overall_success:
                status = 'success'
                status_text = 'Completed successfully'
                status_emoji = '\U0001f7e2'
            else:
                status = 'error'
                status_text = 'Failed'
                status_emoji = '\U0001f534'

            # Build copyable details
            details_lines = []
            details_lines.append(f"NRW Health Report - {formatted_time}")
            details_lines.append(f"Status: {status_text}")
            details_lines.append("")

            # Add phase info
            phases = data.get('phases', [])
            for phase in phases:
                phase_status = '\u2705' if phase.get('success') else '\u274c'
                details_lines.append(f"{phase_status} {phase.get('name', 'Unknown phase')}")

            # Add failures
            if failures:
                details_lines.append("")
                details_lines.append("FAILURES:")
                for f in failures:
                    details_lines.append(f"  - {f.get('phase', 'Unknown')}: {f.get('message', 'No details')}")

            # Add warnings
            if warnings:
                details_lines.append("")
                details_lines.append("WARNINGS:")
                for w in warnings:
                    details_lines.append(f"  - {w}")

            # Add health issues
            if health_issues:
                details_lines.append("")
                details_lines.append("HEALTH ISSUES:")
                for h in health_issues:
                    details_lines.append(f"  - {h}")

            # Add data quality summary
            dq = data.get('data_quality', {})
            if dq:
                details_lines.append("")
                details_lines.append(f"Data: {dq.get('available', 0)} available, {dq.get('data_movies', 0)} on site")

            return {
                'status': status,
                'status_emoji': status_emoji,
                'status_text': status_text,
                'timestamp': formatted_time,
                'failure_count': len(failures),
                'warning_count': len(warnings) + len(health_issues),
                'details': '\n'.join(details_lines),
                'has_issues': bool(failures or warnings or health_issues)
            }
    except Exception as e:
        pass

    return None


def compute_delta_summary() -> dict:
    """Compute delta summary for change tracking.

    NOTE: This function supports the /delta-summary endpoint, which is staged for
    a future Operations/Tools tab in the admin panel. See IMPLEMENTATION_ROADMAP.md
    Phase 2 for planned maintenance features (manual full regen, RT score refresh,
    link rebuilding, etc.). Currently unused but intentionally preserved.

    Returns:
        Dictionary with counts of various changes and issues,
        including count of films released (films with provider data found)
    """
    featured = load_json(FEATURED_FILE, [])
    ordering = load_json('admin/ordering.json', [])

    # Load current data to analyze for issues
    data = load_json(DATA_FILE, {})

    # Handle different data shapes from data.json
    if data and isinstance(data, dict) and 'movies' in data and isinstance(data['movies'], list):
        movies_list = data['movies']
    elif isinstance(data, list):
        movies_list = data
    else:
        movies_list = []

    # Count all films we've found providers for
    # A "released" film has both digital_date (date we found providers) AND provider data
    # Note: digital_date is our custom field (date we discovered availability), not from TMDB API
    new_films_released = sum(
        1 for movie in movies_list
        if movie.get('digital_date')
        and movie.get('providers')
    )

    # Count issues by type
    issues = {
        'missing_rt': 0,
        'missing_trailer': 0,
        'missing_stream_link': 0,
        'missing_rent_link': 0,
        'missing_buy_link': 0
    }

    for movie in movies_list:
        # Check for missing RT score
        if not movie.get('rt_score'):
            issues['missing_rt'] += 1

        # Check for missing trailer
        if not movie.get('links', {}).get('trailer'):
            issues['missing_trailer'] += 1

        # Check for missing streaming/vod links
        watch_links = movie.get('watch_links', {})
        providers = movie.get('providers', {})

        if not (watch_links.get('streaming') or providers.get('streaming')):
            issues['missing_stream_link'] += 1
        if not (watch_links.get('vod') or providers.get('rent') or providers.get('buy')):
            issues['missing_vod_link'] += 1

    return {
        'new_films_released': new_films_released,
        'issues': issues
    }
