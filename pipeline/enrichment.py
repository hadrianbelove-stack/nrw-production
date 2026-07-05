#!/usr/bin/env python3
"""
Enrichment Service - Watch link discovery and metadata enrichment for NRW pipeline.

Extracted from generate_data.py (2025-11-10) to separate enrichment concerns.
Handles all watch link discovery across multiple sources with priority waterfall.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
import re
from urllib.parse import urljoin

from constants import PLACEHOLDER_ASINS
from pipeline.provider_names import normalize_watch_links


class EnrichmentService:
    """
    Centralized enrichment operations for watch links and metadata.

    Responsibilities:
        - Orchestrate watch link discovery across multiple sources
        - Integrate agent scraper and platform scraper
        - Apply rate limiting and caching strategies
        - Normalize and validate watch link URLs
        - Manage affiliate tag insertion
        - Handle priority waterfall: manual > overrides > cache > JustWatch API > scrapers

    Design:
        - Integrates with StorageService for caching
        - Integrates with ValidationService for schema validation
        - Maintains shared statistics dict for metrics tracking
        - Lazy initialization of scrapers (agent, platform)
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        config: Optional[Dict] = None,
        storage_service: Optional[Any] = None,
        validator_service: Optional[Any] = None,
        stats_dict: Optional[Dict] = None,
        streaming_scraper: Optional[Any] = None,
        vod_scraper: Optional[Any] = None,
        enrichment_enabled: bool = True
    ):
        """
        Initialize enrichment service.

        Args:
            logger: Logger instance for operation tracking
            config: Configuration dict for runtime settings
            storage_service: StorageService instance for file operations
            validator_service: ValidationService instance for schema validation
            stats_dict: Shared statistics dict to update (optional, creates new if not provided)
            streaming_scraper: Streaming scraper instance (lazy init if None)
            vod_scraper: VOD scraper instance (lazy init if None)
            enrichment_enabled: Whether enrichment is enabled globally
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = config or {}
        self.storage = storage_service
        self.validator = validator_service
        self.enrichment_enabled = enrichment_enabled

        # Log enrichment flag state for debugging
        self.logger.info(f"EnrichmentService initialized with enrichment_enabled={enrichment_enabled}")

        # Scraper instances (lazy initialization)
        self.streaming_scraper = streaming_scraper
        self.vod_scraper = vod_scraper

        # Rate limiting state
        self._last_streaming_scraper_time = 0
        self._last_vod_scraper_time = 0

        # Amazon ASIN cache for reusing deep links
        self._amazon_asin_cache = {}

        # Use shared stats dict or create new one
        if stats_dict is not None:
            self.stats = stats_dict
        else:
            self.stats = {
                'cache_hits': 0,
                'override_hits': 0,
                'manual_tracking_hits': 0,
                'justwatch_successes': 0,
                'streaming_attempts': 0,
                'streaming_successes': 0,
                'streaming_failures': 0,
                'streaming_cache_hits': 0,
                'search_calls': 0,
                'source_calls': 0
            }

        # Cache references (will be injected)
        self.watch_links_cache = {}
        self.watch_links_overrides = {}

    def set_cache_references(self, watch_links_cache, watch_links_overrides):
        """
        Inject cache references from parent DataGenerator.

        Args:
            watch_links_cache: Reference to watch_links_cache dict
            watch_links_overrides: Reference to watch_links_overrides dict (overrides/watch_links_overrides.json)
        """
        self.watch_links_cache = watch_links_cache
        self.watch_links_overrides = watch_links_overrides

    def get_watch_links(self, movie_id, title, year, providers, force_refresh=False,
                        tracking_data=None, original_title=None, alternative_titles=None,
                        director=None, tmdb_id=None):
        """
        Get deep links with canonical streaming/vod structure.

        Single exit boundary for ALL waterfall paths (manual/override/cache/
        JustWatch/scrapers): results are normalized here — service names
        simplified, legacy dict shape coerced to list, one entry per
        simplified service. Callers get display-ready links; nothing
        downstream needs to rename or dedupe.
        """
        links = self._get_watch_links_impl(
            movie_id, title, year, providers, force_refresh=force_refresh,
            tracking_data=tracking_data, original_title=original_title,
            alternative_titles=alternative_titles, director=director, tmdb_id=tmdb_id
        )
        return normalize_watch_links(links)

    def _get_watch_links_impl(self, movie_id, title, year, providers, force_refresh=False,
                              tracking_data=None, original_title=None, alternative_titles=None,
                              director=None, tmdb_id=None):
        """
        Get deep links with canonical streaming/vod structure.

        Priority waterfall:
        1. Manual watch links from movie_tracking.json - highest priority
        2. Overrides (overrides/watch_links_overrides.json) - always wins over automated
        3. Cache (cache/watch_links_cache.json)
        3.5. Apple Music Live rule - force Apple TV streaming
        4. JustWatch API (primary source for rent/buy deep links)
        5. VOD scraper (Amazon, Apple TV) - Playwright fallback
        6. TMDB provider names with null links - last resort

        Args:
            movie_id: TMDB movie ID
            title: Movie title (English)
            year: Release year
            providers: Dict with streaming/vod provider lists from TMDB
            force_refresh: Skip cache and re-fetch
            tracking_data: Movie tracking data with optional manual_watch_links
            original_title: Original language title from TMDB (for scraper fallback)
            alternative_titles: List of TMDB alternative title dicts (for scraper fallback)

        Returns:
            Dict: {
                'streaming': [{'service': 'Netflix', 'link': 'https://...'}],
                'vod': [{'service': 'Amazon Video', 'link': 'https://...'}]
            }
        """
        # Build title variants for scraper fallback (English → original → US alternative)
        title_variants = [title]
        if original_title and original_title.lower() != title.lower():
            title_variants.append(original_title)
        if alternative_titles:
            for alt in alternative_titles:
                if alt.get('iso_3166_1') == 'US':
                    us_title = alt.get('title')
                    if us_title and us_title.lower() != title.lower():
                        title_variants.append(us_title)
                    break

        cache_key = str(movie_id)

        # 1. Try manual watch links (highest priority)
        manual_result = self._try_manual_links(tracking_data, title, cache_key)
        if manual_result:
            return manual_result

        # 2. Try override links (always wins over automated sources)
        override_result = self._try_override_links(cache_key, title)
        if override_result:
            return override_result

        # Legacy admin overrides removed (Dec 2024) - empty dict for compatibility
        validated_overrides = {}

        # 2.5. Apple Music Live — always Apple TV streaming, no VOD
        # Runs BEFORE cache so stale cached data can't override the known-correct platform
        if title and title.lower().startswith('apple music live'):
            self.logger.info(f"Apple Music Live detected: {title} — forcing Apple TV streaming only")
            apple_link = None
            has_vod_scraper = self._check_vod_scraper_available()
            if has_vod_scraper:
                try:
                    apple_link = self.get_platform_deep_link_with_cache(title, year, 'Apple TV')
                except Exception as e:
                    self.logger.error(f"Scraper failed for Apple Music Live '{title}': {e}")
            if apple_link:
                watch_links = {
                    'streaming': [{'service': 'Apple TV', 'link': apple_link}],
                    'vod': []
                }
                watch_links = self.normalize_watch_links_urls(watch_links)
                validated_links = self.validator.validate_watch_links_schema(watch_links, title)
                if validated_links:
                    self._apply_affiliate_tags_batch(validated_links, title)
                    self.watch_links_cache[cache_key] = {
                        'links': validated_links,
                        'cached_at': datetime.now().isoformat(),
                        'source': 'apple_music_live_rule'
                    }
                    self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                    return validated_links
            else:
                self.logger.warning(f"Apple Music Live '{title}' — couldn't find Apple TV link, returning empty to prevent wrong platform links")
                return {'streaming': [{'service': 'Apple TV', 'link': None}], 'vod': []}

        # 3. Try cached links
        cached_result = self._try_cached_links(cache_key, force_refresh)
        if cached_result:
            return cached_result

        # 4. Try JustWatch API (primary source for rent/buy deep links)
        justwatch_result, jw_provider_names = self._try_justwatch_api(
            title, year, cache_key, validated_overrides, providers=providers,
            original_title=original_title, director=director, tmdb_id=tmdb_id
        )
        if justwatch_result:
            return justwatch_result

        # 5. Build from scrapers (fallback — Amazon, Apple TV via Playwright)
        watch_links, vod_scraper_used = self._build_scraper_fallback_links(
            movie_id, title, year, providers, validated_overrides,
            title_variants=title_variants
        )

        # 6. Normalize URLs, validate, apply affiliate tags, cache
        watch_links = self.normalize_watch_links_urls(watch_links)
        validated_links = self.validator.validate_watch_links_schema(watch_links, title)
        self._apply_affiliate_tags_batch(validated_links, title)
        self._validate_link_consistency_batch(validated_links, title)
        self._cache_watch_links_result(cache_key, validated_links, vod_scraper_used)

        return validated_links

    # ============================================================================
    # Watch Links Helper Methods (extracted from get_watch_links for clarity)
    # ============================================================================

    def _try_manual_links(self, tracking_data, title, cache_key):
        """
        Try to get manual watch links from tracking data.

        Args:
            tracking_data: Movie tracking data with optional manual_watch_links
            title: Movie title for logging
            cache_key: Cache key (movie_id as string)

        Returns:
            Dict of validated links if found, None otherwise
        """
        if not (tracking_data and 'watch_links' in tracking_data and tracking_data.get('manual_watch_links')):
            return None

        manual_links = tracking_data['watch_links']
        try:
            validated_manual = self.validator.validate_watch_links_schema(manual_links, title)
            if validated_manual:
                self.logger.info(f"Using manual watch links from tracking data for {title}: {list(validated_manual.keys())}")
                self.stats['manual_tracking_hits'] = self.stats.get('manual_tracking_hits', 0) + 1

                # Cache the validated manual links
                now = datetime.now().isoformat()
                self.watch_links_cache[cache_key] = {
                    'links': validated_manual,
                    'cached_at': now,
                    'source': 'manual_tracking'
                }
                self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

                return validated_manual
        except Exception as e:
            self.logger.warning(f"Invalid manual watch links in tracking data for {title}: {e}")

        return None

    def _try_override_links(self, cache_key, title):
        """
        Try to get override links from watch_links_overrides.json.

        Args:
            cache_key: Cache key (movie_id as string)
            title: Movie title for logging

        Returns:
            Dict of validated links if found, None otherwise
        """
        if cache_key not in self.watch_links_overrides:
            return None

        override_data = self.watch_links_overrides[cache_key]
        try:
            # Intentionally-empty override: streaming and vod are both empty arrays.
            # This means "this movie should have NO links" (e.g., clearing bad
            # JustWatch matches). Return empty-but-valid structure to stop the
            # waterfall from falling through to cache/JustWatch.
            # Only check streaming/vod keys — ignore metadata like "notes".
            all_empty = override_data and all(
                isinstance(override_data.get(k), list) and len(override_data[k]) == 0
                for k in ('streaming', 'vod') if k in override_data
            )
            if all_empty:
                self.logger.info(f"Using empty override for {title} (clearing bad links)")
                self.stats['override_hits'] = self.stats.get('override_hits', 0) + 1
                return {'streaming': [], 'vod': []}

            # Normalize single-dict vod to array format
            if isinstance(override_data.get('vod'), dict):
                override_data['vod'] = [override_data['vod']]
            validated_override = self.validator.validate_watch_links_schema(override_data, title)
            if validated_override:
                self.logger.info(f"Using override from watch_links_overrides.json for {title}: {list(validated_override.keys())}")
                self.stats['override_hits'] = self.stats.get('override_hits', 0) + 1
                return validated_override
        except Exception as e:
            self.logger.warning(f"Invalid override in watch_links_overrides.json for {title}: {e}")

        return None

    def _try_cached_links(self, cache_key, force_refresh):
        """
        Try to get links from cache, handling placeholder ASIN purging and format migration.

        Args:
            cache_key: Cache key (movie_id as string)
            force_refresh: If True, skip cache lookup

        Returns:
            Dict of cached links if found and valid, None otherwise
        """
        if force_refresh or cache_key not in self.watch_links_cache:
            return None

        cached = self.watch_links_cache[cache_key]
        if not cached.get('links'):
            return None

        self.stats['cache_hits'] += 1

        # Check for placeholder ASINs and purge if found
        if self._has_placeholder_asin(cached['links']):
            del self.watch_links_cache[cache_key]
            self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
            self.logger.info(f"Purged cache entry {cache_key} containing placeholder ASIN")
            return None

        # Migrate legacy cache format if needed
        migrated_links = self.migrate_legacy_cache_format(cached['links'])
        if migrated_links != cached['links']:
            self._update_cache_with_migration(cache_key, migrated_links)

        return migrated_links

    def _has_placeholder_asin(self, links):
        """Check if links contain any placeholder ASINs."""
        for category in ['streaming', 'vod']:
            category_data = links.get(category)
            if not category_data:
                continue

            if isinstance(category_data, list):
                for item in category_data:
                    if isinstance(item, dict):
                        link = item.get('link', '')
                        if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                            return True
            elif isinstance(category_data, dict):
                link = category_data.get('link', '')
                if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                    return True

        return False

    def _update_cache_with_migration(self, cache_key, migrated_links):
        """Update cache entry with migrated format and recomputed metadata."""
        self.watch_links_cache[cache_key]['links'] = migrated_links

        # Recompute source metadata
        has_links = any(
            self._check_category_has_links(category_data)
            for category_data in migrated_links.values()
        )
        source_type = 'legacy_cache' if has_links else 'tmdb_providers'
        self.watch_links_cache[cache_key]['source'] = source_type
        self.watch_links_cache[cache_key]['cached_at'] = datetime.now().isoformat()

        self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

    def _check_category_has_links(self, category_data):
        """Check if a category (array or dict) has any non-null links."""
        if isinstance(category_data, list):
            return any(item.get('link') is not None for item in category_data if isinstance(item, dict))
        elif isinstance(category_data, dict):
            return category_data.get('link') is not None
        return False

    def _try_justwatch_api(self, title, year, cache_key, validated_overrides, providers=None,
                           original_title=None, director=None, tmdb_id=None):
        """
        Try to get links from JustWatch API with confidence checking.

        Uses verify_availability() to ensure JustWatch matched the correct movie
        before accepting watch links. Rejects low-confidence matches (e.g., wrong
        title/year) to prevent linking to the wrong film.

        Args:
            title: Movie title
            year: Release year
            cache_key: Cache key for storing result
            validated_overrides: Dict of admin overrides to apply
            providers: TMDB provider dict for cross-validation
            original_title: Original language title (for JustWatch title matching)
            director: Director name (for disambiguation of same-title movies)
            tmdb_id: TMDB ID for fallback matching when titles differ

        Returns:
            Tuple of (validated_links or None, provider_names dict or None).
            provider_names contains service names JustWatch identified, even when
            watch_links are incomplete.
        """
        jw_provider_names = None

        try:
            from pipeline.justwatch import JustWatchClient

            # Get affiliate tag from config
            amazon_tag = self._get_amazon_affiliate_tag()

            # Get excluded services from config (e.g. Philo, fuboTV)
            excluded_services = self.config.get('tracking', {}).get('excluded_services', ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo'])

            # Initialize JustWatch client (lazy)
            if not hasattr(self, '_justwatch_client'):
                self._justwatch_client = JustWatchClient(logger=self.logger)

            # Detect TV shows (tv_ prefix on TMDB ID) and search JustWatch accordingly
            content_type = 'tv' if cache_key.startswith('tv_') else 'movie'

            # Use verify_availability for confidence-checked search
            result = self._justwatch_client.verify_availability(
                title, year, excluded_services=excluded_services, affiliate_tag=amazon_tag,
                content_type=content_type, original_title=original_title, director=director,
                tmdb_id=tmdb_id
            )

            if result is None:
                self.logger.debug(f"JustWatch: no results for {title}")
                return None, None

            # Reject low-confidence matches (prevents wrong-movie links).
            # Do NOT pass provider_names from rejected matches — they're from the wrong movie.
            confidence = result.get('match_confidence', 'first_result')
            jw_config = self.config.get('justwatch_verification', {})
            min_confidence = jw_config.get('min_confidence', 'close_year')
            confidence_levels = ['exact_year', 'tmdb_id', 'close_year', 'title_only', 'first_result']
            min_idx = confidence_levels.index(min_confidence) if min_confidence in confidence_levels else 1
            result_idx = confidence_levels.index(confidence) if confidence in confidence_levels else 3

            if result_idx > min_idx:
                self.logger.warning(
                    f"JustWatch enrichment: low-confidence match for {title} ({year}) — "
                    f"matched '{result['jw_title']}' ({result['jw_year']}) "
                    f"[confidence: {confidence}] — rejecting watch links"
                )
                return None, None

            # Confidence is good — extract provider names
            jw_provider_names = result.get('provider_names')

            justwatch_links = result.get('watch_links', {})

            if justwatch_links:
                self.logger.info(
                    f"JustWatch found links for {title} [confidence: {confidence}, "
                    f"matched: '{result['jw_title']}' ({result['jw_year']})]: "
                    f"{list(justwatch_links.keys())}"
                )
                self.stats['justwatch_successes'] = self.stats.get('justwatch_successes', 0) + 1

                # Domain validation: reject JustWatch links where service doesn't match URL domain
                justwatch_links = self._validate_justwatch_domains(justwatch_links, title, providers)

                validated_links = self.validator.validate_watch_links_schema(justwatch_links, title)
                if validated_links:
                    # Overlay any admin overrides
                    for category, override_data in validated_overrides.items():
                        validated_links[category] = override_data

                    # Cache the result
                    self.watch_links_cache[cache_key] = {
                        'links': validated_links,
                        'cached_at': datetime.now().isoformat(),
                        'source': 'justwatch_api'
                    }
                    self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

                    return validated_links, jw_provider_names
            else:
                self.logger.debug(f"JustWatch: no watch links for {title}")

        except ImportError:
            self.logger.debug("JustWatch client not available")
        except Exception as e:
            self.logger.warning(f"JustWatch API error for {title}: {e}")

        return None, jw_provider_names

    def _validate_justwatch_domains(self, justwatch_links, title, providers=None):
        """Validate JustWatch results: check URL domain matches service name."""
        for category in list(justwatch_links.keys()):
            link_data = justwatch_links[category]

            # Handle both dict (single entry) and list formats
            entries = link_data if isinstance(link_data, list) else [link_data] if isinstance(link_data, dict) else []
            validated_entries = []

            for entry in entries:
                if not isinstance(entry, dict):
                    validated_entries.append(entry)
                    continue

                service = entry.get('service', '')
                link = entry.get('link', '')

                # Check 1: Domain must match service name
                if link and not self._validate_link_domain(link, service):
                    self.logger.warning(
                        f"JustWatch domain mismatch for '{title}': service '{service}' returned link '{link}'. Rejecting."
                    )
                    continue

                validated_entries.append(entry)

            # Update the category with validated entries
            if isinstance(link_data, list):
                justwatch_links[category] = validated_entries
            elif isinstance(link_data, dict):
                justwatch_links[category] = validated_entries[0] if validated_entries else {'service': link_data.get('service', ''), 'link': None}

        return justwatch_links

    def _get_amazon_affiliate_tag(self):
        """Get Amazon affiliate tag from config if enabled."""
        affiliate_config = self.config.get('affiliate', {})
        if not affiliate_config.get('enabled'):
            return None
        if not affiliate_config.get('amazon', {}).get('enabled'):
            return None

        amazon_tag = affiliate_config.get('amazon', {}).get('tag')
        if amazon_tag == 'REPLACE_WITH_YOUR_AMAZON_TAG':
            return None

        return amazon_tag

    def _build_scraper_fallback_links(self, movie_id, title, year, providers, validated_overrides,
                                       title_variants=None):
        """
        Build watch links from scrapers when JustWatch has no data.

        Args:
            movie_id: TMDB movie ID
            title: Movie title
            year: Release year
            providers: Dict with streaming/vod provider lists from TMDB
            validated_overrides: Dict of admin overrides
            title_variants: List of title variants to try (English, original, US alt)

        Returns:
            Tuple of (watch_links dict, vod_scraper_used bool)
        """
        # Skip scraper calls for categories that already have overrides
        skip_streaming = 'streaming' in validated_overrides
        skip_rent = 'rent' in validated_overrides
        skip_buy = 'buy' in validated_overrides

        # Initialize tracking lists
        tmdb_streaming = []
        tmdb_rent = []
        tmdb_buy = []

        # Capture lengths before platform scraper
        streaming_len_before = len(tmdb_streaming)
        rent_len_before = len(tmdb_rent)
        buy_len_before = len(tmdb_buy)

        # Try VOD scraper on every film — TMDB provider data is unreliable
        # (Type 4 movies often have zero providers listed but ARE available).
        # Films with existing watch_links are already short-circuited by the cache
        # at step 3 of the waterfall, so this only runs on uncached films.
        # Note: Playwright is not thread-safe — running VOD scraper in a
        # separate thread poisons the shared browser for all subsequent scrapers.
        # Rely on built-in page timeouts (10s) + speculative retries=1 instead.
        has_vod_scraper = self._check_vod_scraper_available()
        if has_vod_scraper:
            self.try_vod_scraper(title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy,
                                 skip_streaming, skip_rent, skip_buy)

        # Check if platform scraper added any links
        vod_scraper_used = (
            len(tmdb_streaming) > streaming_len_before or
            len(tmdb_rent) > rent_len_before or
            len(tmdb_buy) > buy_len_before
        )

        # Build watch_links structure
        watch_links = {}

        # Build streaming links (deduped at the get_watch_links exit boundary
        # via normalize_watch_links — no per-path dedup needed here)
        if not skip_streaming:
            streaming = self._build_streaming_links(
                movie_id, title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy,
                title_variants=title_variants
            )
            if streaming:
                watch_links['streaming'] = streaming

        # Build VOD links
        if not (skip_rent and skip_buy):
            watch_links['vod'] = self._build_vod_links(
                movie_id, title, year, providers, tmdb_rent, tmdb_buy, has_vod_scraper,
                title_variants=title_variants
            )

        # Overlay admin overrides
        for category, override_data in validated_overrides.items():
            watch_links[category] = override_data

        return watch_links, vod_scraper_used

    def _check_vod_scraper_available(self):
        """Check if StreamingPlatformScraper is available."""
        try:
            from streaming_platform_scraper import StreamingPlatformScraper
            return True
        except ImportError:
            return False

    def _build_streaming_links(self, movie_id, title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy,
                               title_variants=None):
        """Build streaming service list (deduped) from available sources."""
        streaming_services = []

        if tmdb_streaming:
            for source in tmdb_streaming:
                if source.get('link') and not self.is_excluded_service(source.get('service')):
                    streaming_services.append(source)

        if not streaming_services and providers.get('streaming'):
            for provider in providers['streaming']:
                if self.is_excluded_service(provider):
                    continue

                # Smart fallback: reuse Amazon rent/buy link for Prime Video
                if 'Amazon Prime Video' in provider and (tmdb_rent or tmdb_buy):
                    amazon_link = self._find_amazon_link(tmdb_rent, tmdb_buy)
                    streaming_services.append({'service': provider, 'link': amazon_link})
                else:
                    agent_result = self.try_streaming_scraper(movie_id, title, year, provider, 'streaming',
                                                              title_variants=title_variants)
                    streaming_services.append(agent_result)

        # Return ALL streaming options as a list (dedupe by service). The UI
        # renders every free stream side by side, mirroring the VOD row.
        seen = {}
        for s in streaming_services:
            svc = s.get('service')
            if svc and svc not in seen:
                seen[svc] = s
        deduped = list(seen.values())
        with_links = [s for s in deduped if s.get('link')]
        if with_links:
            return with_links
        if deduped:
            return deduped[:1]
        return None

    def _find_amazon_link(self, tmdb_rent, tmdb_buy):
        """Find an Amazon link from rent or buy sources."""
        for source in tmdb_rent + tmdb_buy:
            if 'Amazon' in source.get('service', '') and source.get('link'):
                return source['link']
        return None

    def _build_vod_links(self, movie_id, title, year, providers, tmdb_rent, tmdb_buy, has_vod_scraper,
                         title_variants=None):
        """Build VOD services array filtered to Amazon and Apple TV."""
        vod_sources = tmdb_rent + tmdb_buy

        # Filter to Amazon and Apple TV
        filtered_vod = []
        for source in vod_sources:
            if source.get('link') and self.is_amazon_or_apple_service(source.get('service')):
                filtered_vod.append(source)

        if not filtered_vod:
            # Try additional providers from TMDB + always include Amazon/Apple
            vod_providers = providers.get('rent', []) + providers.get('buy', [])
            amazon_apple_providers = [p for p in vod_providers if self.is_amazon_or_apple_service(p)]

            # Always include Amazon and Apple TV as candidates (TMDB data is incomplete)
            platforms_config = self.config.get('vod_scraper', {}).get('platforms', {})
            if platforms_config.get('amazon', True) and 'Amazon Video' not in amazon_apple_providers:
                amazon_apple_providers.append('Amazon Video')
            if platforms_config.get('apple_tv', True) and 'Apple TV' not in amazon_apple_providers:
                amazon_apple_providers.append('Apple TV')

            for vod_service in amazon_apple_providers:
                if has_vod_scraper:
                    self.try_vod_scraper(title, year, providers, [], tmdb_rent, tmdb_buy, True, False, False)
                    for source in tmdb_rent + tmdb_buy:
                        if source.get('link') and self.is_amazon_or_apple_service(source.get('service')):
                            if source not in filtered_vod:
                                filtered_vod.append(source)

                if not any(self.is_amazon_or_apple_service(s.get('service')) and s.get('service') == vod_service
                           for s in filtered_vod):
                    agent_result = self.try_streaming_scraper(movie_id, title, year, vod_service, 'vod',
                                                              title_variants=title_variants)
                    if agent_result.get('link'):
                        filtered_vod.append(agent_result)

        return filtered_vod

    def _apply_affiliate_tags_batch(self, validated_links, title):
        """Apply affiliate tags to all links in validated_links (modifies in place)."""
        for category in ['streaming', 'vod']:
            if category not in validated_links:
                continue

            category_data = validated_links[category]

            if isinstance(category_data, list):
                for link_data in category_data:
                    if isinstance(link_data, dict) and link_data.get('link') and link_data.get('service'):
                        original_link = link_data['link']
                        tagged_link = self.append_affiliate_tag(original_link, link_data['service'])
                        if tagged_link != original_link:
                            link_data['link'] = tagged_link
                            self.logger.debug(f"Added affiliate tag to {category} link for {title}: {link_data['service']}")

            elif isinstance(category_data, dict):
                if category_data.get('link') and category_data.get('service'):
                    original_link = category_data['link']
                    tagged_link = self.append_affiliate_tag(original_link, category_data['service'])
                    if tagged_link != original_link:
                        validated_links[category]['link'] = tagged_link
                        self.logger.debug(f"Added affiliate tag to {category} link for {title}: {category_data['service']}")

    def _validate_link_consistency_batch(self, validated_links, title):
        """Validate service/link consistency and null out mismatches (modifies in place)."""
        for category in ['streaming', 'vod']:
            if category not in validated_links:
                continue

            category_data = validated_links[category]

            if isinstance(category_data, list):
                for link_data in category_data:
                    if isinstance(link_data, dict):
                        service = link_data.get('service')
                        link = link_data.get('link')
                        if service and link and not self.validate_service_link_consistency(service, link, title):
                            self.logger.warning(f"Replacing mismatched {category} link for {title} with null")
                            link_data['link'] = None

            elif isinstance(category_data, dict):
                service = category_data.get('service')
                link = category_data.get('link')
                if service and link and not self.validate_service_link_consistency(service, link, title):
                    self.logger.warning(f"Replacing mismatched {category} link for {title} with null")
                    validated_links[category]['link'] = None

    def _cache_watch_links_result(self, cache_key, validated_links, vod_scraper_used):
        """Cache the validated watch links with source metadata."""
        if not validated_links:
            return

        # Determine source type
        has_links = any(
            self._check_category_has_links(category_data)
            for category_data in validated_links.values()
        )

        if vod_scraper_used:
            source_type = 'agent_search'
        elif has_links:
            source_type = 'legacy_cache'
        else:
            source_type = 'tmdb_providers'

        self.watch_links_cache[cache_key] = {
            'links': validated_links,
            'cached_at': datetime.now().isoformat(),
            'source': source_type
        }
        self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

    # Expected URL domains for each streaming service — used to reject cross-service mismatches
    EXPECTED_DOMAINS = {
        'Netflix': ['netflix.com'],
        'Disney+': ['disneyplus.com'],
        'Disney Plus': ['disneyplus.com'],
        'HBO Max': ['max.com', 'play.max.com'],
        'Max': ['max.com', 'play.max.com'],
        'Hulu': ['hulu.com'],
        'Amazon Video': ['amazon.com', 'watch.amazon.com', 'primevideo.com'],
        'Amazon Prime Video': ['amazon.com', 'watch.amazon.com', 'primevideo.com'],
        'Prime Video': ['amazon.com', 'watch.amazon.com', 'primevideo.com'],
        'Apple TV': ['tv.apple.com'],
        'Shudder': ['shudder.com'],
        'Criterion': ['criterionchannel.com'],
        'MUBI': ['mubi.com'],
        'Paramount+': ['paramountplus.com'],
        'Paramount Plus': ['paramountplus.com'],
        'Peacock': ['peacocktv.com'],
        'Eventive': ['eventive.org', 'watch.eventive.org'],
        'YouTube': ['youtube.com', 'www.youtube.com'],
    }

    def _validate_link_domain(self, link_url, service):
        """Check if a link URL's domain matches the expected service."""
        if not link_url or not service:
            return True  # Can't validate, allow through
        expected = self.EXPECTED_DOMAINS.get(service)
        if not expected:
            return True  # Unknown service, allow through
        link_lower = link_url.lower()
        return any(domain in link_lower for domain in expected)

    # Known URL patterns for services not covered by scraper
    SERVICE_URL_PATTERNS = {
        'Bloodstream': 'https://bloodstreamtv.com/show-details/{slug}',
    }

    def _generate_service_url(self, service, title):
        """Generate watch URL for services with known URL patterns."""
        pattern = self.SERVICE_URL_PATTERNS.get(service)
        if not pattern:
            return None
        slug = title.lower().replace("'", "").replace(":", "").replace(" ", "-")
        return pattern.replace('{slug}', slug)

    def try_streaming_scraper(self, movie_id, title, year, service, category, title_variants=None):
        """
        Try Playwright agent scraper for supported platforms, with title variant fallback.

        Args:
            movie_id: TMDB movie ID
            title: Movie title (primary)
            year: Release year
            service: Service name to try
            category: Category (streaming/vod)
            title_variants: Optional list of title variants to try in sequence

        Returns:
            Dict: {'service': service_name, 'link': url_or_none}
        """
        supported_platforms = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max', 'Hulu']

        if service not in supported_platforms:
            # Try URL pattern generation for known services
            generated_url = self._generate_service_url(service, title)
            if generated_url:
                self.logger.info(f"Generated URL for {title} on {service}: {generated_url}")
                return {'service': service, 'link': generated_url}
            self.logger.debug(f"'{service}' not supported by any scraper, returning null")
            return {'service': service, 'link': None}

        # Initialize agent scraper if needed
        self._init_streaming_scraper()
        self.logger.debug(f"Agent scraper state: {type(self.streaming_scraper).__name__ if self.streaming_scraper else 'None or False'}")
        if self.streaming_scraper is False:
            return {'service': service, 'link': None}

        # Build list of titles to try (primary title + variants)
        titles_to_try = title_variants if title_variants else [title]

        for title_attempt in titles_to_try:
            try:
                self.logger.debug(f"Trying agent scraper for '{title_attempt}' on {service}")
                self.stats['streaming_attempts'] += 1

                result = self.streaming_scraper.find_watch_link(movie_id, title_attempt, year, service)

                # Defensive logging and guard against None result shape
                self.logger.debug(f"Agent result type: {type(result).__name__}, value: {result}")
                if not isinstance(result, dict):
                    self.logger.warning(f"Agent result was not a dict, converting to {{'link': None}}")
                    result = {'link': None}

                if result.get('cached'):
                    self.stats['vod_cache_hits'] += 1

                link = result.get('link')

                # Domain validation: reject links that don't match the expected service
                if link and not self._validate_link_domain(link, service):
                    self.logger.warning(f"Domain mismatch for {title_attempt}: got '{link}' but expected {service} domain. Rejecting.")
                    continue  # Try next title variant

                if link:
                    self.stats['streaming_successes'] += 1
                    if title_attempt != title:
                        self.logger.info(f"Agent found link for '{title}' on {service} using variant title: '{title_attempt}'")
                    else:
                        self.logger.info(f"Agent found link for {title} on {service}")
                    return {'service': service, 'link': link}

            except Exception as e:
                self.logger.error(f"Error in agent scraper for '{title_attempt}' on {service}: {e}")
                continue  # Try next title variant

        # All title variants failed
        self.stats['streaming_failures'] += 1
        if len(titles_to_try) > 1:
            self.logger.debug(f"Agent could not find link for {title} on {service} (tried {len(titles_to_try)} title variants)")
        else:
            self.logger.debug(f"Agent could not find link for {title} on {service}")
        return {'service': service, 'link': None}

    def _init_streaming_scraper(self):
        """Initialize agent scraper if not already initialized"""
        if self.streaming_scraper is None:
            # Check enrichment flag first
            if not self.enrichment_enabled:
                self.logger.debug("Agent scraper disabled - enrichment not enabled")
                self.streaming_scraper = False
                return

            try:
                from agent_link_scraper import AgentLinkScraper
                self.streaming_scraper = AgentLinkScraper()
                self.logger.info("Agent scraper initialized")
            except Exception as e:
                self.logger.warning(f"Could not initialize agent scraper: {e}")
                self.streaming_scraper = False

    def _init_vod_scraper(self):
        """Initialize VOD scraper (Amazon/Apple TV) if needed."""
        if self.vod_scraper is None:
            # Check enrichment flag first
            if not self.enrichment_enabled:
                self.logger.debug("VOD scraper disabled - enrichment not enabled")
                self.vod_scraper = False
                return

            try:
                from streaming_platform_scraper import StreamingPlatformScraper
                vod_config = self.config.get('vod_scraper', {})
                headless_mode = vod_config.get('headless', True)
                self.vod_scraper = StreamingPlatformScraper(
                    headless=headless_mode,
                    config=self.config
                )
                self.logger.info(f"VOD scraper initialized (headless={headless_mode}, timeout={self.vod_scraper.timeout_seconds}s)")
            except Exception as e:
                self.logger.warning(f"Could not initialize VOD scraper: {e}")
                self.vod_scraper = False

    def try_vod_scraper(self, title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy, skip_streaming, skip_rent, skip_buy):
        """
        Try platform scraper (Playwright) for Amazon/Apple TV deep links.

        Args:
            title: Movie title
            year: Release year
            providers: Dict with streaming/vod provider lists from TMDB
            tmdb_streaming: List of streaming sources to append to
            tmdb_rent: List of rent sources to append to
            tmdb_buy: List of buy sources to append to
            skip_streaming: Skip streaming category
            skip_rent: Skip rent category
            skip_buy: Skip buy category
        """
        # Import here to avoid circular dependency
        try:
            from streaming_platform_scraper import StreamingPlatformScraper
        except ImportError:
            return

        # Check if platform scraper is enabled in config
        vod_config = self.config.get('vod_scraper', {})
        if not vod_config.get('enabled', True):
            self.logger.debug(f"Platform scraper disabled in config, skipping {title}")
            return

        # Check if Amazon is enabled
        platforms_config = vod_config.get('platforms', {})
        amazon_enabled = platforms_config.get('amazon', True)
        apple_tv_enabled = platforms_config.get('apple_tv', True)
        youtube_enabled = platforms_config.get('youtube', True)

        if not amazon_enabled and not apple_tv_enabled and not youtube_enabled:
            self.logger.debug(f"No platforms enabled in config, skipping {title}")
            return

        # Initialize VOD scraper if needed
        self._init_vod_scraper()

        # Skip if initialization failed
        if self.vod_scraper is False:
            self.logger.warning(f"Platform scraper initialization failed, skipping {title}")
            return

        # Track platform scraper attempts
        self.stats['vod_attempts'] = self.stats.get('vod_attempts', 0) + 1

        # Helper to check if links are Google fallbacks
        def has_google_fallback(link_list):
            if not link_list:
                return False
            return any('google.com/search' in item.get('link', '') for item in link_list)

        # Try streaming providers (if no streaming data OR Google fallback, and not skipped)
        if not skip_streaming and (not tmdb_streaming or has_google_fallback(tmdb_streaming)) and providers.get('streaming'):
            for provider in providers['streaming']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True
                elif youtube_enabled and 'youtube' in provider.lower():
                    should_try_provider = True

                if should_try_provider:
                    try:
                        self.logger.debug(f"Trying platform scraper for {title} streaming on {provider}")
                        deep_link = self.get_platform_deep_link_with_cache(title, year, provider)
                        if deep_link:
                            self.logger.info(f"Platform scraper found streaming link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            tmdb_streaming[:] = [s for s in tmdb_streaming if 'google.com/search' not in s.get('link', '')]
                            tmdb_streaming.append({'service': provider, 'link': deep_link})
                            self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        self.logger.error(f"Error in platform scraper for {title} streaming on {provider}: {e}")
                        self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1
                else:
                    self.logger.debug(f"Platform {provider} disabled in config, skipping")

        # Try rent providers (if no rent data OR Google fallback, and not skipped)
        if not skip_rent and (not tmdb_rent or has_google_fallback(tmdb_rent)) and providers.get('rent'):
            for provider in providers['rent']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True
                elif youtube_enabled and 'youtube' in provider.lower():
                    should_try_provider = True

                if should_try_provider:
                    try:
                        self.logger.debug(f"Trying platform scraper for {title} rent on {provider}")
                        deep_link = self.get_platform_deep_link_with_cache(title, year, provider)
                        if deep_link:
                            self.logger.info(f"Platform scraper found rent link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            tmdb_rent[:] = [s for s in tmdb_rent if 'google.com/search' not in s.get('link', '')]
                            tmdb_rent.append({'service': provider, 'link': deep_link})
                            self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        self.logger.error(f"Error in platform scraper for {title} rent on {provider}: {e}")
                        self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1
                else:
                    self.logger.debug(f"Platform {provider} disabled in config, skipping")

        # Try buy providers (if no buy data OR Google fallback, and not skipped)
        if not skip_buy and (not tmdb_buy or has_google_fallback(tmdb_buy)) and providers.get('buy'):
            for provider in providers['buy']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True
                elif youtube_enabled and 'youtube' in provider.lower():
                    should_try_provider = True

                if should_try_provider:
                    try:
                        self.logger.debug(f"Trying platform scraper for {title} buy on {provider}")
                        deep_link = self.get_platform_deep_link_with_cache(title, year, provider)
                        if deep_link:
                            self.logger.info(f"Platform scraper found buy link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            tmdb_buy[:] = [s for s in tmdb_buy if 'google.com/search' not in s.get('link', '')]
                            tmdb_buy.append({'service': provider, 'link': deep_link})
                            self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        self.logger.error(f"Error in platform scraper for {title} buy on {provider}: {e}")
                        self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1
                else:
                    self.logger.debug(f"Platform {provider} disabled in config, skipping")

        # --- Speculative scraping: try Amazon/Apple/YouTube for ALL movies ---
        # TMDB provider data is often incomplete. Many movies are available on
        # Amazon/Apple/YouTube but TMDB doesn't list them. Try all platforms regardless.
        vod_config = self.config.get('vod_scraper', {})
        if not vod_config.get('speculative_scraping', True):
            return

        already_has_amazon = any(
            self.is_actual_amazon_service(s.get('service', ''))
            for s in (tmdb_rent + tmdb_buy + tmdb_streaming) if s.get('link')
        )
        already_has_apple = any(
            self.is_actual_apple_service(s.get('service', ''))
            for s in (tmdb_rent + tmdb_buy + tmdb_streaming) if s.get('link')
        )
        already_has_youtube = any(
            'youtube' in s.get('service', '').lower()
            for s in (tmdb_rent + tmdb_buy) if s.get('link')
        )

        # Reduce retries for speculative scraping (mostly misses, don't waste time)
        original_retries = self.vod_scraper.max_retries
        self.vod_scraper.max_retries = 1

        try:
            if amazon_enabled and not already_has_amazon and not skip_rent:
                try:
                    self.logger.debug(f"Speculative Amazon scrape for {title} (not in TMDB providers)")
                    deep_link = self.get_platform_deep_link_with_cache(title, year, 'Amazon Video')
                    if deep_link:
                        self.logger.info(f"Speculative scrape found Amazon link for {title}")
                        tmdb_rent.append({'service': 'Amazon Video', 'link': deep_link})
                        self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                    else:
                        self.stats['vod_speculative_misses'] = self.stats.get('vod_speculative_misses', 0) + 1
                except Exception as e:
                    self.logger.error(f"Error in speculative Amazon scrape for {title}: {e}")
                    self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1

            if apple_tv_enabled and not already_has_apple and not skip_buy:
                try:
                    self.logger.debug(f"Speculative Apple TV scrape for {title} (not in TMDB providers)")
                    deep_link = self.get_platform_deep_link_with_cache(title, year, 'Apple TV')
                    if deep_link:
                        self.logger.info(f"Speculative scrape found Apple TV link for {title}")
                        tmdb_buy.append({'service': 'Apple TV', 'link': deep_link})
                        self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                    else:
                        self.stats['vod_speculative_misses'] = self.stats.get('vod_speculative_misses', 0) + 1
                except Exception as e:
                    self.logger.error(f"Error in speculative Apple TV scrape for {title}: {e}")
                    self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1

            # YouTube: NO speculative scraping — only search when JustWatch
            # confirms YouTube availability (via provider-based scraping above).
            # Speculative YouTube searches produce false positives (podcasts, etc).
        finally:
            self.vod_scraper.max_retries = original_retries

    def get_platform_deep_link_with_cache(self, title, year, provider):
        """
        Get platform deep link with ASIN caching for Amazon services.

        Args:
            title: Movie title
            year: Release year
            provider: Provider name

        Returns:
            str: Deep link URL or None
        """
        # Check ASIN cache for Amazon links first
        cached_asin = self._amazon_asin_cache.get((title.lower(), str(year or '').strip()))
        if cached_asin and self.is_actual_amazon_service(provider):
            self.logger.debug(f"Using cached Amazon ASIN {cached_asin} for {title}")
            return f"https://www.amazon.com/gp/video/detail/{cached_asin}"

        # No cache hit, perform actual search
        self.enforce_vod_scraper_rate_limit()
        deep_link = self.vod_scraper.get_platform_deep_link(title, year, provider)

        # Cache Amazon ASIN if found
        if deep_link and self.is_actual_amazon_service(provider):
            asin_match = re.search(r'/gp/video/detail/([A-Z0-9]{10})', deep_link)
            if asin_match:
                self._amazon_asin_cache[(title.lower(), str(year or '').strip())] = asin_match.group(1)

        return deep_link

    def enforce_vod_scraper_rate_limit(self):
        """Enforce rate limiting for platform scraper calls"""
        if hasattr(self.vod_scraper, 'rate_limit_seconds') and self.vod_scraper.rate_limit_seconds:
            time_since_last = time.time() - self._last_vod_scraper_time
            if time_since_last < self.vod_scraper.rate_limit_seconds:
                sleep_time = self.vod_scraper.rate_limit_seconds - time_since_last
                self.logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s before platform scraper")
                time.sleep(sleep_time)

            self._last_vod_scraper_time = time.time()

    def normalize_watch_links_urls(self, watch_links):
        """
        Normalize relative Amazon and Apple TV links to absolute URLs.

        Args:
            watch_links: Dict with streaming/vod categories (supports both array and dict formats)

        Returns:
            Dict: watch_links with normalized URLs
        """
        if not watch_links:
            return watch_links

        normalized = watch_links.copy()

        def normalize_single_link(link_data):
            """Normalize a single link dict in place."""
            if not isinstance(link_data, dict) or not link_data.get('link'):
                return
            original_link = link_data['link']
            service = link_data.get('service', '')

            # Normalize Amazon links
            if 'amazon' in service.lower() or 'amazon.com' in original_link.lower():
                normalized_link = urljoin('https://www.amazon.com', original_link)
                if normalized_link != original_link:
                    link_data['link'] = normalized_link

            # Normalize Apple TV links
            elif 'apple' in service.lower() or 'tv.apple.com' in original_link.lower():
                normalized_link = urljoin('https://tv.apple.com', original_link)
                if normalized_link != original_link:
                    link_data['link'] = normalized_link

        for category in ['streaming', 'vod']:
            if category not in normalized:
                continue
            category_data = normalized[category]
            # Handle array format (new)
            if isinstance(category_data, list):
                for link_data in category_data:
                    normalize_single_link(link_data)
            # Handle dict format (legacy/backward compatibility)
            elif isinstance(category_data, dict):
                normalize_single_link(category_data)

        return normalized

    def migrate_legacy_cache_format(self, links):
        """
        Migrate legacy free/paid cache format to streaming/vod and normalize URLs.

        Args:
            links: Dict with watch links (potentially in old format)

        Returns:
            Dict: Migrated watch links in canonical format
        """
        if not isinstance(links, dict):
            return links

        # Define search URL patterns that should be normalized to null
        search_url_patterns = [
            'google.com/search',
            'amazon.com/s?',
            'play.google.com/store/search',
            'vudu.com/',
            'microsoft.com/store/search'
        ]

        def normalize_link(link_obj):
            """Normalize a link object, setting search URLs to null while preserving service"""
            if not isinstance(link_obj, dict) or 'service' not in link_obj:
                return link_obj

            link_url = link_obj.get('link')
            if link_url and any(pattern in link_url for pattern in search_url_patterns):
                return {'service': link_obj['service'], 'link': None}
            return link_obj

        # Start with a copy to avoid modifying original
        migrated = {}

        # Remove 'default' key entirely if present
        for key, value in links.items():
            if key == 'default':
                continue  # Skip default key entirely
            migrated[key] = value

        # Convert old 'free/paid' keys to 'streaming/vod'
        if 'free' in migrated:
            migrated['streaming'] = migrated.pop('free')
        if 'paid' in migrated:
            migrated['vod'] = migrated.pop('paid')

        # Normalize all link objects to remove search URLs and convert to array format
        for category in ['streaming', 'vod']:
            if category in migrated:
                category_data = migrated[category]
                # Handle array format - normalize each item
                if isinstance(category_data, list):
                    migrated[category] = [normalize_link(item) for item in category_data]
                # Handle single dict format - normalize and convert to array
                elif isinstance(category_data, dict):
                    normalized_item = normalize_link(category_data)
                    migrated[category] = [normalized_item] if normalized_item.get('service') else []

        # Ensure we only return canonical categories
        final_migrated = {}
        for category in ['streaming', 'vod']:
            if category in migrated:
                final_migrated[category] = migrated[category]

        return final_migrated if final_migrated else {}

    # ============================================================================
    # Utility Methods
    # ============================================================================

    def append_affiliate_tag(self, url, service_name):
        """
        Append affiliate tags to streaming service URLs.

        Args:
            url (str): The original URL
            service_name (str): The service name (e.g., "Amazon Video", "Apple TV")

        Returns:
            str: URL with affiliate tag appended, or original URL if not applicable
        """
        # Return original URL if None or empty
        if not url or not isinstance(url, str):
            return url

        # Check if affiliate tagging is enabled globally
        affiliate_config = self.config.get('affiliate', {})
        if not affiliate_config.get('enabled', False):
            return url

        # Normalize service name for matching
        service_lower = service_name.lower() if service_name else ''

        # Amazon affiliate tagging
        if 'amazon' in service_lower or 'amazon' in url.lower():
            amazon_config = affiliate_config.get('amazon', {})
            if amazon_config.get('enabled', False):
                tag = amazon_config.get('tag', '')
                # Only add tag if it's not a placeholder
                if tag and tag != 'REPLACE_WITH_YOUR_AMAZON_TAG':
                    # Check if URL already has parameters
                    separator = '&' if '?' in url else '?'
                    # Check if tag already exists in URL
                    if 'tag=' not in url:
                        return f"{url}{separator}tag={tag}"

        # Apple affiliate tagging
        elif 'apple' in service_lower or 'itunes' in url.lower() or 'apple.com' in url.lower():
            apple_config = affiliate_config.get('apple', {})
            if apple_config.get('enabled', False):
                token = apple_config.get('token', '')
                # Only add token if it's not a placeholder
                if token and token != 'REPLACE_WITH_YOUR_APPLE_TOKEN':
                    # Check if URL already has parameters
                    separator = '&' if '?' in url else '?'
                    # Check if token already exists in URL
                    if 'at=' not in url:
                        return f"{url}{separator}at={token}"

        # Return original URL if no affiliate tag was added
        return url

    def is_excluded_service(self, service_name):
        """
        Check if a service should be excluded from provider data.

        Args:
            service_name (str): Name of the service to check

        Returns:
            bool: True if service should be excluded, False otherwise
        """
        if not service_name:
            return False
        service_lower = service_name.lower()
        excluded_services = self.config.get('tracking', {}).get('excluded_services', ['fuboTV', 'Philo', 'Sun Nxt', 'Google Play Movies', 'Google Play', 'Shahid VIP', 'Viki', 'Futo'])
        return any(excluded.lower() in service_lower for excluded in excluded_services)

    def is_actual_amazon_service(self, provider):
        """
        Check if a provider is actual Amazon Prime Video vs Amazon Channel subscription.

        Args:
            provider (str): Provider name from TMDB

        Returns:
            bool: True if genuine Amazon Prime Video, False if Amazon Channel
        """
        if not provider or 'Amazon' not in provider:
            return False

        # Reject Amazon Channel subscriptions
        if 'Channel' in provider or 'Channels' in provider:
            return False

        # Accept genuine Amazon Prime Video services
        genuine_amazon_services = [
            'Amazon Video',
            'Amazon Prime Video',
            'Prime Video',
            'Amazon'
        ]

        return provider in genuine_amazon_services or provider == 'Amazon Video'

    def is_actual_apple_service(self, provider):
        """
        Check if a provider is actual Apple TV vs Apple TV Channel subscription.

        Args:
            provider (str): Provider name from TMDB

        Returns:
            bool: True if genuine Apple TV, False if Apple TV Channel
        """
        if not provider or 'Apple' not in provider:
            return False

        # Reject Apple TV Channel subscriptions
        if 'Channel' in provider or 'Channels' in provider:
            return False

        # Accept genuine Apple TV services
        genuine_apple_services = [
            'Apple TV',
            'Apple iTunes',
            'iTunes',
            'Apple TV Plus'
        ]

        return provider in genuine_apple_services

    def is_amazon_or_apple_service(self, service_name):
        """
        Check if service is Amazon or Apple TV for VOD filtering.

        Used to filter VOD options to only show Amazon and Apple TV
        (the two services we have affiliate relationships with).

        Args:
            service_name (str): Service name to check

        Returns:
            bool: True if service is Amazon or Apple TV variant
        """
        if not service_name:
            return False

        amazon_variants = ['Amazon', 'Amazon Video', 'Prime Video', 'Amazon Prime Video']
        apple_variants = ['Apple TV', 'Apple TV+', 'Apple iTunes', 'iTunes']

        return any(variant in service_name for variant in amazon_variants + apple_variants)

    def validate_service_link_consistency(self, service, link, title):
        """
        Validate that a service name matches its link domain.

        Args:
            service (str): Service name
            link (str): Watch link URL
            title (str): Movie title for logging

        Returns:
            bool: True if service and link are consistent, False if mismatch
        """
        if not service or not link:
            return True  # Nothing to validate

        # Define expected domains for each service
        service_domains = {
            'Max': ['max.com', 'hbomax.com'],
            'HBO Max': ['max.com', 'hbomax.com'],
            'Netflix': ['netflix.com'],
            'Disney Plus': ['disneyplus.com'],
            'Disney+': ['disneyplus.com'],
            'Hulu': ['hulu.com'],
            'Amazon Prime Video': ['amazon.com'],
            'Amazon Video': ['amazon.com'],
            'Prime Video': ['amazon.com'],
            'Amazon': ['amazon.com'],
            'Apple TV': ['tv.apple.com', 'itunes.apple.com'],
            'Apple iTunes': ['tv.apple.com', 'itunes.apple.com'],
            'iTunes': ['tv.apple.com', 'itunes.apple.com'],
            'Paramount Plus': ['paramountplus.com'],
            'Peacock': ['peacocktv.com'],
            'Crunchyroll': ['crunchyroll.com'],
            'Funimation': ['funimation.com']
        }

        expected_domains = service_domains.get(service, [])
        if not expected_domains:
            # Unknown service, can't validate
            return True

        # Check if link contains any expected domain
        for domain in expected_domains:
            if domain in link.lower():
                return True

        # Check if it's a Google search fallback (always valid)
        if 'google.com/search' in link.lower():
            return True

        # Mismatch detected
        self.logger.warning(f"Service/link mismatch for {title}: service='{service}' but link='{link}'")
        return False
