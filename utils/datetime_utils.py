"""
Shared date/time utilities for the NRW pipeline.

Consolidates common patterns: ISO timestamps, date parsing, cache freshness checks.
Available for any module to import. Not yet adopted by all files — migration
happens organically over time.
"""

from datetime import datetime, timedelta
from typing import Optional


def get_today() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return datetime.now().strftime('%Y-%m-%d')


def get_iso_now() -> str:
    """Return current timestamp in ISO 8601 format."""
    return datetime.now().isoformat()


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse a YYYY-MM-DD date string into a datetime object.

    Returns None if the string is empty, None, or unparseable.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str), '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def parse_iso(iso_str: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string into a datetime object.

    Handles both with and without timezone info (Z suffix).
    Returns None if the string is empty, None, or unparseable.
    """
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(str(iso_str).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


def is_cache_fresh(iso_timestamp: str, ttl_days: int) -> bool:
    """Check if a cached timestamp is still within its time-to-live.

    Args:
        iso_timestamp: ISO 8601 timestamp of when the cache was written
        ttl_days: Number of days the cache should be considered valid

    Returns:
        True if the cache is still fresh, False if expired or unparseable
    """
    dt = parse_iso(iso_timestamp)
    if dt is None:
        return False
    now = datetime.now()
    # Handle timezone-aware timestamps
    if dt.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    return (now - dt) < timedelta(days=ttl_days)


def days_since(iso_timestamp: str) -> Optional[int]:
    """Calculate the number of days since a given ISO timestamp.

    Returns None if the timestamp is empty or unparseable.
    """
    dt = parse_iso(iso_timestamp)
    if dt is None:
        return None
    now = datetime.now()
    if dt.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    return (now - dt).days
