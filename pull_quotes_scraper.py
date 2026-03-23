#!/usr/bin/env python3
"""
Pull Quotes Orchestrator

Coordinates RT critic quotes + Letterboxd popular reviews + Gemini extraction
to produce curated pull quotes for each movie.

Workflow:
1. Fetch all RT critic quotes (unfiltered — user curates these in admin)
2. Fetch Letterboxd popular reviews
3. Run Gemini extraction on Letterboxd reviews → punchy pull quotes
4. Combine into unified cache per movie
5. All quotes start selected: false

Created: 2026-03-10
"""

import json
import os
import logging
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class PullQuotesOrchestrator:
    """Orchestrates pull quote collection from multiple sources."""

    def __init__(self, cache_file='cache/pull_quotes_combined.json'):
        self.cache_file = cache_file
        self.cache = self._load_cache()

        # Lazy-initialized scrapers
        self._rt_scraper = None
        self._lb_scraper = None
        self._extractor = None

        self.stats = {
            'movies_processed': 0,
            'rt_quotes_total': 0,
            'lb_quotes_total': 0,
            'extraction_failures': 0
        }

    def _load_cache(self) -> Dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load pull quotes cache: {e}")
        return {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save pull quotes cache: {e}")

    @property
    def rt_scraper(self):
        if self._rt_scraper is None:
            from rt_quote_scraper import RTQuoteScraper
            self._rt_scraper = RTQuoteScraper()
        return self._rt_scraper

    @property
    def lb_scraper(self):
        if self._lb_scraper is None:
            from letterboxd_review_scraper import LetterboxdReviewScraper
            self._lb_scraper = LetterboxdReviewScraper()
        return self._lb_scraper

    @property
    def extractor(self):
        if self._extractor is None:
            from gemini_scraper import GeminiQuoteExtractor
            self._extractor = GeminiQuoteExtractor()
        return self._extractor

    def get_quotes(self, title: str, year: int, rt_url: str = None,
                   force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get pull quotes for a movie from all sources.

        Args:
            title: Movie title
            year: Release year
            rt_url: Rotten Tomatoes URL (optional — skips RT if not provided)
            force_refresh: If True, bypass cache and re-scrape

        Returns:
            Dict with 'rt_quotes', 'lb_quotes', and metadata
        """
        cache_key = f"{title}_{year}"

        # Check cache (unless forcing refresh)
        if not force_refresh and cache_key in self.cache:
            cached = self.cache[cache_key]
            logger.info(f"Using cached pull quotes for {title} ({year})")
            return cached

        logger.info(f"Fetching pull quotes for {title} ({year})")
        result = {
            'title': title,
            'year': year,
            'rt_quotes': [],
            'lb_quotes': [],
            'scraped_at': datetime.now().isoformat(),
            'rt_url': rt_url
        }

        # 1. Fetch RT critic quotes
        if rt_url:
            try:
                rt_quotes = self.rt_scraper.scrape_quotes(rt_url, title, year)
                result['rt_quotes'] = rt_quotes
                self.stats['rt_quotes_total'] += len(rt_quotes)
                logger.info(f"  RT: {len(rt_quotes)} critic quotes")
            except Exception as e:
                logger.error(f"  RT scraping failed for {title}: {e}")
        else:
            logger.info(f"  RT: skipped (no URL)")

        # 2. Fetch Letterboxd popular reviews
        try:
            lb_reviews = self.lb_scraper.scrape_reviews(title, year)

            # 3. Run Gemini extraction on Letterboxd reviews
            if lb_reviews:
                try:
                    lb_reviews = self.extractor.extract_quotes(lb_reviews, title, year)
                except Exception as e:
                    logger.error(f"  Gemini extraction failed for {title}: {e}")
                    self.stats['extraction_failures'] += 1
                    # Reviews still usable without extraction

            result['lb_quotes'] = lb_reviews
            self.stats['lb_quotes_total'] += len(lb_reviews)
            logger.info(f"  Letterboxd: {len(lb_reviews)} reviews")
        except Exception as e:
            logger.error(f"  Letterboxd scraping failed for {title}: {e}")

        # Cache result
        self.cache[cache_key] = result
        self._save_cache()
        self.stats['movies_processed'] += 1

        total = len(result['rt_quotes']) + len(result['lb_quotes'])
        logger.info(f"  Total: {total} quotes for {title}")

        return result

    def get_all_quotes_flat(self, title: str, year: int, rt_url: str = None,
                            force_refresh: bool = False) -> List[Dict]:
        """
        Get all quotes as a flat list (RT + Letterboxd combined).
        Letterboxd reviews use their extracted pull_quote if available.
        """
        data = self.get_quotes(title, year, rt_url, force_refresh)

        all_quotes = []

        # RT quotes go in as-is (user curates these)
        for q in data.get('rt_quotes', []):
            q['display_text'] = q.get('text', '')
            all_quotes.append(q)

        # Letterboxd: use pull_quote if extracted, otherwise full text
        for q in data.get('lb_quotes', []):
            pull_quote = q.get('pull_quote')
            q['display_text'] = pull_quote if pull_quote else q.get('text', '')
            all_quotes.append(q)

        return all_quotes

    def cleanup(self):
        """Clean up all scrapers."""
        if self._rt_scraper:
            try:
                self._rt_scraper.close()
            except Exception:
                pass
        if self._lb_scraper:
            try:
                self._lb_scraper.close()
            except Exception:
                pass

    def close(self):
        self.cleanup()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    # Test with a movie
    title = sys.argv[1] if len(sys.argv) > 1 else "Anora"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    rt_url = sys.argv[3] if len(sys.argv) > 3 else None

    orchestrator = PullQuotesOrchestrator()
    try:
        quotes = orchestrator.get_all_quotes_flat(title, year, rt_url)

        print(f"\n{'='*60}")
        print(f"Pull Quotes for {title} ({year})")
        print(f"{'='*60}")

        rt_count = sum(1 for q in quotes if q['source'] == 'rt_critic')
        lb_count = sum(1 for q in quotes if q['source'] == 'letterboxd')
        print(f"RT: {rt_count} | Letterboxd: {lb_count} | Total: {len(quotes)}")

        for q in quotes:
            source_tag = "RT" if q['source'] == 'rt_critic' else "LB"
            fresh = ""
            if q.get('fresh'):
                fresh = f" [{q['fresh']}]"
            print(f"\n  [{source_tag}{fresh}] {q.get('critic', '?')} ({q.get('outlet', '?')})")
            print(f"    \"{q['display_text']}\"")
    finally:
        orchestrator.cleanup()
