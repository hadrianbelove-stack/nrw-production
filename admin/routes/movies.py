"""Admin panel movie management routes — add, remove, search TMDB."""

import json
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify

from file_lock import safe_write_json
from admin.config import FEATURED_FILE
from admin.logging_setup import logger
from admin.tmdb import get_tmdb_api_key
from admin.utils import load_json, mark_changes_pending

bp = Blueprint('movies', __name__)


@bp.route('/search-tmdb', methods=['GET'])
def search_tmdb() -> dict:
    """Search TMDB for movies by title."""
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({'success': False, 'error': 'Search query required'})

    if len(query) < 2:
        return jsonify({'success': False, 'error': 'Search query too short'})

    api_key = get_tmdb_api_key()
    if not api_key:
        return jsonify({'success': False, 'error': 'TMDB API key not configured'})

    try:
        response = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params={
                "api_key": api_key,
                "query": query,
                "language": "en-US",
                "include_adult": False
            },
            timeout=10
        )

        if response.status_code != 200:
            logger.warning(f"TMDB search returned status {response.status_code}")
            return jsonify({'success': False, 'error': f'TMDB API error: {response.status_code}'})

        data = response.json()
        results = []

        for movie in data.get('results', [])[:10]:  # Limit to top 10 results
            year = ''
            if movie.get('release_date'):
                year = movie['release_date'][:4]

            poster_url = None
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w92{movie['poster_path']}"

            results.append({
                'id': movie['id'],
                'title': movie['title'],
                'year': year,
                'poster_url': poster_url,
                'overview': movie.get('overview', '')[:200]  # Truncate for display
            })

        logger.info(f"TMDB search for '{query}' returned {len(results)} results")
        return jsonify({'success': True, 'results': results})

    except requests.Timeout:
        logger.error("TMDB search timed out")
        return jsonify({'success': False, 'error': 'Search timed out'})
    except Exception as e:
        logger.error(f"TMDB search error: {e}")
        return jsonify({'success': False, 'error': f'Search error: {str(e)}'})


@bp.route('/add-movie', methods=['POST'])
def add_movie() -> dict:
    """Add a new movie manually to the tracking database."""
    try:
        data = request.json or {}
        tmdb_id = str(data.get('tmdb_id', '')).strip()
        title = str(data.get('title', '')).strip() if data.get('title') else None
        digital_date = data.get('digital_date', '').strip() if data.get('digital_date') else None
        providers = data.get('providers', {})
        synopsis = data.get('synopsis', '').strip() if data.get('synopsis') else None
        poster_url = data.get('poster_url', '').strip() if data.get('poster_url') else None
        watch_link = data.get('watch_link')  # {service, type, url}

        # Validation
        if not tmdb_id:
            return jsonify({'success': False, 'error': 'TMDB ID is required'})

        # Validate TMDB ID is numeric
        try:
            int(tmdb_id)
        except ValueError:
            return jsonify({'success': False, 'error': 'TMDB ID must be numeric'})

        # Validate digital date format if provided
        if digital_date:
            try:
                datetime.strptime(digital_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Digital date must be in YYYY-MM-DD format'
                })

        # Load movie tracking database
        try:
            with open('movie_tracking.json', 'r') as f:
                tracking_data = json.load(f)
        except FileNotFoundError:
            return jsonify({'success': False, 'error': 'movie_tracking.json not found'})

        # Check if movie already exists in tracking
        existing_in_tracking = tmdb_id in tracking_data.get('movies', {})

        # Check if movie already exists in data.json
        try:
            with open('data.json', 'r') as f:
                site_data = json.load(f)
            existing_in_data = any(str(m.get('id')) == tmdb_id for m in site_data.get('movies', []))
        except FileNotFoundError:
            site_data = {'movies': []}
            existing_in_data = False

        # If already in data.json, that's a real duplicate
        if existing_in_data:
            return jsonify({
                'success': False,
                'error': f'Movie already exists on site'
            })

        # Fetch TMDB data (required if title not provided)
        tmdb_data = {}
        director = None
        api_key = get_tmdb_api_key()
        if api_key:
            try:
                # Fetch basic movie info
                response = requests.get(
                    f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                    params={"api_key": api_key, "language": "en-US"},
                    timeout=10
                )
                if response.status_code == 200:
                    tmdb_data = response.json()
                    logger.info(f"Fetched TMDB data for {tmdb_id}: {tmdb_data.get('title', 'Unknown')}")
                elif response.status_code == 404:
                    return jsonify({'success': False, 'error': f'Movie not found on TMDB (ID: {tmdb_id})'})
                else:
                    logger.warning(f"TMDB API returned {response.status_code} for movie {tmdb_id}")

                # Fetch credits to get director
                credits_response = requests.get(
                    f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits",
                    params={"api_key": api_key},
                    timeout=10
                )
                if credits_response.status_code == 200:
                    credits_data = credits_response.json()
                    for crew_member in credits_data.get('crew', []):
                        if crew_member.get('job') == 'Director':
                            director = crew_member.get('name')
                            break
                    if director:
                        logger.info(f"Found director for {tmdb_id}: {director}")
            except Exception as e:
                logger.warning(f"Failed to fetch TMDB data for {tmdb_id}: {e}")

        # Use TMDB title if not provided
        if not title:
            title = tmdb_data.get('title')
            if not title:
                return jsonify({'success': False, 'error': 'Could not fetch movie title from TMDB'})

        # Create movie entry
        now = datetime.now().isoformat()
        movie_entry = {
            'id': tmdb_id,
            'title': title,
            'manually_added': True,
            'source': 'admin',
            'intake_date': datetime.now().strftime('%Y-%m-%d'),
            'last_manual_edit': now,
            'manually_corrected': True
        }

        # Default digital_date to today if not provided (so movie appears on wall)
        if not digital_date:
            digital_date = datetime.now().strftime('%Y-%m-%d')
        movie_entry['digital_date'] = digital_date
        movie_entry['status'] = 'available'

        # Add TMDB data if available
        if tmdb_data:
            if tmdb_data.get('release_date'):
                movie_entry['theatrical_date'] = tmdb_data['release_date']
                movie_entry['year'] = int(tmdb_data['release_date'][:4])
            if tmdb_data.get('overview'):
                movie_entry['synopsis'] = synopsis or tmdb_data['overview']
            if tmdb_data.get('runtime'):
                movie_entry['runtime'] = tmdb_data['runtime']
            if tmdb_data.get('production_countries') and len(tmdb_data['production_countries']) > 0:
                movie_entry['country'] = tmdb_data['production_countries'][0].get('name', '')

        # Add director if found
        if director:
            if 'crew' not in movie_entry:
                movie_entry['crew'] = {}
            movie_entry['crew']['director'] = director
            if tmdb_data.get('poster_path') and not poster_url:
                movie_entry['poster'] = f"https://image.tmdb.org/t/p/w300{tmdb_data['poster_path']}"
            if tmdb_data.get('vote_average'):
                movie_entry['vote_average'] = tmdb_data['vote_average']

        # Add provided optional fields
        if synopsis:
            movie_entry['synopsis'] = synopsis
        if poster_url:
            movie_entry['poster'] = poster_url
        if providers:
            movie_entry['providers'] = providers

        # Add watch link if provided
        if watch_link and watch_link.get('url'):
            link_type = watch_link.get('type', 'vod')  # 'streaming' or 'vod'
            service = watch_link.get('service', 'UNKNOWN')
            url = watch_link.get('url')

            if 'watch_links' not in movie_entry:
                movie_entry['watch_links'] = {}

            movie_entry['watch_links'][link_type] = {
                'service': service,
                'url': url
            }

        # Add to tracking database (or update if already there)
        if 'movies' not in tracking_data:
            tracking_data['movies'] = {}

        if existing_in_tracking:
            # Movie exists in tracking - update it with digital_date and status
            tracking_data['movies'][tmdb_id]['digital_date'] = digital_date
            tracking_data['movies'][tmdb_id]['status'] = 'available'
            tracking_data['movies'][tmdb_id]['last_manual_edit'] = now
            if watch_link and watch_link.get('url'):
                if 'watch_links' not in tracking_data['movies'][tmdb_id]:
                    tracking_data['movies'][tmdb_id]['watch_links'] = {}
                link_type = watch_link.get('type', 'vod')
                tracking_data['movies'][tmdb_id]['watch_links'][link_type] = {
                    'service': watch_link.get('service', 'UNKNOWN'),
                    'url': watch_link.get('url')
                }
            logger.info(f"Activated existing tracked movie {tmdb_id}: {title}")
        else:
            tracking_data['movies'][tmdb_id] = movie_entry

        # Save atomically to movie_tracking.json
        safe_write_json('movie_tracking.json', tracking_data)

        if existing_in_tracking:
            logger.info(f"Activated tracked movie {tmdb_id}: {title}")
        else:
            logger.info(f"Manually added movie {tmdb_id}: {title}")

        # Also add directly to data.json so it appears immediately (no regeneration needed)
        try:
            # site_data already loaded above when checking existing_in_data

            # Build the movie object for data.json
            site_movie = {
                'id': int(tmdb_id),
                'title': title,
                'digital_date': digital_date,
                'manually_added': True
            }

            # Add TMDB data
            if tmdb_data:
                if tmdb_data.get('release_date'):
                    site_movie['year'] = int(tmdb_data['release_date'][:4]) if tmdb_data['release_date'] else None
                if tmdb_data.get('overview'):
                    site_movie['synopsis'] = tmdb_data['overview']
                if tmdb_data.get('poster_path'):
                    site_movie['poster'] = f"https://image.tmdb.org/t/p/w300{tmdb_data['poster_path']}"
                if tmdb_data.get('runtime'):
                    site_movie['runtime'] = tmdb_data['runtime']
                if tmdb_data.get('production_countries') and len(tmdb_data['production_countries']) > 0:
                    site_movie['country'] = tmdb_data['production_countries'][0].get('name', '')
                # Add studio and budget for categorization
                if tmdb_data.get('production_companies') and len(tmdb_data['production_companies']) > 0:
                    site_movie['studio'] = tmdb_data['production_companies'][0].get('name', '')
                if tmdb_data.get('budget'):
                    site_movie['budget'] = tmdb_data['budget']

            # Add director
            if director:
                site_movie['crew'] = {'director': director}

            # Add watch link if provided
            if watch_link and watch_link.get('url'):
                link_type = watch_link.get('type', 'vod')
                service = watch_link.get('service', 'UNKNOWN')
                url = watch_link.get('url')
                site_movie['watch_links'] = {}
                site_movie['watch_links'][link_type] = {
                    'service': service,
                    'url': url
                }

            # Add to movies list
            if 'movies' not in site_data:
                site_data['movies'] = []
            site_data['movies'].append(site_movie)

            safe_write_json('data.json', site_data)
            logger.info(f"Added movie {tmdb_id} to data.json - now visible on site")

        except Exception as e:
            logger.error(f"Failed to add to data.json: {e} - movie saved to tracking only")

        # Mark that changes need to be saved (for git commit)
        mark_changes_pending()

        return jsonify({
            'success': True,
            'message': f'"{title}" added and now visible on site!',
            'movie_id': tmdb_id,
            'title': title,
            'status': movie_entry['status']
        })

    except Exception as e:
        logger.error(f"Error adding movie: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error adding movie: {str(e)}'
        })


@bp.route('/remove-movie', methods=['POST'])
def remove_movie() -> dict:
    """Remove a movie from the New Arrivals Wall."""
    try:
        data = request.json or {}
        movie_id = str(data.get('movie_id', '')).strip()

        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID is required'})

        logger.info(f"Removing movie {movie_id} from New Arrivals Wall")

        # 1. Update movie_tracking.json - set digital_date to null
        try:
            with open('movie_tracking.json', 'r') as f:
                tracking_data = json.load(f)
        except FileNotFoundError:
            return jsonify({'success': False, 'error': 'movie_tracking.json not found'})

        if movie_id not in tracking_data.get('movies', {}):
            return jsonify({'success': False, 'error': f'Movie {movie_id} not found in tracking database'})

        movie = tracking_data['movies'][movie_id]
        title = movie.get('title', 'Unknown')

        # Clear digital_date so it won't be included in future regenerations
        movie['digital_date'] = None
        movie['removed_from_wall'] = True
        movie['removed_at'] = datetime.now().isoformat()

        safe_write_json('movie_tracking.json', tracking_data)
        logger.info(f"Cleared digital_date for movie {movie_id} ({title}) in tracking")

        # 2. Remove from data.json
        try:
            with open('data.json', 'r') as f:
                site_data = json.load(f)

            original_count = len(site_data.get('movies', []))
            site_data['movies'] = [m for m in site_data.get('movies', []) if str(m.get('id')) != movie_id]
            new_count = len(site_data['movies'])

            if new_count < original_count:
                safe_write_json('data.json', site_data)
                logger.info(f"Removed movie {movie_id} from data.json ({original_count} -> {new_count} movies)")
            else:
                logger.warning(f"Movie {movie_id} was not found in data.json")

        except Exception as e:
            logger.error(f"Failed to update data.json: {e}")
            return jsonify({
                'success': False,
                'error': f'Updated tracking but failed to update data.json: {e}'
            })

        # 3. Remove from featured list if present
        featured = load_json(FEATURED_FILE, [])
        if movie_id in featured:
            featured.remove(movie_id)
            safe_write_json(FEATURED_FILE, featured)
            logger.info(f"Removed movie {movie_id} from featured list")

        # 4. Remove from ordering if present
        ordering = load_json('admin/ordering.json', [])
        if movie_id in ordering:
            ordering.remove(movie_id)
            safe_write_json('admin/ordering.json', ordering)
            logger.info(f"Removed movie {movie_id} from ordering")

        mark_changes_pending()

        return jsonify({
            'success': True,
            'message': f'"{title}" removed from New Arrivals Wall',
            'title': title
        })

    except Exception as e:
        logger.error(f"Error removing movie: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error removing movie: {str(e)}'
        })
