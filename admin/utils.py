"""Admin panel utility functions."""

import os
import json
import hashlib
import yaml
from datetime import datetime
from typing import Optional, Union

from file_lock import safe_write_json, safe_write_json_atomic
from admin.config import PENDING_CHANGES_FLAG
from admin.logging_setup import logger


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
