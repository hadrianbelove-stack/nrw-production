#!/usr/bin/env python3
"""
Enrichment Service - Watch link discovery and metadata enrichment for NRW pipeline.

Extracted from generate_data.py (2025-11-10) to separate enrichment concerns.
Handles all watch link discovery across multiple sources with priority waterfall.
"""

import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Union, Any
import logging
from urllib.parse import urljoin

from constants import PLACEHOLDER_ASINS


class EnrichmentService:
    """
    Centralized enrichment operations for watch links and metadata.

    Responsibilities:
        - Orchestrate watch link discovery across multiple sources
        - Integrate agent scraper and platform scraper
        - Apply rate limiting and caching strategies
        - Normalize and validate watch link URLs
        - Manage affiliate tag insertion
        - Handle priority waterfall: manual > overrides > cache > Watchmode > scrapers

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
                'watchmode_successes': 0,
                'streaming_attempts': 0,
                'streaming_successes': 0,
                'streaming_failures': 0,
                'streaming_cache_hits': 0,
                'streaming_attempts': 0,
                'streaming_successes': 0,
                'streaming_failures': 0,
                'search_calls': 0,
                'source_calls': 0
            }

        # Cache references (will be injected)
        self.watch_links_cache = {}
        self.watch_links_overrides = {}
        self.watch_link_overrides = {}

        # Watchmode enabled flag
        self.watchmode_enabled = self.config.get('watchmode', {}).get('enabled', False)

    def set_cache_references(self, watch_links_cache, watch_links_overrides, watch_link_overrides):
        """
        Inject cache references from parent DataGenerator.

        Args:
            watch_links_cache: Reference to watch_links_cache dict
            watch_links_overrides: Reference to watch_links_overrides dict
            watch_link_overrides: Reference to watch_link_overrides dict (legacy)
        """
        self.watch_links_cache = watch_links_cache
        self.watch_links_overrides = watch_links_overrides
        self.watch_link_overrides = watch_link_overrides

    def get_watch_links(self, movie_id, title, year, providers, force_refresh=False, tracking_data=None):
        """
        Get deep links with canonical streaming/vod structure.

        Priority waterfall:
        1. Manual watch links from movie_tracking.json - highest priority
        2. Admin overrides (admin/watch_link_overrides.json) - backward compatibility
        3. Cache (cache/watch_links_cache.json)
        4. Watchmode API
        5. Agent scraper (Netflix, Disney+, HBO Max, Hulu)
        6. TMDB provider names with null links

        Args:
            movie_id: TMDB movie ID
            title: Movie title
            year: Release year
            providers: Dict with streaming/vod provider lists from TMDB
            force_refresh: Skip cache and re-fetch
            tracking_data: Movie tracking data with optional manual_watch_links

        Returns:
            Dict: {
                'streaming': {'service': 'Netflix', 'link': 'https://...'},
                'rent': {'service': 'Amazon', 'link': 'https://...'},
                'buy': {'service': 'Apple TV', 'link': 'https://...'}
            }
        """
        # 1. Check manual watch links from tracking data FIRST (highest priority)
        if tracking_data and 'watch_links' in tracking_data and tracking_data.get('manual_watch_links'):
            manual_links = tracking_data['watch_links']
            try:
                validated_manual = self.validator.validate_watch_links_schema(manual_links, title)
                if validated_manual:
                    print(f"  Using manual watch links from tracking data for {title}: {list(validated_manual.keys())}")
                    self.stats['manual_tracking_hits'] = self.stats.get('manual_tracking_hits', 0) + 1

                    # Cache the validated manual links
                    cache_key = str(movie_id)
                    now = datetime.now().isoformat()
                    self.watch_links_cache[cache_key] = {
                        'links': validated_manual,
                        'cached_at': now,
                        'source': 'manual_tracking'
                    }
                    self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

                    return validated_manual
            except Exception as e:
                print(f"  Warning: Invalid manual watch links in tracking data for {title}: {e}")

        # 2. Check overrides/watch_links_overrides.json (highest priority after manual tracking)
        cache_key = str(movie_id)
        if cache_key in self.watch_links_overrides:
            override_data = self.watch_links_overrides[cache_key]
            try:
                validated_override = self.validator.validate_watch_links_schema(override_data, title)
                if validated_override:
                    print(f"  Using override from watch_links_overrides.json for {title}: {list(validated_override.keys())}")
                    self.stats['override_hits'] = self.stats.get('override_hits', 0) + 1
                    return validated_override
            except Exception as e:
                print(f"  Warning: Invalid override in watch_links_overrides.json for {title}: {e}")

        # 3. Check admin overrides (backward compatibility)
        validated_overrides = {}
        if cache_key in self.watch_link_overrides:
            overrides = self.watch_link_overrides[cache_key]
            # Validate overrides but continue with waterfall for non-overridden categories
            for category in ['streaming', 'vod']:
                if category in overrides:
                    override_data = overrides[category]
                    # Validate structure
                    if isinstance(override_data, dict) and 'service' in override_data and 'link' in override_data:
                        # Validate service name is non-empty string
                        service = override_data['service']
                        if not service or not isinstance(service, str) or not service.strip():
                            print(f"  Warning: Invalid override service name for {title} {category}: {service}")
                            continue
                        # Validate URL if link is not None/empty
                        link = override_data['link']
                        if link and isinstance(link, str) and (link.startswith('http://') or link.startswith('https://')):
                            validated_overrides[category] = override_data
                        elif not link:  # Empty link means "no override for this category"
                            continue
                        else:
                            print(f"  Warning: Invalid override link for {title} {category}: {link}")

            if validated_overrides:
                print(f"  Using admin overrides for {title}: {list(validated_overrides.keys())}")
                self.stats['override_hits'] += 1

        # 4. Check cache (unless force refresh)
        if not force_refresh and cache_key in self.watch_links_cache:
            cached = self.watch_links_cache[cache_key]
            if cached.get('links'):
                self.stats['cache_hits'] += 1

                # Check for placeholder ASINs in cached links and purge if found
                has_placeholder_asin = False
                detected_asin = None
                for category in ['streaming', 'vod']:
                    category_data = cached['links'].get(category, {})
                    if category_data and isinstance(category_data, dict):
                        link = category_data.get('link', '')
                        if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                            detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                            has_placeholder_asin = True
                            break

                if has_placeholder_asin:
                    # Delete the cache entry with placeholder ASIN
                    del self.watch_links_cache[cache_key]
                    self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                    print(f"  Purged cache entry {cache_key} containing placeholder ASIN {detected_asin}")
                else:
                    # Migrate legacy cache format if needed
                    migrated_links = self.migrate_legacy_cache_format(cached['links'])
                    if migrated_links != cached['links']:
                        # Update cache with migrated format
                        self.watch_links_cache[cache_key]['links'] = migrated_links

                        # Recompute source metadata based on whether any category has a non-null link
                        has_links = any(
                            link.get('link') is not None
                            for link in migrated_links.values()
                            if isinstance(link, dict)
                        )
                        source_type = 'watchmode_api' if has_links else 'tmdb_providers'
                        self.watch_links_cache[cache_key]['source'] = source_type
                        self.watch_links_cache[cache_key]['cached_at'] = datetime.now().isoformat()

                        self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')
                    return migrated_links

        # Service priority hierarchies
        STREAMING_PRIORITY = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max',
                              'Hulu', 'Amazon Prime Video', 'Prime Video', 'Apple TV+',
                              'Paramount+', 'Paramount Plus', 'Peacock', 'MUBI', 'Shudder', 'Criterion Channel']

        PAID_PRIORITY = ['Amazon Video', 'Amazon', 'Prime Video', 'Apple TV', 'Vudu',
                         'Google Play Movies', 'Google Play', 'Microsoft Store']

        def select_best_service(service_list, priority_list):
            """Select best service from list based on priority, filtering out excluded services"""
            # Filter out excluded services first
            filtered_services = [s for s in service_list if not self.is_excluded_service(s)]

            if not filtered_services:
                return None

            for priority_service in priority_list:
                for available_service in filtered_services:
                    if priority_service.lower() in available_service.lower():
                        return available_service
            # If no priority match, return first available (from filtered list)
            return filtered_services[0] if filtered_services else None

        # Collect sources from Watchmode API (skip categories that already have overrides)
        tmdb_streaming = []
        tmdb_rent = []
        tmdb_buy = []

        # Skip external API calls for categories that already have overrides
        skip_streaming = 'streaming' in validated_overrides
        skip_rent = 'rent' in validated_overrides
        skip_buy = 'buy' in validated_overrides

        # Agent search tier (optional): Try to find deep links for Amazon/Apple TV when needed
        # Capture lengths before platform scraper to detect if it added links
        streaming_len_before = len(tmdb_streaming)
        rent_len_before = len(tmdb_rent)
        buy_len_before = len(tmdb_buy)

        # Helper function to check if a list contains Google fallback URLs
        def has_google_fallback(link_list):
            """Check if any links in the list are Google search fallbacks"""
            if not link_list:
                return False
            return any('google.com/search' in item.get('link', '') for item in link_list)

        # Call platform scraper if:
        # 1. No data from Watchmode (original logic), OR
        # 2. Watchmode returned Google fallback URLs (needs real link)
        should_try_vod_scraper = (
            not tmdb_streaming or not tmdb_rent or not tmdb_buy or
            has_google_fallback(tmdb_streaming) or
            has_google_fallback(tmdb_rent) or
            has_google_fallback(tmdb_buy)
        )

        # Import StreamingPlatformScraper dynamically to avoid circular import
        try:
            from streaming_platform_scraper import StreamingPlatformScraper
            has_vod_scraper = True
        except ImportError:
            has_vod_scraper = False

        if has_vod_scraper and should_try_vod_scraper:
            self.try_vod_scraper(title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy, skip_streaming, skip_rent, skip_buy)

        # Check if platform scraper actually added any links
        vod_scraper_used = (
            len(tmdb_streaming) > streaming_len_before or
            len(tmdb_rent) > rent_len_before or
            len(tmdb_buy) > buy_len_before
        )

        # Build final watch_links with canonical streaming/vod structure
        watch_links = {}

        # STREAMING: Prefer Watchmode, fallback to TMDB providers with smart Amazon handling (skip if overridden)
        if not skip_streaming:
            if tmdb_streaming:
                # Use Watchmode streaming data
                best_service = select_best_service([s['service'] for s in tmdb_streaming], STREAMING_PRIORITY)
                for source in tmdb_streaming:
                    if source['service'] == best_service:
                        watch_links['streaming'] = source
                        break
            elif providers.get('streaming'):
                # Fallback to TMDB provider data
                service = select_best_service(providers['streaming'], STREAMING_PRIORITY)

                # SMART FALLBACK: If TMDB says "Amazon Prime Video" but Watchmode didn't find subscription,
                # reuse any Amazon rent/buy link we have (it's the same detail page on Amazon)
                if 'Amazon Prime Video' in service and (tmdb_rent or tmdb_buy):
                    # Find any Amazon link in rent or buy sources
                    amazon_link = None
                    for source in tmdb_rent + tmdb_buy:
                        if 'Amazon' in source['service'] and source.get('link'):
                            amazon_link = source['link']
                            break

                    if amazon_link:
                        watch_links['streaming'] = {
                            'service': service,
                            'link': amazon_link  # Same page shows both Prime (free) and rent/buy options
                        }
                    else:
                        # No Amazon link available, leave as null (no Google fallback)
                        watch_links['streaming'] = {
                            'service': service,
                            'link': None
                        }
                else:
                    # Try agent scraper for supported platforms before returning null
                    agent_result = self.try_streaming_scraper(movie_id, title, year, service, 'streaming')
                    watch_links['streaming'] = agent_result

        # VOD: Combine rent and buy into single VOD category
        # Use Watchmode or fallback to platform links (skip if both rent and buy are overridden)
        if not (skip_rent and skip_buy):
            # Combine rent and buy sources
            vod_sources = tmdb_rent + tmdb_buy

            if vod_sources:
                # Pick best service from combined rent+buy options
                best_service = select_best_service([s['service'] for s in vod_sources], PAID_PRIORITY)
                for source in vod_sources:
                    if source['service'] == best_service:
                        watch_links['vod'] = source
                        break
            else:
                # Try rent providers first, then buy providers
                vod_providers = providers.get('rent', []) + providers.get('buy', [])
                if vod_providers:
                    vod_service = select_best_service(vod_providers, PAID_PRIORITY)
                    if vod_service:
                        # Try platform scraper for Amazon/Apple TV before returning null
                        if has_vod_scraper and (self.is_actual_amazon_service(vod_service) or self.is_actual_apple_service(vod_service)):
                            self.try_vod_scraper(title, year, providers, [], tmdb_rent, tmdb_buy, True, False, False)
                            # Check if platform scraper added vod links
                            vod_sources = tmdb_rent + tmdb_buy
                            if vod_sources:
                                best_service = select_best_service([s['service'] for s in vod_sources], PAID_PRIORITY)
                                for source in vod_sources:
                                    if source['service'] == best_service:
                                        watch_links['vod'] = source
                                        break
                            else:
                                # Try agent scraper for supported services
                                agent_result = self.try_streaming_scraper(movie_id, title, year, vod_service, 'vod')
                                watch_links['vod'] = agent_result
                        else:
                            # Try agent scraper for supported services
                            agent_result = self.try_streaming_scraper(movie_id, title, year, vod_service, 'vod')
                            watch_links['vod'] = agent_result

        # Overlay admin overrides on top of auto-discovered links
        for category, override_data in validated_overrides.items():
            watch_links[category] = override_data

        # Normalize relative URLs to absolute URLs as second line of defense
        watch_links = self.normalize_watch_links_urls(watch_links)

        # Validate schema before caching and returning
        validated_links = self.validator.validate_watch_links_schema(watch_links, title)

        # Apply affiliate tags to all validated links (after validation, before caching)
        for category in ['streaming', 'vod']:
            if category in validated_links and isinstance(validated_links[category], dict):
                link_data = validated_links[category]
                if link_data.get('link') and link_data.get('service'):
                    # Append affiliate tag to the link
                    original_link = link_data['link']
                    tagged_link = self.append_affiliate_tag(original_link, link_data['service'])
                    if tagged_link != original_link:
                        validated_links[category]['link'] = tagged_link
                        self.logger.debug(f"Added affiliate tag to {category} link for {title}: {link_data['service']}")

        # Validate service/link consistency and fix mismatches
        for category in ['streaming', 'vod']:
            if category in validated_links and isinstance(validated_links[category], dict):
                link_data = validated_links[category]
                service = link_data.get('service')
                link = link_data.get('link')

                if service and link and not self.validate_service_link_consistency(service, link, title):
                    # Mismatch detected, set to null (no Google fallback)
                    self.logger.warning(f"Replacing mismatched {category} link for {title} with null (admin flag needed)")
                    validated_links[category]['link'] = None

        # Cache result with canonical schema (use validated links)
        if validated_links:
            # Determine source type based on where links came from
            has_links = any(
                link.get('link') is not None
                for link in validated_links.values()
                if isinstance(link, dict)
            )

            # Use vod_scraper_used to accurately determine if streamer scraper added links
            if vod_scraper_used:
                source_type = 'agent_search'
            elif has_links:
                source_type = 'watchmode_api'
            else:
                source_type = 'tmdb_providers'

            self.watch_links_cache[cache_key] = {
                'links': validated_links,
                'cached_at': datetime.now().isoformat(),
                'source': source_type
            }
            self.storage.save_cache(self.watch_links_cache, 'cache/watch_links_cache.json')

        return validated_links

    def try_streaming_scraper(self, movie_id, title, year, service, category):
        """
        Try agent scraper for supported platforms.

        Args:
            movie_id: TMDB movie ID
            title: Movie title
            year: Release year
            service: Service name to try
            category: Category (streaming/vod)

        Returns:
            Dict: {'service': service_name, 'link': url_or_none}
        """
        supported_platforms = ['Netflix', 'Disney+', 'Disney Plus', 'HBO Max', 'Max', 'Hulu']
        print(f"  [DEBUG] Checking if '{service}' is in supported platforms: {supported_platforms}")

        # Check if service is supported
        if service not in supported_platforms:
            print(f"  [DEBUG] '{service}' not supported by agent scraper, returning null")
            return {'service': service, 'link': None}

        # Initialize agent scraper if needed
        self._init_streaming_scraper()
        print(f"  [DEBUG] Agent scraper state: {type(self.streaming_scraper).__name__ if self.streaming_scraper else 'None or False'}")
        if self.streaming_scraper is False:
            return {'service': service, 'link': None}

        try:
            print(f"  Trying agent scraper for {title} on {service}...")
            self.stats['streaming_attempts'] += 1

            result = self.streaming_scraper.find_watch_link(movie_id, title, year, service)

            # Defensive logging and guard against None result shape
            print(f"  [DEBUG] Agent result type: {type(result).__name__}, value: {result}")
            if not isinstance(result, dict):
                print(f"  [WARNING] Agent result was not a dict, converting to {{'link': None}}")
                result = {'link': None}

            if result.get('cached'):
                self.stats['vod_cache_hits'] += 1

            if result.get('link'):
                self.stats['streaming_successes'] += 1
                print(f"  ✓ Agent found link for {title} on {service}")
            else:
                self.stats['streaming_failures'] += 1
                print(f"  ✗ Agent could not find link for {title} on {service}")

            # Return found link or null (no Google fallback)
            return {'service': service, 'link': result.get('link')}

        except Exception as e:
            self.stats['streaming_failures'] += 1
            print(f"  Error in agent scraper for {title}: {e}")
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
                print(f"  VOD scraper initialized (headless={headless_mode}, timeout={self.vod_scraper.timeout_seconds}s)")
            except Exception as e:
                print(f"  Warning: Could not initialize VOD scraper: {e}")
                self.vod_scraper = False

    def try_vod_scraper(self, title, year, providers, tmdb_streaming, tmdb_rent, tmdb_buy, skip_streaming, skip_rent, skip_buy):
        """
        Try platform scraper (Playwright) for Amazon/Apple TV when Watchmode API has no data.

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
            print(f"  Platform scraper disabled in config, skipping {title}")
            return

        # Check if Amazon is enabled
        platforms_config = vod_config.get('platforms', {})
        amazon_enabled = platforms_config.get('amazon', True)
        apple_tv_enabled = platforms_config.get('apple_tv', True)

        if not amazon_enabled and not apple_tv_enabled:
            print(f"  No platforms enabled in config, skipping {title}")
            return

        # Initialize VOD scraper if needed
        self._init_vod_scraper()

        # Skip if initialization failed
        if self.vod_scraper is False:
            print(f"  Platform scraper initialization failed, skipping {title}")
            return

        # Track platform scraper attempts
        self.stats['vod_attempts'] = self.stats.get('vod_attempts', 0) + 1

        # Helper to check if links are Google fallbacks
        def has_google_fallback(link_list):
            if not link_list:
                return False
            return any('google.com/search' in item.get('link', '') for item in link_list)

        # Try streaming providers (if no Watchmode streaming data OR Google fallback, and not skipped)
        if not skip_streaming and (not tmdb_streaming or has_google_fallback(tmdb_streaming)) and providers.get('streaming'):
            for provider in providers['streaming']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} streaming on {provider}...")
                        deep_link = self.get_platform_deep_link_with_cache(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found streaming link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            tmdb_streaming[:] = [s for s in tmdb_streaming if 'google.com/search' not in s.get('link', '')]
                            tmdb_streaming.append({'service': provider, 'link': deep_link})
                            self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        print(f"  Error in platform scraper for {title} streaming on {provider}: {e}")
                        self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1
                else:
                    print(f"  Platform {provider} disabled in config, skipping")

        # Try rent providers (if no Watchmode rent data OR Google fallback, and not skipped)
        if not skip_rent and (not tmdb_rent or has_google_fallback(tmdb_rent)) and providers.get('rent'):
            for provider in providers['rent']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} rent on {provider}...")
                        deep_link = self.get_platform_deep_link_with_cache(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found rent link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            tmdb_rent[:] = [s for s in tmdb_rent if 'google.com/search' not in s.get('link', '')]
                            tmdb_rent.append({'service': provider, 'link': deep_link})
                            self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        print(f"  Error in platform scraper for {title} rent on {provider}: {e}")
                        self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1
                else:
                    print(f"  Platform {provider} disabled in config, skipping")

        # Try buy providers (if no Watchmode buy data OR Google fallback, and not skipped)
        if not skip_buy and (not tmdb_buy or has_google_fallback(tmdb_buy)) and providers.get('buy'):
            for provider in providers['buy']:
                # Filter platforms based on config and validate actual services
                should_try_provider = False
                if amazon_enabled and self.is_actual_amazon_service(provider):
                    should_try_provider = True
                elif apple_tv_enabled and self.is_actual_apple_service(provider):
                    should_try_provider = True

                if should_try_provider:
                    try:
                        print(f"  Trying platform scraper for {title} buy on {provider}...")
                        deep_link = self.get_platform_deep_link_with_cache(title, year, provider)
                        if deep_link:
                            print(f"  ✓ Platform scraper found buy link for {title} on {provider}")
                            # Remove any existing Google fallbacks before adding real link
                            tmdb_buy[:] = [s for s in tmdb_buy if 'google.com/search' not in s.get('link', '')]
                            tmdb_buy.append({'service': provider, 'link': deep_link})
                            self.stats['vod_successes'] = self.stats.get('vod_successes', 0) + 1
                            break  # Found a link, stop searching
                    except Exception as e:
                        print(f"  Error in platform scraper for {title} buy on {provider}: {e}")
                        self.stats['vod_failures'] = self.stats.get('vod_failures', 0) + 1
                else:
                    print(f"  Platform {provider} disabled in config, skipping")

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
            print(f"  ✓ Using cached Amazon ASIN {cached_asin} for {title}")
            return f"https://www.amazon.com/gp/video/detail/{cached_asin}"

        # No cache hit, perform actual search
        self.enforce_vod_scraper_rate_limit()
        deep_link = self.vod_scraper.get_platform_deep_link(title, year, provider)

        # Cache Amazon ASIN if found
        if deep_link and self.is_actual_amazon_service(provider):
            import re
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
                print(f"  Rate limiting: sleeping {sleep_time:.1f}s before platform scraper")
                time.sleep(sleep_time)

            self._last_vod_scraper_time = time.time()

    def normalize_watch_links_urls(self, watch_links):
        """
        Normalize relative Amazon and Apple TV links to absolute URLs.

        Args:
            watch_links: Dict with streaming/vod categories

        Returns:
            Dict: watch_links with normalized URLs
        """
        if not watch_links:
            return watch_links

        normalized = watch_links.copy()

        for category in ['streaming', 'vod']:
            if category in normalized and isinstance(normalized[category], dict):
                link_data = normalized[category]
                if link_data.get('link'):
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

        # Convert old 'rent/buy' keys to single 'vod' (pick first non-null)
        if 'rent' in migrated or 'buy' in migrated:
            # Prefer rent over buy (arbitrary choice, both are VOD)
            if 'rent' in migrated:
                migrated['vod'] = migrated.pop('rent')
                migrated.pop('buy', None)  # Remove buy if it exists
            elif 'buy' in migrated:
                migrated['vod'] = migrated.pop('buy')

        # Normalize all link objects to remove search URLs
        for category in ['streaming', 'vod']:
            if category in migrated:
                migrated[category] = normalize_link(migrated[category])

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
        excluded_services = self.config.get('tracking', {}).get('excluded_services', ['fuboTV', 'Philo'])
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
