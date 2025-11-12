#!/usr/bin/env python3
"""
Admin panel for curating movie selections.
Simple Flask app for editing movie data and controlling visibility.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, session
import json
import os
import subprocess
import sys
import argparse
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
import yaml
import glob
import shutil
import logging
from logging.handlers import RotatingFileHandler
import traceback
from typing import Dict, List, Optional, Union, Any, Tuple
import requests
from file_lock import safe_write_json, safe_write_json_atomic

app = Flask(__name__,
            template_folder='admin/templates',
            static_folder='admin/static',
            static_url_path='/admin/static')

# Configure session security
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# Security headers and HTTPS enforcement
@app.before_request
def security_headers():
    """Enforce security policies before each request."""
    # HTTPS enforcement in production
    if os.environ.get('FLASK_ENV') == 'production' and not request.is_secure:
        return redirect(request.url.replace('http://', 'https://'), code=301)

@app.after_request
def apply_security_headers(response):
    """Apply security headers to all responses."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    # Prevent content type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # XSS protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # CSP for admin panel (strict)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'"
    )
    response.headers['Content-Security-Policy'] = csp

    return response

# Authentication removed for local development


# Authentication removed for local development

# Password verification removed for local development

# Configuration
DATA_FILE = 'data.json'  # Root directory - production display data
HIDDEN_FILE = 'admin/hidden_movies.json'  # Admin overrides
FEATURED_FILE = 'admin/featured_movies.json'  # Admin overrides
WATCH_LINK_OVERRIDES_FILE = 'admin/watch_link_overrides.json'
PENDING_CHANGES_FLAG = 'admin/.pending_changes'  # Dirty flag for unsaved changes


def mark_changes_pending() -> None:
    """Mark that changes have been made and need to be saved.

    Creates a flag file to indicate pending changes.
    """
    try:
        os.makedirs('admin', exist_ok=True)
        with open(PENDING_CHANGES_FLAG, 'w') as f:
            f.write(datetime.now().isoformat())
        logger.debug("Marked changes as pending")
    except Exception as e:
        logger.warning(f"Failed to mark changes as pending: {e}")

def clear_changes_pending() -> None:
    """Clear the pending changes flag after successful save.

    Removes the flag file.
    """
    try:
        if os.path.exists(PENDING_CHANGES_FLAG):
            os.remove(PENDING_CHANGES_FLAG)
        logger.debug("Cleared pending changes flag")
    except Exception as e:
        logger.warning(f"Failed to clear pending changes flag: {e}")

def has_pending_changes() -> bool:
    """Check if there are pending changes that need to be saved.

    Returns:
        True if changes are pending, False otherwise
    """
    return os.path.exists(PENDING_CHANGES_FLAG)


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

def compute_tracking_digest() -> Optional[str]:
    """Compute SHA-256 hash of movie_tracking.json for change tracking.

    Returns:
        SHA-256 hex digest string, or None if file not found
    """
    try:
        with open('movie_tracking.json', 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        logger.warning("movie_tracking.json not found for digest computation")
        return None
    except Exception as e:
        logger.error(f"Error computing tracking digest: {e}")
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
    hidden = load_json(HIDDEN_FILE, [])
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

        # Check for missing stream/rent/buy links
        watch_links = movie.get('watch_links', {})
        providers = movie.get('providers', {})

        if not (watch_links.get('streaming') or providers.get('streaming')):
            issues['missing_stream_link'] += 1
        if not (watch_links.get('rent') or providers.get('rent')):
            issues['missing_rent_link'] += 1
        if not (watch_links.get('buy') or providers.get('buy')):
            issues['missing_buy_link'] += 1

    return {
        'new_films_released': new_films_released,
        'issues': issues
    }

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
        else:
            logger.warning(f"TMDB API returned status {response.status_code} for movie ID {tmdb_id}")
            return None
    except (requests.Timeout, requests.RequestException) as e:
        logger.warning(f"Request error fetching poster for TMDB ID {tmdb_id}: {str(e)}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error fetching poster for TMDB ID {tmdb_id}: {str(e)}")
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

def format_subprocess_output(text: Optional[str], max_chars: int = 500) -> str:
    """Format subprocess output with consistent truncation.

    Truncates long output to last N characters for logging and responses.

    Args:
        text: Output text to format (stdout or stderr)
        max_chars: Maximum characters to keep (default 500)

    Returns:
        Formatted output string (last max_chars if text is longer)
    """
    if not text:
        return ''
    return text[-max_chars:] if len(text) > max_chars else text


def validate_movie_update_request(data: dict) -> tuple[bool, Optional[str]]:
    """
    Validate JSON request for movie field updates.

    Args:
        data: Request JSON data

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])

    Schema:
        - movie_id: required, non-empty string
        - rt_score: optional, integer 0-100
        - rt_link, trailer_link, wikipedia_link, poster_url: optional, valid HTTP(S) URL
        - director, country: optional, string max 200 chars
        - year: optional, integer 1900-2100
        - runtime: optional, integer 1-500
        - digital_date: optional, ISO format YYYY-MM-DD
        - synopsis: optional, string max 5000 chars
        - watch_links: optional, dict with streaming/vod keys
    """
    # List of allowed fields
    ALLOWED_FIELDS = {
        'movie_id', 'rt_score', 'rt_link', 'trailer_link', 'wikipedia_link',
        'director', 'country', 'year', 'runtime', 'poster_url',
        'digital_date', 'synopsis', 'watch_links'
    }

    # Check for unexpected fields
    unexpected = set(data.keys()) - ALLOWED_FIELDS
    if unexpected:
        return False, f"Unexpected fields: {', '.join(unexpected)}"

    # Validate movie_id (required)
    if 'movie_id' not in data or not data['movie_id']:
        return False, "movie_id is required and cannot be empty"

    if not isinstance(data['movie_id'], (str, int)):
        return False, "movie_id must be a string or integer"

    # Validate string length limits
    if 'director' in data and data['director']:
        if len(str(data['director'])) > 200:
            return False, "director must be 200 characters or less"

    if 'country' in data and data['country']:
        if len(str(data['country'])) > 200:
            return False, "country must be 200 characters or less"

    if 'synopsis' in data and data['synopsis']:
        if len(str(data['synopsis'])) > 5000:
            return False, "synopsis must be 5000 characters or less"

    # Validate URLs (basic check - detailed validation happens in endpoint)
    url_fields = ['rt_link', 'trailer_link', 'wikipedia_link', 'poster_url']
    for field in url_fields:
        if field in data and data[field]:
            url = str(data[field]).strip()
            if url and not url.startswith(('http://', 'https://')):
                return False, f"{field} must be a valid URL starting with http:// or https://"

    # Validate year range
    if 'year' in data and data['year'] is not None:
        try:
            year = int(data['year'])
            if year < 1900 or year > 2100:
                return False, "year must be between 1900 and 2100"
        except (ValueError, TypeError):
            return False, "year must be a valid integer"

    # Validate runtime range
    if 'runtime' in data and data['runtime'] is not None:
        try:
            runtime = int(data['runtime'])
            if runtime < 1 or runtime > 500:
                return False, "runtime must be between 1 and 500 minutes"
        except (ValueError, TypeError):
            return False, "runtime must be a valid integer"

    # Validate RT score
    if 'rt_score' in data and data['rt_score'] is not None:
        try:
            score = int(data['rt_score'])
            if score < 0 or score > 100:
                return False, "rt_score must be between 0 and 100"
        except (ValueError, TypeError):
            return False, "rt_score must be a valid integer"

    # Validate watch_links structure
    if 'watch_links' in data and data['watch_links']:
        if not isinstance(data['watch_links'], dict):
            return False, "watch_links must be a dictionary"

        allowed_categories = {'streaming', 'vod'}
        for category, link_data in data['watch_links'].items():
            if category not in allowed_categories:
                return False, f"watch_links category must be one of: {', '.join(allowed_categories)}"

            if not isinstance(link_data, dict):
                return False, f"watch_links.{category} must be a dictionary"

            if 'service' not in link_data or 'link' not in link_data:
                return False, f"watch_links.{category} must have 'service' and 'link' keys"

    return True, None

# safe_write_json now imported from file_lock.py (with file locking support)


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
    record.user = 'system'
    return record

logging.setLogRecordFactory(record_factory)

# Initialize logger
logger = setup_logger('admin', 'logs/admin.log', logging.INFO)

@app.route('/')
def index() -> str:
    """Main admin panel page.

    Displays all movies in a grid with filtering, search, and inline editing.
    Shows statistics (total, visible, hidden, featured, missing data counts).

    Authentication:
        No authentication required for local development

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
            for category in ['streaming', 'vod']:
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

        # Skip synchronous TMDB poster fetching to avoid slowing admin page
        # Poster URLs should be precomputed in generate_data.py or fetched client-side
        # if not movie_copy.get('poster_url') and not movie_copy.get('poster') and movie_copy.get('id'):
        #     movie_copy['poster_url'] = get_poster_url(movie_copy['id'])

        # Normalize rt_score to integer for template comparisons
        if movie_copy.get('rt_score'):
            rt_score_str = str(movie_copy['rt_score']).strip().replace('%', '')
            try:
                movie_copy['rt_score'] = int(rt_score_str)
            except (ValueError, TypeError):
                movie_copy['rt_score'] = None

        # Add bootstrap date and manually corrected flags for display
        movie_copy['bootstrap_date'] = movie_copy.get('bootstrap_date', False)
        movie_copy['manually_corrected'] = movie_copy.get('manually_corrected', False)

        processed_movies[movie_id] = movie_copy

    # Calculate stats
    total_count = len(movies_list)
    hidden_count = len(hidden)
    visible_count = total_count - hidden_count
    featured_count = len(featured)

    # Calculate missing data count
    missing_data_count = sum(
        1 for movie in processed_movies.values()
        if not movie.get('links', {}).get('trailer')
        or not (movie.get('poster_url') or movie.get('poster'))
        or not movie.get('director')
        or movie.get('director') == 'Unknown'
        or not movie.get('country')
    )

    # Calculate bootstrap movies count
    bootstrap_count = sum(1 for movie in processed_movies.values() if movie.get('bootstrap_date'))

    return render_template(
        'index.html',
        movies=processed_movies,
        hidden=hidden,
        featured=featured,
        visible_count=visible_count,
        hidden_count=hidden_count,
        featured_count=featured_count,
        missing_data_count=missing_data_count,
        bootstrap_count=bootstrap_count
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
def toggle_status() -> dict:
    """Toggle movie status (hidden or featured).

    Unified endpoint for toggling movie visibility and featured status.
    Replaces separate /toggle-hidden and /toggle-featured endpoints.

    Authentication:
        No authentication required for local development

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

        # Toggle logic and track changes
        changed = False
        if value and movie_id not in status_list:
            status_list.append(movie_id)
            changed = True
        elif not value and movie_id in status_list:
            status_list.remove(movie_id)
            changed = True

        # Save file with atomic write
        # Ensure admin directory exists
        os.makedirs('admin', exist_ok=True)
        safe_write_json(file_path, status_list)

        # Mark changes as pending if state actually changed
        if changed:
            mark_changes_pending()

        # Increment session counters for tracking real changes
        # Log action
        verb_true, verb_false = STATUS_VERBS[status_type]
        action = verb_true if value else verb_false
        logger.info(f"Movie {movie_id} {action}")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error toggling {status_type} status for movie {movie_id}: {str(e)}")
        return jsonify({'success': False, 'error': f'Internal error: {str(e)}'})

@app.route('/update-date', methods=['POST'])
def update_date() -> dict:
    """Update movie's digital release date.

    Updates the date in movie_tracking.json and sets a pending flag requiring a later publish via POST /regenerate.

    Authentication:
        No authentication required for local development

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
        Returns error JSON if movie not found or validation fails
    """
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

@app.route('/regenerate', methods=['POST'])
def regenerate() -> dict:
    """Manually trigger data.json regeneration.

    Runs generate_data.py as a subprocess to rebuild data.json from
    movie_tracking.json with all admin overrides applied.

    Authentication:
        No authentication required for local development

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
            [sys.executable, 'generate_data.py'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout (longer than date update)
        )

        if result.returncode == 0:
            logger.info("Data.json regenerated successfully")
            # Clear pending changes flag after successful regeneration
            clear_changes_pending()
            return jsonify({
                'success': True,
                'message': 'Changes saved successfully',
                'output': format_subprocess_output(result.stdout)
            })
        else:
            logger.error(f"Regeneration failed with exit code {result.returncode}: {format_subprocess_output(result.stderr)}")
            return jsonify({
                'success': False,
                'error': f'Regeneration failed with exit code {result.returncode}',
                'stderr': format_subprocess_output(result.stderr)
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
def update_movie_fields() -> dict:
    """Update all editable fields for a movie.

    Updates fields directly in movie_tracking.json with validation
    and sets a pending flag requiring a later publish via POST /regenerate.

    Authentication:
        No authentication required for local development

    Request JSON:
        {
            "movie_id": str,  # Required
            "rt_score": int,  # Optional, 0-100
            "rt_link": str,  # Optional, must be valid URL
            "trailer_link": str,  # Optional, must be valid URL
            "wikipedia_link": str,  # Optional, must be valid URL
            "director": str,  # Optional
            "country": str,  # Optional
            "year": int,  # Optional, 1900-2100
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
            "error": str  # On validation or save failure
        }

    Validation:
        - RT score: Must be integer 0-100
        - Year: Must be integer 1900-2100
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

        # Validate request schema first (new as of 2025-11-09)
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

        # Update Wikipedia Link
        if 'wikipedia_link' in data:
            wikipedia_link = data['wikipedia_link'].strip() if data['wikipedia_link'] else ''

            if wikipedia_link == '':
                # Empty string clears the field
                if 'wikipedia' in movie.get('links', {}):
                    del movie['links']['wikipedia']
                movie['manual_wikipedia'] = False
                changes_made.append('Wikipedia (cleared)')
            else:
                # VALIDATION: URL must start with http:// or https://
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

        # Update Year
        if 'year' in data and data['year'] is not None:
            year_value = data['year']

            # Validate year is an integer
            if isinstance(year_value, int):
                year = year_value
            elif isinstance(year_value, str):
                year_str = year_value.strip()
                import re
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

            # Validate year range (1900-2100)
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

            # Validate runtime is an integer
            if isinstance(runtime_value, int):
                runtime = runtime_value
            elif isinstance(runtime_value, str):
                runtime_str = runtime_value.strip()
                import re
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

            # Validate runtime range (1-500 minutes)
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
                for category in ['streaming', 'vod']:
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

        # Mark that changes need to be saved
        mark_changes_pending()

        logger.info(f"Successfully updated fields for movie {movie_id}: {', '.join(changes_made)}")
        return jsonify({
            'success': True,
            'message': f'Updated {", ".join(changes_made)}. Click "Save Changes" to rebuild.'
        })

    except Exception as e:
        logger.error(f"Error updating fields for movie {movie_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating fields: {str(e)}',
            'traceback': traceback.format_exc()
        })

@app.route('/create-youtube-playlist', methods=['POST'])
def create_youtube_playlist() -> dict:
    """Create a YouTube playlist with custom date parameters.

    Calls youtube_playlist_manager.py as a subprocess to create
    a playlist from movie trailers in data.json.

    Authentication:
        No authentication required for local development

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
        cmd = [sys.executable, 'youtube_playlist_manager.py', 'custom']

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
            logger.error(f"YouTube playlist creation failed: {format_subprocess_output(error_msg)}")
            return jsonify({
                'success': False,
                'error': f'Playlist creation failed: {format_subprocess_output(error_msg)}'
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

@app.route('/add-movie', methods=['POST'])
def add_movie() -> dict:
    """Add a new movie manually to the tracking database.

    Creates a new entry in movie_tracking.json for movies missed by discovery.

    Authentication:
        No authentication required for local development

    Request JSON:
        {
            "tmdb_id": str,  # Required TMDB movie ID (numeric string)
            "title": str,  # Required movie title
            "digital_date": str,  # Optional YYYY-MM-DD format
            "providers": dict,  # Optional provider data
            "synopsis": str,  # Optional synopsis
            "poster_url": str  # Optional poster URL
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,
            "movie_id": str,  # TMDB ID of added movie
            "error": str  # On failure
        }
    """
    try:
        data = request.json or {}
        tmdb_id = str(data.get('tmdb_id', '')).strip()
        title = str(data.get('title', '')).strip()
        digital_date = data.get('digital_date', '').strip() if data.get('digital_date') else None
        providers = data.get('providers', {})
        synopsis = data.get('synopsis', '').strip() if data.get('synopsis') else None
        poster_url = data.get('poster_url', '').strip() if data.get('poster_url') else None

        # Validation
        if not tmdb_id:
            return jsonify({'success': False, 'error': 'TMDB ID is required'})

        if not title:
            return jsonify({'success': False, 'error': 'Movie title is required'})

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

        # Check if movie already exists
        if tmdb_id in tracking_data.get('movies', {}):
            return jsonify({
                'success': False,
                'error': f'Movie with TMDB ID {tmdb_id} already exists'
            })

        # Try to fetch basic TMDB data if API key available
        tmdb_data = {}
        api_key = get_tmdb_api_key()
        if api_key:
            try:
                response = requests.get(
                    f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                    params={"api_key": api_key},
                    timeout=10
                )
                if response.status_code == 200:
                    tmdb_data = response.json()
                    logger.info(f"Fetched TMDB data for {tmdb_id}: {tmdb_data.get('title', 'Unknown')}")
                else:
                    logger.warning(f"TMDB API returned {response.status_code} for movie {tmdb_id}")
            except Exception as e:
                logger.warning(f"Failed to fetch TMDB data for {tmdb_id}: {e}")

        # Create movie entry
        now = datetime.now().isoformat()
        movie_entry = {
            'id': tmdb_id,
            'title': title,
            'manually_added': True,
            'source': 'admin',
            'added_date': now,
            'last_manual_edit': now,
            'manually_corrected': True
        }

        # Set status based on digital date
        if digital_date:
            movie_entry['digital_date'] = digital_date
            movie_entry['status'] = 'available'
        else:
            movie_entry['status'] = 'tracking'

        # Add TMDB data if available
        if tmdb_data:
            if tmdb_data.get('release_date'):
                movie_entry['theatrical_date'] = tmdb_data['release_date']
            if tmdb_data.get('overview'):
                movie_entry['synopsis'] = synopsis or tmdb_data['overview']
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

        # Add to tracking database
        if 'movies' not in tracking_data:
            tracking_data['movies'] = {}

        tracking_data['movies'][tmdb_id] = movie_entry

        # Save atomically
        safe_write_json('movie_tracking.json', tracking_data)

        logger.info(f"Manually added movie {tmdb_id}: {title}")

        # Mark that changes need to be saved
        mark_changes_pending()

        return jsonify({
            'success': True,
            'message': f'Movie "{title}" added successfully. Click "Save Changes" to rebuild.',
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

@app.route('/update-ordering', methods=['POST'])
def update_ordering() -> dict:
    """Update editorial ordering of movies.

    Saves ordered array of TMDB IDs to admin/ordering.json for pinning
    specific movies to the top of the display list.

    Authentication:
        No authentication required for local development

    Request JSON:
        {
            "ordered_ids": list  # Array of TMDB IDs in desired order
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,
            "ordered_count": int,  # Number of movies in ordering
            "error": str  # On failure
        }
    """
    try:
        data = request.json or {}
        ordered_ids = data.get('ordered_ids', [])

        # Validate that ordered_ids is a list
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


@app.route('/pending-changes', methods=['GET'])
def pending_changes() -> dict:
    """Check if there are pending changes that need to be saved.

    Authentication:
        No authentication required for local development

    Returns:
        JSON response:
        {
            "has_pending_changes": bool,
            "pending_change_count": int
        }
    """
    return jsonify({
        'has_pending_changes': has_pending_changes(),
        'pending_change_count': 0  # Draft system removed - always 0
    })

@app.route('/delta-summary', methods=['GET'])
def delta_summary() -> Union[Response, tuple[Response, int]]:
    """Get current delta summary for preview.

    Returns the result of compute_delta_summary() for preview purposes.

    Authentication:
        No authentication required for local development

    Returns:
        JSON response:
        {
            "success": bool,
            "delta": dict,  # Delta summary
            "error": str  # On failure
        }
    """
    try:
        delta = compute_delta_summary()

        return jsonify({
            'success': True,
            'delta': delta
        })

    except Exception as e:
        logger.error(f"Error computing delta summary: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error computing delta summary: {str(e)}'
        }), 500


@app.route('/filter-data', methods=['GET'])
def filter_data() -> dict:
    """Get hidden and featured movie IDs for frontend filtering.

    Returns:
        dict: JSON response with hidden and featured movie ID lists
    """
    try:
        # Load hidden movies
        hidden_ids = []
        if os.path.exists(HIDDEN_FILE):
            try:
                with open(HIDDEN_FILE, 'r') as f:
                    hidden_ids = json.load(f)
            except (json.JSONDecodeError, TypeError):
                hidden_ids = []

        # Load featured movies
        featured_ids = []
        if os.path.exists(FEATURED_FILE):
            try:
                with open(FEATURED_FILE, 'r') as f:
                    featured_ids = json.load(f)
            except (json.JSONDecodeError, TypeError):
                featured_ids = []

        return jsonify({
            'success': True,
            'hidden': hidden_ids,
            'featured': featured_ids
        })

    except Exception as e:
        logger.error(f"Error loading filter data: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error loading filter data: {str(e)}'
        }), 500


if __name__ == '__main__':
    print("\n🎬 NRW Admin Panel - Local Curation Mode (No Authentication Required) - Port: 5556")
    print("==================================================================")

    # Configure debug and host based on environment
    flask_debug = os.environ.get('FLASK_DEBUG', '').lower() in ('true', '1', 'yes')
    flask_env = os.environ.get('FLASK_ENV', 'development').lower()

    # Default to development mode for local access
    port = int(os.environ.get('ADMIN_PORT', 5556))
    debug_mode = True
    host = '0.0.0.0'  # All interfaces for development

    print(f"🚀 Admin panel available at http://localhost:{port}")
    print("🔓 No authentication required - direct access enabled\n")
    print("\nPress Ctrl+C to stop\n")

    # Ensure admin directory exists
    os.makedirs('admin', exist_ok=True)

    # Run the Flask app with environment-appropriate settings
    port = int(os.environ.get('ADMIN_PORT', 5556))
    app.run(debug=debug_mode, host=host, port=port)
