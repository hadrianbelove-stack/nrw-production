"""Admin panel curation routes — toggle status, update date, update fields, ordering."""

import os
import re
import json
import traceback
from datetime import datetime

from flask import Blueprint, request, jsonify

from file_lock import safe_write_json
from admin.config import (
    FEATURED_FILE, RESTORATIONS_FILE, CATEGORY_OVERRIDES_FILE,
)
from admin.logging_setup import logger
from admin.utils import (
    load_json, mark_changes_pending, validate_movie_update_request,
)

bp = Blueprint('curation', __name__)


@bp.route('/toggle-status', methods=['POST'])
def toggle_status() -> dict:
    """Toggle movie featured status."""
    try:
        data = request.json
        movie_id = data.get('movie_id')
        status_type = data.get('status_type')
        value = data.get('value')

        # Validation
        if not movie_id:
            return jsonify({'success': False, 'error': 'Missing required parameter: movie_id'})

        if not status_type:
            return jsonify({'success': False, 'error': 'Missing required parameter: status_type'})

        if value is None:
            return jsonify({'success': False, 'error': 'Missing required parameter: value'})

        if not isinstance(value, bool):
            return jsonify({'success': False, 'error': 'Parameter value must be boolean'})

        # Status types that use sidecar list files (legacy pattern)
        STATUS_FILES = {
            'featured': FEATURED_FILE,
            'restoration': RESTORATIONS_FILE
        }

        STATUS_VERBS = {
            'featured': ('featured', 'unfeatured'),
            'restoration': ('marked as restoration', 'unmarked as restoration')
        }

        # Status types that use category_overrides.json
        CATEGORY_OVERRIDE_TYPES = {
            'big_time': 'is_big_time',
            'indie': 'is_indie',
            'foreign': 'is_foreign',
            'series': 'is_series',
            'virtual_screening': 'is_virtual_screening',
            'documentary': 'is_documentary'
        }

        ALL_TYPES = set(STATUS_FILES.keys()) | set(CATEGORY_OVERRIDE_TYPES.keys())

        if status_type not in ALL_TYPES:
            return jsonify({
                'success': False,
                'error': f'Invalid status_type "{status_type}". Must be one of: {", ".join(sorted(ALL_TYPES))}'
            })

        changed = False

        if status_type in STATUS_FILES:
            # Legacy sidecar file toggle (featured, restoration)
            file_path = STATUS_FILES[status_type]
            status_list = load_json(file_path, [])

            if value and movie_id not in status_list:
                status_list.append(movie_id)
                changed = True
            elif not value and movie_id in status_list:
                status_list.remove(movie_id)
                changed = True

            os.makedirs('admin', exist_ok=True)
            safe_write_json(file_path, status_list)
        else:
            # Category override toggle
            field_name = CATEGORY_OVERRIDE_TYPES[status_type]
            overrides = load_json(CATEGORY_OVERRIDES_FILE, {})

            if movie_id not in overrides:
                overrides[movie_id] = {}

            current = overrides[movie_id].get(field_name)
            if current != value:
                overrides[movie_id][field_name] = value
                changed = True

            # Clean up empty override entries
            if not overrides[movie_id]:
                del overrides[movie_id]

            os.makedirs('admin', exist_ok=True)
            safe_write_json(CATEGORY_OVERRIDES_FILE, overrides)

        # Mark changes as pending if state actually changed
        if changed:
            mark_changes_pending()

        # Log action
        verb = status_type.replace('_', ' ')
        action = f"set {verb}={value}"
        logger.info(f"Movie {movie_id} {action}")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error toggling {status_type} status for movie {movie_id}: {str(e)}")
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'})


@bp.route('/update-date', methods=['POST'])
def update_date() -> dict:
    """Update movie's digital release date."""
    data = request.json
    movie_id = data.get('movie_id')
    new_date = data.get('digital_date')

    # Validate ISO date format before proceeding
    if new_date:
        try:
            datetime.strptime(new_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Digital date must be in ISO format YYYY-MM-DD (e.g., 2025-10-20)'
            })

    # Update in tracking database
    try:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)

        if movie_id in db['movies']:
            logger.info(f"Updating digital date for movie {movie_id} to {new_date}")
            db['movies'][movie_id]['digital_date'] = new_date
            db['movies'][movie_id]['manually_corrected'] = True

            safe_write_json('movie_tracking.json', db)

            # Mark that changes need to be saved
            mark_changes_pending()

            logger.info(f"Successfully updated date for movie {movie_id} to {new_date}")
            return jsonify({'success': True, 'message': f'Date updated to {new_date}. Click "Save Changes" to rebuild.'})
    except Exception as e:
        logger.error(f"Failed to update date for movie {movie_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

    return jsonify({'success': False, 'error': 'Movie not found'})


@bp.route('/update-movie-fields', methods=['POST'])
def update_movie_fields() -> dict:
    """Update all editable fields for a movie."""
    try:
        data = request.json

        # Validate request schema first
        is_valid, error_msg = validate_movie_update_request(data)
        if not is_valid:
            logger.warning(f"Invalid update request: {error_msg}")
            return jsonify({'success': False, 'error': error_msg})

        raw_movie_id = data.get('movie_id')

        # Validate movie_id exists and is not None before str() conversion
        if raw_movie_id is None:
            return jsonify({'success': False, 'error': 'Movie ID required'})

        movie_id = str(raw_movie_id).strip()

        # Check if empty after strip
        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID cannot be empty'})

        logger.info(f"Updating fields for movie {movie_id}")

        # Load movie_tracking.json
        tracking_file = 'movie_tracking.json'
        try:
            with open(tracking_file, 'r') as f:
                tracking_data = json.load(f)
        except FileNotFoundError:
            return jsonify({'success': False, 'error': 'movie_tracking.json not found'})

        # Check if movie exists
        if movie_id not in tracking_data.get('movies', {}):
            return jsonify({'success': False, 'error': f'Movie {movie_id} not found in tracking database'})

        movie = tracking_data['movies'][movie_id]
        changes_made = []

        # Update RT Score
        if 'rt_score' in data and data['rt_score'] is not None:
            rt_score_value = data['rt_score']

            if isinstance(rt_score_value, int):
                rt_score = rt_score_value
            elif isinstance(rt_score_value, str):
                rt_score_str = rt_score_value.strip()
                if not re.match(r'^[-+]?\d+$', rt_score_str):
                    return jsonify({
                        'success': False,
                        'error': 'RT score must be an integer between 0 and 100'
                    })
                try:
                    rt_score = int(rt_score_str)
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'RT score must be an integer between 0 and 100'
                    })
            else:
                return jsonify({
                    'success': False,
                    'error': 'RT score must be an integer between 0 and 100'
                })

            if rt_score < 0 or rt_score > 100:
                return jsonify({
                    'success': False,
                    'error': 'RT score must be between 0 and 100'
                })

            movie['rt_score'] = rt_score
            movie['manual_rt_score'] = True
            changes_made.append('RT Score')

        # Update Links
        if 'links' not in movie:
            movie['links'] = {}

        if 'rt_link' in data:
            rt_link = data['rt_link'].strip() if data['rt_link'] else ''

            if rt_link == '':
                if 'rt' in movie.get('links', {}):
                    del movie['links']['rt']
                movie['manual_rt_link'] = False
                changes_made.append('RT Link (cleared)')
            else:
                if not rt_link.startswith(('http://', 'https://')):
                    return jsonify({
                        'success': False,
                        'error': 'RT link must be a valid URL starting with http:// or https://'
                    })

                movie['links']['rt'] = rt_link
                movie['manual_rt_link'] = True
                changes_made.append('RT Link')

        if 'trailer_link' in data:
            trailer_link = data['trailer_link'].strip() if data['trailer_link'] else ''

            if trailer_link == '':
                if 'trailer' in movie.get('links', {}):
                    del movie['links']['trailer']
                movie['manual_trailer'] = False
                changes_made.append('Trailer (cleared)')
            else:
                if not trailer_link.startswith(('http://', 'https://')):
                    return jsonify({
                        'success': False,
                        'error': 'Trailer link must be a valid URL starting with http:// or https://'
                    })

                movie['links']['trailer'] = trailer_link
                movie['manual_trailer'] = True
                changes_made.append('Trailer')

        # Update Wikipedia Link
        if 'wikipedia_link' in data:
            wikipedia_link = data['wikipedia_link'].strip() if data['wikipedia_link'] else ''

            if wikipedia_link == '':
                if 'wikipedia' in movie.get('links', {}):
                    del movie['links']['wikipedia']
                movie['manual_wikipedia'] = False
                changes_made.append('Wikipedia (cleared)')
            else:
                if not wikipedia_link.startswith(('http://', 'https://')):
                    return jsonify({
                        'success': False,
                        'error': 'Wikipedia link must be a valid URL starting with http:// or https://'
                    })

                movie['links']['wikipedia'] = wikipedia_link
                movie['manual_wikipedia'] = True
                changes_made.append('Wikipedia')

        # Update Director
        if 'director' in data:
            director = str(data['director']).strip() if data['director'] else ''

            if director == '':
                if 'crew' in movie and 'director' in movie['crew']:
                    del movie['crew']['director']
                movie['manual_director'] = False
                changes_made.append('Director (cleared)')
            else:
                if 'crew' not in movie:
                    movie['crew'] = {}
                movie['crew']['director'] = director
                movie['manual_director'] = True
                changes_made.append('Director')

        # Update Country
        if 'country' in data:
            country = str(data['country']).strip() if data['country'] else ''

            if country == '':
                if 'country' in movie:
                    del movie['country']
                movie['manual_country'] = False
                changes_made.append('Country (cleared)')
            else:
                movie['country'] = country
                movie['manual_country'] = True
                changes_made.append('Country')

        # Update Year
        if 'year' in data and data['year'] is not None:
            year_value = data['year']

            if isinstance(year_value, int):
                year = year_value
            elif isinstance(year_value, str):
                year_str = year_value.strip()
                if not re.match(r'^\d+$', year_str):
                    return jsonify({
                        'success': False,
                        'error': 'Year must be a valid integer'
                    })
                try:
                    year = int(year_str)
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Year must be a valid integer'
                    })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Year must be a valid integer'
                })

            if year < 1900 or year > 2100:
                return jsonify({
                    'success': False,
                    'error': 'Year must be between 1900 and 2100'
                })

            movie['year'] = year
            movie['manual_year'] = True
            changes_made.append('Year')

        # Update Runtime
        if 'runtime' in data and data['runtime'] is not None:
            runtime_value = data['runtime']

            if isinstance(runtime_value, int):
                runtime = runtime_value
            elif isinstance(runtime_value, str):
                runtime_str = runtime_value.strip()
                if not re.match(r'^\d+$', runtime_str):
                    return jsonify({
                        'success': False,
                        'error': 'Runtime must be a valid integer'
                    })
                try:
                    runtime = int(runtime_str)
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Runtime must be a valid integer'
                    })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Runtime must be a valid integer'
                })

            if runtime < 1 or runtime > 500:
                return jsonify({
                    'success': False,
                    'error': 'Runtime must be between 1 and 500 minutes'
                })

            movie['runtime'] = runtime
            movie['manual_runtime'] = True
            changes_made.append('Runtime')

        # Update Poster URL
        if 'poster_url' in data:
            poster_url = data['poster_url'].strip() if data['poster_url'] else ''

            if poster_url == '':
                if 'poster' in movie:
                    del movie['poster']
                movie['manual_poster'] = False
                changes_made.append('Poster (cleared)')
            else:
                if not poster_url.startswith(('http://', 'https://')):
                    return jsonify({
                        'success': False,
                        'error': 'Poster URL must be a valid URL starting with http:// or https://'
                    })

                movie['poster'] = poster_url
                movie['manual_poster'] = True
                changes_made.append('Poster')

        # Update Digital Release Date
        if 'digital_date' in data:
            digital_date = data['digital_date'].strip() if data['digital_date'] else ''

            if digital_date == '':
                if 'digital_date' in movie:
                    del movie['digital_date']
                changes_made.append('Digital Date (cleared)')
            else:
                try:
                    datetime.strptime(digital_date, '%Y-%m-%d')
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Digital date must be in ISO format YYYY-MM-DD (e.g., 2025-10-20)'
                    })

                movie['digital_date'] = digital_date
                movie['manually_corrected'] = True
                changes_made.append('Digital Date')

        # Update Synopsis
        if 'synopsis' in data:
            synopsis = str(data['synopsis']).strip() if data['synopsis'] else ''

            if synopsis == '':
                if 'synopsis' in movie:
                    del movie['synopsis']
                movie['manual_synopsis'] = False
                changes_made.append('Synopsis (cleared)')
            else:
                if len(synopsis) > 5000:
                    return jsonify({
                        'success': False,
                        'error': 'Synopsis is too long (maximum 5000 characters)'
                    })

                movie['synopsis'] = synopsis
                movie['manual_synopsis'] = True
                changes_made.append('Synopsis')

        # Update Watch Links
        if 'watch_links' in data:
            if data['watch_links']:
                watch_links = data['watch_links']

                if not isinstance(watch_links, dict):
                    return jsonify({
                        'success': False,
                        'error': 'Watch links must be a dictionary'
                    })

                # Validate each category and normalize trimmed values
                for category in ['streaming', 'vod']:
                    if category in watch_links:
                        cat_data = watch_links[category]

                        if not isinstance(cat_data, dict) or 'service' not in cat_data or 'link' not in cat_data:
                            return jsonify({
                                'success': False,
                                'error': f'Watch links {category} must have "service" and "link" fields'
                            })

                        service = str(cat_data['service']).strip()
                        if not service:
                            return jsonify({
                                'success': False,
                                'error': f'Watch links {category} service cannot be empty'
                            })
                        cat_data['service'] = service

                        link = cat_data['link']
                        if link:
                            link = link.strip()
                            if not link:
                                cat_data['link'] = None
                            elif not link.startswith(('http://', 'https://')):
                                return jsonify({
                                    'success': False,
                                    'error': f'Watch links {category} link must be a valid URL starting with http:// or https://'
                                })
                            else:
                                cat_data['link'] = link
                        else:
                            cat_data['link'] = None

                movie['watch_links'] = watch_links
                movie['manual_watch_links'] = True
                changes_made.append('Watch Links')
            else:
                if 'watch_links' in movie:
                    del movie['watch_links']
                movie['manual_watch_links'] = False
                changes_made.append('Watch Links')

        # Mark as manually corrected
        movie['manually_corrected'] = True
        movie['last_manual_edit'] = datetime.now().isoformat()

        # Save back to movie_tracking.json (with atomic write and backup)
        safe_write_json(tracking_file, tracking_data)

        logger.info(f"Saved {len(changes_made)} field changes for movie {movie_id}: {', '.join(changes_made)}")

        # Also update data.json directly so changes appear immediately on site
        try:
            data_file = 'data.json'
            with open(data_file, 'r') as f:
                site_data = json.load(f)

            # Find the movie in data.json by ID
            site_movie = None
            for m in site_data.get('movies', []):
                if str(m.get('id')) == movie_id:
                    site_movie = m
                    break

            if site_movie:
                # Copy display-relevant fields from tracking movie to site movie
                if 'links' not in site_movie:
                    site_movie['links'] = {}
                if movie.get('links', {}).get('trailer'):
                    site_movie['links']['trailer'] = movie['links']['trailer']
                elif 'trailer' in site_movie.get('links', {}):
                    del site_movie['links']['trailer']

                if movie.get('links', {}).get('rt'):
                    site_movie['links']['rt'] = movie['links']['rt']
                elif 'rt' in site_movie.get('links', {}):
                    del site_movie['links']['rt']

                if movie.get('links', {}).get('wikipedia'):
                    site_movie['links']['wikipedia'] = movie['links']['wikipedia']
                elif 'wikipedia' in site_movie.get('links', {}):
                    del site_movie['links']['wikipedia']

                if movie.get('rt_score') is not None:
                    site_movie['rt_score'] = movie['rt_score']
                elif 'rt_score' in site_movie:
                    del site_movie['rt_score']

                if movie.get('poster'):
                    site_movie['poster'] = movie['poster']

                if movie.get('crew', {}).get('director'):
                    if 'crew' not in site_movie:
                        site_movie['crew'] = {}
                    site_movie['crew']['director'] = movie['crew']['director']

                if movie.get('country'):
                    site_movie['country'] = movie['country']

                if movie.get('year'):
                    site_movie['year'] = movie['year']

                if movie.get('runtime'):
                    site_movie['runtime'] = movie['runtime']

                if movie.get('synopsis'):
                    site_movie['synopsis'] = movie['synopsis']

                if movie.get('digital_date'):
                    site_movie['digital_date'] = movie['digital_date']

                if movie.get('watch_links'):
                    site_movie['watch_links'] = movie['watch_links']

                safe_write_json(data_file, site_data)
                logger.info(f"Also updated data.json for movie {movie_id} - changes are live")
            else:
                logger.warning(f"Movie {movie_id} not found in data.json - changes saved to tracking only")
        except Exception as e:
            logger.error(f"Failed to update data.json: {e} - changes saved to tracking only")

        # Mark that changes need to be saved (for git commit)
        mark_changes_pending()

        logger.info(f"Successfully updated fields for movie {movie_id}: {', '.join(changes_made)}")
        return jsonify({
            'success': True,
            'message': f'Updated {", ".join(changes_made)}. Changes are live on site.'
        })

    except Exception as e:
        logger.error(f"Error updating fields for movie {movie_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating fields: {str(e)}',
            'traceback': traceback.format_exc()
        })


@bp.route('/update-ordering', methods=['POST'])
def update_ordering() -> dict:
    """Update editorial ordering of movies."""
    try:
        data = request.json or {}
        ordered_ids = data.get('ordered_ids', [])

        if not isinstance(ordered_ids, list):
            return jsonify({
                'success': False,
                'error': 'ordered_ids must be an array'
            })

        # Convert all IDs to strings and validate they're not empty
        normalized_ids = []
        for movie_id in ordered_ids:
            movie_id_str = str(movie_id).strip()
            if movie_id_str:
                normalized_ids.append(movie_id_str)

        # Ensure admin directory exists
        os.makedirs('admin', exist_ok=True)

        # Save ordering
        safe_write_json('admin/ordering.json', normalized_ids)

        logger.info(f"Editorial ordering updated with {len(normalized_ids)} movies")

        # Mark that changes need to be saved
        mark_changes_pending()

        return jsonify({
            'success': True,
            'message': f'Editorial ordering updated with {len(normalized_ids)} movies. Click "Save Changes" to rebuild.',
            'ordered_count': len(normalized_ids)
        })

    except Exception as e:
        logger.error(f"Error updating ordering: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating ordering: {str(e)}'
        })
