#!/usr/bin/env python3
"""
Generate report of movies needing link corrections.
Outputs to metrics/missing_links.json for admin review.
"""

import json
import os
from datetime import datetime

def generate_missing_links_report(data_path='data.json', output_path='metrics/missing_links.json'):
    """Find movies where we know the streaming service but don't have a direct link."""

    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    movies = data.get('movies', [])

    missing_streaming_links = []
    missing_vod_links = []

    for movie in movies:
        title = movie.get('title', 'Unknown')
        tmdb_id = movie.get('id', movie.get('tmdb_id', 'N/A'))
        digital_date = movie.get('digital_date', 'N/A')
        providers = movie.get('providers', {})
        watch_links = movie.get('watch_links', {})

        # Check streaming: service known but no link
        streaming_providers = providers.get('streaming', [])
        streaming_link = watch_links.get('streaming', {})

        # Filter out "with Ads" variants
        primary_streamers = [p for p in streaming_providers if 'with Ads' not in p]

        if primary_streamers:
            # We know streaming is available
            has_streaming_link = streaming_link.get('link') if isinstance(streaming_link, dict) else None

            if not has_streaming_link:
                missing_streaming_links.append({
                    'title': title,
                    'tmdb_id': tmdb_id,
                    'digital_date': digital_date,
                    'known_services': primary_streamers,
                    'current_watch_links': watch_links
                })

        # Check VOD: rent/buy providers known but no link
        rent_providers = providers.get('rent', [])
        buy_providers = providers.get('buy', [])
        vod_link = watch_links.get('vod', {})

        has_vod_link = vod_link.get('link') if isinstance(vod_link, dict) else None

        # Prioritize Amazon and Apple for VOD
        priority_vod = []
        for provider in rent_providers + buy_providers:
            p_lower = provider.lower()
            if 'amazon' in p_lower or 'apple' in p_lower:
                if provider not in priority_vod:
                    priority_vod.append(provider)

        if priority_vod and not has_vod_link:
            missing_vod_links.append({
                'title': title,
                'tmdb_id': tmdb_id,
                'digital_date': digital_date,
                'known_services': priority_vod,
                'all_rent': rent_providers,
                'all_buy': buy_providers,
                'current_watch_links': watch_links
            })

    # Sort by date (most recent first)
    missing_streaming_links.sort(key=lambda x: x['digital_date'], reverse=True)
    missing_vod_links.sort(key=lambda x: x['digital_date'], reverse=True)

    report = {
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_movies': len(movies),
            'missing_streaming_links': len(missing_streaming_links),
            'missing_vod_links': len(missing_vod_links)
        },
        'streaming_needs_link': missing_streaming_links[:50],  # Top 50 most recent
        'vod_needs_link': missing_vod_links[:50]  # Top 50 most recent
    }

    # Ensure metrics directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Missing Links Report generated: {output_path}")
    print(f"  - {len(missing_streaming_links)} movies need streaming links")
    print(f"  - {len(missing_vod_links)} movies need VOD links")

    # Print summary of streaming issues
    if missing_streaming_links:
        print("\nStreaming links needed (most recent):")
        for m in missing_streaming_links[:10]:
            services = ', '.join(m['known_services'])
            print(f"  {m['digital_date']} | {m['title']} | {services}")

    return report


if __name__ == '__main__':
    generate_missing_links_report()
