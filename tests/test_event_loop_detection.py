#!/usr/bin/env python3
"""
Minimal test to detect exactly where the event loop is created
"""
import sys
import asyncio

def check_event_loop(label):
    """Check if event loop exists"""
    try:
        loop = asyncio.get_running_loop()
        print(f"❌ {label}: EVENT LOOP EXISTS - {type(loop)}")
        return True
    except RuntimeError:
        print(f"✅ {label}: No event loop")
        return False

print("=" * 80)
print("Event Loop Detection Test")
print("=" * 80)

# 1. Before any imports
check_event_loop("1. Before imports")

# 2. After YouTube scraper import
print("\n2. Importing YouTube scraper...")
from scripts.youtube_trailer_scraper import YouTubeTrailerScraper
check_event_loop("   After YouTube import")

# 3. After RT scraper import
print("\n3. Importing RT scraper...")
from rt_scraper_playwright import RTScraperPlaywright
check_event_loop("   After RT import")

# 4. After Wikipedia scraper import
print("\n4. Importing Wikipedia scraper...")
from wikipedia_scraper_playwright import WikipediaScraperPlaywright
check_event_loop("   After Wikipedia import")

# 5. After Agent scraper import
print("\n5. Importing Agent scraper...")
from agent_link_scraper import AgentLinkScraper
check_event_loop("   After Agent import")

# 6. After Platform scraper import
print("\n6. Importing Platform scraper...")
from streaming_platform_scraper import StreamingPlatformScraper
check_event_loop("   After Platform import")

# 7. (Watchmode API deprecated - removed 2024-12)

# 8. Creating YouTube scraper instance
print("\n8. Creating YouTube scraper instance...")
yt_scraper = YouTubeTrailerScraper()
check_event_loop("   After YouTube instance")

# 9. Initializing YouTube scraper browser
print("\n9. Initializing YouTube scraper browser...")
try:
    yt_scraper._init_browser()
    check_event_loop("   After YouTube browser init")
except Exception as e:
    print(f"   Error: {e}")
    check_event_loop("   After YouTube browser error")

# 10. Creating RT scraper instance
print("\n10. Creating RT scraper instance...")
rt_scraper = RTScraperPlaywright()
check_event_loop("    After RT instance")

# 11. Initializing RT scraper browser
print("\n11. Initializing RT scraper browser...")
try:
    rt_scraper._init_browser()
    check_event_loop("    After RT browser init")
except Exception as e:
    print(f"    Error: {e}")
    check_event_loop("    After RT browser error")

# 12. Creating Wikipedia scraper instance
print("\n12. Creating Wikipedia scraper instance...")
wiki_scraper = WikipediaScraperPlaywright()
check_event_loop("    After Wikipedia instance")

# 13. Initializing Wikipedia scraper browser
print("\n13. Initializing Wikipedia scraper browser...")
try:
    wiki_scraper._init_browser()
    check_event_loop("    After Wikipedia browser init")
except Exception as e:
    print(f"    Error: {e}")
    check_event_loop("    After Wikipedia browser error")

print("\n" + "=" * 80)
print("Test Complete")
print("=" * 80)
