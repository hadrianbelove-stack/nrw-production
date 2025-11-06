#!/usr/bin/env python3
"""
Test to detect WHEN an event loop is created during generate_data.py execution
"""
import asyncio

def check_loop(label):
    try:
        loop = asyncio.get_running_loop()
        print(f"❌ {label}: EVENT LOOP EXISTS")
        return True
    except RuntimeError:
        print(f"✅ {label}: No event loop")
        return False

print("=" * 80)
print("Testing event loop creation in generate_data.py flow")
print("=" * 80)

check_loop("1. At script start")

# Mimic generate_data.py imports
print("\n" + "=" * 80)
print("Importing modules...")
print("=" * 80)

check_loop("2. Before imports")

from scripts.youtube_trailer_scraper import YouTubeTrailerScraper
check_loop("3. After YouTubeTrailerScraper import")

from rt_scraper_playwright import RTScraperPlaywright
check_loop("4. After RTScraperPlaywright import")

from wikipedia_scraper_playwright import WikipediaScraperPlaywright
check_loop("5. After WikipediaScraperPlaywright import")

from agent_link_scraper import AgentLinkScraper
check_loop("6. After AgentLinkScraper import")

from streaming_platform_scraper import StreamingPlatformScraper
check_loop("7. After StreamingPlatformScraper import")

# Try instantiating (without config)
print("\n" + "=" * 80)
print("Instantiating scrapers...")
print("=" * 80)

try:
    scraper1 = StreamingPlatformScraper()
    check_loop("8. After StreamingPlatformScraper()")
except Exception as e:
    print(f"Error instantiating StreamingPlatformScraper: {e}")
    check_loop("8. After StreamingPlatformScraper() ERROR")

print("\n" + "=" * 80)
print("Done")
print("=" * 80)
