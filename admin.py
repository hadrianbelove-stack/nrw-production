#!/usr/bin/env python3
"""
Admin panel for curating movie selections.
Simple Flask app for editing movie data and controlling visibility.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
import subprocess
from datetime import datetime
import yaml
import glob
import shutil
import logging
from logging.handlers import RotatingFileHandler
import traceback
from typing import Dict, List, Optional, Union, Any, Tuple

app = Flask(__name__,
            template_folder='admin/templates',
            static_folder='admin/static',
            static_url_path='/admin/static')

from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()

# Load credentials from environment or use defaults (change in production!)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme')

@auth.verify_password
def verify_password(username: str, password: str) -> Optional[str]:
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return username
    return None

# Configuration
DATA_FILE = 'data.json'  # Root directory - production display data
HIDDEN_FILE = 'admin/hidden_movies.json'  # Admin overrides
FEATURED_FILE = 'admin/featured_movies.json'  # Admin overrides
WATCH_LINK_OVERRIDES_FILE = 'admin/watch_link_overrides.json'


def load_json(filepath: str, default: Optional[Union[dict, list]] = None) -> Union[dict, list]:
    """Load JSON file with fallback to default value.

    Args:
        filepath: Path to JSON file to load
        default: Default value if file doesn't exist or is invalid (defaults to {})

    Returns:
        Loaded JSON data (dict or list) or default value
    """
    if default is None:
        default = {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return default

def load_config() -> dict:
    """Load configuration from config.yaml.

    Returns:
        Configuration dictionary, or empty dict if file not found or invalid
    """
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config.yaml: {e}")
        return {}

def get_tmdb_api_key() -> Optional[str]:
    """Get TMDB API key from environment or config.yaml.

    Checks environment variable TMDB_API_KEY first (12-factor app pattern),
    then falls back to config.yaml api.tmdb_api_key.

    Returns:
        API key string, or None if not found
    """
    # Try environment variable first (12-factor app pattern)
    api_key = os.environ.get('TMDB_API_KEY')
    if api_key:
        return api_key

    # Fall back to config.yaml
    config = load_config()
    api_key = config.get('api', {}).get('tmdb_api_key')
    if api_key:
        return api_key

    # Last resort: log warning
    logger.warning("No TMDB API key found in environment or config.yaml")
    return None

def get_poster_url(tmdb_id: Union[str, int]) -> Optional[str]:
    """Fetch poster URL from TMDB API.

    Args:
        tmdb_id: TMDB movie ID (string or integer)

    Returns:
        Poster URL (w300 size), or None if not found or API error

    Note:
        Requires TMDB API key from environment or config.yaml.
        Has 10 second timeout to prevent hanging.
    """
    if not tmdb_id:
        return None

    api_key = get_tmdb_api_key()
    if not api_key:
        return None

    try:
        import requests
        response = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": api_key},
            timeout=10  # 10 second timeout
        )
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get('poster_path')
            if poster_path:
                return f"https://image.tmdb.org/t/p/w300{poster_path}"
    except requests.Timeout:
        logger.warning(f"Timeout fetching poster for TMDB ID {tmdb_id}")
        return None
    except:
        pass
    return None

def save_json(filepath: str, data: Union[dict, list]) -> None:
    """Save data to JSON file.

    Creates parent directories if they don't exist.

    Args:
        filepath: Path to JSON file to write
        data: Data to serialize as JSON (dict or list)

    Raises:
        IOError: If file cannot be written
        TypeError: If data is not JSON-serializable
    """
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def safe_write_json(filepath: str, data: Union[dict, list], indent: int = 2, max_backups: int = 10) -> bool:
    """
    Safely write JSON data to a file with atomic operations and backup creation.

    Args:
        filepath (str): Path to the JSON file to write
        data (dict): Python dictionary to serialize as JSON
        indent (int): JSON indentation level (default 2)
        max_backups (int): Maximum number of backup files to keep (default 10)

    Returns:
        bool: True on success

    Raises:
        Exception: On write failure (original file remains untouched)
    """
    try:
        # Step 1: Create timestamped backup if original file exists
        if os.path.exists(filepath):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{filepath}.backup.{timestamp}"
            shutil.copy2(filepath, backup_file)

        # Step 2: Write to temporary file
        temp_file = f"{filepath}.tmp"
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=indent)
        except Exception:
            # Clean up temp file if write failed
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

        # Step 3: Atomic rename (all-or-nothing)
        os.replace(temp_file, filepath)

        # Step 4: Cleanup old backups
        try:
            backup_pattern = f"{filepath}.backup.*"
            backup_files = glob.glob(backup_pattern)
            if len(backup_files) > max_backups:
                # Sort by timestamp (newest first)
                backup_files.sort(reverse=True)
                # Remove old backups beyond max_backups
                for old_backup in backup_files[max_backups:]:
                    os.remove(old_backup)
        except Exception:
            # Backup cleanup failure shouldn't fail the write
            pass

        return True

    except Exception as e:
        # Ensure temp file is cleaned up
        temp_file = f"{filepath}.tmp"
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        raise


def setup_logger(name: str, log_file: str = 'logs/admin.log', level: int = logging.INFO) -> logging.Logger:
    """
    Configure logging with file rotation and console output.

    Args:
        name (str): Logger name (e.g., 'admin', 'data_generator')
        log_file (str): Path to log file (default: 'logs/admin.log')
        level (int): Logging level (default: logging.INFO)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Get or create logger
    logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if not logger.handlers:
        logger.setLevel(level)

        # Create formatter with user context placeholder
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(user)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler with rotation (10MB, 5 backups)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler for development visibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Custom LogRecord factory to inject user context
old_factory = logging.getLogRecordFactory()

def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Custom LogRecord factory that injects user context.

    Wraps the default LogRecord factory to add 'user' attribute
    with the current authenticated user from Flask-HTTPAuth.

    Args:
        *args: Positional arguments passed to default factory
        **kwargs: Keyword arguments passed to default factory

    Returns:
        LogRecord with added 'user' attribute
    """
    record = old_factory(*args, **kwargs)
    # Inject user context
    try:
        record.user = auth.current_user() or 'system'
    except:
        record.user = 'system'
    return record

logging.setLogRecordFactory(record_factory)

# Initialize logger
logger = setup_logger('admin', 'logs/admin.log', logging.INFO)

@app.route('/')
@auth.login_required
def index() -> str:
    """Main admin panel page.

    Displays all movies in a grid with filtering, search, and inline editing.
    Shows statistics (total, visible, hidden, featured, missing data counts).

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Returns:
        Rendered HTML template with movie data and statistics

    Template Variables:
        movies: Dict of movie objects keyed by movie ID
        hidden: List of hidden movie IDs
        featured: List of featured movie IDs
        visible_count: Number of visible movies
        hidden_count: Number of hidden movies
        featured_count: Number of featured movies
        missing_data_count: Number of movies with incomplete data
    """
    data = load_json(DATA_FILE, {})
    hidden = load_json(HIDDEN_FILE, [])
    featured = load_json(FEATURED_FILE, [])

    # Handle different data shapes from data.json
    if data and isinstance(data, dict) and 'movies' in data and isinstance(data['movies'], list):
        movies_list = data['movies']
    elif isinstance(data, list):
        movies_list = data
    else:
        movies_list = []

    # Process all movies and build dict keyed by movie ID
    processed_movies = {}

    for movie in movies_list:
        movie_id = str(movie.get('id'))
        movie_copy = dict(movie)

        # Normalize movie fields expected by template
        # Set rt_url from links.rt if available
        if movie_copy.get('links', {}).get('rt'):
            movie_copy['rt_url'] = movie_copy['links']['rt']

        # Set director from crew.director if available
        if movie_copy.get('crew', {}).get('director'):
            movie_copy['director'] = movie_copy['crew']['director']

        # Build provider_list from providers or watch_links
        providers = set()
        if movie_copy.get('providers'):
            for category in ['streaming', 'rent', 'buy']:
                if category in movie_copy['providers']:
                    providers.update(movie_copy['providers'][category])
        if movie_copy.get('watch_links'):
            for category_data in movie_copy['watch_links'].values():
                if isinstance(category_data, dict) and 'service' in category_data:
                    providers.add(category_data['service'])
        movie_copy['provider_list'] = ', '.join(sorted(providers)) if providers else ''

        # Handle poster URLs
        if movie_copy.get('poster') and not movie_copy.get('poster_url'):
            movie_copy['poster_url'] = movie_copy['poster']

        # Fetch from TMDB only if both poster and poster_url are missing and id exists
        if not movie_copy.get('poster_url') and not movie_copy.get('poster') and movie_copy.get('id'):
            movie_copy['poster_url'] = get_poster_url(movie_copy['id'])

        # Normalize rt_score to integer for template comparisons
        if movie_copy.get('rt_score'):
            rt_score_str = str(movie_copy['rt_score']).strip().replace('%', '')
            try:
                movie_copy['rt_score'] = int(rt_score_str)
            except (ValueError, TypeError):
                movie_copy['rt_score'] = None

        processed_movies[movie_id] = movie_copy

    # Calculate stats
    total_count = len(movies_list)
    hidden_count = len(hidden)
    visible_count = total_count - hidden_count
    featured_count = len(featured)

    # Calculate missing data count
    missing_data_count = sum(
        1 for movie in processed_movies.values()
        if not movie.get('rt_score')
        or not movie.get('links', {}).get('trailer')
        or not (movie.get('poster_url') or movie.get('poster'))
        or not movie.get('director')
        or movie.get('director') == 'Unknown'
        or not movie.get('country')
    )


    return render_template(
        'index.html',
        movies=processed_movies,
        hidden=hidden,
        featured=featured,
        visible_count=visible_count,
        hidden_count=hidden_count,
        featured_count=featured_count,
        missing_data_count=missing_data_count
    )

"""
VERIFICATION STEPS FOR /toggle-status ENDPOINT:
===============================================

Test commands for manual verification (requires admin panel running on localhost:5555):

1. Hide a movie:
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"movie_id": "12345", "status_type": "hidden", "value": true}'

2. Show a movie (unhide):
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"movie_id": "12345", "status_type": "hidden", "value": false}'

3. Feature a movie:
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"movie_id": "12345", "status_type": "featured", "value": true}'

4. Unfeature a movie:
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"movie_id": "12345", "status_type": "featured", "value": false}'

5. Test invalid status_type:
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"movie_id": "12345", "status_type": "invalid", "value": true}'
   Expected: {"success": false, "error": "Invalid status_type \"invalid\". Must be \"hidden\" or \"featured\""}

6. Test missing movie_id:
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"status_type": "hidden", "value": true}'
   Expected: {"success": false, "error": "Missing required parameter: movie_id"}

7. Test invalid value type:
   curl -X POST http://localhost:5555/toggle-status -u admin:changeme -H "Content-Type: application/json" -d '{"movie_id": "12345", "status_type": "hidden", "value": "not_boolean"}'
   Expected: {"success": false, "error": "Parameter value must be boolean"}

All tests should return HTTP 200. Success cases return {"success": true}, error cases return {"success": false, "error": "..."}
Check admin/hidden_movies.json and admin/featured_movies.json for file updates after successful operations.
"""

@app.route('/toggle-status', methods=['POST'])
@auth.login_required
def toggle_status() -> dict:
    """Toggle movie status (hidden or featured).

    Unified endpoint for toggling movie visibility and featured status.
    Replaces separate /toggle-hidden and /toggle-featured endpoints.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "movie_id": str,  # TMDB movie ID
            "status_type": str,  # 'hidden' or 'featured'
            "value": bool  # True to enable, False to disable
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "error": str  # On failure (invalid status_type or movie_id)
        }

    Examples:
        Hide a movie:
        {"movie_id": "12345", "status_type": "hidden", "value": true}

        Show a movie:
        {"movie_id": "12345", "status_type": "hidden", "value": false}

        Feature a movie:
        {"movie_id": "12345", "status_type": "featured", "value": true}
    """
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

        # Status type mapping
        STATUS_FILES = {
            'hidden': HIDDEN_FILE,
            'featured': FEATURED_FILE
        }

        STATUS_VERBS = {
            'hidden': ('hidden', 'shown'),
            'featured': ('featured', 'unfeatured')
        }

        if status_type not in STATUS_FILES:
            return jsonify({
                'success': False,
                'error': f'Invalid status_type "{status_type}". Must be "hidden" or "featured"'
            })

        # Load appropriate file
        file_path = STATUS_FILES[status_type]
        status_list = load_json(file_path, [])

        # Toggle logic
        if value and movie_id not in status_list:
            status_list.append(movie_id)
        elif not value and movie_id in status_list:
            status_list.remove(movie_id)

        # Save file
        save_json(file_path, status_list)

        # Log action
        verb_true, verb_false = STATUS_VERBS[status_type]
        action = verb_true if value else verb_false
        logger.info(f"Movie {movie_id} {action}")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error toggling {status_type} status for movie {movie_id}: {str(e)}")
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'})

@app.route('/update-date', methods=['POST'])
@auth.login_required
def update_date() -> dict:
    """Update movie's digital release date.

    Updates the date in movie_tracking.json and triggers data.json regeneration.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "movie_id": str,  # TMDB movie ID
            "digital_date": str  # ISO format YYYY-MM-DD
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,  # On success
            "error": str  # On failure
        }

    Raises:
        Returns error JSON if movie not found or regeneration fails
    """
    data = request.json
    movie_id = data.get('movie_id')
    new_date = data.get('digital_date')
    
    # Update in tracking database
    try:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)
        
        if movie_id in db['movies']:
            logger.info(f"Updating digital date for movie {movie_id} to {new_date}")
            db['movies'][movie_id]['digital_date'] = new_date
            db['movies'][movie_id]['manually_corrected'] = True

            safe_write_json('movie_tracking.json', db)

            # Regenerate data.json from movie_tracking.json
            try:
                result = subprocess.run(
                    ['python3', 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=60  # 1 minute timeout
                )
                if result.returncode == 0:
                    logger.info(f"Successfully updated date and regenerated data.json for movie {movie_id}")
                    return jsonify({'success': True, 'message': f'Date updated to {new_date} and data.json regenerated'})
                else:
                    logger.error(f"Date updated but regeneration failed for movie {movie_id}: {result.stderr}")
                    return jsonify({'success': False, 'error': f'Date updated but regeneration failed: {result.stderr}'})
            except subprocess.TimeoutExpired:
                logger.error(f"Date updated but regeneration timed out for movie {movie_id}")
                return jsonify({'success': False, 'error': 'Date updated but regeneration timed out'})
            except Exception as e:
                logger.error(f"Date updated but regeneration failed for movie {movie_id}: {str(e)}")
                return jsonify({'success': False, 'error': f'Date updated but regeneration failed: {str(e)}'})
    except Exception as e:
        logger.error(f"Failed to update date for movie {movie_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Movie not found'})


@app.route('/regenerate', methods=['POST'])
@auth.login_required
def regenerate() -> dict:
    """Manually trigger data.json regeneration.

    Runs generate_data.py as a subprocess to rebuild data.json from
    movie_tracking.json with all admin overrides applied.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,  # On success
            "output": str,  # Last 500 chars of stdout (on success)
            "error": str,  # On failure
            "stderr": str  # Last 500 chars of stderr (on failure)
        }

    Note:
        Has 2 minute timeout. Regeneration typically takes 10-30 seconds.
    """
    logger.info("Manual data.json regeneration triggered")
    try:
        result = subprocess.run(
            ['python3', 'generate_data.py'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout (longer than date update)
        )

        if result.returncode == 0:
            logger.info("Data.json regenerated successfully")
            return jsonify({
                'success': True,
                'message': 'data.json regenerated successfully',
                'output': result.stdout[-500:] if result.stdout else ''  # Last 500 chars
            })
        else:
            logger.error(f"Regeneration failed with exit code {result.returncode}: {result.stderr[-200:] if result.stderr else ''}")
            return jsonify({
                'success': False,
                'error': f'Regeneration failed with exit code {result.returncode}',
                'stderr': result.stderr[-500:] if result.stderr else ''
            })
    except subprocess.TimeoutExpired:
        logger.error("Regeneration timed out after 2 minutes")
        return jsonify({
            'success': False,
            'error': 'Regeneration timed out after 2 minutes'
        })
    except Exception as e:
        logger.error(f"Failed to trigger regeneration: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to trigger regeneration: {str(e)}'
        })

@app.route('/update-movie-fields', methods=['POST'])
@auth.login_required
def update_movie_fields() -> dict:
    """Update all editable fields for a movie.

    Updates fields directly in movie_tracking.json with validation,
    then triggers data.json regeneration.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "movie_id": str,  # Required
            "rt_score": int,  # Optional, 0-100
            "rt_link": str,  # Optional, must be valid URL
            "trailer_link": str,  # Optional, must be valid URL
            "director": str,  # Optional
            "country": str,  # Optional
            "poster_url": str,  # Optional, must be valid URL
            "digital_date": str,  # Optional, ISO format YYYY-MM-DD
            "synopsis": str,  # Optional, max 5000 chars
            "watch_links": {  # Optional
                "streaming": {"service": str, "link": str},
                "rent": {"service": str, "link": str},
                "buy": {"service": str, "link": str}
            }
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,  # Lists fields updated
            "error": str,  # On validation or save failure
            "warning": str  # If save succeeded but regeneration failed
        }

    Validation:
        - RT score: Must be integer 0-100
        - URLs: Must start with http:// or https://
        - Date: Must be ISO format YYYY-MM-DD
        - Synopsis: Max 5000 characters
        - Watch links: Must have service and link fields

    Note:
        All changes are marked with manual_* flags to prevent
        overwriting by daily scraper.
    """
    try:
        data = request.json
        movie_id = str(data.get('movie_id'))

        logger.info(f"Updating fields for movie {movie_id}")

        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID required'})

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
            # VALIDATION: RT score must be integer 0-100, reject floats
            rt_score_value = data['rt_score']

            # If it's already an int, accept it
            if isinstance(rt_score_value, int):
                rt_score = rt_score_value
            # If it's a string, ensure it matches an optional sign followed by digits only
            elif isinstance(rt_score_value, str):
                rt_score_str = rt_score_value.strip()
                # Check if it matches an integer pattern (optional sign + digits)
                import re
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
            # Reject floats or any other type
            else:
                return jsonify({
                    'success': False,
                    'error': 'RT score must be an integer between 0 and 100'
                })

            # Check range after confirming it's an integer
            if rt_score < 0 or rt_score > 100:
                return jsonify({
                    'success': False,
                    'error': 'RT score must be between 0 and 100'
                })

            # Update with validated integer value
            movie['rt_score'] = rt_score
            movie['manual_rt_score'] = True
            changes_made.append('RT Score')

        # Update Links
        if 'links' not in movie:
            movie['links'] = {}

        if 'rt_link' in data:
            rt_link = data['rt_link'].strip() if data['rt_link'] else ''

            if rt_link == '':
                # Empty string clears the field
                if 'rt' in movie.get('links', {}):
                    del movie['links']['rt']
                movie['manual_rt_link'] = False
                changes_made.append('RT Link (cleared)')
            else:
                # VALIDATION: URL must start with http:// or https://
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
                # Empty string clears the field
                if 'trailer' in movie.get('links', {}):
                    del movie['links']['trailer']
                movie['manual_trailer'] = False
                changes_made.append('Trailer (cleared)')
            else:
                # VALIDATION: URL must start with http:// or https://
                if not trailer_link.startswith(('http://', 'https://')):
                    return jsonify({
                        'success': False,
                        'error': 'Trailer link must be a valid URL starting with http:// or https://'
                    })

                movie['links']['trailer'] = trailer_link
                movie['manual_trailer'] = True
                changes_made.append('Trailer')

        # Update Director
        if 'director' in data:
            director = str(data['director']).strip() if data['director'] else ''

            if director == '':
                # Empty string clears the field
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
                # Empty string clears the field
                if 'country' in movie:
                    del movie['country']
                movie['manual_country'] = False
                changes_made.append('Country (cleared)')
            else:
                movie['country'] = country
                movie['manual_country'] = True
                changes_made.append('Country')

        # Update Poster URL
        if 'poster_url' in data:
            poster_url = data['poster_url'].strip() if data['poster_url'] else ''

            if poster_url == '':
                # Empty string clears the field
                if 'poster' in movie:
                    del movie['poster']
                movie['manual_poster'] = False
                changes_made.append('Poster (cleared)')
            else:
                # VALIDATION: URL must start with http:// or https://
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
                # Empty string clears the field
                if 'digital_date' in movie:
                    del movie['digital_date']
                changes_made.append('Digital Date (cleared)')
            else:
                # VALIDATION: Date must be ISO format YYYY-MM-DD
                try:
                    # This will raise ValueError if format is wrong or date is invalid
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
                # Empty string clears the field
                if 'synopsis' in movie:
                    del movie['synopsis']
                movie['manual_synopsis'] = False
                changes_made.append('Synopsis (cleared)')
            else:
                # VALIDATION: Maximum length check
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

                # VALIDATION: Watch links structure
                if not isinstance(watch_links, dict):
                    return jsonify({
                        'success': False,
                        'error': 'Watch links must be a dictionary'
                    })

                # Validate each category and normalize trimmed values
                for category in ['streaming', 'rent', 'buy']:
                    if category in watch_links:
                        cat_data = watch_links[category]

                        # Must have 'service' and 'link' keys
                        if not isinstance(cat_data, dict) or 'service' not in cat_data or 'link' not in cat_data:
                            return jsonify({
                                'success': False,
                                'error': f'Watch links {category} must have "service" and "link" fields'
                            })

                        # Service must be non-empty string and assign trimmed value back
                        service = str(cat_data['service']).strip()
                        if not service:
                            return jsonify({
                                'success': False,
                                'error': f'Watch links {category} service cannot be empty'
                            })
                        cat_data['service'] = service  # Persist normalized value

                        # Link validation and normalization
                        link = cat_data['link']
                        if link:
                            link = link.strip()
                            if not link:
                                # Empty string after trimming - treat as clearing the link
                                cat_data['link'] = None
                            elif not link.startswith(('http://', 'https://')):
                                return jsonify({
                                    'success': False,
                                    'error': f'Watch links {category} link must be a valid URL starting with http:// or https://'
                                })
                            else:
                                cat_data['link'] = link  # Persist normalized value
                        else:
                            cat_data['link'] = None  # Ensure null for empty

                # Save to movie_tracking.json (consistent with other manual corrections)
                movie['watch_links'] = watch_links
                movie['manual_watch_links'] = True
                changes_made.append('Watch Links')
            else:
                # Clear watch links when null or empty
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

        # Trigger regeneration of data.json
        try:
            result = subprocess.run(
                ['python3', 'generate_data.py'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.warning(f"Fields updated for movie {movie_id} but regeneration failed: {result.stderr}")
                return jsonify({
                    'success': True,
                    'message': f'Fields updated ({", ".join(changes_made)}) but regeneration failed',
                    'warning': result.stderr
                })
        except Exception as e:
            logger.warning(f"Fields updated for movie {movie_id} but regeneration failed: {str(e)}")
            return jsonify({
                'success': True,
                'message': f'Fields updated ({", ".join(changes_made)}) but regeneration failed: {str(e)}'
            })

        logger.info(f"Successfully updated and regenerated for movie {movie_id}: {', '.join(changes_made)}")
        return jsonify({
            'success': True,
            'message': f'Updated {", ".join(changes_made)} and regenerated data.json'
        })

    except Exception as e:
        logger.error(f"Error updating fields for movie {movie_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating fields: {str(e)}',
            'traceback': traceback.format_exc()
        })

@app.route('/create-youtube-playlist', methods=['POST'])
@auth.login_required
def create_youtube_playlist() -> dict:
    """Create a YouTube playlist with custom date parameters.

    Calls youtube_playlist_manager.py as a subprocess to create
    a playlist from movie trailers in data.json.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "date_type": str,  # 'last_x_days' or 'date_range'
            "days_back": int,  # Required if date_type='last_x_days'
            "from_date": str,  # Required if date_type='date_range' (YYYY-MM-DD)
            "to_date": str,  # Required if date_type='date_range' (YYYY-MM-DD)
            "title": str,  # Optional custom title
            "privacy": str,  # 'public', 'unlisted', or 'private'
            "dry_run": bool  # If true, preview only (don't create)
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,
            "playlist_url": str,  # YouTube playlist URL (if created)
            "title": str,  # Playlist title
            "video_count": int,  # Number of videos added
            "date_range": str,  # Date range covered
            "preview_videos": list,  # First 5 video titles (if dry_run)
            "error": str  # On failure
        }

    Note:
        Requires YouTube OAuth credentials in youtube_credentials/.
        Has 3 minute timeout for playlist creation.
        See YOUTUBE_PLAYLIST_SETUP.md for setup instructions.
    """
    try:
        data = request.json
        date_type = data.get('date_type', 'last_x_days')
        privacy = data.get('privacy', 'public')
        dry_run = data.get('dry_run', False)
        custom_title = data.get('title')

        logger.info(f"Creating YouTube playlist: {date_type}, privacy={privacy}, dry_run={dry_run}")

        # Build command arguments
        cmd = ['python3', 'youtube_playlist_manager.py', 'custom']

        if dry_run:
            cmd.append('--dry-run')

        cmd.extend(['--privacy', privacy])

        if custom_title:
            cmd.extend(['--title', custom_title])

        # Add date parameters
        if date_type == 'last_x_days':
            days_back = data.get('days_back', 7)
            cmd.extend(['--days-back', str(days_back)])
        else:  # date_range
            from_date = data.get('from_date')
            to_date = data.get('to_date')

            if not from_date or not to_date:
                return jsonify({
                    'success': False,
                    'error': 'Both from_date and to_date required for date range'
                })

            cmd.extend(['--from-date', from_date, '--to-date', to_date])

        # Run the playlist manager
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout
        )

        if result.returncode == 0:
            # Parse output for details
            output = result.stdout

            response_data = {
                'success': True,
                'message': 'Playlist created successfully' if not dry_run else 'Preview generated'
            }

            # Try to extract playlist URL from output
            import re
            url_match = re.search(r'https://youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)', output)
            if url_match:
                response_data['playlist_url'] = url_match.group(0)

            # Extract title
            title_match = re.search(r'Title: (.+)', output)
            if title_match:
                response_data['title'] = title_match.group(1).strip()

            # Extract video count
            video_match = re.search(r'Videos: (\d+)', output)
            if video_match:
                response_data['video_count'] = int(video_match.group(1))

            # Extract date range
            date_match = re.search(r'Date range: (.+)', output)
            if date_match:
                response_data['date_range'] = date_match.group(1).strip()

            # Extract preview videos (first 5)
            preview_matches = re.findall(r'• (.+) - https://youtube\.com/watch', output)
            if preview_matches:
                response_data['preview_videos'] = preview_matches[:5]

            logger.info(f"YouTube playlist created: {response_data.get('title', 'Unknown')} with {response_data.get('video_count', 0)} videos")
            return jsonify(response_data)
        else:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            logger.error(f"YouTube playlist creation failed: {error_msg[-200:]}")
            return jsonify({
                'success': False,
                'error': f'Playlist creation failed: {error_msg[-500:]}'  # Last 500 chars
            })

    except subprocess.TimeoutExpired:
        logger.error("YouTube playlist creation timed out after 3 minutes")
        return jsonify({
            'success': False,
            'error': 'Playlist creation timed out after 3 minutes'
        })
    except Exception as e:
        logger.error(f"Error creating YouTube playlist: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error creating playlist: {str(e)}',
            'traceback': traceback.format_exc()
        })

if __name__ == '__main__':
    print("\n🎬 New Release Wall Admin Panel")
    print("================================")
    print("Starting server at http://localhost:5555")
    print(f"\n🔐 Authentication enabled")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Password: {'*' * len(ADMIN_PASSWORD)}")
    if ADMIN_PASSWORD == 'changeme':
        print("\n⚠️  WARNING: Using default password!")
        print("   Set ADMIN_PASSWORD environment variable for production")
    print("\nPress Ctrl+C to stop\n")

    # Ensure admin directory exists
    os.makedirs('admin', exist_ok=True)

    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5555)
