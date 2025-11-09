#!/usr/bin/env python3
"""
Migration script to convert existing approval artifacts to the new drafts system.

This script reads admin/approval.json and related approval files and converts them
to the new admin/drafts/<id>.json format.
"""

import json
import os
import sys
import hashlib
from datetime import datetime
from pathlib import Path


def main():
    print("🔄 Migrating approval artifacts to drafts system...")

    # Ensure we're in the project root
    if not os.path.exists('admin'):
        print("❌ Error: admin/ directory not found. Run from project root.")
        sys.exit(1)

    # Ensure drafts directory exists
    os.makedirs('admin/drafts', exist_ok=True)

    migrated_count = 0

    # Migrate admin/approval.json if it exists
    approval_file = 'admin/approval.json'
    if os.path.exists(approval_file):
        try:
            with open(approval_file, 'r') as f:
                approval = json.load(f)

            # Extract data from approval
            timestamp = approval.get('timestamp', datetime.now().isoformat())
            reviewer = approval.get('reviewer', 'admin')

            # Try to get movie data from current data.json if available
            movie_ids = []
            movie_titles = []

            if os.path.exists('data.json'):
                with open('data.json', 'r') as f:
                    data = json.load(f)
                movies = data.get('movies', [])

                # Get recent movies as candidates for the migration
                from datetime import timedelta
                cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                recent_movies = [m for m in movies if m.get('digital_date', '') >= cutoff_date]

                if recent_movies:
                    movie_ids = [str(m.get('id', '')) for m in recent_movies]
                    movie_titles = [m.get('title', 'Unknown') for m in recent_movies]

            # Create draft ID from timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                draft_id = dt.strftime('%Y%m%d_%H%M%S')
            except:
                draft_id = datetime.now().strftime('%Y%m%d_%H%M%S')

            # Compute source digest if movie_tracking.json exists
            source_digest = None
            if os.path.exists('movie_tracking.json'):
                with open('movie_tracking.json', 'rb') as f:
                    source_digest = hashlib.sha256(f.read()).hexdigest()

            # Create draft object
            draft = {
                'id': draft_id,
                'createdAt': timestamp,
                'migratedFrom': 'approval.json',
                'reviewer': reviewer,
                'titles': movie_titles,
                'movieIds': movie_ids,
                'sourceDigest': source_digest,
                'movieCount': len(movie_ids),
                'dateRange': f"migrated from approval at {timestamp}"
            }

            # Save draft file
            draft_file = f'admin/drafts/{draft_id}.json'
            with open(draft_file, 'w') as f:
                json.dump(draft, f, indent=2)

            print(f"✅ Migrated approval.json to {draft_file}")
            print(f"   Movies: {len(movie_ids)} items")
            print(f"   Reviewer: {reviewer}")
            print(f"   Timestamp: {timestamp}")

            # Create backup of original approval file
            backup_file = f'admin/approval.json.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            os.rename(approval_file, backup_file)
            print(f"✅ Original approval.json backed up to {backup_file}")

            migrated_count += 1

        except Exception as e:
            print(f"❌ Error migrating approval.json: {e}")
    else:
        print("ℹ️ No admin/approval.json found")

    # Look for other approval-related files that might need migration
    approval_patterns = [
        'admin/approval_*.json',
        'admin/*approval*.json'
    ]

    import glob
    for pattern in approval_patterns:
        for file_path in glob.glob(pattern):
            if 'backup' in file_path or 'drafts' in file_path:
                continue  # Skip backups and drafts

            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                # Create a draft ID from the file name
                file_name = Path(file_path).stem
                draft_id = f"migrated_{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # Create minimal draft object
                draft = {
                    'id': draft_id,
                    'createdAt': datetime.now().isoformat(),
                    'migratedFrom': file_path,
                    'titles': data.get('titles', []),
                    'movieIds': data.get('movieIds', []),
                    'movieCount': len(data.get('movieIds', [])),
                    'dateRange': f"migrated from {file_path}"
                }

                # Save draft file
                draft_file = f'admin/drafts/{draft_id}.json'
                with open(draft_file, 'w') as f:
                    json.dump(draft, f, indent=2)

                print(f"✅ Migrated {file_path} to {draft_file}")

                # Create backup of original file
                backup_file = f'{file_path}.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                os.rename(file_path, backup_file)
                print(f"✅ Original {file_path} backed up to {backup_file}")

                migrated_count += 1

            except Exception as e:
                print(f"❌ Error migrating {file_path}: {e}")

    # Clean up any remaining approval-related files
    cleanup_files = [
        'admin/ordering.json',
        'admin/hidden_movies.json',
        'admin/featured_movies.json',
        'admin/watch_link_overrides.json'
    ]

    for cleanup_file in cleanup_files:
        if os.path.exists(cleanup_file):
            # Don't delete these - they're still used by the admin system
            # Just report their existence
            print(f"ℹ️ Preserved {cleanup_file} (still used by admin system)")

    # Summary
    print("\n" + "=" * 50)
    print("📊 MIGRATION SUMMARY")
    print("=" * 50)
    print(f"✅ Files migrated: {migrated_count}")

    if migrated_count > 0:
        print(f"📁 Drafts created in: admin/drafts/")
        print("📝 Next steps:")
        print("   1. Review drafts in the admin panel")
        print("   2. Edit titles if needed")
        print("   3. Publish approved drafts to production")
        print("   4. Delete backup files once migration is confirmed")
    else:
        print("ℹ️ No approval artifacts found to migrate")

    print("\n✨ Migration complete!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️ Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)