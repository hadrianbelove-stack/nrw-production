#!/usr/bin/env python3
"""
Enrichment State Cleanup Script

This script addresses orphaned records in enrichment_state.json that resulted from
the Oct 26 migration. During that migration, enrichment flags were copied without
the actual movie data, creating a mismatch where enrichment_state.json contains
~1400+ records but data.json only has 235 movies.

The script identifies and removes orphaned enrichment records (IDs present in
enrichment_state.json but not in data.json), creating timestamped backups and
providing detailed statistics about the cleanup operation.

Usage:
    # Preview changes without modifying files
    python3 scripts/cleanup_enrichment_state.py --dry-run

    # Apply cleanup with default file paths
    python3 scripts/cleanup_enrichment_state.py

    # Use custom file paths
    python3 scripts/cleanup_enrichment_state.py --enrichment-state path/to/enrichment_state.json --data-file path/to/data.json

    # Keep more backup files
    python3 scripts/cleanup_enrichment_state.py --keep-backups 10

Author: Claude Code
Created: 2025-12-05
"""

import json
import os
import sys
import argparse
import shutil
from datetime import datetime


def load_json_file(file_path: str) -> dict:
    """Load JSON file with error handling.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data as dict, or None on failure
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {file_path}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading {file_path}: {e}")
        return None


def extract_movie_ids_from_data(data: dict) -> set:
    """Extract movie IDs from data.json movies array.

    Args:
        data: Parsed data.json content

    Returns:
        Set of movie ID strings
    """
    if not data or 'movies' not in data:
        return set()

    movie_ids = set()
    for movie in data.get('movies', []):
        if isinstance(movie, dict) and 'id' in movie:
            movie_ids.add(str(movie['id']))

    return movie_ids


def extract_movie_ids_from_enrichment(enrichment_state: dict) -> set:
    """Extract movie IDs from enrichment_state.json keys.

    Args:
        enrichment_state: Parsed enrichment_state.json content

    Returns:
        Set of movie ID strings
    """
    if not enrichment_state:
        return set()

    return set(str(key) for key in enrichment_state.keys())


def find_orphaned_records(enrichment_ids: set, data_ids: set) -> set:
    """Find orphaned enrichment records.

    Args:
        enrichment_ids: Set of IDs from enrichment_state.json
        data_ids: Set of IDs from data.json

    Returns:
        Set of orphaned IDs (in enrichment but not in data)
    """
    return enrichment_ids - data_ids


def analyze_orphans(orphaned_ids: set, enrichment_state: dict) -> dict:
    """Analyze orphaned records for detailed statistics.

    Args:
        orphaned_ids: Set of orphaned movie IDs
        enrichment_state: Parsed enrichment_state.json content

    Returns:
        Dict with analysis results
    """
    analysis = {
        'total_orphans': len(orphaned_ids),
        'by_date': {},
        'migrated_count': 0,
        'earliest_date': None,
        'latest_date': None,
        'dates_found': []
    }

    for movie_id in orphaned_ids:
        record = enrichment_state.get(movie_id, {})

        # Count migrated records
        if record.get('migrated_from_tracking_db') is True:
            analysis['migrated_count'] += 1

        # Analyze by enrichment date
        enrichment_date = record.get('enrichment_date')
        if enrichment_date:
            analysis['dates_found'].append(enrichment_date)
            if enrichment_date not in analysis['by_date']:
                analysis['by_date'][enrichment_date] = 0
            analysis['by_date'][enrichment_date] += 1

    # Determine date range
    if analysis['dates_found']:
        analysis['earliest_date'] = min(analysis['dates_found'])
        analysis['latest_date'] = max(analysis['dates_found'])

    return analysis


def create_backup(file_path: str) -> str:
    """Create timestamped backup of file.

    Args:
        file_path: Path to file to backup

    Returns:
        Path to created backup file
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{file_path}.backup_{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def remove_orphaned_records(enrichment_state: dict, orphaned_ids: set) -> dict:
    """Create new enrichment state excluding orphaned IDs.

    Args:
        enrichment_state: Original enrichment state dict
        orphaned_ids: Set of IDs to remove

    Returns:
        Cleaned enrichment state dict
    """
    return {
        movie_id: record
        for movie_id, record in enrichment_state.items()
        if movie_id not in orphaned_ids
    }


def save_enrichment_state_atomic(state: dict, file_path: str):
    """Save enrichment state atomically using temp file + rename.

    Args:
        state: Enrichment state dict to save
        file_path: Target file path
    """
    temp_path = f"{file_path}.tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, file_path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def cleanup_old_backups(base_path: str, keep_count: int = 5):
    """Remove old backup files, keeping only the most recent ones.

    Args:
        base_path: Base file path (e.g., 'enrichment_state.json')
        keep_count: Number of recent backups to keep
    """
    backup_dir = os.path.dirname(base_path) or '.'
    base_name = os.path.basename(base_path)

    # Find all backup files
    backup_files = []
    for filename in os.listdir(backup_dir):
        if filename.startswith(f"{base_name}.backup_"):
            backup_path = os.path.join(backup_dir, filename)
            backup_files.append((backup_path, os.path.getmtime(backup_path)))

    # Sort by modification time (newest first)
    backup_files.sort(key=lambda x: x[1], reverse=True)

    # Remove old backups
    for backup_path, _ in backup_files[keep_count:]:
        try:
            os.unlink(backup_path)
            print(f"ℹ️  Removed old backup: {os.path.basename(backup_path)}")
        except Exception as e:
            print(f"⚠️  Warning: Could not remove backup {backup_path}: {e}")


def main():
    """Main script execution."""
    parser = argparse.ArgumentParser(
        description="Clean orphaned records from enrichment_state.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Preview changes
  %(prog)s                              # Apply cleanup
  %(prog)s --keep-backups 10            # Keep more backups
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--enrichment-state',
        default='enrichment_state.json',
        help='Path to enrichment_state.json (default: enrichment_state.json)'
    )
    parser.add_argument(
        '--data-file',
        default='data.json',
        help='Path to data.json (default: data.json)'
    )
    parser.add_argument(
        '--keep-backups',
        type=int,
        default=5,
        help='Number of old backups to retain (default: 5)'
    )

    args = parser.parse_args()

    # Print header
    print("🧹 Enrichment State Cleanup Script")
    print("=" * 50)

    try:
        # Validate files exist
        if not os.path.exists(args.enrichment_state):
            print(f"❌ Error: Enrichment state file not found: {args.enrichment_state}")
            sys.exit(1)

        if not os.path.exists(args.data_file):
            print(f"❌ Error: Data file not found: {args.data_file}")
            sys.exit(1)

        # Load both files
        print(f"ℹ️  Loading {args.enrichment_state}...")
        enrichment_state = load_json_file(args.enrichment_state)
        if enrichment_state is None:
            sys.exit(1)

        print(f"ℹ️  Loading {args.data_file}...")
        data = load_json_file(args.data_file)
        if data is None:
            sys.exit(1)

        # Extract movie IDs
        enrichment_ids = extract_movie_ids_from_enrichment(enrichment_state)
        data_ids = extract_movie_ids_from_data(data)

        # Find orphaned records and calculate intersections
        orphaned_ids = find_orphaned_records(enrichment_ids, data_ids)
        valid_enrichment_ids = enrichment_ids & data_ids

        # Analyze orphans
        analysis = analyze_orphans(orphaned_ids, enrichment_state)

        # Print analysis results
        print(f"\n📊 Analysis Results:")
        print(f"   Total enrichment records: {len(enrichment_ids)}")
        print(f"   Valid enrichment records (also in data.json): {len(valid_enrichment_ids)}")
        print(f"   Total movies in data.json: {len(data_ids)}")
        print(f"   Orphaned records: {analysis['total_orphans']}")

        if analysis['total_orphans'] > 0:
            print(f"\n📈 Orphan Breakdown:")
            print(f"   Records with migration flag: {analysis['migrated_count']}")

            if analysis['earliest_date'] and analysis['latest_date']:
                print(f"   Date range: {analysis['earliest_date']} to {analysis['latest_date']}")

            if analysis['by_date']:
                print(f"   By enrichment date:")
                for date, count in sorted(analysis['by_date'].items()):
                    print(f"     {date}: {count} records")

        # Handle dry run mode
        if args.dry_run:
            if analysis['total_orphans'] > 0:
                print(f"\n[DRY RUN] Would remove {analysis['total_orphans']} orphaned records")
                print(f"[DRY RUN] Would create backup: {args.enrichment_state}.backup_TIMESTAMP")
            else:
                print(f"\n[DRY RUN] No orphaned records found - no action needed")
            sys.exit(0)

        # Apply cleanup if needed
        if analysis['total_orphans'] == 0:
            print(f"\n✅ No orphaned records found - no cleanup needed")
            sys.exit(0)

        print(f"\n🧹 Starting cleanup...")

        # Create backup
        backup_path = create_backup(args.enrichment_state)
        print(f"✅ Created backup: {os.path.basename(backup_path)}")

        # Remove orphaned records
        cleaned_state = remove_orphaned_records(enrichment_state, orphaned_ids)

        # Save cleaned state
        save_enrichment_state_atomic(cleaned_state, args.enrichment_state)
        print(f"✅ Saved cleaned enrichment state")

        # Cleanup old backups
        cleanup_old_backups(args.enrichment_state, args.keep_backups)

        # Print summary
        print(f"\n📊 CLEANUP SUMMARY")
        print(f"   Records before: {len(enrichment_ids)}")
        print(f"   Records after: {len(cleaned_state)}")
        print(f"   Valid records retained: {len(valid_enrichment_ids)}")
        print(f"   Orphans removed: {analysis['total_orphans']}")
        print(f"   Backup created: {os.path.basename(backup_path)}")

        # Get file sizes
        original_size = os.path.getsize(backup_path)
        new_size = os.path.getsize(args.enrichment_state)
        size_reduction = original_size - new_size

        print(f"   Size reduction: {size_reduction:,} bytes ({size_reduction/1024:.1f} KB)")
        print(f"\n✅ Cleanup completed successfully!")

    except KeyboardInterrupt:
        print(f"\n⚠️  Cleanup interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()