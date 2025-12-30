#!/usr/bin/env python3
"""
Enrichment State Manager - Separate persistence for enrichment tracking.

This module manages the enrichment state independently from movie_tracking.json,
preventing race conditions where display generation overwrites discovery results.

Architecture Decision (2025-11-11):
- movie_tracking.json: ONLY written by discovery/monitoring (read-only for display)
- enrichment_state.json: ONLY written by display generation (tracks which movies are enriched)
- No overlap, no race conditions, clean separation of concerns
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, Set
import logging

logger = logging.getLogger(__name__)


class EnrichmentStateManager:
    """
    Manages enrichment state separately from movie tracking database.

    Purpose:
    - Track which movies have been enriched (RT scores, Wikipedia links, etc.)
    - Prevent display generation from overwriting movie_tracking.json
    - Enable safe concurrent operation of discovery and display generation
    """

    def __init__(self, state_file: str = 'enrichment_state.json'):
        """
        Initialize enrichment state manager.

        Args:
            state_file: Path to enrichment state file (default: enrichment_state.json)
        """
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Dict]:
        """
        Load enrichment state from file.

        Returns:
            Dict mapping movie_id -> enrichment metadata
            Format: {
                "12345": {
                    "enriched": true,
                    "enrichment_date": "2025-11-11T10:30:00",
                    "enrichment_version": 1,
                    "failure_count": 0,
                    "last_failure_timestamp": null,
                    "last_failure_reason": null
                }
            }
        """
        if not os.path.exists(self.state_file):
            logger.info(f"No existing enrichment state file found at {self.state_file}, starting fresh")
            return {}

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            logger.info(f"Loaded enrichment state: {len(state)} movies tracked")

            # Ensure backward compatibility by adding missing failure tracking fields
            for movie_id, movie_data in state.items():
                # Skip if movie_data is not a dict (corrupted entry)
                if not isinstance(movie_data, dict):
                    continue

                if 'failure_count' not in movie_data:
                    movie_data['failure_count'] = 0
                if 'last_failure_timestamp' not in movie_data:
                    movie_data['last_failure_timestamp'] = None
                if 'last_failure_reason' not in movie_data:
                    movie_data['last_failure_reason'] = None

            return state
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load enrichment state from {self.state_file}: {e}")
            # Backup corrupted file
            backup_path = f"{self.state_file}.corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                os.rename(self.state_file, backup_path)
                logger.warning(f"Corrupted enrichment state backed up to {backup_path}")
            except:
                pass
            return {}

    def _save_state(self):
        """Save enrichment state to file atomically"""
        try:
            # Write to temp file first
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(self.state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            os.replace(temp_file, self.state_file)
            logger.debug(f"Enrichment state saved: {len(self.state)} movies")

        except Exception as e:
            logger.error(f"Failed to save enrichment state: {e}")
            raise

    def is_enriched(self, movie_id: str) -> bool:
        """
        Check if a movie has been enriched.

        Args:
            movie_id: TMDB movie ID (string)

        Returns:
            True if movie is marked as enriched, False otherwise
        """
        return self.state.get(movie_id, {}).get('enriched', False)

    def get_enrichment_date(self, movie_id: str) -> Optional[str]:
        """
        Get the enrichment date for a movie.

        Args:
            movie_id: TMDB movie ID (string)

        Returns:
            ISO format enrichment date string, or None if not enriched
        """
        return self.state.get(movie_id, {}).get('enrichment_date')

    def mark_enriched(self, movie_id: str) -> None:
        """
        Mark a movie as enriched and reset failure count.

        Args:
            movie_id: TMDB movie ID (string)
        """
        self.state[movie_id] = {
            'enriched': True,
            'enrichment_date': datetime.now().isoformat(),
            'enrichment_version': 1,
            'failure_count': 0,
            'last_failure_timestamp': None,
            'last_failure_reason': None
        }

    def mark_unenriched(self, movie_id: str) -> None:
        """
        Mark a movie as needing re-enrichment.

        Args:
            movie_id: TMDB movie ID (string)
        """
        if movie_id in self.state:
            self.state[movie_id]['enriched'] = False

    def batch_mark_enriched(self, movie_ids: Set[str]) -> int:
        """
        Mark multiple movies as enriched in one operation.

        Args:
            movie_ids: Set of TMDB movie IDs

        Returns:
            Number of movies marked
        """
        count = 0
        for movie_id in movie_ids:
            self.mark_enriched(movie_id)
            count += 1
        return count

    def save(self) -> None:
        """Save current state to disk"""
        self._save_state()

    def get_failure_count(self, movie_id: str) -> int:
        """
        Get the consecutive failure count for a movie.

        Args:
            movie_id: TMDB movie ID (string)

        Returns:
            Number of consecutive failures (0 if no failures or movie not tracked)
        """
        return self.state.get(movie_id, {}).get('failure_count', 0)

    def record_failure(self, movie_id: str, reason: Optional[str] = None) -> None:
        """
        Record a failure for a movie, incrementing the consecutive failure count.

        Args:
            movie_id: TMDB movie ID (string)
            reason: Optional description of the failure
        """
        if movie_id not in self.state:
            # Initialize entry for new movie
            self.state[movie_id] = {
                'enriched': False,
                'enrichment_date': None,
                'enrichment_version': 1,
                'failure_count': 0,
                'last_failure_timestamp': None,
                'last_failure_reason': None
            }

        # Increment failure count and update timestamp
        self.state[movie_id]['failure_count'] = self.state[movie_id].get('failure_count', 0) + 1
        self.state[movie_id]['last_failure_timestamp'] = datetime.now().isoformat()
        if reason:
            self.state[movie_id]['last_failure_reason'] = reason

    def reset_failures(self, movie_id: str) -> None:
        """
        Reset the failure count for a movie (called on successful enrichment).

        Args:
            movie_id: TMDB movie ID (string)
        """
        if movie_id in self.state:
            self.state[movie_id]['failure_count'] = 0
            self.state[movie_id]['last_failure_timestamp'] = None
            self.state[movie_id]['last_failure_reason'] = None

    def should_skip_for_failures(self, movie_id: str, threshold: int = 5) -> bool:
        """
        Check if a movie should be skipped due to consecutive failures (circuit breaker).

        Args:
            movie_id: TMDB movie ID (string)
            threshold: Number of consecutive failures before triggering circuit breaker (default: 3)

        Returns:
            True if movie should be skipped, False if it's safe to retry
        """
        failure_count = self.get_failure_count(movie_id)
        return failure_count >= threshold

    def get_enrichment_stats(self) -> Dict:
        """
        Get statistics about enrichment state.

        Returns:
            Dict with enrichment statistics
        """
        total = len(self.state)
        enriched = sum(1 for m in self.state.values() if m.get('enriched', False))

        # Count movies with failures
        failed = sum(1 for m in self.state.values() if m.get('failure_count', 0) > 0)
        circuit_breaker_triggered = sum(1 for m in self.state.values() if m.get('failure_count', 0) >= 5)

        return {
            'total_tracked': total,
            'enriched': enriched,
            'unenriched': total - enriched,
            'with_failures': failed,
            'circuit_breaker_triggered': circuit_breaker_triggered
        }

    def migrate_from_tracking_db(self, tracking_db: Dict) -> int:
        """
        One-time migration: Extract enrichment flags from movie_tracking.json.

        This is used during the initial transition to separate enrichment state.
        After migration, movie_tracking.json no longer needs enrichment flags.

        Args:
            tracking_db: The movie_tracking.json database (dict with 'movies' key)

        Returns:
            Number of enrichment records migrated
        """
        migrated = 0
        movies = tracking_db.get('movies', {})

        for movie_id, movie_data in movies.items():
            # Only migrate if enriched flag exists in tracking db
            if 'enriched' in movie_data:
                self.state[movie_id] = {
                    'enriched': movie_data.get('enriched', False),
                    'enrichment_date': movie_data.get('enrichment_date'),
                    'enrichment_version': 1,
                    'migrated_from_tracking_db': True,
                    'failure_count': 0,
                    'last_failure_timestamp': None,
                    'last_failure_reason': None
                }
                migrated += 1

        if migrated > 0:
            self._save_state()
            logger.info(f"Migrated {migrated} enrichment records from movie_tracking.json")

        return migrated


def migrate_enrichment_flags_once():
    """
    One-time migration utility: Extract enrichment flags from movie_tracking.json
    and create enrichment_state.json.

    This should be run once during the transition to separate enrichment state.
    """
    if os.path.exists('enrichment_state.json'):
        print("⚠️  enrichment_state.json already exists, skipping migration")
        return

    if not os.path.exists('movie_tracking.json'):
        print("⚠️  movie_tracking.json not found, nothing to migrate")
        return

    print("🔄 Migrating enrichment flags from movie_tracking.json...")

    # Load tracking database
    with open('movie_tracking.json', 'r') as f:
        tracking_db = json.load(f)

    # Create enrichment state manager and migrate
    manager = EnrichmentStateManager()
    migrated = manager.migrate_from_tracking_db(tracking_db)

    print(f"✅ Migration complete: {migrated} enrichment records extracted")
    print(f"   New file created: enrichment_state.json")
    print(f"   movie_tracking.json remains unchanged (enrichment flags still present but will be ignored)")

    # Show stats
    stats = manager.get_enrichment_stats()
    print(f"\n📊 Enrichment State Statistics:")
    print(f"   Total tracked: {stats['total_tracked']}")
    print(f"   Enriched: {stats['enriched']}")
    print(f"   Needs enrichment: {stats['unenriched']}")
    print(f"   With failures: {stats['with_failures']}")
    print(f"   Circuit breaker triggered: {stats['circuit_breaker_triggered']}")


if __name__ == '__main__':
    # Run migration when executed directly
    migrate_enrichment_flags_once()
