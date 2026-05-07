"""Admin panel TMDB API integration."""

import os
import requests
from typing import Optional, Union

from admin.logging_setup import logger
from admin.utils import load_config


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
        response = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": api_key, "language": "en-US"},
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
