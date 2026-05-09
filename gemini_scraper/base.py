"""
Gemini finder base class and shared utilities.

Provides: GeminiFinderBase (cache, rate limiting, retry, API init),
_load_config(), _get_gemini_api_key().
"""

import load_env  # Load .env into os.environ
import json
import os
import re
import time
import logging
import random
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger('gemini_scraper')


def _load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    try:
        import yaml
        config_path = Path(__file__).parent.parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config.yaml: {e}")
    return {}


def _get_gemini_api_key() -> Optional[str]:
    """Get Gemini API key from environment or config."""
    # Environment variable takes precedence
    key = os.environ.get('GEMINI_API_KEY')
    if key:
        return key

    # Fall back to config.yaml
    config = _load_config()
    return config.get('api', {}).get('gemini_api_key')


class GeminiFinderBase:
    """
    Base class for all Gemini-powered finders.

    Provides shared functionality:
    - Gemini API initialization
    - Rate limiting between API calls
    - Retry with exponential backoff
    - Cache load/save
    - Cleanup interface
    """

    # Subclasses set this for log messages (e.g., "YouTube", "RT", "Wikipedia")
    _finder_name = 'Gemini'

    def __init__(self, cache_file: str):
        """Initialize common Gemini finder attributes.

        Args:
            cache_file: Path to cache file
        """
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.client = None
        self.types = None
        self.grounding_tool = None
        self.model_name = None
        self._initialized = False

        # Load config values from config.yaml
        config = _load_config()
        scraper_config = config.get('gemini_scraper', {})
        self.timeout_seconds = scraper_config.get('timeout_seconds', 30)
        self.rate_limit = scraper_config.get('rate_limit', 1.0)
        self.cache_ttl_days = scraper_config.get('cache_ttl_days', 90)
        self.max_retries = scraper_config.get('max_retries', 3)
        self.last_request_time = 0

        # Error log for diagnostic breadcrumbs (capped at 50)
        self._error_log = []

        # Base stats - subclasses extend via _get_extra_stats()
        self.stats = {
            'gemini_attempts': 0,
            'gemini_successes': 0,
            'gemini_failures': 0,
            'cache_hits': 0,
            'retries': 0
        }
        self.stats.update(self._get_extra_stats())

    def _get_extra_stats(self) -> Dict[str, int]:
        """Override in subclasses to add finder-specific stats."""
        return {}

    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load {self._finder_name} cache: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save {self._finder_name} cache: {e}")

    def _enforce_rate_limit(self):
        """Ensure minimum time between API requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _retry_with_backoff(self, fn, max_attempts: int = None):
        """Retry function with exponential backoff.

        Args:
            fn: Function to call (should return result or raise exception)
            max_attempts: Maximum retry attempts (defaults to self.max_retries)

        Returns:
            Result from fn, or None if all attempts failed
        """
        if max_attempts is None:
            max_attempts = self.max_retries

        from datetime import datetime

        for attempt in range(max_attempts):
            try:
                result = fn()
                if result is not None:
                    return result
                # fn returned None - still counts as "success" (no error)
                return None
            except Exception as e:
                # Classify error type for breadcrumbs
                etype = type(e).__name__
                emsg = str(e).lower()
                if 'resourceexhausted' in etype.lower() or '429' in str(e) or 'quota' in emsg:
                    error_type = 'rate_limit'
                elif 'deadline' in etype.lower() or 'timeout' in emsg:
                    error_type = 'timeout'
                elif 'unauthenticated' in etype.lower() or 'invalid api key' in emsg:
                    error_type = 'auth_error'
                else:
                    error_type = etype

                if len(self._error_log) < 50:
                    self._error_log.append({
                        'error_type': error_type,
                        'message': str(e)[:500],
                        'timestamp': datetime.now().isoformat(),
                    })

                if attempt < max_attempts - 1:
                    # Exponential backoff: 0.5s, 1s, 2s, capped at 5s
                    base_delay = 0.5 * (2 ** attempt)
                    delay = min(5.0, base_delay)
                    # Add jitter (±20%)
                    jitter = random.uniform(-0.2 * delay, 0.2 * delay)
                    sleep_time = delay + jitter
                    logger.warning(f"{self._finder_name} attempt {attempt + 1} failed ({error_type}): {e}, retrying in {sleep_time:.1f}s")
                    self.stats['retries'] += 1
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All {max_attempts} {self._finder_name} attempts failed ({error_type}): {e}")
        return None

    def _generate(self, contents, config=None):
        """Call Gemini generate_content with timeout protection.

        All finders should use this instead of calling
        self.client.models.generate_content() directly.
        """
        http_opts = self.types.HttpOptions(timeout=self.timeout_seconds)
        if config is not None:
            config.http_options = http_opts
        else:
            config = self.types.GenerateContentConfig(http_options=http_opts)
        return self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=config,
        )

    def _init_gemini(self) -> bool:
        """Initialize Gemini API client. Returns True if successful."""
        if self._initialized:
            return self.client is not None

        self._initialized = True

        api_key = _get_gemini_api_key()
        if not api_key:
            logger.error(f"No Gemini API key found for {self._finder_name} finder")
            return False

        try:
            from google import genai
            from google.genai import types

            self.client = genai.Client(api_key=api_key)
            self.types = types
            self.grounding_tool = types.Tool(google_search=types.GoogleSearch())
            self.model_name = 'gemini-2.5-flash'

            logger.info(f"Gemini {self._finder_name} finder initialized")
            return True

        except ImportError:
            logger.error("google-genai not installed. Run: pip install google-genai")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Gemini for {self._finder_name}: {e}")
            return False

    def get_error_log(self):
        """Return error log for diagnostic breadcrumbs."""
        return list(self._error_log)

    def get_stats(self) -> Dict[str, int]:
        """Return statistics about finder usage."""
        return self.stats.copy()

    def cleanup(self):
        """Clean up resources. Override in subclasses if needed."""
        pass

    def close(self):
        """Alias for cleanup (compatibility with other scrapers)."""
        self.cleanup()
