#!/usr/bin/env python3
"""
Letterboxd Popular Reviews Scraper

Extracts popular user reviews from Letterboxd film pages.
These are real, verbatim user reviews sorted by engagement (likes/comments).
This is where the funny, smart, well-written user reviews come from.

Uses Playwright because Letterboxd has Cloudflare protection (403 on plain requests).

Created: 2026-03-10
"""

import json
import os
import re
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from scraper_base import PlaywrightScraperBase

logger = logging.getLogger(__name__)


class LetterboxdReviewScraper(PlaywrightScraperBase):
    """Scrapes popular user reviews from Letterboxd film pages.

    Targets the "Popular reviews" section on the main film page,
    which contains the most-liked/engaged reviews.
    """

    def __init__(self, cache_file='cache/letterboxd_reviews_cache.json', config=None, logger_inst=None):
        super().__init__(
            cache_file=cache_file,
            config=config,
            logger=logger_inst,
            config_key='rt_scraper',  # Reuse RT scraper config for timeouts etc
            log_prefix='LetterboxdReviews',
            screenshot_subdir='letterboxd'
        )
        self.rate_limit = 2.0

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached reviews are still fresh (90-day TTL)."""
        if cache_key not in self.cache:
            return False
        entry = self.cache[cache_key]
        if 'scraped_at' not in entry:
            return False
        try:
            scraped_at = datetime.fromisoformat(entry['scraped_at'])
            return datetime.now() < scraped_at + timedelta(days=90)
        except (ValueError, KeyError):
            return False

    def _resolve_slug(self, title: str, year: int = 0) -> Optional[str]:
        """Construct Letterboxd slug from movie title.

        Letterboxd slugs are lowercase, hyphenated, with articles kept.
        e.g., "The Brutalist" -> "the-brutalist"
              "Anora" -> "anora"
        """
        slug = title.lower()
        # Remove special characters but keep hyphens and spaces
        slug = re.sub(r'[^\w\s-]', '', slug)
        # Replace spaces with hyphens
        slug = re.sub(r'\s+', '-', slug)
        # Remove double hyphens
        slug = re.sub(r'-+', '-', slug)
        slug = slug.strip('-')
        return slug

    def _extract_reviews(self) -> List[Dict]:
        """Extract popular reviews from the Letterboxd film page.

        Targets article.production-viewing elements in the popular reviews section.
        Each contains: username, rating, review text, comment count.
        """
        reviews = []

        # Extract all reviews from the popular reviews section
        extracted = self.page.evaluate('''() => {
            let results = [];

            // Find the popular reviews section
            let popSection = document.querySelector("[data-url*='popular-reviews']");
            if (!popSection) {
                // Fallback: look in the full page
                popSection = document;
            }

            let articles = popSection.querySelectorAll("article.production-viewing");
            for (let art of articles) {
                let r = {};

                // Username
                let name = art.querySelector("strong.displayname");
                r.username = name ? name.textContent.trim() : null;
                if (!r.username) continue;

                // Review text - may be in .js-review-body or direct .body-text
                let body = art.querySelector(".js-review-body");
                r.text = body ? body.textContent.trim() : "";

                // Skip empty reviews or very short ones
                if (!r.text || r.text.length < 10) continue;

                // Skip spoiler-hidden reviews (text is hidden)
                let spoiler = art.querySelector(".js-spoiler-container");
                if (spoiler && !body) continue;

                // Rating - class like "rated-8" means 4 stars (rating/2)
                let ratingEl = art.querySelector("span.rating");
                r.rating = null;
                r.ratingStars = "";
                if (ratingEl) {
                    r.ratingStars = ratingEl.textContent.trim();
                    let cls = ratingEl.className;
                    let match = cls.match(/rated-(\\d+)/);
                    if (match) {
                        r.rating = parseInt(match[1]) / 2.0;
                    }
                }

                // Comment count
                let commentLink = art.querySelector("a[href*='#comments'] .label");
                r.comments = commentLink ? parseInt(commentLink.textContent.trim()) || 0 : 0;

                // Liked
                r.liked = !!art.querySelector(".icon-liked");

                // Profile URL for attribution
                let profileLink = art.querySelector("a.avatar");
                r.profileUrl = profileLink ? profileLink.getAttribute("href") : null;

                // Review URL (the "context" link goes to the full review)
                let reviewLink = art.querySelector("a.context");
                r.reviewUrl = reviewLink ? reviewLink.getAttribute("href") : null;

                results.push(r);
            }
            return results;
        }''')

        now = datetime.now().isoformat()

        for item in extracted:
            if not item.get('text') or not item.get('username'):
                continue

            reviews.append({
                'text': item['text'],
                'critic': item['username'],  # Using 'critic' for consistency with RT format
                'outlet': 'Letterboxd',
                'source': 'letterboxd',
                'verbatim': True,
                'selected': False,
                'fresh': None,  # Not applicable for Letterboxd
                'rating': item.get('rating'),
                'rating_stars': item.get('ratingStars', ''),
                'comments': item.get('comments', 0),
                'liked': item.get('liked', False),
                'profile_url': item.get('profileUrl'),
                'review_url': 'https://letterboxd.com' + item['reviewUrl'] if item.get('reviewUrl') else '',
                'added_at': now
            })

        return reviews

    def scrape_reviews(self, title: str, year: int = 0, slug: str = None) -> List[Dict]:
        """Scrape popular reviews from Letterboxd for a movie.

        Args:
            title: Movie title
            year: Release year
            slug: Optional Letterboxd slug (if known). If not provided, constructed from title.

        Returns:
            List of review dicts, or empty list if scraping fails
        """
        cache_key = f"{title}_{year}"

        # Check cache
        if self._is_cache_valid(cache_key):
            cached = self.cache[cache_key]
            self.stats['cache_hits'] += 1
            self._log(f"Cache hit for {title}: {len(cached.get('reviews', []))} reviews")
            return cached.get('reviews', [])

        self.stats['attempts'] += 1
        self._init_browser()
        self._enforce_rate_limit()

        # Resolve slug
        if not slug:
            slug = self._resolve_slug(title, year)

        film_url = f"https://letterboxd.com/film/{slug}/"
        all_reviews = []

        try:
            self._log(f"Navigating to: {film_url}")
            resp = self.page.goto(film_url, wait_until='domcontentloaded', timeout=20000)

            if resp and resp.status == 404:
                # Slug didn't work, try with year appended
                slug_with_year = f"{slug}-{year}"
                film_url = f"https://letterboxd.com/film/{slug_with_year}/"
                self._log(f"404, trying with year: {film_url}")
                resp = self.page.goto(film_url, wait_until='domcontentloaded', timeout=20000)

            if resp and resp.status != 200:
                self._log(f"Failed to load {film_url}: status {resp.status}", level='warning')
            else:
                # Wait for page to render and AJAX to load popular reviews
                time.sleep(5)
                # Scroll to trigger lazy loading
                self.page.evaluate('window.scrollTo(0, 800)')
                time.sleep(2)

                all_reviews = self._extract_reviews()
                self._log(f"Extracted {len(all_reviews)} reviews for {title}")

            # Cache results
            self.cache[cache_key] = {
                'reviews': all_reviews,
                'film_url': film_url,
                'slug': slug,
                'title': title,
                'year': year,
                'scraped_at': datetime.now().isoformat(),
                'count': len(all_reviews)
            }
            self._save_cache()

            if all_reviews:
                self.stats['successes'] += 1
            else:
                self.stats['failures'] += 1

        except Exception as e:
            self._log(f"Error scraping reviews for {title}: {e}", level='error')
            self.stats['failures'] += 1
            self.cache[cache_key] = {
                'reviews': [],
                'film_url': film_url,
                'title': title,
                'year': year,
                'scraped_at': datetime.now().isoformat(),
                'count': 0,
                'error': str(e)
            }
            self._save_cache()

        return all_reviews

    def close(self):
        """Clean up browser resources."""
        self._cleanup_browser()
        self._log("LetterboxdReviewScraper closed")


# =============================================================================
# Standalone test
# =============================================================================
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.DEBUG)

    scraper = LetterboxdReviewScraper()
    try:
        test_title = sys.argv[1] if len(sys.argv) > 1 else 'Anora'
        test_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2024

        print(f"\nScraping Letterboxd reviews for: {test_title} ({test_year})\n")

        reviews = scraper.scrape_reviews(test_title, test_year)

        if reviews:
            print(f"Found {len(reviews)} reviews:\n")
            for i, r in enumerate(reviews, 1):
                stars = r.get('rating_stars', '')
                comments = r.get('comments', 0)
                print(f"  {i}. @{r['critic']} — {stars} — {comments} comments")
                # Truncate long reviews for display
                text = r['text']
                if len(text) > 200:
                    text = text[:200] + '...'
                print(f"     \"{text}\"\n")
        else:
            print("No reviews found.")

        print(f"Stats: {scraper.get_stats()}")
    finally:
        scraper.close()
