#!/usr/bin/env python3
"""
Clear cache entries for movies with placeholder ASINs
"""

import json
import os
from datetime import datetime
from constants import PLACEHOLDER_ASINS

def clear_cache_for_placeholder_asins():
    """Clear cache entries for movies with placeholder ASINs"""

    cache_file = 'cache/watch_links_cache.json'

    if not os.path.exists(cache_file):
        print("ℹ️  Cache file not found: cache/watch_links_cache.json")
        print("   This is normal if no cache has been created yet.")
        return True

    try:
        # Load cache
        with open(cache_file, 'r') as f:
            cache = json.load(f)

        placeholder_list = ', '.join(PLACEHOLDER_ASINS)
        print(f"🔍 Scanning {len(cache)} cache entries for placeholder ASINs: {placeholder_list}...")

        # Track removals
        removed_count = 0
        removed_entries = []

        # Find entries with placeholder ASIN
        cache_keys_to_remove = []

        for cache_key, cache_entry in cache.items():
            links = cache_entry.get('links', {})
            has_placeholder = False

            # Check each category for placeholder ASINs
            for category in ['streaming', 'rent', 'buy']:
                category_data = links.get(category, {})
                if isinstance(category_data, dict):
                    link = category_data.get('link', '')
                    if link and any(asin in link for asin in PLACEHOLDER_ASINS):
                        has_placeholder = True
                        detected_asin = next(asin for asin in PLACEHOLDER_ASINS if asin in link)
                        print(f"  🔍 Found placeholder ASIN {detected_asin} in cache entry: {cache_key}")
                        break

            if has_placeholder:
                cache_keys_to_remove.append(cache_key)
                removed_entries.append(cache_key)

        # Remove problematic cache entries
        for cache_key in cache_keys_to_remove:
            del cache[cache_key]
            removed_count += 1

        if removed_count > 0:
            # Backup original cache
            backup_file = f'cache/watch_links_cache_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            if os.path.exists(cache_file):
                import shutil
                shutil.copy(cache_file, backup_file)
                print(f"💾 Backup created: {backup_file}")

            # Save cleaned cache
            with open(cache_file, 'w') as f:
                json.dump(cache, f, indent=2)

            print(f"✅ Removed {removed_count} cache entries with placeholder ASINs")
            print(f"📝 Removed entries:")
            for entry in removed_entries:
                print(f"   - {entry}")
        else:
            print("✅ No cache entries with placeholder ASINs found")

        return True

    except Exception as e:
        print(f"❌ Error processing cache file: {e}")
        return False

if __name__ == "__main__":
    print("🧹 Cache Cleanup Tool for Placeholder ASINs")
    print("=" * 50)

    success = clear_cache_for_placeholder_asins()

    if success:
        print("\n✅ Cache cleanup completed successfully!")
        print("📝 Next steps:")
        print("   1. Run: python3 generate_data.py")
        asin_grep_pattern = '|'.join(PLACEHOLDER_ASINS)
        print(f"   2. Verify: grep -c '{asin_grep_pattern}' data.json (should be 0)")
    else:
        print("\n❌ Cache cleanup failed. Check error messages above.")