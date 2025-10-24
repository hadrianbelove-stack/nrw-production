#!/usr/bin/env python3
"""
One-time script to flag bootstrap movies in movie_tracking.json.

Purpose: Identify and mark all movies affected by the Sept 6, 2025 bootstrap issue
where digital_date was set to discovery date instead of actual digital release date.

Usage:
    python3 scripts/flag_bootstrap_dates.py --dry-run  # Preview changes
    python3 scripts/flag_bootstrap_dates.py            # Apply changes
"""

import json
import argparse
import shutil
from datetime import datetime
from pathlib import Path

def load_movies(file_path):
    """Load movies from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {file_path} not found")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        return None

def save_movies(movies, file_path, dry_run=False):
    """Save movies to JSON file with backup."""
    if dry_run:
        print(f"[DRY RUN] Would save {len(movies)} movies to {file_path}")
        return True

    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup_{timestamp}"

    try:
        # Create backup
        shutil.copy2(file_path, backup_path)
        print(f"Created backup: {backup_path}")

        # Write updated data atomically
        temp_path = f"{file_path}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(movies, f, indent=2, ensure_ascii=False)

        # Atomic move
        shutil.move(temp_path, file_path)
        print(f"Successfully updated {file_path}")

        # Clean up old backups (keep last 5)
        cleanup_old_backups(file_path)

        return True

    except Exception as e:
        print(f"Error saving file: {e}")
        # Clean up temp file if it exists
        if Path(f"{file_path}.tmp").exists():
            Path(f"{file_path}.tmp").unlink()
        return False

def cleanup_old_backups(file_path, keep=5):
    """Remove old backup files, keeping only the most recent ones."""
    base_path = Path(file_path).parent
    backup_pattern = f"{Path(file_path).name}.backup_*"

    backup_files = list(base_path.glob(backup_pattern))
    backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # Remove old backups beyond the keep limit
    for old_backup in backup_files[keep:]:
        try:
            old_backup.unlink()
            print(f"Removed old backup: {old_backup}")
        except Exception as e:
            print(f"Warning: Could not remove {old_backup}: {e}")

def is_bootstrap_movie(movie):
    """
    Check if movie is affected by bootstrap issue.

    Criteria:
    - digital_date is '2025-09-06' or '2025-09-05'
    - added timestamp starts with '2025-09-06'
    - manually_corrected is not already true
    """
    digital_date = movie.get('digital_date')
    added = movie.get('added', '')
    manually_corrected = movie.get('manually_corrected', False)

    # Skip if already manually corrected
    if manually_corrected:
        return False

    # Check for bootstrap dates
    bootstrap_dates = ['2025-09-06', '2025-09-05']
    if digital_date not in bootstrap_dates:
        return False

    # Check if added on bootstrap day
    if not added.startswith('2025-09-06'):
        return False

    return True

def flag_bootstrap_movies(movies, dry_run=False):
    """Flag bootstrap movies and return statistics."""
    flagged_movies = []
    total_movies = len(movies)

    for movie_id, movie in movies.items():
        if is_bootstrap_movie(movie):
            if not dry_run:
                movie['bootstrap_date'] = True

            flagged_movies.append({
                'id': movie_id,
                'title': movie.get('title', 'Unknown'),
                'digital_date': movie.get('digital_date'),
                'added': movie.get('added', '')
            })

    return flagged_movies, total_movies

def print_statistics(flagged_movies, total_movies, dry_run=False):
    """Print summary statistics."""
    action = "Would flag" if dry_run else "Flagged"
    print(f"\n{action} {len(flagged_movies)} movies out of {total_movies} total movies")

    if flagged_movies:
        print(f"\n{action} movies:")
        for movie in flagged_movies[:10]:  # Show first 10
            print(f"  - {movie['title']} (ID: {movie['id']}) - {movie['digital_date']}")

        if len(flagged_movies) > 10:
            print(f"  ... and {len(flagged_movies) - 10} more movies")
    else:
        print("No movies match bootstrap criteria")

def main():
    parser = argparse.ArgumentParser(description='Flag bootstrap movies in movie_tracking.json')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying the file')
    parser.add_argument('--file', default='movie_tracking.json',
                       help='Path to movie tracking JSON file (default: movie_tracking.json)')

    args = parser.parse_args()

    # Load movies
    print(f"Loading movies from {args.file}...")
    movies = load_movies(args.file)
    if movies is None:
        return 1

    # Flag bootstrap movies
    print("Analyzing movies for bootstrap date issue...")
    flagged_movies, total_movies = flag_bootstrap_movies(movies, args.dry_run)

    # Print statistics
    print_statistics(flagged_movies, total_movies, args.dry_run)

    # Save if not dry run
    if not args.dry_run and flagged_movies:
        print(f"\nSaving changes to {args.file}...")
        if not save_movies(movies, args.file):
            return 1
        print("Bootstrap movie flagging completed successfully!")
    elif args.dry_run:
        print("\n[DRY RUN] No changes made. Run without --dry-run to apply changes.")
    elif not flagged_movies:
        print("No changes needed.")

    return 0

if __name__ == '__main__':
    exit(main())