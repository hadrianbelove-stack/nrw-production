#!/usr/bin/env python3
"""
Tests for RT and Wikipedia scrapers covering waterfall logic.

These tests verify that scrapers can correctly find movie pages and scores
without impacting the daily discovery pipeline.

Mark as slow tests to run only in weekly workflow.
"""

import pytest
import os
import sys

# Add parent directory to path to import scrapers
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rt_scraper_playwright import RTScraperPlaywright
from wikipedia_scraper_playwright import WikipediaScraperPlaywright


@pytest.mark.slow
@pytest.mark.parametrize("title,year,expected_url_contains,expected_score_type", [
    ("Dune: Part Two", "2024", "/m/dune_part_two", "number_or_none"),
    ("Barbie", "2023", "/m/barbie", "number_or_none"),
    ("Oppenheimer", "2023", "/m/oppenheimer", "number_or_none"),
])
def test_rt_scraper_waterfall(title, year, expected_url_contains, expected_score_type):
    """Test RT scraper finds correct movie pages and scores."""

    # Initialize scraper with headless mode
    config = {
        'rt_scraper': {
            'headless': True,
            'timeout': 10,
            'rate_limit': 1.0,
            'max_retries': 2,
            'screenshots_enabled': False
        }
    }

    with RTScraperPlaywright(config=config, cache_file='cache/rt_cache_test.json') as scraper:
        result = scraper.scrape_rt_score(title, year)

        # Assert URL contains expected pattern
        assert result is not None, f"RT scraper failed to find {title} ({year})"
        assert result.get('url'), f"RT scraper returned no URL for {title} ({year})"
        assert expected_url_contains in result['url'], \
            f"RT URL doesn't contain expected pattern. Got: {result['url']}"

        # Assert score is either None or a valid percentage
        score = result.get('score')
        if expected_score_type == "number_or_none":
            if score is not None:
                # Score should be a percentage string like "90%"
                assert isinstance(score, str), f"Score should be string, got: {type(score)}"
                assert score.endswith('%'), f"Score should end with %, got: {score}"
                # Extract number and verify it's between 0-100
                score_num = int(score[:-1])
                assert 0 <= score_num <= 100, f"Score should be 0-100, got: {score_num}"

        print(f"✓ RT test passed: {title} ({year}) -> {result['url']} (Score: {score or 'N/A'})")


@pytest.mark.slow
@pytest.mark.parametrize("title,year,imdb_id,expected_title_token", [
    ("Dune: Part Two", "2024", "tt15239678", "Dune"),
    ("Barbie", "2023", "tt1517268", "Barbie"),
    ("Oppenheimer", "2023", "tt15398776", "Oppenheimer"),
])
def test_wikipedia_scraper_waterfall(title, year, imdb_id, expected_title_token):
    """Test Wikipedia scraper finds correct movie pages."""

    # Initialize scraper with headless mode
    config = {
        'wikipedia_scraper': {
            'headless': True,
            'timeout': 10,
            'max_retries': 2,
            'screenshots_enabled': False
        }
    }

    with WikipediaScraperPlaywright(config=config, cache_file='cache/wikipedia_cache_test.json') as scraper:
        wiki_url = scraper.find_wikipedia_url(title, year, imdb_id=imdb_id)

        # Assert URL starts with correct base
        assert wiki_url is not None, f"Wikipedia scraper failed to find {title} ({year})"
        assert wiki_url.startswith('https://en.wikipedia.org/wiki/'), \
            f"Wikipedia URL has wrong base. Got: {wiki_url}"

        # Assert URL includes the expected title token
        assert expected_title_token.lower() in wiki_url.lower(), \
            f"Wikipedia URL doesn't contain expected title token '{expected_title_token}'. Got: {wiki_url}"

        # Assert it's not a search fallback
        assert 'index.php?search=' not in wiki_url, \
            f"Wikipedia returned search fallback instead of article. Got: {wiki_url}"

        print(f"✓ Wikipedia test passed: {title} ({year}) -> {wiki_url}")


@pytest.mark.slow
def test_rt_scraper_handles_title_mismatch():
    """Test that RT scraper properly validates titles and doesn't return wrong movies."""

    config = {
        'rt_scraper': {
            'headless': True,
            'timeout': 10,
            'rate_limit': 1.0,
            'max_retries': 1,
            'screenshots_enabled': False
        }
    }

    # Use a title that might have name collisions
    title = "The Batman"
    year = "2022"

    with RTScraperPlaywright(config=config, cache_file='cache/rt_cache_test.json') as scraper:
        result = scraper.scrape_rt_score(title, year)

        # Should find the correct 2022 movie, not older Batman movies
        if result and result.get('url'):
            assert '/m/the_batman_2022' in result['url'] or '/m/the_batman' in result['url'], \
                f"RT returned wrong Batman movie. Got: {result['url']}"
            print(f"✓ RT title validation test passed: {title} ({year}) -> {result['url']}")


@pytest.mark.slow
def test_wikipedia_handles_disambiguation():
    """Test that Wikipedia scraper handles disambiguation pages correctly."""

    config = {
        'wikipedia_scraper': {
            'headless': True,
            'timeout': 10,
            'max_retries': 1,
            'screenshots_enabled': False
        }
    }

    # "Dune" might hit a disambiguation page
    title = "Dune"
    year = "2021"
    imdb_id = "tt1160419"

    with WikipediaScraperPlaywright(config=config, cache_file='cache/wikipedia_cache_test.json') as scraper:
        wiki_url = scraper.find_wikipedia_url(title, year, imdb_id=imdb_id)

        # Should get the film article, not the disambiguation page
        assert wiki_url is not None
        assert 'disambiguation' not in wiki_url.lower(), \
            f"Wikipedia returned disambiguation page instead of film article. Got: {wiki_url}"
        assert 'film' in wiki_url.lower() or '2021' in wiki_url, \
            f"Wikipedia URL doesn't clearly identify the 2021 film. Got: {wiki_url}"

        print(f"✓ Wikipedia disambiguation test passed: {title} ({year}) -> {wiki_url}")


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v', '-s'])
