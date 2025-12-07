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
    for category in ['streaming', 'vod']:
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

    def run_command_with_retries(self, cmd, description, critical=True, max_retries=2, retry_delays=None):
        """Execute command with retry logic and exponential backoff"""
        if retry_delays is None:
            retry_delays = [30, 45]  # Default delays in seconds

        max_retries = min(max_retries, len(retry_delays))  # Ensure we don't exceed available delays

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            if attempt > 0:
                delay = retry_delays[attempt - 1]
                print(f"⏳ Retrying {description} in {delay}s (attempt {attempt + 1}/{max_retries + 1})...")
                time.sleep(delay)

            success = self.run_command(cmd, description, critical=False)  # Don't exit on failure for retries

            if success:
                if attempt > 0:
                    print(f"✅ {description} succeeded on attempt {attempt + 1}")
                return True
            else:
                if attempt < max_retries:
                    print(f"❌ Attempt {attempt + 1} failed, will retry...")
                else:
                    print(f"❌ All {max_retries + 1} attempts failed for {description}")
                    if critical:
                        self.print_summary()
                        sys.exit(1)

        return False

    def check_changes(self):
        """Check if there are git changes to commit (only data.json for CI workflow)"""
        result = subprocess.run(
            "git diff --quiet data.json",
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
            # 1. Check file existence and size
            if not os.path.exists('data.json'):
                raise Exception("data.json file not found")

            file_size = os.path.getsize('data.json')
            file_size_mb = file_size / (1024 * 1024)

            # Size sanity checks
            if file_size < 1000:  # Less than 1KB
                raise Exception(f"data.json file suspiciously small: {file_size} bytes")

            if file_size_mb > 100:  # More than 100MB
                print(f"⚠️ Warning: data.json is very large: {file_size_mb:.1f}MB")

            print(f"📊 data.json file size: {file_size_mb:.2f}MB")

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

            # Check all movies for basic structural checks with early exit on errors
            movies = data['movies']
            error_count = 0
            max_errors = 50  # Early exit after first 50 errors

            for i, movie in enumerate(movies):
                if not isinstance(movie, dict):
                    error_count += 1
                    print(f"⚠️ Error {error_count}: movie[{i}] is not a dict: {type(movie)}")
                    if error_count >= max_errors:
                        raise Exception(f"Too many structural errors ({error_count}+) - stopping validation")
                    continue

                # Check required movie keys (digital_date is optional)
                required_movie_keys = ['id', 'title']
                for key in required_movie_keys:
                    if key not in movie:
                        error_count += 1
                        print(f"⚠️ Error {error_count}: movie[{i}] missing required key: {key}")
                        if error_count >= max_errors:
                            raise Exception(f"Too many structural errors ({error_count}+) - stopping validation")

            if error_count > 0:
                print(f"⚠️ Found {error_count} structural issues in movies data")
                if error_count >= max_errors:
                    raise Exception(f"Found {error_count}+ structural errors - data quality unacceptable")

            # 3. Check minimum movie count (warn on low counts)
            movies = data['movies']  # Already validated to exist and be a list
            if len(movies) < 50:
                print(f"⚠️  Warning: Very low movie count ({len(movies)}) - expected at least 50. Check for data issues.")
            elif len(movies) < 150:
                print(f"⚠️  Warning: Movie count is low ({len(movies)}) - expected 150+, but continuing")

            # 4. Check for recent movies - strict 7-day window per charter
            from datetime import timedelta
            import yaml

            # Load validation configuration
            config = {}
            if os.path.exists('config.yaml'):
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f) or {}

            validation_config = config.get('validation', {})
            recent_days = validation_config.get('recent_days', 7)  # Default to 7-day window
            fail_on_no_recent = validation_config.get('fail_on_no_recent', False)  # Default to warn behavior
            cutoff_date = (datetime.now() - timedelta(days=recent_days)).strftime('%Y-%m-%d')
            recent_movies = [m for m in movies if m.get('digital_date', '') >= cutoff_date]

            if len(recent_movies) == 0:
                if fail_on_no_recent:
                    # Fail validation when flag is true
                    raise Exception(f"No recent movies found in last {recent_days} days (since {cutoff_date}). This indicates discovery system failure or data quality issues.")
                else:
                    # Warning instead of failure - allow pipeline to continue
                    print(f"⚠️ Warning: No recent movies found in last {recent_days} days (since {cutoff_date}). Continuing with validation.")
                # Skip provider coverage validation when no recent movies
                skip_provider_check = True
            else:
                skip_provider_check = False

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

            # 7. Provider coverage sanity check (only if we have recent movies)
            if not skip_provider_check:
                self.validate_provider_coverage(recent_movies)

            # Print validation summary
            if len(recent_movies) == 0:
                print(f"✅ Quality check completed: {len(movies)} total, {len(recent_movies)} recent")
                print(f"   Note: No recent movies found but pipeline is continuing")
            else:
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

    def get_link_source_mix(self):
        """Analyze link sources in data.json (Watchmode vs platform scrapers vs none)"""
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)

            movies = data.get('movies', [])
            link_sources = {
                'watchmode': 0,
                'platform_scrapers': 0,
                'search_urls': 0,
                'no_links': 0
            }

            search_url_patterns = [
                'google.com/search',
                'amazon.com/s?',
                'play.google.com/store/search'
            ]

            for movie in movies:
                watch_links = movie.get('watch_links', {})
                has_any_links = False
                has_search_urls = False

                # Check all link categories
                for category in ['streaming', 'vod']:
                    if category in watch_links:
                        link_obj = watch_links[category]
                        if isinstance(link_obj, dict) and link_obj.get('link'):
                            has_any_links = True
                            link_url = link_obj['link']

                            # Check if it's a search URL
                            if any(pattern in link_url for pattern in search_url_patterns):
                                has_search_urls = True

                if has_search_urls:
                    link_sources['search_urls'] += 1
                elif has_any_links:
                    # Assume Watchmode if we have real links (more detailed tracking would need to be added to link generation)
                    link_sources['watchmode'] += 1
                else:
                    link_sources['no_links'] += 1

            return link_sources

        except Exception as e:
            return {'error': str(e)}


    def extract_discovery_metrics(self):
        """Extract discovery metrics from dedicated discovery JSON artifact or fallback to log parsing"""
        polled = 0
        transitions = 0

        # Primary path: Read from dedicated discovery JSON artifact for provider availability
        try:
            if os.path.exists('metrics/discovery_run.json'):
                with open('metrics/discovery_run.json', 'r') as f:
                    discovery_data = json.load(f)

                operation = discovery_data.get('operation')
                if operation == 'discover_availability':
                    results = discovery_data.get('results', {})
                    polled = results.get('polled', 0)
                    transitions = results.get('transitions', 0)
                    print(f"📊 Discovery metrics from JSON artifact: {polled} polled, {transitions} transitions")
                    return polled, transitions
                else:
                    print(f"⚠️ Unexpected operation in discovery_run.json: {operation} (expected 'discover_availability')")

        except Exception as e:
            print(f"⚠️ Failed to read discovery JSON artifact: {e}")

        # Fallback to log parsing if JSON artifact not available or invalid
        print("📊 Falling back to log parsing for discovery metrics")
        for result in self.results:
            if result['success'] and result['output']:
                output_lines = result['output'].split('\n')
                for line in output_lines:
                    # Look for the standardized metrics line: "Polled X movies, Y changes detected"
                    if line.startswith('Polled ') and 'changes detected' in line:
                        import re
                        # Extract numbers using regex
                        match = re.search(r'Polled (\d+) movies, (\d+) changes detected', line)
                        if match:
                            polled = int(match.group(1))
                            transitions = int(match.group(2))
                            print(f"📊 Extracted metrics from logs: {polled} polled, {transitions} transitions")
                            break

        return polled, transitions

    def save_daily_metrics(self):
        """Save consolidated daily metrics to metrics/daily.jsonl from separate intake and discovery files"""
        max_retries = 3
        retry_delay = 0.5  # 500ms

        for attempt in range(max_retries):
            try:
                # Ensure metrics directory exists
                os.makedirs('metrics', exist_ok=True)

                # Read metrics from separate intake and discovery files
                discovered_today = 0
                polled = 0
                transitions = 0

                # Read intake metrics
                if os.path.exists('metrics/intake_run.json'):
                    with open('metrics/intake_run.json', 'r') as f:
                        intake_data = json.load(f)

                    if intake_data.get('operation') == 'intake_premieres':
                        results = intake_data.get('results', {})
                        discovered_today = results.get('discovered', 0)

                # Read discovery metrics for polled and transitions
                if os.path.exists('metrics/discovery_run.json'):
                    with open('metrics/discovery_run.json', 'r') as f:
                        discovery_data = json.load(f)

                    if discovery_data.get('operation') == 'discover_availability':
                        results = discovery_data.get('results', {})
                        polled = results.get('polled', 0)
                        transitions = results.get('transitions', 0)
                    else:
                        # LEGACY SUPPORT (SCHEDULED FOR REMOVAL): Historical combined schema
                        # TODO: Remove after 2025-12-31 when all historical backfill needs are complete
                        # This branch handles pre-separation metrics where discovery_run.json contained intake operations
                        operation = discovery_data.get('operation')
                        if operation == 'intake_premieres':
                            # Minimal historical support: treat intake as discovery for legacy compatibility
                            discovered_today = discovery_data.get('results', {}).get('discovered', 0)
                            transitions = discovered_today
                            print(f"⚠️ DEPRECATED: Using legacy combined schema (intake in discovery_run.json)")
                        # Drop support for unknown operations - they should not exist in historical files

                # Create consolidated metrics entry
                metrics_entry = {
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'timestamp': datetime.now().isoformat(),
                    'discovered_today': discovered_today,
                    'polled': polled,
                    'transitions': transitions
                }

                # Append to metrics file with durable write
                metrics_file = 'metrics/daily.jsonl'
                with open(metrics_file, 'a') as f:
                    f.write(json.dumps(metrics_entry) + '\n')
                    f.flush()  # Flush Python buffer to OS
                    os.fsync(f.fileno())  # Force OS to write to disk

                print(f"✅ Daily metrics saved: {discovered_today} discovered, {polled} polled, {transitions} transitions")
                return  # Success, exit retry loop

            except Exception as e:
                print(f"⚠️ Failed to save daily metrics (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"❌ All {max_retries} attempts to save metrics failed")

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

        # Link source mix analysis
        link_sources = self.get_link_source_mix()
        if 'error' not in link_sources:
            print(f"\n🔗 Link Source Mix:")
            total_movies = sum(link_sources.values())
            if total_movies > 0:
                for source, count in link_sources.items():
                    pct = (count / total_movies) * 100
                    print(f"{source.replace('_', ' ').title()}: {count} ({pct:.1f}%)")

                # Fail on search URLs if enabled
                if link_sources['search_urls'] > 0:
                    fail_on_search = os.getenv('NRW_FAIL_ON_SEARCH_URLS', 'false').lower() == 'true'
                    if fail_on_search:
                        print(f"❌ ERROR: Found {link_sources['search_urls']} Google search URLs in data.json")
                        print("   Set NRW_FAIL_ON_SEARCH_URLS=false to disable this check")
                        sys.exit(1)
                    else:
                        print(f"⚠️ Warning: Found {link_sources['search_urls']} search URLs (set NRW_FAIL_ON_SEARCH_URLS=true to fail on this)")

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
        # Acquire exclusive lock to prevent concurrent runs
        # Skip lock in CI environments (fresh container each run)
        is_ci = os.getenv('CI') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true'
        lock_file = '.nrw_orchestrator.lock'

        # PID-aware stale lock cleanup
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    lock_info = json.load(f)
                pid = lock_info.get('pid')
                if pid and os.path.exists(f'/proc/{pid}'):  # Linux check
                    print(f'❌ Active process {pid} holds lock')
                    sys.exit(1)
                else:
                    print(f'⚠️ Removing stale lock (PID {pid} not running)')
                    os.remove(lock_file)
            except:
                os.remove(lock_file)  # Force remove corrupted lock

        # Create lock file with PID and timestamp
        try:
            with open(lock_file, 'w') as f:
                json.dump({
                    'pid': os.getpid(),
                    'started_at': datetime.now().isoformat(),
                    'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
                }, f)
        except Exception as e:
            print(f"⚠️  Failed to create lock file: {e}")

        try:
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

            # Load orchestrator configuration
            config = {}
            if os.path.exists('config.yaml'):
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f) or {}

            orchestrator_config = config.get('orchestrator', {})
            discovery_retries = int(os.getenv('DISCOVERY_RETRIES', orchestrator_config.get('discovery_retries', 2)))
            retry_delays = orchestrator_config.get('discovery_retry_delays', [30, 45])

            # Pipeline steps for daily discovery and publication
            discovery_pipeline = [
                # Phase 1: Intake new premieres from TMDB
                ("python3 generate_data.py --intake",
                 "Intake new premieres using production discovery", True, True),  # Last True indicates retry

                # Phase 2: Discovery – check tracked movies for digital availability
                ("python3 generate_data.py --discover",
                 "Discover provider availability for tracking movies", True, False),  # Last False indicates no retry
            ]

            # Execute discovery and monitoring pipeline
            for step in discovery_pipeline:
                if len(step) == 4:
                    cmd, description, critical, use_retry = step
                    if use_retry:
                        self.run_command_with_retries(cmd, description, critical, discovery_retries, retry_delays)
                    else:
                        self.run_command(cmd, description, critical)
                else:
                    # Backward compatibility for 3-element tuples
                    cmd, description, critical = step
                    self.run_command(cmd, description, critical)

            # Phase 2: Log metrics for diagnostics (no enforcement - just reporting)
            print(f"\n📊 Phase 2: Metrics Summary")

            if os.path.exists('metrics/discovery_run.json'):
                try:
                    with open('metrics/discovery_run.json') as f:
                        discovery_metrics = json.load(f)
                    operation = discovery_metrics.get('operation', 'unknown')
                    polled = discovery_metrics.get('results', {}).get('polled', 0)
                    transitions = discovery_metrics.get('results', {}).get('transitions', 0)
                    print(f'   Discovery: {polled} polled, {transitions} transitions')
                except Exception as e:
                    print(f'   Discovery metrics: could not read ({e})')
            else:
                print('   Discovery metrics: file not found')

            if os.path.exists('metrics/intake_run.json'):
                try:
                    with open('metrics/intake_run.json') as f:
                        intake_metrics = json.load(f)
                    discovered = intake_metrics.get('results', {}).get('discovered', 0)
                    print(f'   Intake: {discovered} new movies discovered')
                except Exception as e:
                    print(f'   Intake metrics: could not read ({e})')
            else:
                print('   Intake metrics: file not found')

            # Save consolidated daily metrics for historical tracking
            self.save_daily_metrics()

            # Phase 3: Generate final display data with enrichment
            # NOTE: data.json uses eventual consistency model - only updated here in Phase 3
            # This means data.json may temporarily lag behind movie_tracking.json between
            # discovery (Phase 2) and final generation (Phase 3)
            print(f"\n📊 Phase 3: Data Generation")
            success = self.run_command(
                "python3 generate_data.py",
                "Generate data.json for website with enriched links",
                True
            )

            # Log data quality info (report-only, no enforcement)
            if success:
                print("\n🔍 Validating RT data...")
                self.validate_rt_data()

                print("\n🔍 Validating data quality...")
                try:
                    self.validate_data_quality()
                except Exception as e:
                    print(f"⚠️ Data quality issue: {e}")

            # Final summary
            self.print_summary()

            # Success message
            print("\n✨ Daily update complete - data.json ready for auto-publish!")
            return 0
        finally:
            # Always remove lock file
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                except:
                    pass

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