#!/usr/bin/env python3
"""
Date verification utility for manual research and correction of bootstrap dates.

Purpose: Provide tools for manually researching and correcting bootstrap dates,
since automated scraping (Reelgood) has proven unreliable.

Usage:
    python3 date_verification.py                    # Interactive mode
    python3 date_verification.py --csv corrections.csv  # Batch mode with CSV
    python3 date_verification.py --list             # List bootstrap movies only
"""

import json
import argparse
import csv
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

def save_movies(movies, file_path):
    """Save movies to JSON file with backup."""
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

        return True

    except Exception as e:
        print(f"Error saving file: {e}")
        # Clean up temp file if it exists
        if Path(f"{file_path}.tmp").exists():
            Path(f"{file_path}.tmp").unlink()
        return False

def get_bootstrap_movies(movies):
    """Get list of movies with bootstrap_date flag."""
    bootstrap_movies = []

    for movie_id, movie in movies.items():
        if movie.get('bootstrap_date', False):
            bootstrap_movies.append({
                'id': movie_id,
                'title': movie.get('title', 'Unknown'),
                'digital_date': movie.get('digital_date'),
                'premiere_date': movie.get('premiere_date'),
                'vote_count': movie.get('vote_count', 0),
                'popularity': movie.get('popularity', 0.0),
                'added': movie.get('added', ''),
                'manually_corrected': movie.get('manually_corrected', False)
            })

    # Sort by prominence (vote_count desc, then popularity desc)
    bootstrap_movies.sort(key=lambda x: (x['vote_count'], x['popularity']), reverse=True)

    return bootstrap_movies

def format_movie_info(movie):
    """Format movie information for display."""
    return f"""
Movie: {movie['title']} (ID: {movie['id']})
Current Digital Date: {movie['digital_date']}
Premiere Date: {movie.get('premiere_date', 'Unknown')}
Popularity: {movie.get('popularity', 0):.1f} | Votes: {movie.get('vote_count', 0)}
Added: {movie.get('added', 'Unknown')}
Manually Corrected: {movie.get('manually_corrected', False)}

Research Links:
TMDB: https://www.themoviedb.org/movie/{movie['id']}
JustWatch: https://www.justwatch.com/us/search?q={movie['title'].replace(' ', '%20')}
Google: https://www.google.com/search?q="{movie['title']}"+digital+release+date
"""

def interactive_mode(movies, file_path):
    """Interactive mode for correcting bootstrap dates."""
    bootstrap_movies = get_bootstrap_movies(movies)

    if not bootstrap_movies:
        print("No bootstrap movies found.")
        return

    print(f"\nFound {len(bootstrap_movies)} bootstrap movies.")
    print("Movies are sorted by prominence (vote count, then popularity).\n")

    corrected_count = 0
    skipped_count = 0

    for i, movie in enumerate(bootstrap_movies, 1):
        print(f"\n{'='*60}")
        print(f"Movie {i}/{len(bootstrap_movies)}")
        print(format_movie_info(movie))

        while True:
            action = input("\nActions:\n"
                          "  [c] Correct date\n"
                          "  [s] Skip this movie\n"
                          "  [q] Quit\n"
                          "Choice: ").lower().strip()

            if action == 'q':
                print(f"\nSession summary:")
                print(f"Corrected: {corrected_count} movies")
                print(f"Skipped: {skipped_count} movies")
                print(f"Remaining: {len(bootstrap_movies) - i + 1} movies")
                return

            elif action == 's':
                skipped_count += 1
                print("Skipped.")
                break

            elif action == 'c':
                new_date = input("Enter corrected date (YYYY-MM-DD): ").strip()

                # Validate date format
                try:
                    datetime.strptime(new_date, '%Y-%m-%d')
                except ValueError:
                    print("Invalid date format. Please use YYYY-MM-DD.")
                    continue

                # Apply correction
                movie_id = movie['id']
                movies[movie_id]['digital_date'] = new_date
                movies[movie_id]['manually_corrected'] = True
                movies[movie_id].pop('bootstrap_date', None)  # Remove bootstrap flag

                # Save immediately
                if save_movies(movies, file_path):
                    print(f"✓ Corrected {movie['title']} to {new_date}")
                    corrected_count += 1
                    break
                else:
                    print("✗ Failed to save correction")
                    continue

            else:
                print("Invalid choice. Please enter 'c', 's', or 'q'.")

    print(f"\n{'='*60}")
    print(f"All movies processed!")
    print(f"Corrected: {corrected_count} movies")
    print(f"Skipped: {skipped_count} movies")

def batch_mode(movies, file_path, csv_path):
    """Batch mode for correcting dates from CSV file."""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            corrections = list(reader)
    except FileNotFoundError:
        print(f"Error: CSV file {csv_path} not found")
        return
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    print(f"Loading {len(corrections)} corrections from {csv_path}")

    applied_count = 0
    error_count = 0

    for correction in corrections:
        movie_id = correction.get('movie_id', '').strip()
        corrected_date = correction.get('corrected_date', '').strip()
        notes = correction.get('notes', '').strip()

        if not movie_id or not corrected_date:
            print(f"Skipping row with missing movie_id or corrected_date")
            error_count += 1
            continue

        if movie_id not in movies:
            print(f"Warning: Movie ID {movie_id} not found in database")
            error_count += 1
            continue

        # Validate date format
        try:
            datetime.strptime(corrected_date, '%Y-%m-%d')
        except ValueError:
            print(f"Error: Invalid date format '{corrected_date}' for movie {movie_id}")
            error_count += 1
            continue

        # Apply correction
        movie = movies[movie_id]
        old_date = movie.get('digital_date')

        movie['digital_date'] = corrected_date
        movie['manually_corrected'] = True
        movie.pop('bootstrap_date', None)  # Remove bootstrap flag

        if notes:
            # Store notes in a correction_notes field
            movie['correction_notes'] = notes

        print(f"✓ {movie.get('title', 'Unknown')} (ID: {movie_id}): {old_date} → {corrected_date}")
        if notes:
            print(f"  Notes: {notes}")

        applied_count += 1

    # Save all corrections
    if applied_count > 0:
        if save_movies(movies, file_path):
            print(f"\nSuccessfully applied {applied_count} corrections")
        else:
            print(f"\nError: Failed to save corrections")

    if error_count > 0:
        print(f"Errors: {error_count} corrections failed")

def list_mode(movies):
    """List all bootstrap movies."""
    bootstrap_movies = get_bootstrap_movies(movies)

    if not bootstrap_movies:
        print("No bootstrap movies found.")
        return

    print(f"Bootstrap Movies ({len(bootstrap_movies)} total):")
    print("=" * 80)

    for movie in bootstrap_movies:
        status = "✓ CORRECTED" if movie['manually_corrected'] else "⚠ NEEDS REVIEW"
        print(f"{movie['title']} (ID: {movie['id']}) - {movie['digital_date']} - {status}")

        if movie.get('premiere_date') and movie['premiere_date'] != movie['digital_date']:
            print(f"  Premiere: {movie['premiere_date']} | Votes: {movie['vote_count']} | Pop: {movie['popularity']:.1f}")

        print()

def create_sample_csv():
    """Create a sample CSV file for batch corrections."""
    sample_data = [
        {'movie_id': '1404864', 'corrected_date': '2025-09-04', 'notes': 'Netflix release confirmed'},
        {'movie_id': '1522103', 'corrected_date': '2025-08-30', 'notes': 'Hulu premiere date'},
    ]

    with open('corrections_sample.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['movie_id', 'corrected_date', 'notes']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_data)

    print("Created sample CSV file: corrections_sample.csv")
    print("Edit this file with your corrections and run: python3 date_verification.py --csv corrections_sample.csv")

def main():
    parser = argparse.ArgumentParser(description='Verify and correct bootstrap movie dates')
    parser.add_argument('--file', default='movie_tracking.json',
                       help='Path to movie tracking JSON file (default: movie_tracking.json)')
    parser.add_argument('--csv',
                       help='CSV file with corrections (columns: movie_id, corrected_date, notes)')
    parser.add_argument('--list', action='store_true',
                       help='List all bootstrap movies and exit')
    parser.add_argument('--create-sample', action='store_true',
                       help='Create sample CSV file and exit')

    args = parser.parse_args()

    if args.create_sample:
        create_sample_csv()
        return 0

    # Load movies
    print(f"Loading movies from {args.file}...")
    movies = load_movies(args.file)
    if movies is None:
        return 1

    if args.list:
        list_mode(movies)
    elif args.csv:
        batch_mode(movies, args.file, args.csv)
    else:
        interactive_mode(movies, args.file)

    return 0

if __name__ == '__main__':
    exit(main())