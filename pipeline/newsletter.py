#!/usr/bin/env python3
"""
Newsletter Data Query Service - Data access and filtering for newsletter generation.

Provides methods to load movies, filter by date, extract metadata fields,
and provide sorting/grouping utilities for newsletter content curation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

from pipeline.storage import StorageService


class NewsletterDataQuery:
    """
    Query and filter movie data for newsletter generation.

    Responsibilities:
        - Load movies from data.json using StorageService
        - Filter by digital_date (with _discovered_at fallback)
        - Extract required metadata fields for newsletter content
        - Provide sorting/grouping utilities (by RT score, platform, genre)
        - Convenience methods for recent releases and top-rated candidates

    Design:
        - Integrates with StorageService for data access
        - Follows existing pipeline patterns for logging and error handling
        - Graceful handling of missing fields
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        storage_service: Optional[StorageService] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize newsletter data query service.

        Args:
            logger: Logger instance for operation tracking
            storage_service: StorageService instance for file operations
            config: Configuration dict for runtime settings
        """
        self.logger = logger or logging.getLogger(__name__)
        self.storage = storage_service or StorageService(self.logger)
        self.config = config or {}

        # Default configuration values
        self.default_days_back = self.config.get('days_back', 7)
        self.data_file = self.config.get('data_file', 'data.json')

        # Initialize stats for tracking operations
        self.stats = {
            'movies_loaded': 0,
            'movies_filtered': 0,
            'queries_executed': 0,
            'missing_fields': 0,
            'errors': 0
        }

        self.logger.info("NewsletterDataQuery initialized")

    def load_movies(self) -> List[Dict]:
        """
        Load all movies from data.json.

        Returns:
            List of movie dictionaries

        Note:
            Returns empty list on error (graceful degradation).
        """
        try:
            display_data = self.storage.load_json(
                self.data_file,
                default={'movies': [], 'count': 0},
                expected_type=dict
            )

            movies = display_data.get('movies', [])
            self.stats['movies_loaded'] = len(movies)
            self.logger.debug(f"Loaded {len(movies)} movies from {self.data_file}")

            return movies

        except Exception as e:
            self.logger.error(f"Error loading movies from {self.data_file}: {e}")
            self.stats['errors'] += 1
            return []

    def _get_effective_date(self, movie: Dict) -> Optional[datetime]:
        """
        Get the effective date for a movie (digital_date with _discovered_at fallback).

        Args:
            movie: Movie dictionary

        Returns:
            datetime object or None if no date available
        """
        # Try digital_date first
        digital_date = movie.get('digital_date')
        if digital_date:
            try:
                return datetime.strptime(digital_date, '%Y-%m-%d')
            except (ValueError, TypeError) as e:
                self.logger.debug(f"Invalid digital_date format for {movie.get('title', 'Unknown')}: {e}")

        # Fallback to _discovered_at
        discovered_at = movie.get('_discovered_at')
        if discovered_at:
            try:
                # Handle ISO format with or without microseconds
                if 'T' in str(discovered_at):
                    # Try full ISO format first
                    try:
                        return datetime.fromisoformat(discovered_at.replace('Z', '+00:00'))
                    except ValueError:
                        # Try without timezone
                        return datetime.fromisoformat(discovered_at.split('+')[0].split('Z')[0])
            except (ValueError, TypeError) as e:
                self.logger.debug(f"Invalid _discovered_at format for {movie.get('title', 'Unknown')}: {e}")

        return None

    def filter_by_date(
        self,
        movies: List[Dict],
        days_back: Optional[int] = None,
        require_digital_date: bool = False
    ) -> List[Dict]:
        """
        Filter movies by digital_date within last N days (with _discovered_at fallback).

        Args:
            movies: List of movie dictionaries
            days_back: Number of days to look back (defaults to config value)
            require_digital_date: If True, only include movies with actual digital_date (no fallback)

        Returns:
            List of movies within the date range
        """
        if days_back is None:
            days_back = self.default_days_back

        cutoff_date = datetime.now() - timedelta(days=days_back)
        filtered = []

        for movie in movies:
            # If require_digital_date, skip movies without a real digital_date
            if require_digital_date and not movie.get('digital_date'):
                continue
            effective_date = self._get_effective_date(movie)
            if effective_date and effective_date >= cutoff_date:
                filtered.append(movie)

        self.stats['movies_filtered'] = len(filtered)
        self.stats['queries_executed'] += 1
        self.logger.debug(f"Filtered to {len(filtered)} movies from last {days_back} days")

        return filtered

    def extract_metadata(self, movie: Dict) -> Dict[str, Any]:
        """
        Extract required metadata fields for newsletter content.

        Extracts: title, synopsis, RT score, director, runtime, poster,
        streaming links, and VOD links.

        Args:
            movie: Movie dictionary

        Returns:
            Dict with extracted fields (missing fields are None)
        """
        metadata = {
            'id': movie.get('id'),
            'title': movie.get('title'),
            'year': movie.get('year'),
            'synopsis': movie.get('synopsis'),
            'rt_score': self._parse_rt_score(movie.get('rt_score')),
            'metacritic_score': movie.get('metacritic_score'),
            'imdb_rating': movie.get('imdb_rating'),
            'runtime': movie.get('runtime'),
            'poster': movie.get('poster'),
            'genres': movie.get('genres', []),
            'country': movie.get('country'),
            'digital_date': movie.get('digital_date'),
            '_discovered_at': movie.get('_discovered_at'),
        }

        # Extract director from crew
        crew = movie.get('crew', {})
        if isinstance(crew, dict):
            metadata['director'] = crew.get('director')
            metadata['cast'] = crew.get('cast', [])
        else:
            metadata['director'] = None
            metadata['cast'] = []
            self.stats['missing_fields'] += 1

        # Extract watch links
        # NEW: Handle both array format (new) and single-object format (legacy)
        watch_links = movie.get('watch_links', {})
        if isinstance(watch_links, dict):
            streaming = watch_links.get('streaming', {})
            vod = watch_links.get('vod', {})

            # Handle array format for streaming
            if isinstance(streaming, list) and len(streaming) > 0:
                first_streaming = streaming[0]
                metadata['streaming_service'] = first_streaming.get('service') if isinstance(first_streaming, dict) else None
                metadata['streaming_link'] = first_streaming.get('link') if isinstance(first_streaming, dict) else None
            # Handle single dict format (backward compatibility)
            elif isinstance(streaming, dict):
                metadata['streaming_service'] = streaming.get('service')
                metadata['streaming_link'] = streaming.get('link')
            else:
                metadata['streaming_service'] = None
                metadata['streaming_link'] = None

            # Handle array format for vod
            if isinstance(vod, list) and len(vod) > 0:
                first_vod = vod[0]
                metadata['vod_service'] = first_vod.get('service') if isinstance(first_vod, dict) else None
                metadata['vod_link'] = first_vod.get('link') if isinstance(first_vod, dict) else None
            # Handle single dict format (backward compatibility)
            elif isinstance(vod, dict):
                metadata['vod_service'] = vod.get('service')
                metadata['vod_link'] = vod.get('link')
            else:
                metadata['vod_service'] = None
                metadata['vod_link'] = None
        else:
            metadata['streaming_service'] = None
            metadata['streaming_link'] = None
            metadata['vod_service'] = None
            metadata['vod_link'] = None

        # Transform watch_links into template-compatible streaming_services and vod_services lists
        # Each list contains dicts with 'name' and 'url' keys
        # NEW: Handle both array format (new) and single-object format (legacy)
        metadata['streaming_services'] = []
        metadata['vod_services'] = []

        if isinstance(watch_links, dict):
            streaming = watch_links.get('streaming', {})
            vod = watch_links.get('vod', {})

            # Handle array format for streaming (NEW)
            if isinstance(streaming, list):
                for item in streaming:
                    if isinstance(item, dict) and item.get('service') and item.get('link'):
                        metadata['streaming_services'].append({
                            'name': item['service'],
                            'url': item['link']
                        })
            # Handle single dict format (backward compatibility)
            elif isinstance(streaming, dict) and streaming.get('service') and streaming.get('link'):
                metadata['streaming_services'].append({
                    'name': streaming['service'],
                    'url': streaming['link']
                })

            # Handle array format for vod (NEW)
            if isinstance(vod, list):
                for item in vod:
                    if isinstance(item, dict) and item.get('service') and item.get('link'):
                        svc = item.get('service', '').lower()
                        lnk = item.get('link', '')
                        is_screening = 'eventive' in svc or 'eventive.org' in lnk or 'festivalplayer' in lnk or 'shift72.com' in lnk
                        metadata['vod_services'].append({
                            'name': 'Buy Ticket' if is_screening else item['service'],
                            'url': item['link'],
                            'is_screening': is_screening
                        })
            # Handle single dict format (backward compatibility)
            elif isinstance(vod, dict) and vod.get('service') and vod.get('link'):
                svc = vod.get('service', '').lower()
                lnk = vod.get('link', '')
                is_screening = 'eventive' in svc or 'eventive.org' in lnk or 'festivalplayer' in lnk or 'shift72.com' in lnk
                metadata['vod_services'].append({
                    'name': 'Buy Ticket' if is_screening else vod['service'],
                    'url': vod['link'],
                    'is_screening': is_screening
                })

        # Extract trailer link
        links = movie.get('links', {})
        if isinstance(links, dict):
            metadata['trailer'] = links.get('trailer')
            metadata['rt_url'] = links.get('rt')
            metadata['metacritic_url'] = links.get('metacritic')
            metadata['wikipedia_url'] = links.get('wikipedia')
            # Template-compatible alias for trailer
            metadata['trailer_url'] = links.get('trailer')
        else:
            metadata['trailer'] = None
            metadata['rt_url'] = None
            metadata['metacritic_url'] = None
            metadata['wikipedia_url'] = None
            metadata['trailer_url'] = None

        # Category flags
        categories = movie.get('categories', {})
        metadata['is_staff_pick'] = bool(categories.get('is_staff_pick'))
        metadata['is_restoration'] = bool(categories.get('is_restoration'))
        metadata['is_preorder'] = bool(movie.get('_is_preorder'))

        # Cast
        crew = movie.get('crew', {})
        cast = crew.get('cast', [])
        metadata['cast'] = ', '.join(cast[:3]) if cast else None

        # Virtual screening info
        screening_info = movie.get('virtual_screening_info', {})
        metadata['is_virtual_screening'] = bool(categories.get('is_virtual_screening'))
        metadata['screening_name'] = screening_info.get('screening_name')
        metadata['screening_available_end'] = screening_info.get('available_end')
        # Pre-formatted display string for templates
        if metadata['screening_available_end']:
            try:
                parts = metadata['screening_available_end'].split('-')
                months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
                metadata['screening_end_display'] = f"Ends {months[int(parts[1])-1]} {int(parts[2])}"
            except (IndexError, ValueError):
                metadata['screening_end_display'] = None
        else:
            metadata['screening_end_display'] = None

        # Track missing critical fields
        critical_fields = ['title', 'synopsis', 'poster']
        for field in critical_fields:
            if not metadata.get(field):
                self.stats['missing_fields'] += 1
                self.logger.debug(f"Missing {field} for movie {movie.get('id', 'Unknown')}")

        return metadata

    def _parse_rt_score(self, score: Any) -> Optional[int]:
        """
        Safely parse and normalize RT score to integer.

        Args:
            score: RT score value (may be int, float, str like "89" or "89%", or None)

        Returns:
            Integer score clamped to 0-100, or None if invalid/missing
        """
        if score is None:
            return None
        try:
            # Handle string values like "89%" or " 85 % "
            if isinstance(score, str):
                score_str = score.replace('%', '').strip()
                score_val = float(score_str)
            elif isinstance(score, (int, float)):
                score_val = float(score)
            else:
                return None

            # Convert to int (floor) and clamp to 0-100
            score_int = int(score_val)
            return max(0, min(100, score_int))
        except (ValueError, TypeError):
            return None

    def sort_by_rt_score(
        self,
        movies: List[Dict],
        descending: bool = True
    ) -> List[Dict]:
        """
        Sort movies by Rotten Tomatoes score.

        Args:
            movies: List of movie dictionaries
            descending: If True, highest scores first (default)

        Returns:
            Sorted list of movies (movies without RT scores are placed at end)
        """
        def sort_key(movie):
            score = self._parse_rt_score(movie.get('rt_score'))
            if score is None:
                return -1 if descending else 101  # Push to end
            return score

        return sorted(movies, key=sort_key, reverse=descending)

    def sort_by_date(
        self,
        movies: List[Dict],
        descending: bool = True
    ) -> List[Dict]:
        """
        Sort movies by digital_date (with _discovered_at fallback).

        Args:
            movies: List of movie dictionaries
            descending: If True, most recent first (default)

        Returns:
            Sorted list of movies
        """
        def sort_key(movie):
            effective_date = self._get_effective_date(movie)
            if effective_date is None:
                return datetime.min if descending else datetime.max
            return effective_date

        return sorted(movies, key=sort_key, reverse=descending)

    def group_by_platform(self, movies: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group movies by streaming/VOD platform.

        Args:
            movies: List of movie dictionaries

        Returns:
            Dict mapping platform names to lists of movies
            Special keys: 'streaming', 'vod', 'both', 'none'
        """
        groups: Dict[str, List[Dict]] = {
            'streaming': [],
            'vod': [],
            'both': [],
            'none': []
        }

        # Also group by specific service
        by_service: Dict[str, List[Dict]] = {}

        def has_valid_links(category_data):
            """Check if category data has any valid links (handles both array and dict formats)."""
            if isinstance(category_data, list):
                return any(item.get('link') for item in category_data if isinstance(item, dict))
            elif isinstance(category_data, dict):
                return bool(category_data.get('link'))
            return False

        def get_services(category_data):
            """Get list of service names from category data (handles both array and dict formats)."""
            services = []
            if isinstance(category_data, list):
                for item in category_data:
                    if isinstance(item, dict) and item.get('link'):
                        services.append(item.get('service', 'Unknown'))
            elif isinstance(category_data, dict) and category_data.get('link'):
                services.append(category_data.get('service', 'Unknown'))
            return services

        for movie in movies:
            watch_links = movie.get('watch_links', {})
            streaming = watch_links.get('streaming', {}) if isinstance(watch_links, dict) else {}
            vod = watch_links.get('vod', {}) if isinstance(watch_links, dict) else {}

            has_streaming = has_valid_links(streaming)
            has_vod = has_valid_links(vod)

            # Categorize by availability
            if has_streaming and has_vod:
                groups['both'].append(movie)
            elif has_streaming:
                groups['streaming'].append(movie)
            elif has_vod:
                groups['vod'].append(movie)
            else:
                groups['none'].append(movie)

            # Group by specific service names
            for service in get_services(streaming):
                if service not in by_service:
                    by_service[service] = []
                by_service[service].append(movie)

            for service in get_services(vod):
                if service not in by_service:
                    by_service[service] = []
                by_service[service].append(movie)

        # Merge service groups into result
        groups.update(by_service)

        self.logger.debug(
            f"Grouped {len(movies)} movies: "
            f"streaming={len(groups['streaming'])}, vod={len(groups['vod'])}, "
            f"both={len(groups['both'])}, none={len(groups['none'])}"
        )

        return groups

    def group_by_genre(self, movies: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group movies by genre.

        Args:
            movies: List of movie dictionaries

        Returns:
            Dict mapping genre names to lists of movies
            (movies may appear in multiple genre groups)
        """
        groups: Dict[str, List[Dict]] = {}

        for movie in movies:
            genres = movie.get('genres', [])
            if not genres:
                if 'Unknown' not in groups:
                    groups['Unknown'] = []
                groups['Unknown'].append(movie)
                continue

            for genre in genres:
                if genre not in groups:
                    groups[genre] = []
                groups[genre].append(movie)

        self.logger.debug(f"Grouped movies into {len(groups)} genres")

        return groups

    def get_recent_releases(
        self,
        days_back: Optional[int] = None,
        limit: Optional[int] = None,
        require_digital_date: bool = False
    ) -> List[Dict]:
        """
        Convenience method to fetch recent releases sorted by date.

        Args:
            days_back: Number of days to look back (defaults to config value)
            limit: Maximum number of movies to return (optional)
            require_digital_date: If True, only include movies with actual digital_date (no fallback)

        Returns:
            List of recent movies with extracted metadata
        """
        movies = self.load_movies()
        filtered = self.filter_by_date(movies, days_back, require_digital_date=require_digital_date)
        sorted_movies = self.sort_by_date(filtered, descending=True)

        if limit:
            sorted_movies = sorted_movies[:limit]

        # Extract metadata for each movie
        result = []
        for movie in sorted_movies:
            metadata = self.extract_metadata(movie)
            # Include original movie data merged with extracted metadata
            combined = {**movie, **metadata}
            result.append(combined)

        self.logger.info(f"Retrieved {len(result)} recent releases from last {days_back or self.default_days_back} days")

        return result

    def get_top_rated(
        self,
        min_score: Optional[int] = None,
        days_back: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Convenience method to fetch top-rated movie candidates.

        Args:
            min_score: Minimum RT score filter (optional)
            days_back: Number of days to look back (optional, None for all movies)
            limit: Maximum number of movies to return (optional)

        Returns:
            List of top-rated movies sorted by RT score descending
        """
        movies = self.load_movies()

        # Optionally filter by date
        if days_back is not None:
            movies = self.filter_by_date(movies, days_back)

        # Filter by minimum score if specified
        if min_score is not None:
            movies = [
                m for m in movies
                if (self._parse_rt_score(m.get('rt_score')) or 0) >= min_score
            ]

        # Sort by RT score
        sorted_movies = self.sort_by_rt_score(movies, descending=True)

        if limit:
            sorted_movies = sorted_movies[:limit]

        # Extract metadata for each movie
        result = []
        for movie in sorted_movies:
            metadata = self.extract_metadata(movie)
            combined = {**movie, **metadata}
            result.append(combined)

        self.logger.info(
            f"Retrieved {len(result)} top-rated movies"
            + (f" (min score: {min_score})" if min_score else "")
        )

        return result

    def get_by_platform(
        self,
        platform: str,
        days_back: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get movies available on a specific platform.

        Args:
            platform: Platform name (e.g., 'Netflix', 'Amazon', 'streaming', 'vod')
            days_back: Number of days to look back (optional)
            limit: Maximum number of movies to return (optional)

        Returns:
            List of movies on the specified platform
        """
        movies = self.load_movies()

        if days_back is not None:
            movies = self.filter_by_date(movies, days_back)

        grouped = self.group_by_platform(movies)

        # Handle both category keys and specific service names
        platform_movies = grouped.get(platform, [])

        # Sort by date (most recent first)
        platform_movies = self.sort_by_date(platform_movies, descending=True)

        if limit:
            platform_movies = platform_movies[:limit]

        # Extract metadata
        result = []
        for movie in platform_movies:
            metadata = self.extract_metadata(movie)
            combined = {**movie, **metadata}
            result.append(combined)

        self.logger.info(f"Retrieved {len(result)} movies for platform: {platform}")

        return result

    def get_by_genre(
        self,
        genre: str,
        days_back: Optional[int] = None,
        limit: Optional[int] = None,
        sort_by: str = 'date'
    ) -> List[Dict]:
        """
        Get movies in a specific genre.

        Args:
            genre: Genre name (e.g., 'Horror', 'Drama', 'Comedy')
            days_back: Number of days to look back (optional)
            limit: Maximum number of movies to return (optional)
            sort_by: Sort order - 'date' or 'rt_score' (default: 'date')

        Returns:
            List of movies in the specified genre
        """
        movies = self.load_movies()

        if days_back is not None:
            movies = self.filter_by_date(movies, days_back)

        grouped = self.group_by_genre(movies)
        genre_movies = grouped.get(genre, [])

        # Apply sorting
        if sort_by == 'rt_score':
            genre_movies = self.sort_by_rt_score(genre_movies, descending=True)
        else:
            genre_movies = self.sort_by_date(genre_movies, descending=True)

        if limit:
            genre_movies = genre_movies[:limit]

        # Extract metadata
        result = []
        for movie in genre_movies:
            metadata = self.extract_metadata(movie)
            combined = {**movie, **metadata}
            result.append(combined)

        self.logger.info(f"Retrieved {len(result)} movies for genre: {genre}")

        return result

    def get_stats(self) -> Dict[str, int]:
        """
        Get operation statistics.

        Returns:
            Dict with stats counters
        """
        return self.stats.copy()
