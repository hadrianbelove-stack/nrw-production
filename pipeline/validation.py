#!/usr/bin/env python3
"""
Validation Service - Data validation and consistency checks for NRW pipeline.

Extracted from generate_data.py (2025-11-10) to separate validation concerns.
Handles all runtime validation for watch links, enrichment consistency, and schema validation.
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Union, Any, Tuple
import logging
from urllib.parse import urlparse

from constants import PLACEHOLDER_ASINS


class ValidationService:
    """
    Centralized validation operations for data integrity and schema compliance.

    Responsibilities:
        - Validate watch_links schema (streaming/vod structure)
        - Validate enrichment consistency (enriched=true requires watch_links)
        - Validate data.json schema before loading
        - Track validation metrics and warnings

    Design:
        - Stateless validation methods (can be called independently)
        - Integrates with StorageService for file operations
        - Returns cleaned/validated data or boolean success indicators
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        storage_service: Optional[Any] = None,
        config: Optional[Dict] = None,
        stats_dict: Optional[Dict] = None
    ):
        """
        Initialize validation service.

        Args:
            logger: Logger instance for operation tracking
            storage_service: StorageService instance for file operations
            config: Configuration dict for runtime settings
            stats_dict: Shared statistics dict to update (optional, creates new if not provided)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.storage = storage_service
        self.config = config or {}

        # Use shared stats dict or create new one
        if stats_dict is not None:
            self.stats = stats_dict
            # Ensure validation keys exist
            if 'schema_validation_warnings' not in self.stats:
                self.stats['schema_validation_warnings'] = 0
            if 'schema_validation_passes' not in self.stats:
                self.stats['schema_validation_passes'] = 0
        else:
            self.stats = {
                'schema_validation_warnings': 0,
                'schema_validation_passes': 0
            }

    def validate_watch_links_schema(self, watch_links: Dict, movie_title: str = 'Unknown') -> Dict:
        """
        Runtime validation that watch_links conform to canonical streaming/vod schema.

        Args:
            watch_links: Dict to validate (typically from get_watch_links)
            movie_title: String for logging context

        Returns:
            Dict: Validated/cleaned watch_links with invalid entries removed

        Schema:
            {
                'streaming': {'service': str, 'link': str|None},
                'vod': {'service': str, 'link': str|None}
            }
        """
        # Type check: Verify watch_links is a dict
        if not isinstance(watch_links, dict):
            self.logger.warning(
                f"Invalid watch_links type '{type(watch_links).__name__}' for {movie_title}, expected dict"
            )
            self.stats['schema_validation_warnings'] += 1
            return {}

        validated_links = {}
        had_warnings = False
        valid_categories = ['streaming', 'vod']

        for category, category_data in watch_links.items():
            # Category validation: Check that all keys are in ['streaming', 'vod']
            if category not in valid_categories:
                self.logger.warning(f"Invalid watch link category '{category}' for {movie_title}")
                had_warnings = True
                continue

            # Structure validation: For each category, verify it's a dict with 'service' and 'link' keys
            if not isinstance(category_data, dict):
                self.logger.warning(
                    f"Invalid category data type for '{category}' in {movie_title}, expected dict"
                )
                had_warnings = True
                continue

            if 'service' not in category_data or 'link' not in category_data:
                self.logger.warning(
                    f"Missing required keys (service/link) in '{category}' for {movie_title}"
                )
                had_warnings = True
                continue

            # Service validation: Verify service is non-empty string
            if not isinstance(category_data['service'], str) or not category_data['service'].strip():
                self.logger.warning(f"Invalid service in '{category}' for {movie_title}")
                had_warnings = True
                continue

            # Link validation: Verify link is either None or valid HTTP/HTTPS URL string
            link = category_data['link']
            if link is not None:
                if not isinstance(link, str):
                    self.logger.warning(
                        f"Invalid link type in '{category}' for {movie_title}, expected string or None"
                    )
                    had_warnings = True
                    continue

                # Basic URL validation
                try:
                    parsed = urlparse(link)
                    if not parsed.scheme or parsed.scheme not in ['http', 'https']:
                        self.logger.warning(f"Invalid URL scheme in '{category}' for {movie_title}")
                        had_warnings = True
                        continue
                    if not parsed.netloc:
                        print(f"Warning: Invalid URL netloc in '{category}' for {movie_title}")
                        had_warnings = True
                        continue
                except Exception:
                    print(f"Warning: Malformed URL in '{category}' for {movie_title}")
                    had_warnings = True
                    continue

                # Check for known placeholder ASINs
                if any(asin in link for asin in PLACEHOLDER_ASINS):
                    detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                    self.logger.warning(
                        f"Detected placeholder ASIN {detected_asin} in {category} link for {movie_title}, rejecting"
                    )
                    had_warnings = True
                    continue

            # If we reach here, the category data is valid
            validated_links[category] = category_data

        # Update statistics
        if had_warnings:
            self.stats['schema_validation_warnings'] += 1
        else:
            self.stats['schema_validation_passes'] += 1

        return validated_links

    def validate_enrichment_consistency(self) -> int:
        """
        Validate that movies marked as enriched actually have watch_links.

        Cross-checks movie_tracking.json (enriched=true) against data.json (watch_links present).
        Detects and corrects inconsistencies where:
        - Movie marked enriched=true but has no watch_links
        - Movie has empty watch_links dict
        - Movie has placeholder ASINs in watch_links

        Returns:
            int: Number of inconsistencies found and corrected

        Note:
            Requires StorageService to be configured.
            Modifies movie_tracking.json if inconsistencies found.
        """
        if not self.storage:
            self.logger.error("ValidationService requires StorageService for enrichment consistency check")
            return 0

        try:
            # Load all movies (merged from tracking and archived) for iteration
            archive_enabled = self.config.get('tracking', {}).get('archive_available_on_detect', False)
            combined = self.storage.load_all_movies(archive_enabled=archive_enabled)
            if not combined.get('movies'):
                self.logger.info("No movie tracking database found, skipping enrichment validation")
                return 0

            # Load the main tracking database for modifications
            if not os.path.exists('movie_tracking.json'):
                self.logger.info("No movie_tracking.json found, skipping enrichment validation")
                return 0

            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)

            # Early check for data.json existence - skip cross-check if missing
            if not os.path.exists('data.json'):
                self.logger.info("data.json not found, skipping enrichment consistency cross-check")
                return 0

            inconsistencies_found = 0
            total_available = 0

            for movie_id, movie in combined.get('movies', {}).items():
                if movie.get('status') == 'available':
                    total_available += 1

                    # Check if marked as enriched but missing watch_links
                    if movie.get('enriched', False):
                        # Load corresponding data.json to check for watch_links
                        data_file = 'data.json'
                        if os.path.exists(data_file):
                            try:
                                # Validate schema before loading
                                if not self.validate_data_json_schema(data_file):
                                    self.logger.warning(
                                        f"data.json schema validation failed during enrichment check for movie {movie.get('title', 'Unknown')}"
                                    )
                                    continue

                                with open(data_file, 'r') as df:
                                    data_movies = json.load(df).get('movies', [])

                                # Find corresponding movie in data.json
                                data_movie = None
                                for dm in data_movies:
                                    if str(dm.get('id')) == str(movie_id):
                                        data_movie = dm
                                        break

                                if data_movie:
                                    watch_links = data_movie.get('watch_links')

                                    # Check if watch_links is missing, empty, or contains placeholder ASIN
                                    has_placeholder_asin = False
                                    detected_asin = None

                                    if watch_links and isinstance(watch_links, dict):
                                        # Check for placeholder ASINs in any category
                                        for category in ['streaming', 'vod']:
                                            category_data = watch_links.get(category, {})
                                            if category_data and isinstance(category_data, dict):
                                                link = category_data.get('link', '')
                                                if link:
                                                    for asin in PLACEHOLDER_ASINS:
                                                        if asin in link:
                                                            has_placeholder_asin = True
                                                            detected_asin = asin
                                                            break
                                            if has_placeholder_asin:
                                                break

                                    if not watch_links or (isinstance(watch_links, dict) and not any(watch_links.values())) or has_placeholder_asin:
                                        # Inconsistency found: enriched=true but no/bad watch_links
                                        reason = "no watch_links" if not watch_links else "empty watch_links" if not any(watch_links.values()) else f"placeholder ASIN {detected_asin}"
                                        self.logger.warning(
                                            f"Enrichment inconsistency: {movie.get('title', 'Unknown')} (ID: {movie_id}) marked enriched=true but has {reason}"
                                        )

                                        # Only modify if movie exists in main tracking database
                                        if movie_id in db.get('movies', {}):
                                            db['movies'][movie_id]['enriched'] = False
                                            # Remove enrichment_date if present
                                            if 'enrichment_date' in db['movies'][movie_id]:
                                                del db['movies'][movie_id]['enrichment_date']
                                            inconsistencies_found += 1

                            except Exception as e:
                                self.logger.warning(
                                    f"Error checking data.json for movie {movie.get('title', 'Unknown')}: {e}"
                                )

            # Save corrected database if any inconsistencies were found
            if inconsistencies_found > 0:
                if self.storage.atomic_write_json(db, 'movie_tracking.json'):
                    self.logger.info(
                        f"Corrected {inconsistencies_found} enrichment inconsistencies in movie_tracking.json"
                    )
                else:
                    self.logger.error(f"Failed to save corrected enrichment inconsistencies")

            # Log summary
            consistent_count = total_available - inconsistencies_found
            self.logger.info(
                f"Enrichment consistency: {consistent_count}/{total_available} valid, {inconsistencies_found} corrected"
            )
            print(
                f"  🔍 Enrichment consistency: {consistent_count}/{total_available} valid, {inconsistencies_found} corrected"
            )

            return inconsistencies_found

        except Exception as e:
            self.logger.error(f"Error during enrichment consistency validation: {e}")
            print(f"  ❌ Error during enrichment consistency validation: {e}")
            return 0

    def validate_data_json_schema(self, file_path: str = 'data.json') -> bool:
        """
        Validate data.json structure before loading.

        Checks that:
        - Root object has required keys: generated_at, count, movies
        - Types are correct (generated_at: str, count: int, movies: list)
        - Movies are dicts with required keys: id, title, digital_date

        Args:
            file_path: Path to data.json file (default: 'data.json')

        Returns:
            bool: True if schema is valid, False otherwise

        Note:
            Logs specific validation errors for debugging.
        """
        if not os.path.exists(file_path):
            self.logger.warning(f"{file_path} does not exist")
            return False

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Check required root keys
            required_root_keys = ['generated_at', 'count', 'movies']
            for key in required_root_keys:
                if key not in data:
                    self.logger.error(f"{file_path} missing required key: {key}")
                    return False

            # Check data types
            if not isinstance(data['generated_at'], str):
                self.logger.error(
                    f"{file_path} generated_at must be string, got {type(data['generated_at'])}"
                )
                return False

            if not isinstance(data['count'], int):
                self.logger.error(f"{file_path} count must be int, got {type(data['count'])}")
                return False

            if not isinstance(data['movies'], list):
                self.logger.error(f"{file_path} movies must be list, got {type(data['movies'])}")
                return False

            # Check movies array structure (all movies)
            movies = data['movies']
            for i, movie in enumerate(movies):  # Check all movies
                if not isinstance(movie, dict):
                    self.logger.error(f"{file_path} movie[{i}] is not a dict: {type(movie)}")
                    return False

                # Check required movie keys
                required_movie_keys = ['id', 'title', 'digital_date']
                for key in required_movie_keys:
                    if key not in movie:
                        self.logger.error(f"{file_path} movie[{i}] missing required key: {key}")
                        return False

            self.logger.info(f"{file_path} schema validation passed: {len(movies)} movies")
            return True

        except json.JSONDecodeError as e:
            self.logger.error(f"{file_path} is not valid JSON: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error validating {file_path} schema: {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
        """
        Get validation statistics.

        Returns:
            Dict with validation metrics:
                - schema_validation_warnings: Number of failed validations
                - schema_validation_passes: Number of successful validations
        """
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset validation statistics counters."""
        self.stats = {
            'schema_validation_warnings': 0,
            'schema_validation_passes': 0
        }
