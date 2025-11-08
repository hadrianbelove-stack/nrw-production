#!/usr/bin/env python3
"""
NRW Daily Orchestrator - Coordinates all daily update tasks
"""

import subprocess
import json
import sys
import os
import yaml
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


def has_real_watch_link(movie):
    """Check if movie has at least one non-search deep link"""
    # Define search URL patterns that should be considered "no real link"
    search_url_patterns = [
        'google.com/search',
        'amazon.com/s?',
        'play.google.com/store/search',
        'vudu.com/search',
        'microsoft.com/store/search',
        'rottentomatoes.com/search',
        'youtube.com/results?search_query'
    ]

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


class NRWOrchestrator:
    def __init__(self):
        self.start_time = datetime.now()
        self.results = []
        self.has_changes = False
        self.phase_timings = []  # Track timing for each phase
        
    def run_command(self, cmd, description, critical=True):
        """Execute command with error handling"""
        phase_start = datetime.now()
        print(f"\n📍 {description}...")

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )

        phase_end = datetime.now()
        phase_duration = phase_end - phase_start

        success = result.returncode == 0

        self.results.append({
            'step': description,
            'success': success,
            'output': result.stdout,
            'error': result.stderr,
            'duration': phase_duration
        })

        # Track phase timing
        self.phase_timings.append({
            'phase': description,
            'duration': phase_duration,
            'success': success
        })
        
        if success:
            print(f"✅ {description} complete ({phase_duration.total_seconds():.1f}s)")
            if result.stdout.strip():
                # Print relevant output
                for line in result.stdout.strip().split('\n')[:5]:  # First 5 lines
                    if line.strip():
                        print(f"   {line}")
        else:
            print(f"❌ Failed: {description} ({phase_duration.total_seconds():.1f}s)")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            if critical:
                self.print_summary()
                sys.exit(1)
        
        return success
    
    def check_changes(self):
        """Check if there are git changes to commit (only data.json for CI workflow)"""
        result = subprocess.run(
            "git diff --quiet data.json",
            shell=True
        )
        self.has_changes = result.returncode != 0
        return self.has_changes

    def wait_for_admin_approval(self, timeout_minutes=60):
        """Wait for admin approval in admin/approval.json"""
        approval_file = 'admin/approval.json'

        # Check if running in CI environment
        is_ci = os.getenv('GITHUB_ACTIONS') or os.getenv('CI')

        if is_ci:
            # In CI, don't wait - just check if approval exists
            if not os.path.exists(approval_file):
                print("❌ CI Environment: No admin approval found")
                print(f"   Missing file: {approval_file}")
                print("   Admin must run 'python3 admin.py --full-review' and approve changes")
                sys.exit(1)

            # Validate the approval
            try:
                self.validate_approval()
                print("✅ CI Environment: Admin approval validated")
                return True
            except Exception as e:
                print(f"❌ CI Environment: Invalid approval: {e}")
                sys.exit(1)

        # Local environment - wait for approval
        print(f"\n⏸️  Waiting for admin approval...")
        print(f"   Please run: python3 admin.py --full-review")
        print(f"   Then review changes and click 'Approve & Generate'")
        print(f"   Waiting for: {approval_file}")
        print(f"   Timeout: {timeout_minutes} minutes")

        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        poll_interval = 5  # Check every 5 seconds

        while time.time() - start_time < timeout_seconds:
            if os.path.exists(approval_file):
                try:
                    self.validate_approval()
                    print(f"✅ Admin approval received and validated")
                    return True
                except Exception as e:
                    print(f"⚠️  Approval file found but invalid: {e}")
                    print(f"   Waiting for valid approval...")

            time.sleep(poll_interval)

            # Show progress every 30 seconds
            elapsed = time.time() - start_time
            if int(elapsed) % 30 == 0:
                remaining = (timeout_seconds - elapsed) / 60
                print(f"   Still waiting... {remaining:.1f} minutes remaining")

        # Timeout
        print(f"❌ Timeout: No admin approval received after {timeout_minutes} minutes")
        sys.exit(1)

    def validate_approval(self):
        """Validate admin/approval.json format and freshness"""
        approval_file = 'admin/approval.json'

        if not os.path.exists(approval_file):
            raise Exception(f"Approval file {approval_file} does not exist")

        try:
            with open(approval_file, 'r') as f:
                approval = json.load(f)
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON in approval file: {e}")

        # Required fields
        if 'timestamp' not in approval:
            raise Exception("Approval missing required field: timestamp")

        # Check timestamp freshness (within 2 hours)
        try:
            approval_time = datetime.fromisoformat(approval['timestamp'].replace('Z', '+00:00'))
            now = datetime.now().astimezone()
            time_diff = now - approval_time

            if time_diff > timedelta(hours=2):
                raise Exception(f"Approval is stale: {time_diff.total_seconds()/3600:.1f} hours old (max 2 hours)")

        except ValueError as e:
            raise Exception(f"Invalid timestamp format: {e}")

        # Optional reviewer validation
        reviewer = approval.get('reviewer')
        if reviewer is not None and (not isinstance(reviewer, str) or not reviewer.strip()):
            raise Exception("Reviewer field must be non-empty string if provided")

        # Optional tracking digest validation
        tracking_digest = approval.get('tracking_digest')
        if tracking_digest:
            try:
                # Compute current digest of movie_tracking.json
                if os.path.exists('movie_tracking.json'):
                    with open('movie_tracking.json', 'rb') as f:
                        current_digest = hashlib.sha256(f.read()).hexdigest()

                    if tracking_digest != current_digest:
                        raise Exception("Tracking digest mismatch - movie_tracking.json has changed since approval")
                else:
                    raise Exception("movie_tracking.json not found for digest validation")
            except Exception as e:
                raise Exception(f"Tracking digest validation failed: {e}")

        return approval

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
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    raise Exception(f"data.json is not valid JSON: {e}")

            # 2.5. Validate schema structure
            if not isinstance(data, dict):
                raise Exception(f"data.json root is not a dict: {type(data)}")

            # Check required root keys
            required_root_keys = ['generated_at', 'count', 'movies']
            for key in required_root_keys:
                if key not in data:
                    raise Exception(f"data.json missing required key: {key}")

            # Check data types
            if not isinstance(data['generated_at'], str):
                raise Exception(f"data.json generated_at must be string, got {type(data['generated_at'])}")

            if not isinstance(data['count'], int):
                raise Exception(f"data.json count must be int, got {type(data['count'])}")

            if not isinstance(data['movies'], list):
                raise Exception(f"data.json movies must be list, got {type(data['movies'])}")

            # Check that movies are dicts with required keys
            for i, movie in enumerate(data['movies'][:5]):  # Check first 5 for performance
                if not isinstance(movie, dict):
                    raise Exception(f"data.json movie[{i}] is not a dict: {type(movie)}")

                # Check required movie keys (digital_date is optional)
                required_movie_keys = ['id', 'title']
                for key in required_movie_keys:
                    if key not in movie:
                        raise Exception(f"data.json movie[{i}] missing required key: {key}")

            # 3. Check minimum movie count (warn on low counts)
            movies = data['movies']  # Already validated to exist and be a list
            if len(movies) < 50:
                print(f"⚠️  Warning: Very low movie count ({len(movies)}) - expected at least 50. Check for data issues.")
            elif len(movies) < 150:
                print(f"⚠️  Warning: Movie count is low ({len(movies)}) - expected 150+, but continuing")

            # 4. Check for recent movies (last 14 days to account for weekends/delays)
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
            recent_movies = [m for m in movies if m.get('digital_date', '') >= cutoff_date]

            if len(recent_movies) == 0:
                # Log warning but don't fail - discovery gaps are normal
                print(f"⚠️  Warning: No recent movies found since {cutoff_date} - this may indicate discovery gaps but doesn't affect existing data")
                # Use a longer lookback for validation (30 days) to ensure we have some movies to validate
                extended_cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                recent_movies = [m for m in movies if m.get('digital_date', '') >= extended_cutoff]
                if len(recent_movies) == 0:
                    print(f"⚠️  Warning: No movies found in last 30 days - discovery may be down, but existing data is still valid")
                    print(f"   Continuing with validation using full dataset")
                    recent_movies = movies[:20]  # Use first 20 movies for validation instead

            # 5. Check required fields on sample of movies
            sample_movies = movies[:5] if len(movies) >= 5 else movies
            for movie in sample_movies:
                if not movie.get('title'):
                    print(f"⚠️  Warning: Movie missing title: {movie.get('id', 'unknown')}")
                if not movie.get('digital_date'):
                    print(f"⚠️  Warning: Movie missing digital_date: {movie.get('title', 'unknown')}")
                if not movie.get('poster'):
                    print(f"⚠️  Warning: Movie missing poster: {movie.get('title', 'unknown')}")

            # 6. Check watch links coverage
            movies_with_links = [m for m in movies if has_real_watch_link(m)]
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
            # Note: Unlike generate_data.py, we fail hard here rather than rebuilding
            # This is intentional - daily_orchestrator validates before deployment
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
        min_coverage = int(os.getenv('MIN_PROVIDER_COVERAGE', validation_config.get('min_provider_coverage_count', 10)))


        # Count movies with real provider links
        movies_with_real_links = [m for m in recent_movies if has_real_watch_link(m)]
        coverage_count = len(movies_with_real_links)

        print(f"🔍 Provider coverage check: {coverage_count}/{len(recent_movies)} recent movies have real watch links")

        # Log some examples for debugging
        if coverage_count > 0:
            sample_movie = movies_with_real_links[0]
            print(f"   Example: {sample_movie.get('title')} has links: {list(sample_movie.get('watch_links', {}).keys())}")

        if coverage_count < min_coverage:
            # Log details about missing coverage (non-fatal warning)
            movies_without_links = [m for m in recent_movies if not has_real_watch_link(m)]
            print(f"⚠️  Warning: Low provider coverage - {coverage_count}/{len(recent_movies)} movies have watch links (target: {min_coverage})")
            print(f"   Movies without real watch links: {len(movies_without_links)}")
            for movie in movies_without_links[:5]:  # Show first 5
                title = movie.get('title', 'Unknown')
                watch_links = movie.get('watch_links', {})
                print(f"   - {title}: {watch_links}")
            print(f"   Note: Frontend will show disabled buttons for movies without links")
            print(f"   This is normal when agent scrapers are down - admin panel can add links manually")

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
            stats['movies_with_links'] = len([m for m in data_movies if has_real_watch_link(m)])
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
        
        # Phase timing summary
        if self.phase_timings:
            print(f"\n⏱️  Phase Timings:")
            for timing in self.phase_timings:
                status_icon = "✅" if timing['success'] else "❌"
                print(f"{status_icon} {timing['phase']}: {timing['duration'].total_seconds():.1f}s")

        # Execution results
        total_duration = datetime.now() - self.start_time
        print(f"\n⏱️  Total Duration: {total_duration}")

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
        forced_cwd = os.getenv('NRW_FORCE_CWD')
        if forced_cwd:
            forced_path = Path(forced_cwd).expanduser()
            if forced_path.exists():
                os.chdir(forced_path)
                print(f"📂 Working directory (forced): {forced_path}")
            else:
                print(f"⚠️  Forced directory {forced_path} does not exist, using current directory")
                print(f"📂 Working directory: {Path.cwd()}")
        else:
            # Use current working directory by default
            print(f"📂 Working directory: {Path.cwd()}")
        
        # Pipeline steps - modified to include mandatory admin approval gate
        discovery_pipeline = [
            # Phase 1: Production Discovery (replaces legacy movie_tracker.py daily)
            ("python3 generate_data.py --discover",
             "Discover new premieres using production discovery", True),

            # Phase 1.5: Check tracking movies for digital availability (provider monitoring)
            ("python3 generate_data.py --check",
             "Check tracking movies for digital availability", True),

            # Phase 1.75: Validate discovery results (fail if recall drops below threshold)
            ("python3 ops/validate_discovery.py --days-back 7",
             "Validate discovery against ground truth", False),  # Non-critical to avoid blocking automation
        ]

        # Execute discovery and monitoring pipeline
        for cmd, description, critical in discovery_pipeline:
            self.run_command(cmd, description, critical)

        # Phase 3: Mandatory Admin Approval Gate
        print(f"\n📋 Phase 3: Admin Approval Gate")
        self.wait_for_admin_approval()

        # Phase 4: Generate final display data with enrichment (post-approval only)
        print(f"\n📊 Phase 4: Post-Approval Data Generation")
        success = self.run_command(
            "python3 generate_data.py",
            "Generate data.json for website with enriched links",
            True
        )

        # Validate data quality only after approval and generation
        if success:
            print("\n🔍 Validating RT data...")
            self.validate_rt_data()

            print("\n🔍 Validating data quality...")
            try:
                self.validate_data_quality()
            except Exception as e:
                # Get approval details for failure context
                try:
                    approval = self.validate_approval()
                    reviewer = approval.get('reviewer', 'unknown')
                    timestamp = approval.get('timestamp', 'unknown')
                    print(f"❌ Data quality validation failed after approval by {reviewer} at {timestamp}")
                except:
                    print(f"❌ Data quality validation failed")

                print(f"   Error: {e}")
                self.print_summary()
                sys.exit(1)

        # Optional newsletter generation
        self.generate_newsletter_if_enabled()

        # Check for changes and commit if needed (skip in CI)
        if self.check_changes():
            print("\n📝 Changes detected...")

            # Skip committing in CI environment - let workflow handle it
            if os.getenv('GITHUB_ACTIONS') or os.getenv('CI'):
                print("🤖 Running in CI - skipping commit/push (workflow will handle)")
            else:
                print("💻 Running locally - committing changes...")

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