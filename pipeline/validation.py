#!/usr/bin/env python3
"""
Validation Service - Data validation and consistency checks for NRW pipeline.

Extracted from generate_data.py (2025-11-10) to separate validation concerns.
Handles all runtime validation for watch links, enrichment consistency, and schema validation.
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional, Any
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

        Schema (NEW - array format):
            {
                'streaming': [{'service': str, 'link': str|None}, ...],
                'vod': [{'service': str, 'link': str|None}, ...]
            }

        Also supports legacy single-object format for backward compatibility:
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

        def validate_single_link(link_data: Dict, category: str, index: int = None) -> Optional[Dict]:
            """Validate a single link object and return it if valid, None otherwise."""
            nonlocal had_warnings
            index_str = f" at index {index}" if index is not None else ""

            # Structure validation: Verify it's a dict with 'service' and 'link' keys
            if not isinstance(link_data, dict):
                self.logger.warning(
                    f"Invalid link data type{index_str} for '{category}' in {movie_title}, expected dict"
                )
                had_warnings = True
                return None

            if 'service' not in link_data or 'link' not in link_data:
                self.logger.warning(
                    f"Missing required keys (service/link){index_str} in '{category}' for {movie_title}"
                )
                had_warnings = True
                return None

            # Service validation: Verify service is non-empty string
            if not isinstance(link_data['service'], str) or not link_data['service'].strip():
                self.logger.warning(f"Invalid service{index_str} in '{category}' for {movie_title}")
                had_warnings = True
                return None

            # Link validation: Verify link is either None or valid HTTP/HTTPS URL string
            link = link_data['link']
            if link is not None:
                if not isinstance(link, str):
                    self.logger.warning(
                        f"Invalid link type{index_str} in '{category}' for {movie_title}, expected string or None"
                    )
                    had_warnings = True
                    return None

                # Basic URL validation
                try:
                    parsed = urlparse(link)
                    if not parsed.scheme or parsed.scheme not in ['http', 'https']:
                        self.logger.warning(f"Invalid URL scheme{index_str} in '{category}' for {movie_title}")
                        had_warnings = True
                        return None
                    if not parsed.netloc:
                        self.logger.warning(f"Invalid URL netloc{index_str} in '{category}' for {movie_title}")
                        had_warnings = True
                        return None
                except Exception:
                    self.logger.warning(f"Malformed URL{index_str} in '{category}' for {movie_title}")
                    had_warnings = True
                    return None

                # Check for known placeholder ASINs
                if any(asin in link for asin in PLACEHOLDER_ASINS):
                    detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                    self.logger.warning(
                        f"Detected placeholder ASIN {detected_asin}{index_str} in {category} link for {movie_title}, rejecting"
                    )
                    had_warnings = True
                    return None

            return link_data

        for category, category_data in watch_links.items():
            # Category validation: Check that all keys are in ['streaming', 'vod']
            if category not in valid_categories:
                self.logger.warning(f"Invalid watch link category '{category}' for {movie_title}")
                had_warnings = True
                continue

            # Handle array format (NEW)
            if isinstance(category_data, list):
                validated_array = []
                for i, item in enumerate(category_data):
                    validated_item = validate_single_link(item, category, i)
                    if validated_item is not None:
                        validated_array.append(validated_item)
                if validated_array:
                    validated_links[category] = validated_array

            # Handle single dict format (legacy backward compatibility)
            elif isinstance(category_data, dict):
                validated_item = validate_single_link(category_data, category)
                if validated_item is not None:
                    validated_links[category] = validated_item

            else:
                self.logger.warning(
                    f"Invalid category data type for '{category}' in {movie_title}, expected list or dict"
                )
                had_warnings = True

        # Update statistics
        if had_warnings:
            self.stats['schema_validation_warnings'] += 1
        else:
            self.stats['schema_validation_passes'] += 1

        return validated_links

    # REMOVED: validate_enrichment_consistency() - was causing loop bug and is unnecessary
    # with correct architecture (movies go to data.json on discovery, enrichment fills extras)
    # Deleted 2025-12-05

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

                # Optional metadata field validation (keep fields optional for legacy compatibility)
                if not self._validate_metadata_fields(movie, f"movie[{i}]", file_path):
                    return False

            self.logger.info(f"{file_path} schema validation passed: {len(movies)} movies")
            return True

        except json.JSONDecodeError as e:
            self.logger.error(f"{file_path} is not valid JSON: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error validating {file_path} schema: {e}")
            return False

    def fix_data_json_schema(self, file_path: str = 'data.json') -> bool:
        """
        Gracefully fix data.json schema - APPEND-ONLY, never wipes movies.

        Only fixes missing root keys (generated_at, count). Never touches movies array.
        If file can't be safely fixed, returns False to signal abort.

        Args:
            file_path: Path to data.json file (default: 'data.json')

        Returns:
            bool: True if schema is valid/fixed, False if file should not be modified
        """
        if not os.path.exists(file_path):
            self.logger.info(f"{file_path} does not exist - will be created fresh")
            return True

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Type checking: if data is not a dict, ABORT - don't wipe
            if not isinstance(data, dict):
                self.logger.error(f"{file_path} root is not a dict (type: {type(data).__name__}) - aborting to preserve file")
                return False

            # Check movies array - if it's not a list, ABORT - don't wipe
            if 'movies' in data and not isinstance(data['movies'], list):
                self.logger.error(f"Movies field is not a list (type: {type(data['movies']).__name__}) - aborting to preserve data")
                return False

            # Fix missing required root keys (safe operations only)
            fixed = False
            if 'generated_at' not in data:
                data['generated_at'] = datetime.now().isoformat()
                self.logger.info(f"Added missing generated_at field to {file_path}")
                fixed = True
            elif not isinstance(data['generated_at'], str):
                data['generated_at'] = datetime.now().isoformat()
                self.logger.info(f"Fixed invalid generated_at type in {file_path}")
                fixed = True

            # Only add movies array if it doesn't exist (first run scenario)
            if 'movies' not in data:
                data['movies'] = []
                self.logger.info(f"Added missing movies array to {file_path}")
                fixed = True

            if 'count' not in data:
                movie_count = len(data.get('movies', []))
                data['count'] = movie_count
                self.logger.info(f"Added missing count field to {file_path} (count: {movie_count})")
                fixed = True
            elif not isinstance(data['count'], int):
                movie_count = len(data.get('movies', []))
                data['count'] = movie_count
                self.logger.info(f"Fixed invalid count type in {file_path} (recalculated: {movie_count})")
                fixed = True

            # If we fixed anything, write back the file
            if fixed:
                with open(file_path, 'w') as f:
                    json.dump(data, f, indent=2)
                self.logger.info(f"Successfully fixed schema for {file_path}")

            return True

        except json.JSONDecodeError as e:
            # File is not valid JSON - ABORT, do not create fresh file
            self.logger.error(f"{file_path} contains invalid JSON: {e} - aborting to preserve file")
            return False

        except Exception as e:
            # Unexpected error - ABORT, do not create fresh file
            self.logger.error(f"Unexpected error reading {file_path}: {e} - aborting to preserve file")
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


    def _validate_metadata_fields(self, movie: Dict, movie_context: str, file_path: str) -> bool:
        """
        Validate optional metadata fields in movie entries.

        Validates underscore-prefixed metadata when present:
        - _discovery_source: Must be non-empty string
        - _enrichment_status: Must be in allowed set (pending/completed/failed/error)
        - _minimal_entry: Must be boolean
        - _tmdb_fetch_failed: Must be boolean
        - _digital_date_source: Must be in allowed set (detection/tmdb_type4)

        Args:
            movie: Movie dict to validate
            movie_context: Context string for logging (e.g., "movie[0]")
            file_path: File path for logging context

        Returns:
            bool: True if all present metadata fields are valid, False otherwise

        Note:
            All metadata fields are optional for legacy compatibility.
        """
        # _discovery_source: Non-empty string validation
        if '_discovery_source' in movie:
            discovery_source = movie['_discovery_source']
            if not isinstance(discovery_source, str) or not discovery_source.strip():
                self.logger.error(f"{file_path} {movie_context} _discovery_source must be non-empty string")
                return False

        # _enrichment_status: Allowed values validation
        if '_enrichment_status' in movie:
            enrichment_status = movie['_enrichment_status']
            allowed_statuses = {'pending', 'completed', 'failed', 'error', 'reverted', 'timeout', 'under_60min'}
            if not isinstance(enrichment_status, str) or enrichment_status not in allowed_statuses:
                self.logger.error(f"{file_path} {movie_context} _enrichment_status must be one of {allowed_statuses}, got '{enrichment_status}'")
                return False

        # _minimal_entry: Boolean validation
        if '_minimal_entry' in movie:
            minimal_entry = movie['_minimal_entry']
            if not isinstance(minimal_entry, bool):
                self.logger.error(f"{file_path} {movie_context} _minimal_entry must be boolean, got {type(minimal_entry)}")
                return False

        # _tmdb_fetch_failed: Boolean validation
        if '_tmdb_fetch_failed' in movie:
            tmdb_fetch_failed = movie['_tmdb_fetch_failed']
            if not isinstance(tmdb_fetch_failed, bool):
                self.logger.error(f"{file_path} {movie_context} _tmdb_fetch_failed must be boolean, got {type(tmdb_fetch_failed)}")
                return False

        # _digital_date_source: Allowed values validation
        if '_digital_date_source' in movie:
            digital_date_source = movie['_digital_date_source']
            allowed_sources = {'detection', 'tmdb_type4'}
            if not isinstance(digital_date_source, str) or digital_date_source not in allowed_sources:
                self.logger.error(f"{file_path} {movie_context} _digital_date_source must be one of {allowed_sources}, got '{digital_date_source}'")
                return False

        return True
