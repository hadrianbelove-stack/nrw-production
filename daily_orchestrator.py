#!/usr/bin/env python3
"""
NRW Daily Orchestrator - Coordinates all daily update tasks
"""

import subprocess
import json
import sys
import os
import yaml
from datetime import datetime
from pathlib import Path

class NRWOrchestrator:
    def __init__(self):
        self.start_time = datetime.now()
        self.results = []
        self.has_changes = False
        
    def run_command(self, cmd, description, critical=True):
        """Execute command with error handling"""
        print(f"\n📍 {description}...")
        
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True
        )
        
        success = result.returncode == 0
        
        self.results.append({
            'step': description,
            'success': success,
            'output': result.stdout,
            'error': result.stderr
        })
        
        if success:
            print(f"✅ {description} complete")
            if result.stdout.strip():
                # Print relevant output
                for line in result.stdout.strip().split('\n')[:5]:  # First 5 lines
                    if line.strip():
                        print(f"   {line}")
        else:
            print(f"❌ Failed: {description}")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            if critical:
                self.print_summary()
                sys.exit(1)
        
        return success
    
    def check_changes(self):
        """Check if there are git changes to commit"""
        result = subprocess.run(
            "git diff --quiet movie_tracking.json data.json",
            shell=True
        )
        self.has_changes = result.returncode != 0
        return self.has_changes
    
    def validate_rt_data(self):
        """Validate RT data in data.json (non-critical check)"""
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)

            movies = data.get('movies', [])
            if not movies:
                print("⚠️  Warning: No movies found in data.json")
                return

            # Check a sample of movies for RT data
            sample_size = min(5, len(movies))
            movies_with_rt = 0

            for movie in movies[:sample_size]:
                if movie.get('rt_url') or movie.get('rt_score'):
                    movies_with_rt += 1

            if movies_with_rt == 0:
                print("⚠️  Warning: No RT data found in sample - RT scraping may not be working")
            else:
                print(f"✅ RT validation: {movies_with_rt}/{sample_size} movies have RT data")

        except Exception as e:
            print(f"⚠️  Warning: Could not validate RT data: {e}")

    def validate_data_quality(self):
        """Comprehensive data quality checks to prevent committing broken data"""
        try:
            # 1. Check file existence
            if not os.path.exists('data.json'):
                raise Exception("data.json file not found")

            # 2. Load and validate JSON
            with open('data.json', 'r') as f:
                data = json.load(f)

            # 3. Check minimum movie count
            movies = data.get('movies', [])
            if len(movies) < 200:
                raise Exception(f"Too few movies ({len(movies)}) - possible data loss! Expected at least 200.")

            # 4. Check for recent movies (last 7 days)
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            recent_movies = [m for m in movies if m.get('digital_date', '') >= cutoff_date]

            if len(recent_movies) == 0:
                raise Exception("No recent movies found - automation may not be discovering new releases")

            # 5. Check required fields on sample of movies
            sample_movies = movies[:5] if len(movies) >= 5 else movies
            for movie in sample_movies:
                if not movie.get('title'):
                    raise Exception(f"Movie missing title: {movie}")
                if not movie.get('digital_date'):
                    raise Exception(f"Movie missing digital_date: {movie.get('title')}")
                if not movie.get('poster'):
                    print(f"⚠️  Warning: Movie missing poster: {movie.get('title')}")

            # 6. Check watch links coverage
            movies_with_links = [m for m in movies if any(m.get('watch_links', {}).values())]
            movies_with_rt = [m for m in movies if m.get('rt_score')]
            movies_with_wikipedia = [m for m in movies if m.get('wikipedia_link')]
            movies_with_trailers = [m for m in movies if m.get('trailer_link')]

            # 7. Provider coverage sanity check
            self.validate_provider_coverage(recent_movies)

            # Print validation summary
            print(f"✅ Quality check passed: {len(movies)} total, {len(recent_movies)} recent")
            print(f"   Data coverage: {len(movies_with_links)} with watch links, {len(movies_with_rt)} with RT scores")
            print(f"   Additional links: {len(movies_with_wikipedia)} Wikipedia, {len(movies_with_trailers)} trailers")

        except Exception as e:
            raise Exception(f"Data quality validation failed: {e}")

    def validate_provider_coverage(self, recent_movies):
        """Validate that we have adequate provider coverage for recent movies"""
        import yaml

        # Load validation configuration
        config = {}
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f) or {}

        validation_config = config.get('validation', {})
        min_coverage = validation_config.get('min_provider_coverage', 10)

        # Define search URL patterns that should be considered "no real link"
        search_url_patterns = [
            'google.com/search',
            'amazon.com/s?',
            'play.google.com/store/search',
            'vudu.com/',
            'microsoft.com/store/search',
            'rottentomatoes.com/search',
            'youtube.com/results?search_query'
        ]

        def has_real_watch_link(movie):
            """Check if movie has at least one non-search deep link"""
            watch_links = movie.get('watch_links', {})
            for category in ['streaming', 'rent', 'buy']:
                if category in watch_links:
                    link_obj = watch_links[category]
                    if isinstance(link_obj, dict) and link_obj.get('link'):
                        link_url = link_obj['link']
                        # Check if it's not a search URL
                        if not any(pattern in link_url for pattern in search_url_patterns):
                            return True
            return False

        # Count movies with real provider links
        movies_with_real_links = [m for m in recent_movies if has_real_watch_link(m)]
        coverage_count = len(movies_with_real_links)

        print(f"🔍 Provider coverage check: {coverage_count}/{len(recent_movies)} recent movies have real watch links")

        # Log some examples for debugging
        if coverage_count > 0:
            sample_movie = movies_with_real_links[0]
            print(f"   Example: {sample_movie.get('title')} has links: {list(sample_movie.get('watch_links', {}).keys())}")

        if coverage_count < min_coverage:
            # Log details about missing coverage
            movies_without_links = [m for m in recent_movies if not has_real_watch_link(m)]
            print(f"❌ Movies without real watch links ({len(movies_without_links)}):")
            for movie in movies_without_links[:5]:  # Show first 5
                title = movie.get('title', 'Unknown')
                watch_links = movie.get('watch_links', {})
                print(f"   - {title}: {watch_links}")

            raise Exception(f"Provider coverage too low: {coverage_count} < {min_coverage}. Weekly provider data may be stale or unavailable.")

    def get_statistics(self):
        """Extract statistics from tracking database and data.json"""
        stats = {
            'total': 0,
            'tracking': 0,
            'available': 0,
            'data_movies': 0,
            'movies_with_links': 0,
            'movies_with_rt': 0,
            'movies_with_wikipedia': 0,
            'movies_with_trailers': 0
        }

        try:
            # Get tracking database stats
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)

            movies = db.get('movies', {})
            stats['tracking'] = len([m for m in movies.values() if m.get('status') == 'tracking'])
            stats['available'] = len([m for m in movies.values() if m.get('status') == 'available'])
            stats['total'] = len(movies)

        except Exception as e:
            stats['tracking_error'] = str(e)

        try:
            # Get data.json stats
            with open('data.json', 'r') as f:
                data = json.load(f)

            data_movies = data.get('movies', [])
            stats['data_movies'] = len(data_movies)
            stats['movies_with_links'] = len([m for m in data_movies if any(m.get('watch_links', {}).values())])
            stats['movies_with_rt'] = len([m for m in data_movies if m.get('rt_score')])
            stats['movies_with_wikipedia'] = len([m for m in data_movies if m.get('wikipedia_link')])
            stats['movies_with_trailers'] = len([m for m in data_movies if m.get('trailer_link')])

        except Exception as e:
            stats['data_error'] = str(e)

        return stats

    def generate_newsletter_if_enabled(self):
        """Generate newsletter if auto-generation is enabled in config"""
        try:
            # Load configuration
            config = {}
            if os.path.exists('config.yaml'):
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f) or {}

            newsletter_config = config.get('newsletter', {})
            auto_generate = newsletter_config.get('auto_generate', False)

            if auto_generate:
                print("\n📧 Generating weekly newsletter...")

                # Get configuration values
                days_back = newsletter_config.get('days_back', 7)
                output_dir = newsletter_config.get('output_dir', 'newsletters/')
                formats = newsletter_config.get('formats', ['markdown', 'html', 'text'])

                # Build command
                cmd_parts = ['python3', 'generate_newsletter.py']
                cmd_parts.extend(['--days', str(days_back)])
                cmd_parts.extend(['--output-dir', output_dir])

                if formats:
                    if len(formats) == 3 and 'markdown' in formats and 'html' in formats and 'text' in formats:
                        cmd_parts.extend(['--format', 'all'])
                    else:
                        # Generate each format separately
                        for fmt in formats:
                            if fmt in ['markdown', 'html', 'text']:
                                result = subprocess.run(
                                    cmd_parts + ['--format', fmt],
                                    capture_output=True,
                                    text=True,
                                    timeout=60
                                )
                                if result.returncode == 0:
                                    print(f"✅ Generated {fmt} newsletter")
                                    if result.stdout.strip():
                                        for line in result.stdout.strip().split('\n')[-2:]:  # Last 2 lines
                                            if line.strip():
                                                print(f"   {line}")
                                else:
                                    print(f"⚠️ Newsletter generation failed for {fmt}: {result.stderr}")
                        return

                # Run single command for all formats
                result = subprocess.run(
                    cmd_parts,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    print("✅ Newsletter generated successfully")
                    if result.stdout.strip():
                        # Show last few lines of output
                        for line in result.stdout.strip().split('\n')[-3:]:
                            if line.strip():
                                print(f"   {line}")
                else:
                    print(f"⚠️ Newsletter generation failed: {result.stderr}")

            else:
                print("\n📧 Newsletter auto-generation disabled (set newsletter.auto_generate: true in config.yaml)")

        except Exception as e:
            print(f"⚠️ Newsletter generation error: {e}")

    def print_summary(self):
        """Print execution summary"""
        print("\n" + "=" * 50)
        print("📊 SUMMARY")
        print("=" * 50)
        
        # Get statistics
        stats = self.get_statistics()
        print(f"Total tracked: {stats['total']}")
        print(f"Still tracking: {stats['tracking']}")
        print(f"Now digital: {stats['available']}")

        # Data.json statistics
        if stats['data_movies'] > 0:
            print(f"\n📊 Data Quality:")
            print(f"Movies in data.json: {stats['data_movies']}")
            if stats['data_movies'] > 0:
                link_pct = (stats['movies_with_links'] / stats['data_movies']) * 100
                rt_pct = (stats['movies_with_rt'] / stats['data_movies']) * 100
                wiki_pct = (stats['movies_with_wikipedia'] / stats['data_movies']) * 100
                trailer_pct = (stats['movies_with_trailers'] / stats['data_movies']) * 100
                print(f"Watch links: {stats['movies_with_links']} ({link_pct:.1f}%)")
                print(f"RT scores: {stats['movies_with_rt']} ({rt_pct:.1f}%)")
                print(f"Wikipedia: {stats['movies_with_wikipedia']} ({wiki_pct:.1f}%)")
                print(f"Trailers: {stats['movies_with_trailers']} ({trailer_pct:.1f}%)")
        
        # Execution results
        print(f"\n⏱️  Duration: {datetime.now() - self.start_time}")
        
        successful = [r for r in self.results if r['success']]
        failed = [r for r in self.results if not r['success']]
        
        if successful:
            print(f"✅ Completed: {len(successful)} steps")
        if failed:
            print(f"❌ Failed: {len(failed)} steps")
            for r in failed:
                print(f"   - {r['step']}")
    
    def run(self):
        """Execute the complete daily pipeline"""
        print(f"🚀 NRW Daily Update - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 50)

        # Ensure we're in the right directory (handle both local and CI environments)
        nrw_dir = Path.home() / "Downloads" / "nrw-production"
        if nrw_dir.exists():
            os.chdir(nrw_dir)
            print(f"📂 Working directory: {nrw_dir}")
        else:
            # In CI, we're already in the repo root
            print(f"📂 Working directory: {Path.cwd()}")
        
        # Pipeline steps - using production discovery path
        pipeline = [
            # Phase 1: Production Discovery (replaces legacy movie_tracker.py daily)
            ("python3 generate_data.py --discover",
             "Discover new premieres using production discovery", True),

            # Phase 1.5: Validate discovery results (fail if recall drops below threshold)
            ("python3 ops/validate_discovery.py --days-back 7",
             "Validate discovery against ground truth", False),  # Non-critical to avoid blocking automation

            # Phase 2: Generate final display data with enrichment
            ("python3 generate_data.py",
             "Generate data.json for website with enriched links", True),
        ]
        
        # Execute pipeline
        for cmd, description, critical in pipeline:
            success = self.run_command(cmd, description, critical)
            # If generate_data.py succeeded, validate data quality
            if success and "generate_data.py" in cmd:
                print("\n🔍 Validating RT data...")
                self.validate_rt_data()

                print("\n🔍 Validating data quality...")
                try:
                    self.validate_data_quality()
                except Exception as e:
                    print(f"❌ Data quality validation failed: {e}")
                    self.print_summary()
                    sys.exit(1)

        # Optional newsletter generation
        self.generate_newsletter_if_enabled()

        # Check for changes and commit if needed
        if self.check_changes():
            print("\n📝 Changes detected, committing...")
            
            self.run_command(
                "git add -A",
                "Stage changes",
                critical=False
            )
            
            commit_msg = f"Daily update - {datetime.now().strftime('%Y-%m-%d')}"
            self.run_command(
                f'git commit -m "{commit_msg}"',
                "Commit changes",
                critical=False
            )
            
            self.run_command(
                "git push",
                "Push to remote",
                critical=False
            )
        else:
            print("\n📭 No changes to commit")
        
        # Final summary
        self.print_summary()
        
        # Success message
        print("\n✨ Daily update complete!")
        return 0

def main():
    """Entry point with error handling"""
    try:
        orchestrator = NRWOrchestrator()
        return orchestrator.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Update interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())