#!/usr/bin/env python3
"""Batch verify pull quotes — find real review URLs via Gemini grounding.

Reads the combined pull quotes cache, runs grounding verification on
quotes that don't have review URLs, and updates the cache.

Usage:
    python3 scripts/batch_verify_quotes.py [--limit N] [--movie TITLE]
"""

import sys
import os
import json
import time
import logging
import argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv('.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s: %(message)s')
for name in ['httpx', 'google_genai', 'httpcore', 'urllib3']:
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger('batch_verify')

COMBINED_CACHE = 'cache/pull_quotes_combined.json'


def resolve_grounding_url(redirect_url):
    """Resolve a Gemini grounding redirect URL to the actual URL."""
    try:
        resp = requests.head(
            redirect_url,
            allow_redirects=False,
            timeout=5,
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            return resp.headers.get('Location', '')
    except Exception:
        pass
    return ''


def match_url_to_outlet(url, outlet):
    """Check if a URL domain plausibly matches a publication outlet name."""
    url_lower = url.lower()
    outlet_lower = outlet.lower().replace('the ', '').strip()
    compressed = outlet_lower.replace(' ', '')
    if compressed in url_lower:
        return True
    for word in outlet_lower.split():
        if len(word) > 4 and word in url_lower:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description='Batch verify pull quote URLs')
    parser.add_argument('--limit', type=int, default=0, help='Max movies to process (0=all)')
    parser.add_argument('--movie', type=str, default='', help='Process a specific movie title')
    args = parser.parse_args()

    # Load combined cache
    with open(COMBINED_CACHE) as f:
        cache = json.load(f)

    # Initialize Gemini
    from google import genai
    from google.genai import types

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    # Find movies needing verification
    movies_to_verify = []
    for movie_key, entry in cache.items():
        title = entry.get('title', movie_key)
        year = entry.get('year', '')

        if args.movie and args.movie.lower() not in title.lower():
            continue

        all_quotes = entry.get('rt_quotes', []) + entry.get('lb_quotes', [])
        missing = [q for q in all_quotes if not q.get('review_url') and q.get('critic', '').strip()]

        if missing:
            movies_to_verify.append({
                'key': movie_key,
                'title': title,
                'year': year,
                'quotes': missing,
            })

    if args.limit:
        movies_to_verify = movies_to_verify[:args.limit]

    total_quotes = sum(len(m['quotes']) for m in movies_to_verify)
    logger.info(f"Verifying {total_quotes} quotes across {len(movies_to_verify)} movies")

    total_verified = 0
    total_checked = 0

    for mi, movie in enumerate(movies_to_verify):
        title = movie['title']
        year = movie['year']
        quotes = movie['quotes']

        logger.info(f"[{mi+1}/{len(movies_to_verify)}] {title} ({year}): {len(quotes)} quotes")

        movie_verified = 0

        for q in quotes:
            critic = q.get('critic', '').strip()
            outlet = q.get('outlet', '').strip()

            if not critic or not outlet:
                continue

            total_checked += 1
            prompt = f'Find the URL for {critic}\'s {outlet} review of "{title}" ({year}).'

            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=config
                )

                # Extract grounding source URLs
                if response.candidates:
                    gm = response.candidates[0].grounding_metadata
                    if gm and gm.grounding_chunks:
                        for chunk in gm.grounding_chunks:
                            if chunk.web and chunk.web.uri:
                                actual = resolve_grounding_url(chunk.web.uri)
                                if actual and match_url_to_outlet(actual, outlet):
                                    q['review_url'] = actual
                                    movie_verified += 1
                                    total_verified += 1
                                    logger.info(f"  Verified: {critic} ({outlet}) -> {actual}")
                                    break

                # Rate limit
                time.sleep(1)

            except Exception as e:
                logger.warning(f"  Error for {critic}: {e}")
                time.sleep(2)

        logger.info(f"  {title}: {movie_verified}/{len(quotes)} verified")

    # Save updated cache
    with open(COMBINED_CACHE, 'w') as f:
        json.dump(cache, f, indent=2)

    logger.info(f"\nDone! Verified {total_verified}/{total_checked} quotes across {len(movies_to_verify)} movies")
    logger.info(f"Updated {COMBINED_CACHE}")


if __name__ == '__main__':
    main()
