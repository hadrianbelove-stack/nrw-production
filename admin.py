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

from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()

# CSRF Protection
def generate_csrf_token():
    """Generate a CSRF token for the current session"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf_token():
    """Validate CSRF token from request headers or form data"""
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    return token and session.get('csrf_token') == token

def csrf_protect(f):
    """Decorator to protect endpoints with CSRF validation"""
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PATCH', 'PUT', 'DELETE']:
            if not validate_csrf_token():
                return jsonify({
                    'success': False,
                    'error': 'Invalid or missing CSRF token'
                }), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Make csrf_token available to all templates
@app.context_processor
def inject_csrf_token():
    """Inject CSRF token into all template contexts"""
    return dict(csrf_token=generate_csrf_token)

# Production environment check and credential enforcement
def check_production_environment():
    """Enforce secure credentials in production environment"""
    is_production = (
        os.environ.get('FLASK_ENV') == 'production' or
        os.environ.get('ENV') == 'production' or
        not os.environ.get('FLASK_DEBUG', '').lower() in ('true', '1', 'yes')
    )

    if is_production:
        if not os.environ.get('ADMIN_USERNAME'):
            print("ERROR: ADMIN_USERNAME environment variable must be set in production")
            exit(1)
        if not os.environ.get('ADMIN_PASSWORD'):
            print("ERROR: ADMIN_PASSWORD environment variable must be set in production")
            exit(1)
        if os.environ.get('ADMIN_PASSWORD') == 'changeme':
            print("ERROR: Default password 'changeme' is not allowed in production")
            exit(1)

# Check environment at startup
check_production_environment()

# Load credentials from environment or use defaults (only in development!)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme')

# Global flag for full-review mode
FULL_REVIEW_MODE = False

# Session tracking variables
SESSION_START_TIME = None
SESSION_COUNTERS = {
    'edits': 0,
    'additions': 0,
    'hidden': 0,
    'featured': 0,
    'ordered': 0
}

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
REVIEWS_FILE = 'admin/movie_reviews.json'


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
    """Compute SHA-256 hash of movie_tracking.json for approval validation.

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
    """Compute delta summary for approval artifact.

    Returns:
        Dictionary with counts of various changes since session start
    """
    global SESSION_COUNTERS

    hidden = load_json(HIDDEN_FILE, [])
    featured = load_json(FEATURED_FILE, [])
    reviews = load_json(REVIEWS_FILE, {})
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
        'edits': SESSION_COUNTERS.get('edits', 0),
        'additions': SESSION_COUNTERS.get('additions', 0),
        'hidden': SESSION_COUNTERS.get('hidden', 0),  # Actual changes, not total count
        'featured': SESSION_COUNTERS.get('featured', 0),  # Actual changes, not total count
        'ordered': SESSION_COUNTERS.get('ordered', 0),  # Number of ordering operations
        'movies_reviewed': len(movies_list),
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
    global SESSION_START_TIME, SESSION_COUNTERS

    # Initialize session tracking on first access in full-review mode
    if FULL_REVIEW_MODE and SESSION_START_TIME is None:
        SESSION_START_TIME = datetime.utcnow()
        SESSION_COUNTERS = {
            'edits': 0,
            'additions': 0,
            'hidden': 0,
            'featured': 0,
            'ordered': 0
        }
        logger.info(f"Session started at {SESSION_START_TIME.isoformat()}Z for full-review mode")

    data = load_json(DATA_FILE, {})
    hidden = load_json(HIDDEN_FILE, [])
    featured = load_json(FEATURED_FILE, [])
    reviews = load_json(REVIEWS_FILE, default={})

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

        # Include review data in movie normalization
        movie_copy['review'] = reviews.get(movie_id, {})

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

    # Calculate reviewed movies count (only for displayed movies)
    processed_movie_ids = set(processed_movies.keys())
    reviewed_count = len([movie_id for movie_id in reviews.keys() if movie_id in processed_movie_ids])


    return render_template(
        'index.html',
        movies=processed_movies,
        hidden=hidden,
        featured=featured,
        reviews=reviews,
        visible_count=visible_count,
        hidden_count=hidden_count,
        featured_count=featured_count,
        missing_data_count=missing_data_count,
        bootstrap_count=bootstrap_count,
        reviewed_count=reviewed_count,
        full_review_mode=FULL_REVIEW_MODE
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
@csrf_protect
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

        # Increment session counters for tracking real changes
        global SESSION_COUNTERS
        if FULL_REVIEW_MODE and changed:
            if status_type == 'hidden':
                SESSION_COUNTERS['hidden'] += 1
            elif status_type == 'featured':
                SESSION_COUNTERS['featured'] += 1

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
@csrf_protect
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

            # Increment session counter for tracking edits
            global SESSION_COUNTERS
            if FULL_REVIEW_MODE:
                SESSION_COUNTERS['edits'] += 1

            # Regenerate data.json from movie_tracking.json (skip in full-review mode)
            if FULL_REVIEW_MODE:
                logger.info(f"Date updated for movie {movie_id} (regeneration skipped in full-review mode)")
                return jsonify({
                    'success': True,
                    'message': f'Date updated to {new_date}. Click "Approve & Generate" to regenerate data.json'
                })
            else:
                try:
                    result = subprocess.run(
                        [sys.executable, 'generate_data.py'],
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

@app.route('/update-review', methods=['POST'])
@auth.login_required
@csrf_protect
def update_review() -> dict:
    """Update or create a movie review.

    Updates review data in admin/movie_reviews.json and triggers data.json regeneration.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "movie_id": str,  # Required TMDB movie ID
            "review_text": str,  # Required review content
            "author": str,  # Optional author name (default "Admin")
            "rating": float,  # Optional rating 0-5
            "featured_in_newsletter": bool  # Optional newsletter flag (default false)
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,  # On success
            "error": str  # On failure
        }

    Validation:
        - movie_id: Must exist in tracking data
        - review_text: Required, non-empty, max 5000 chars
        - rating: Optional, must be 0-5 if provided
        - author: Optional string
        - featured_in_newsletter: Optional boolean
    """
    try:
        data = request.json
        movie_id = data.get('movie_id')
        review_text = data.get('review_text', '').strip()
        author = data.get('author', 'Admin').strip() or 'Admin'
        rating = data.get('rating')
        featured = data.get('featured_in_newsletter', False)

        # Validation
        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID required'})

        movie_id = str(movie_id).strip()
        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID cannot be empty'})

        if not review_text:
            return jsonify({'success': False, 'error': 'Review text required'})

        if len(review_text) > 5000:
            return jsonify({'success': False, 'error': 'Review text too long (max 5000 characters)'})

        # Validate rating if provided
        if rating is not None:
            try:
                rating = float(rating)
                if rating < 0 or rating > 5:
                    return jsonify({'success': False, 'error': 'Rating must be between 0 and 5'})
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Rating must be a number between 0 and 5'})

        # Verify movie exists in tracking data
        try:
            with open('movie_tracking.json', 'r') as f:
                tracking_data = json.load(f)
            if movie_id not in tracking_data.get('movies', {}):
                return jsonify({'success': False, 'error': f'Movie {movie_id} not found in tracking database'})
            movie_title = tracking_data['movies'][movie_id].get('title', f'Movie {movie_id}')
        except FileNotFoundError:
            return jsonify({'success': False, 'error': 'movie_tracking.json not found'})

        # Load existing reviews
        reviews = load_json(REVIEWS_FILE, default={})

        # Create review entry
        now = datetime.now().isoformat()
        review_entry = {
            'review': review_text,
            'author': author,
            'featured_in_newsletter': featured,
            'last_modified': now
        }

        if rating is not None:
            review_entry['rating'] = rating

        # Preserve added_date if review already exists, otherwise set it
        if movie_id in reviews and 'added_date' in reviews[movie_id]:
            review_entry['added_date'] = reviews[movie_id]['added_date']
        else:
            review_entry['added_date'] = now

        # Update reviews
        reviews[movie_id] = review_entry

        # Save atomically
        os.makedirs('admin', exist_ok=True)
        safe_write_json(REVIEWS_FILE, reviews)

        # Log action
        logger.info(f"Review saved for movie {movie_id} ({movie_title}) by {author}")

        # Trigger data regeneration (skip in full-review mode)
        if FULL_REVIEW_MODE:
            logger.info(f"Review saved for movie {movie_id} (regeneration skipped in full-review mode)")
            return jsonify({
                'success': True,
                'message': 'Review saved. Click "Approve & Generate" to regenerate data.json'
            })
        else:
            try:
                result = subprocess.run(
                    [sys.executable, 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.warning(f"Review saved for movie {movie_id} but regeneration failed: {result.stderr}")
                    return jsonify({
                        'success': True,
                        'message': 'Review saved but data regeneration failed',
                        'warning': result.stderr
                    })
            except Exception as e:
                logger.warning(f"Review saved for movie {movie_id} but regeneration failed: {str(e)}")
                return jsonify({
                    'success': True,
                    'message': f'Review saved but regeneration failed: {str(e)}'
                })

        return jsonify({
            'success': True,
            'message': 'Review saved successfully'
        })

    except Exception as e:
        logger.error(f"Error saving review for movie {movie_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error saving review: {str(e)}'
        })

@app.route('/delete-review', methods=['POST'])
@auth.login_required
@csrf_protect
def delete_review() -> dict:
    """Delete a movie review.

    Removes review from admin/movie_reviews.json and triggers data.json regeneration.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "movie_id": str  # Required TMDB movie ID
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,  # On success
            "error": str  # On failure
        }
    """
    try:
        data = request.json
        movie_id = data.get('movie_id')

        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID required'})

        movie_id = str(movie_id).strip()
        if not movie_id:
            return jsonify({'success': False, 'error': 'Movie ID cannot be empty'})

        # Load existing reviews
        reviews = load_json(REVIEWS_FILE, default={})

        # Check if review exists
        if movie_id not in reviews:
            return jsonify({'success': False, 'error': 'Review not found'})

        # Remove review
        del reviews[movie_id]

        # Save atomically
        safe_write_json(REVIEWS_FILE, reviews)

        # Log action
        logger.info(f"Review deleted for movie {movie_id}")

        # Trigger data regeneration (skip in full-review mode)
        if FULL_REVIEW_MODE:
            logger.info(f"Review deleted for movie {movie_id} (regeneration skipped in full-review mode)")
            return jsonify({
                'success': True,
                'message': 'Review deleted. Click "Approve & Generate" to regenerate data.json'
            })
        else:
            try:
                result = subprocess.run(
                    [sys.executable, 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.warning(f"Review deleted for movie {movie_id} but regeneration failed: {result.stderr}")
                    return jsonify({
                        'success': True,
                        'message': 'Review deleted but data regeneration failed',
                        'warning': result.stderr
                    })
            except Exception as e:
                logger.warning(f"Review deleted for movie {movie_id} but regeneration failed: {str(e)}")
                return jsonify({
                    'success': True,
                    'message': f'Review deleted but regeneration failed: {str(e)}'
                })

        return jsonify({
            'success': True,
            'message': 'Review deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting review for movie {movie_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error deleting review: {str(e)}'
        })

@app.route('/regenerate', methods=['POST'])
@auth.login_required
@csrf_protect
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
            [sys.executable, 'generate_data.py'],
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
@csrf_protect
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
            "error": str,  # On validation or save failure
            "warning": str  # If save succeeded but regeneration failed
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

        # Increment session counter for tracking edits
        global SESSION_COUNTERS
        if FULL_REVIEW_MODE and changes_made:
            SESSION_COUNTERS['edits'] += len(changes_made)

        logger.info(f"Saved {len(changes_made)} field changes for movie {movie_id}: {', '.join(changes_made)}")

        # Trigger regeneration of data.json (skip in full-review mode)
        if FULL_REVIEW_MODE:
            logger.info(f"Fields updated for movie {movie_id} (regeneration skipped in full-review mode): {', '.join(changes_made)}")
            return jsonify({
                'success': True,
                'message': f'Fields updated ({", ".join(changes_made)}). Click "Approve & Generate" to regenerate data.json'
            })
        else:
            try:
                result = subprocess.run(
                    [sys.executable, 'generate_data.py'],
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

@app.route('/add-movie', methods=['POST'])
@auth.login_required
def add_movie() -> dict:
    """Add a new movie manually to the tracking database.

    Creates a new entry in movie_tracking.json for movies missed by discovery.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

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

        # Increment session counter for tracking additions
        global SESSION_COUNTERS
        if FULL_REVIEW_MODE:
            SESSION_COUNTERS['additions'] += 1

        logger.info(f"Manually added movie {tmdb_id}: {title}")

        # Don't regenerate in full-review mode
        message = f'Movie "{title}" added successfully'
        if FULL_REVIEW_MODE:
            message += '. Click "Approve & Generate" to include in data.json'
        else:
            # Try to regenerate in normal mode
            try:
                result = subprocess.run(
                    [sys.executable, 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0:
                    message += ' and data.json regenerated'
                else:
                    message += ' but data regeneration failed'
            except Exception:
                message += ' but data regeneration failed'

        return jsonify({
            'success': True,
            'message': message,
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
@auth.login_required
def update_ordering() -> dict:
    """Update editorial ordering of movies.

    Saves ordered array of TMDB IDs to admin/ordering.json for pinning
    specific movies to the top of the display list.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

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

        # Increment session counter for tracking ordering changes
        global SESSION_COUNTERS
        if FULL_REVIEW_MODE:
            SESSION_COUNTERS['ordered'] += 1

        logger.info(f"Editorial ordering updated with {len(normalized_ids)} movies")

        # Don't regenerate in full-review mode
        message = f'Editorial ordering updated with {len(normalized_ids)} movies'
        if FULL_REVIEW_MODE:
            message += '. Click "Approve & Generate" to apply ordering'
        else:
            # Try to regenerate in normal mode
            try:
                result = subprocess.run(
                    [sys.executable, 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0:
                    message += ' and data.json regenerated'
                else:
                    message += ' but data regeneration failed'
            except Exception:
                message += ' but data regeneration failed'

        return jsonify({
            'success': True,
            'message': message,
            'ordered_count': len(normalized_ids)
        })

    except Exception as e:
        logger.error(f"Error updating ordering: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating ordering: {str(e)}'
        })

@app.route('/csrf-token', methods=['GET'])
@auth.login_required
def get_csrf_token() -> dict:
    """Get CSRF token for API requests."""
    return jsonify({
        'csrf_token': generate_csrf_token()
    })

@app.route('/delta-summary', methods=['GET'])
@auth.login_required
def delta_summary() -> Union[Response, tuple[Response, int]]:
    """Get current delta summary without creating approval file.

    Returns the result of compute_delta_summary() for preview purposes.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

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

@app.route('/drafts', methods=['GET'])
@auth.login_required
def get_drafts() -> dict:
    """Get all drafts sorted by createdAt descending.

    Returns drafts with newest first for admin review.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Returns:
        JSON response:
        {
            "success": bool,
            "drafts": list,  # Array of draft objects sorted by createdAt desc
            "count": int,  # Total number of drafts
            "error": str  # On failure
        }
    """
    try:
        drafts_dir = 'admin/drafts'

        if not os.path.exists(drafts_dir):
            return jsonify({
                'success': True,
                'drafts': [],
                'count': 0
            })

        drafts = []

        # Load all draft files
        for filename in os.listdir(drafts_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(drafts_dir, filename)
                try:
                    with open(file_path, 'r') as f:
                        draft = json.load(f)
                        drafts.append(draft)
                except Exception as e:
                    logger.warning(f"Failed to load draft {filename}: {e}")

        # Sort by createdAt descending (newest first)
        drafts.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

        return jsonify({
            'success': True,
            'drafts': drafts,
            'count': len(drafts)
        })

    except Exception as e:
        logger.error(f"Error getting drafts: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error getting drafts: {str(e)}'
        })

@app.route('/drafts/<draft_id>', methods=['PATCH'])
@auth.login_required
@csrf_protect
def update_draft(draft_id: str) -> dict:
    """Update title fields in a draft.

    Allows inline editing of draft titles before publishing.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "titles": list  # Updated array of titles
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,
            "error": str  # On failure
        }
    """
    try:
        data = request.json or {}
        new_titles = data.get('titles', [])

        if not isinstance(new_titles, list):
            return jsonify({
                'success': False,
                'error': 'titles must be an array'
            })

        # Load existing draft
        draft_file = f'admin/drafts/{draft_id}.json'
        if not os.path.exists(draft_file):
            return jsonify({
                'success': False,
                'error': f'Draft {draft_id} not found'
            })

        with open(draft_file, 'r') as f:
            draft = json.load(f)

        # Update titles
        draft['titles'] = new_titles
        draft['lastModified'] = datetime.now().isoformat()

        # Save atomically
        safe_write_json(draft_file, draft)

        logger.info(f"Draft {draft_id} updated by {auth.current_user()}")

        return jsonify({
            'success': True,
            'message': 'Draft updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating draft {draft_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error updating draft: {str(e)}'
        })

@app.route('/drafts/<draft_id>/publish', methods=['POST'])
@auth.login_required
@csrf_protect
def publish_draft(draft_id: str) -> dict:
    """Publish a draft to production data.json.

    Validates the draft, writes to production data atomically,
    and triggers site update.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,
            "publishedId": str,  # Draft ID that was published
            "timestamp": str,  # ISO timestamp of publish
            "error": str  # On failure
        }
    """
    try:
        # Load draft
        draft_file = f'admin/drafts/{draft_id}.json'
        if not os.path.exists(draft_file):
            return jsonify({
                'success': False,
                'error': f'Draft {draft_id} not found'
            })

        with open(draft_file, 'r') as f:
            draft = json.load(f)

        # Validate draft
        validation_result = validate_draft(draft)
        if not validation_result['valid']:
            return jsonify({
                'success': False,
                'error': f'Draft validation failed: {validation_result["error"]}'
            })

        # Load current data.json
        if not os.path.exists('data.json'):
            return jsonify({
                'success': False,
                'error': 'data.json not found'
            })

        with open('data.json', 'r') as f:
            current_data = json.load(f)

        # Apply title changes from draft before atomic write
        movie_ids = draft.get('movieIds', [])
        draft_titles = draft.get('titles', [])

        # Validate title array and movieIds alignment
        if len(draft_titles) != len(movie_ids):
            return jsonify({
                'success': False,
                'error': f'Title count ({len(draft_titles)}) does not match movie IDs count ({len(movie_ids)})'
            })

        # Validate non-empty titles
        for i, title in enumerate(draft_titles):
            if not title or not title.strip():
                return jsonify({
                    'success': False,
                    'error': f'Empty title at index {i} for movie ID {movie_ids[i]}'
                })

        # Apply title changes to movies in current_data
        if 'movies' in current_data:
            movies_by_id = {str(movie.get('id', '')): movie for movie in current_data['movies']}
            for i, movie_id in enumerate(movie_ids):
                if str(movie_id) in movies_by_id and i < len(draft_titles):
                    movies_by_id[str(movie_id)]['title'] = draft_titles[i].strip()

        # Update data.json atomically
        current_data['published_at'] = datetime.now().isoformat()
        current_data['published_draft_id'] = draft_id

        # Write to temp file first, then rename atomically
        temp_file = 'data.json.tmp'
        try:
            with open(temp_file, 'w') as f:
                json.dump(current_data, f, indent=2)
            os.replace(temp_file, 'data.json')
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise e

        # Trigger site update (repository dispatch or commit)
        trigger_site_update(draft_id)

        # Log audit record
        log_publish_audit(auth.current_user(), draft_id)

        # Remove published draft
        os.remove(draft_file)

        logger.info(f"Draft {draft_id} published by {auth.current_user()}")

        return jsonify({
            'success': True,
            'message': 'Draft published successfully',
            'publishedId': draft_id,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error publishing draft {draft_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error publishing draft: {str(e)}'
        })

def validate_draft(draft: dict) -> dict:
    """Validate a draft before publishing.

    Runs schema checks, slug uniqueness, and data quality rules.

    Args:
        draft: Draft object to validate

    Returns:
        dict: {'valid': bool, 'error': str}
    """
    try:
        # Check required fields
        required_fields = ['id', 'createdAt', 'movieIds']
        for field in required_fields:
            if field not in draft:
                return {'valid': False, 'error': f'Missing required field: {field}'}

        # Check movie IDs are valid
        movie_ids = draft.get('movieIds', [])
        if not movie_ids:
            return {'valid': False, 'error': 'Draft has no movie IDs'}

        # Validate against tracking data
        try:
            with open('movie_tracking.json', 'r') as f:
                tracking_data = json.load(f)
        except FileNotFoundError:
            return {'valid': False, 'error': 'movie_tracking.json not found'}

        movies_db = tracking_data.get('movies', {})
        for movie_id in movie_ids:
            if str(movie_id) not in movies_db:
                return {'valid': False, 'error': f'Movie ID {movie_id} not found in tracking database'}

        # Check source digest if provided
        source_digest = draft.get('sourceDigest')
        if source_digest:
            with open('movie_tracking.json', 'rb') as f:
                current_digest = hashlib.sha256(f.read()).hexdigest()
            if source_digest != current_digest:
                return {'valid': False, 'error': 'Source data has changed since draft was created'}

        # Additional data quality checks when publishing
        try:
            result = validate_data_quality_for_publish()
            if not result['valid']:
                return result
        except Exception as e:
            return {'valid': False, 'error': f'Data quality check failed: {str(e)}'}

        return {'valid': True, 'error': None}

    except Exception as e:
        return {'valid': False, 'error': f'Validation error: {str(e)}'}

def validate_data_quality_for_publish() -> dict:
    """Run data quality checks before publishing.

    Returns:
        dict: {'valid': bool, 'error': str}
    """
    try:
        # Check data.json exists and is valid
        if not os.path.exists('data.json'):
            return {'valid': False, 'error': 'data.json file not found'}

        file_size = os.path.getsize('data.json')
        if file_size < 1000:  # Less than 1KB
            return {'valid': False, 'error': f'data.json file suspiciously small: {file_size} bytes'}

        # Load and validate JSON structure
        with open('data.json', 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                return {'valid': False, 'error': f'data.json is not valid JSON: {e}'}

        # Validate schema structure
        if not isinstance(data, dict):
            return {'valid': False, 'error': f'data.json root is not a dict: {type(data)}'}

        # Check required root keys
        required_root_keys = ['generated_at', 'count', 'movies']
        for key in required_root_keys:
            if key not in data:
                return {'valid': False, 'error': f'data.json missing required key: {key}'}

        # Check data types
        if not isinstance(data['movies'], list):
            return {'valid': False, 'error': f'data.json movies must be list, got {type(data["movies"])}'}

        # Check minimum movie count
        movies = data['movies']
        if len(movies) < 50:
            return {'valid': False, 'error': f'Very low movie count ({len(movies)}) - expected at least 50'}

        # Check for recent movies (7-day window)
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        recent_movies = [m for m in movies if m.get('digital_date', '') >= cutoff_date]

        if len(recent_movies) == 0:
            return {'valid': False, 'error': f'No recent movies found in last 7 days (since {cutoff_date})'}

        return {'valid': True, 'error': None}

    except Exception as e:
        return {'valid': False, 'error': f'Data quality validation error: {str(e)}'}

def trigger_site_update(draft_id: str):
    """Trigger site update after successful publish.

    Tries repository_dispatch first, falls back to git commit/push.

    Args:
        draft_id: ID of the published draft
    """
    try:
        # Try to trigger GitHub repository dispatch
        result = subprocess.run([
            'gh', 'api', 'repos/:owner/:repo/dispatches',
            '--method', 'POST',
            '--field', 'event_type=publish-draft',
            '--field', f'client_payload[draft_id]={draft_id}'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            logger.info(f"Repository dispatch triggered for draft {draft_id}")
            return

        logger.warning(f"Repository dispatch failed: {result.stderr}")

    except Exception as e:
        logger.warning(f"GitHub CLI failed: {e}")

    # Fallback: commit and push data.json to trigger publish workflow
    try:
        # Configure git identity for commits
        subprocess.run(['git', 'config', 'user.email', 'noreply@nrw.bot'],
                      capture_output=True, check=True)
        subprocess.run(['git', 'config', 'user.name', 'NRW Admin Bot'],
                      capture_output=True, check=True)

        # Add, commit and push data.json
        subprocess.run(['git', 'add', 'data.json'],
                      capture_output=True, check=True)

        commit_msg = f"Publish draft {draft_id}\n\n🤖 Generated with [Claude Code](https://claude.ai/code)\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        subprocess.run(['git', 'commit', '-m', commit_msg],
                      capture_output=True, check=True)

        subprocess.run(['git', 'push', 'origin', 'main'],
                      capture_output=True, check=True)

        logger.info(f"Git fallback successful - committed and pushed data.json for draft {draft_id}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Git fallback failed: {e}")

        # Final fallback: try GitHub REST API directly
        try:
            import os
            token = os.environ.get('GITHUB_TOKEN') or os.environ.get('PUBLISH_TOKEN')
            if not token:
                logger.error("No GitHub token available for API fallback")
                return

            import urllib.request
            import json as json_lib

            # Get repository info from git remote
            result = subprocess.run(['git', 'remote', 'get-url', 'origin'],
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("Could not get git remote URL")
                return

            remote_url = result.stdout.strip()
            # Extract owner/repo from git URL
            if 'github.com' in remote_url:
                parts = remote_url.replace('.git', '').split('/')
                owner_repo = f"{parts[-2]}/{parts[-1]}"

                # Make GitHub API request
                api_url = f"https://api.github.com/repos/{owner_repo}/dispatches"
                data = json_lib.dumps({
                    'event_type': 'publish-draft',
                    'client_payload': {'draft_id': draft_id}
                }).encode('utf-8')

                req = urllib.request.Request(api_url, data, {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json'
                })

                urllib.request.urlopen(req)
                logger.info(f"GitHub API fallback successful for draft {draft_id}")

        except Exception as api_e:
            logger.error(f"GitHub API fallback also failed: {api_e}")
            logger.error("All trigger methods failed - manual intervention required")

def log_publish_audit(user: str, draft_id: str, additional_data: dict = None):
    """Log audit record for publish action.

    Args:
        user: Username who performed the publish
        draft_id: ID of the draft that was published
        additional_data: Optional additional audit data
    """
    try:
        os.makedirs('metrics', exist_ok=True)

        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'publish_draft',
            'user': user,
            'draft_id': draft_id,
            'user_agent': request.headers.get('User-Agent', 'unknown'),
            'ip_address': request.remote_addr,
            'session_id': session.get('csrf_token', 'unknown')[:8]  # First 8 chars for session tracking
        }

        if additional_data:
            audit_entry.update(additional_data)

        # Write to both audit logs
        with open('metrics/publish.jsonl', 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')
            f.flush()

        # Also write to daily.jsonl for consolidated metrics
        daily_entry = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': audit_entry['timestamp'],
            'user': user,
            'action': 'publish_draft',
            'draft_id': draft_id
        }
        with open('metrics/daily.jsonl', 'a') as f:
            f.write(json.dumps(daily_entry) + '\n')
            f.flush()

    except Exception as e:
        logger.warning(f"Failed to log audit record: {e}")

@app.route('/drafts/<draft_id>/preview', methods=['POST'])
@auth.login_required
def preview_draft(draft_id: str) -> dict:
    """Generate a preview of how a draft will look when published.

    Creates a temporary preview artifact or URL using the edited content.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Returns:
        JSON response:
        {
            "success": bool,
            "preview_url": str,  # URL to preview content
            "preview_data": dict,  # Preview data object
            "expires_at": str,  # Preview expiration time
            "error": str  # On failure
        }
    """
    try:
        # Load draft
        draft_file = f'admin/drafts/{draft_id}.json'
        if not os.path.exists(draft_file):
            return jsonify({
                'success': False,
                'error': f'Draft {draft_id} not found'
            })

        with open(draft_file, 'r') as f:
            draft = json.load(f)

        # Load current data.json to build preview
        if not os.path.exists('data.json'):
            return jsonify({
                'success': False,
                'error': 'data.json not found for preview generation'
            })

        with open('data.json', 'r') as f:
            current_data = json.load(f)

        # Get movie IDs from draft
        movie_ids = draft.get('movieIds', [])
        draft_titles = draft.get('titles', [])

        # Build preview data with updated titles
        preview_movies = []
        current_movies = {str(m.get('id', '')): m for m in current_data.get('movies', [])}

        for i, movie_id in enumerate(movie_ids):
            if str(movie_id) in current_movies:
                movie = current_movies[str(movie_id)].copy()
                # Use edited title if available
                if i < len(draft_titles) and draft_titles[i]:
                    movie['title'] = draft_titles[i]
                    movie['title_edited'] = True
                preview_movies.append(movie)

        # Create preview data structure
        preview_data = {
            'generated_at': datetime.now().isoformat(),
            'preview_of_draft': draft_id,
            'count': len(preview_movies),
            'movies': preview_movies,
            'is_preview': True,
            'expires_at': (datetime.now() + timedelta(hours=1)).isoformat()
        }

        # Generate preview file or URL
        preview_id = f"preview_{draft_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Option 1: Save as temporary file (expires in 1 hour)
        os.makedirs('admin/previews', exist_ok=True)
        preview_file = f'admin/previews/{preview_id}.json'

        with open(preview_file, 'w') as f:
            json.dump(preview_data, f, indent=2)

        # Option 2: Generate preview URL (if using a preview service)
        # For now, we'll use a local file approach
        preview_url = f'/admin/preview/{preview_id}'

        logger.info(f"Preview generated for draft {draft_id} by {auth.current_user()}")

        return jsonify({
            'success': True,
            'preview_url': preview_url,
            'preview_data': {
                'movie_count': len(preview_movies),
                'edited_titles': sum(1 for t in draft_titles if t),
                'draft_id': draft_id
            },
            'expires_at': preview_data['expires_at'],
            'preview_id': preview_id
        })

    except Exception as e:
        logger.error(f"Error generating preview for draft {draft_id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error generating preview: {str(e)}'
        })

@app.route('/admin/preview/<preview_id>')
@auth.login_required
def serve_preview(preview_id: str):
    """Serve a preview file.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Returns:
        JSON preview data or 404 if expired/not found
    """
    try:
        preview_file = f'admin/previews/{preview_id}.json'

        if not os.path.exists(preview_file):
            return jsonify({
                'error': 'Preview not found or expired'
            }), 404

        # Check if preview has expired
        with open(preview_file, 'r') as f:
            preview_data = json.load(f)

        expires_at = preview_data.get('expires_at')
        if expires_at:
            try:
                exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now() > exp_time.replace(tzinfo=None):
                    # Preview expired - clean up and return 404
                    os.remove(preview_file)
                    return jsonify({
                        'error': 'Preview has expired'
                    }), 404
            except:
                pass  # If we can't parse expiry, serve the preview anyway

        return jsonify(preview_data)

    except Exception as e:
        logger.error(f"Error serving preview {preview_id}: {str(e)}")
        return jsonify({
            'error': 'Error serving preview'
        }), 500

@app.route('/approve', methods=['POST'])
@auth.login_required
def approve_changes() -> Union[Response, tuple[Response, int]]:
    """DEPRECATED: Create admin approval artifact for orchestrator.

    This endpoint is deprecated in favor of the drafts→publish workflow.
    Use GET /drafts to list drafts and POST /drafts/:id/publish instead.

    Authentication:
        Requires HTTP Basic Auth (@auth.login_required)

    Request JSON:
        {
            "reviewer": str,  # Optional reviewer name (defaults to current user)
            "trigger_generation": bool  # Optional flag to trigger generation (full-review mode only)
        }

    Returns:
        JSON response:
        {
            "success": bool,
            "message": str,
            "approval_file": str,  # Path to created approval file
            "timestamp": str,  # ISO timestamp of approval
            "delta": dict,  # Delta summary
            "generation_status": str,  # Status if generation was triggered
            "error": str  # On failure
        }
    """
    try:
        # Add deprecation warning
        logger.warning(f"DEPRECATED: /approve endpoint called by {auth.current_user()}. Use drafts→publish workflow instead.")

        data = request.json or {}
        reviewer = data.get('reviewer', auth.current_user() or 'admin')
        trigger_generation = data.get('trigger_generation', False)

        # Compute tracking digest and validate it exists
        tracking_digest = compute_tracking_digest()
        if tracking_digest is None:
            return jsonify({
                'success': False,
                'error': 'Cannot compute tracking digest - movie_tracking.json not found or unreadable'
            }), 400

        # Create approval artifact
        approval = {
            'timestamp': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
            'reviewer': reviewer,
            'tracking_digest': tracking_digest,
            'delta': compute_delta_summary()
        }

        # Get delta reference before using it
        delta = approval['delta']

        # Ensure admin directory exists
        os.makedirs('admin', exist_ok=True)

        # Write approval file atomically
        approval_file = 'admin/approval.json'
        safe_write_json(approval_file, approval)

        logger.info(f"Admin approval created by {reviewer}")

        # Create metrics entry if directory exists
        try:
            os.makedirs('metrics', exist_ok=True)

            # Calculate session duration
            global SESSION_START_TIME, SESSION_COUNTERS
            session_seconds = None
            if SESSION_START_TIME:
                session_duration = datetime.utcnow() - SESSION_START_TIME
                session_seconds = int(session_duration.total_seconds())

            metrics_entry = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': approval['timestamp'],
                'reviewer': reviewer,
                'session_seconds': session_seconds,
                'movies_reviewed': delta.get('movies_reviewed', 0),
                'edits': delta.get('edits', 0),
                'additions': delta.get('additions', 0),
                'hidden': delta.get('hidden', 0),
                'featured': delta.get('featured', 0),
                'ordered': delta.get('ordered', 0),
                'issues': delta.get('issues', {})
            }

            # Append to daily.jsonl atomically
            with open('metrics/daily.jsonl', 'a') as f:
                f.write(json.dumps(metrics_entry) + '\n')
                f.flush()

        except Exception as e:
            logger.warning(f"Failed to write metrics: {e}")

        # Append delta summary to diary
        try:
            os.makedirs('diary', exist_ok=True)
            today_utc = datetime.utcnow().strftime('%Y-%m-%d')
            diary_file = f'diary/{today_utc}.md'

            # Create diary entry header if file doesn't exist
            if not os.path.exists(diary_file):
                header_content = f"""# Daily Log - {today_utc}

## Admin Delta

"""
                with open(diary_file, 'w') as f:
                    f.write(header_content)

            # Generate compact JSON delta summary
            delta_json = {
                'timestamp': approval['timestamp'],
                'reviewer': reviewer,
                'movies_reviewed': delta.get('movies_reviewed', 0),
                'edits': delta.get('edits', 0),
                'additions': delta.get('additions', 0),
                'hidden': delta.get('hidden', 0),
                'featured': delta.get('featured', 0),
                'ordered': delta.get('ordered', 0),
                'issues': delta.get('issues', {})
            }

            # Append to diary file atomically
            delta_entry = f"\n**{approval['timestamp']}** - Admin approval by {reviewer}:\n```json\n{json.dumps(delta_json, indent=2)}\n```\n"
            with open(diary_file, 'a') as f:
                f.write(delta_entry)
                f.flush()

            logger.info(f"Admin delta appended to diary {diary_file}")

        except Exception as e:
            logger.warning(f"Failed to write to diary: {e}")

        response_data = {
            'success': True,
            'message': 'Changes approved successfully',
            'approval_file': approval_file,
            'timestamp': approval['timestamp'],
            'reviewer': reviewer,
            'delta': approval['delta']
        }

        # Trigger generation if requested and in full-review mode
        if trigger_generation and FULL_REVIEW_MODE:
            logger.info(f"Triggering generation after approval by {reviewer}")
            try:
                result = subprocess.run(
                    [sys.executable, 'generate_data.py'],
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout
                )

                if result.returncode == 0:
                    response_data['message'] = 'Changes approved and data.json generated successfully'
                    response_data['generation_status'] = 'success'
                    logger.info(f"Approval and generation completed successfully by {reviewer}")
                else:
                    response_data['message'] = 'Changes approved but generation failed'
                    response_data['generation_status'] = 'failed'
                    response_data['generation_error'] = result.stderr[-500:] if result.stderr else 'Unknown error'
                    logger.error(f"Approval succeeded but generation failed: {result.stderr}")

            except subprocess.TimeoutExpired:
                response_data['message'] = 'Changes approved but generation timed out'
                response_data['generation_status'] = 'timeout'
                logger.error("Approval succeeded but generation timed out")
            except Exception as e:
                response_data['message'] = f'Changes approved but generation failed: {str(e)}'
                response_data['generation_status'] = 'error'
                response_data['generation_error'] = str(e)
                logger.error(f"Approval succeeded but generation failed: {str(e)}")

        elif trigger_generation and not FULL_REVIEW_MODE:
            response_data['message'] = 'Changes approved (generation trigger ignored - not in full-review mode)'
            response_data['generation_status'] = 'skipped'

        # Reset session counters after successful approval
        if FULL_REVIEW_MODE:
            SESSION_COUNTERS = {
                'edits': 0,
                'additions': 0,
                'hidden': 0,
                'featured': 0,
                'ordered': 0
            }
            SESSION_START_TIME = None
            logger.info("Session counters reset after approval")

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error creating approval: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error creating approval: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='NRW Admin Panel')
    parser.add_argument('--full-review', action='store_true',
                        help='Enable full-review mode with mandatory approval gate')
    args = parser.parse_args()

    # Set global full-review mode flag
    FULL_REVIEW_MODE = args.full_review

    print("\n🎬 New Release Wall Admin Panel")
    print("================================")

    if FULL_REVIEW_MODE:
        print("🔒 FULL REVIEW MODE ENABLED")
        print("   Auto-regeneration disabled")
        print("   Use 'Approve & Generate' button to authorize publication")

    # Configure debug and host based on environment
    flask_debug = os.environ.get('FLASK_DEBUG', '').lower() in ('true', '1', 'yes')
    flask_env = os.environ.get('FLASK_ENV', 'development').lower()

    # Production safety: disable debug and restrict host
    is_production = flask_env == 'production' or not flask_debug

    if is_production:
        debug_mode = False
        host = '127.0.0.1'  # Localhost only for production
        print("Starting server at http://127.0.0.1:5555 (production mode)")
        print("🔒 Production mode: debug=False, host=127.0.0.1")
    else:
        debug_mode = True
        host = '0.0.0.0'  # All interfaces for development
        print("Starting server at http://0.0.0.0:5555 (development mode)")
        print("🔧 Development mode: debug=True, host=0.0.0.0")

    print(f"\n🔐 Authentication enabled")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Password: {'*' * len(ADMIN_PASSWORD)}")
    if ADMIN_PASSWORD == 'changeme':
        print("\n⚠️  WARNING: Using default password!")
        print("   Set ADMIN_PASSWORD environment variable for production")
    print("\nPress Ctrl+C to stop\n")

    # Ensure admin directory exists
    os.makedirs('admin', exist_ok=True)

    # Run the Flask app with environment-appropriate settings
    app.run(debug=debug_mode, host=host, port=5555)
