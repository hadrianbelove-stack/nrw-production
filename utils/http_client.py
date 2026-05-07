"""
Shared HTTP client utilities for the NRW pipeline.

Provides pre-configured requests Sessions with automatic retry on transient failures.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Set


# Default status codes to retry on (rate limit + server errors)
DEFAULT_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def create_retry_session(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: Optional[Set[int]] = None,
) -> requests.Session:
    """Create a requests Session with automatic retry on transient failures.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Multiplier for exponential backoff between retries (default: 1.0).
            With backoff_factor=1: retries at 0s, 1s, 2s, 4s, ...
        status_forcelist: HTTP status codes that trigger a retry
            (default: {429, 500, 502, 503, 504})

    Returns:
        A configured requests.Session instance
    """
    if status_forcelist is None:
        status_forcelist = DEFAULT_RETRY_STATUS_CODES

    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session
