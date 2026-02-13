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
from datetime import datetime, timedelta
from pathlib import Path

# Configuration constants - change these to adjust behavior
RT_VALIDATION_SAMPLE_SIZE = 5     # How many movies to sample when validating RT data
MAX_ERRORS_BEFORE_EXIT = 50       # Stop processing after this many errors (fail-fast)


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
        # Failure tracking for end-of-run reporting (never exit, always report)
        self.failures = []  # List of {phase, severity, message, context}
        self.warnings = []  # Non-critical issues
        self.health_issues = []  # Health check results
        self.stall_status = {'stalled': False}  # Stall detection results
        
    def _track_error(self, phase, message, context=None, severity='error'):
        """Track an error or warning for end-of-run reporting.

        Args:
            phase: Which phase/method the error occurred in
            message: Human-readable error message
            context: Optional additional context (exception type, etc.)
            severity: 'error' for failures, 'warning' for non-critical issues
        """
        entry = {
            'phase': phase,
            'message': message,
            'context': context
        }

        if severity == 'error':
            entry['severity'] = 'error'
            self.failures.append(entry)
        else:
            self.warnings.append(entry)

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
                for line in result.stdout.strip().split('\n')[:50]:  # First 50 lines
                    if line.strip():
                        print(f"   {line}")
        else:
            print(f"❌ Failed: {description} ({phase_duration.total_seconds():.1f}s)")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            # Track failure for end-of-run report (best-effort: continue, don't exit)
            self.failures.append({
                'phase': description,
                'severity': 'error',
                'message': f'Phase failed with exit code {result.returncode}',
                'context': result.stderr.strip()[:500] if result.stderr else None,
                'stdout_preview': result.stdout.strip()[:500] if result.stdout else None
            })

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
                    # Note: failure already tracked by run_command, just add retry context
                    if self.failures and self.failures[-1]['phase'] == description:
                        self.failures[-1]['message'] += f' (after {max_retries + 1} attempts)'

        return False

    def check_changes(self):
        """Check if there are git changes to commit (only data.json for CI workflow)"""
        try:
            result = subprocess.run(
                ['git', 'diff', '--quiet', 'data.json'],
                shell=False
            )
            self.has_changes = result.returncode != 0
            return self.has_changes
        except Exception as e:
            print(f"⚠️ Error checking git changes: {e}")
            self._track_error('Git Check', f'Error checking git changes: {e}', severity='warning')
            self.has_changes = False
            return False



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
            sample_size = min(RT_VALIDATION_SAMPLE_SIZE, len(movies))
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
            max_errors = MAX_ERRORS_BEFORE_EXIT

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
                    raise Exception(f"No recent movies found in last {recent_days} days (since {cutoff_date}). This indicates pipeline failure or data quality issues.")
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
            movies_with_rt = [m for m in movies if m.get('links', {}).get('rt')]
            movies_with_wikipedia = [m for m in movies if m.get('links', {}).get('wikipedia')]
            movies_with_trailers = [m for m in movies if m.get('links', {}).get('trailer')]

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
            self._track_error('Statistics', f'Error reading movie_tracking.json: {e}', severity='warning')

        try:
            # Get data.json stats
            with open('data.json', 'r') as f:
                data = json.load(f)

            data_movies = data.get('movies', [])
            stats['data_movies'] = len(data_movies)
            stats['movies_with_links'] = len([m for m in data_movies if has_real_watch_link(m)])
            stats['movies_with_rt'] = len([m for m in data_movies if m.get('links', {}).get('rt')])
            stats['movies_with_wikipedia'] = len([m for m in data_movies if m.get('links', {}).get('wikipedia')])
            stats['movies_with_trailers'] = len([m for m in data_movies if m.get('links', {}).get('trailer')])

        except Exception as e:
            stats['data_error'] = str(e)
            self._track_error('Statistics', f'Error reading data.json: {e}', severity='warning')

        return stats

    def get_link_source_mix(self):
        """Analyze link sources in data.json (real deep links vs search fallbacks vs none)"""
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)

            movies = data.get('movies', [])
            link_sources = {
                'deep_links': 0,  # Real links from JustWatch API or scrapers
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
                    link_sources['deep_links'] += 1
                else:
                    link_sources['no_links'] += 1

            return link_sources

        except Exception as e:
            self._track_error('Link Analysis', f'Error analyzing link sources: {e}', severity='warning')
            return {'error': str(e)}


    def save_daily_metrics(self):
        """Save consolidated daily metrics to metrics/daily.jsonl from separate intake and discovery files"""
        max_retries = 3
        retry_delay = 0.5  # 500ms

        for attempt in range(max_retries):
            try:
                # Ensure metrics directory exists
                os.makedirs('metrics', exist_ok=True)

                # Read metrics from separate intake and discovery files
                intaked_today = 0
                polled = 0
                transitions = 0

                # Read intake metrics
                if os.path.exists('metrics/intake_run.json'):
                    with open('metrics/intake_run.json', 'r') as f:
                        intake_data = json.load(f)

                    if intake_data.get('operation') == 'intake_premieres':
                        results = intake_data.get('results', {})
                        intaked_today = results.get('intaked', 0)

                # Read discovery metrics for polled and transitions
                if os.path.exists('metrics/discovery_run.json'):
                    with open('metrics/discovery_run.json', 'r') as f:
                        discovery_data = json.load(f)

                    if discovery_data.get('operation') == 'discover_availability':
                        results = discovery_data.get('results', {})
                        polled = results.get('polled', 0)
                        transitions = results.get('transitions', 0)
                    else:
                        # Legacy combined schema support (pre-separation metrics)
                        operation = discovery_data.get('operation')
                        if operation == 'intake_premieres':
                            results = discovery_data.get('results', {})
                            intaked_today = results.get('intaked', 0)
                            transitions = intaked_today

                # Create consolidated metrics entry
                metrics_entry = {
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'timestamp': datetime.now().isoformat(),
                    'intaked_today': intaked_today,
                    'polled': polled,
                    'transitions': transitions
                }

                # Append to metrics file with durable write
                metrics_file = 'metrics/daily.jsonl'
                with open(metrics_file, 'a') as f:
                    f.write(json.dumps(metrics_entry) + '\n')
                    f.flush()  # Flush Python buffer to OS
                    os.fsync(f.fileno())  # Force OS to write to disk

                print(f"✅ Daily metrics saved: {intaked_today} intaked, {polled} polled, {transitions} transitions")
                return  # Success, exit retry loop

            except Exception as e:
                print(f"⚠️ Failed to save daily metrics (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"❌ All {max_retries} attempts to save metrics failed")
                    self._track_error('Metrics', f'Failed to save daily metrics after {max_retries} attempts: {e}', severity='warning')

    def _get_metrics_age_hours(self, timestamp_str):
        """Calculate age of metrics timestamp in hours"""
        try:
            metrics_dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(metrics_dt.tzinfo) if metrics_dt.tzinfo else datetime.now()
            return (now - metrics_dt).total_seconds() / 3600
        except (ValueError, TypeError):
            return 999  # Return large number if can't parse

    def check_discovery_health(self):
        """Health check for discovery phase - reports issues but never fails pipeline"""
        print("\n🔍 Running discovery health checks...")
        issues = []

        # Check metrics file exists
        if not os.path.exists('metrics/discovery_run.json'):
            issue = {
                'check': 'metrics_exist',
                'severity': 'error',
                'message': 'discovery_run.json MISSING - discovery phase may have crashed'
            }
            issues.append(issue)
            # Track failure before early return (so it shows in summary)
            print(f"   ❌ {issue['message']}")
            self.failures.append({
                'phase': 'Health Check',
                'severity': 'error',
                'message': issue['message'],
                'context': issue['check']
            })
            self.health_issues = issues
            return issues

        try:
            with open('metrics/discovery_run.json') as f:
                metrics = json.load(f)

            # Check recency (should be from current run)
            timestamp = metrics.get('timestamp')
            if timestamp:
                age_hours = self._get_metrics_age_hours(timestamp)

                # Parse timestamp to compare with orchestrator start time
                try:
                    metrics_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    # Convert to naive datetime for comparison with self.start_time
                    if metrics_dt.tzinfo:
                        metrics_dt = metrics_dt.replace(tzinfo=None)

                    # Check if metrics are from current run (within tolerance)
                    time_diff = abs((metrics_dt - self.start_time).total_seconds())
                    tolerance_minutes = 5  # Allow 5 minute tolerance for clock skew

                    if metrics_dt < self.start_time - timedelta(minutes=tolerance_minutes):
                        issues.append({
                            'check': 'metrics_not_updated_for_current_run',
                            'severity': 'error',
                            'message': f'Current run did not produce fresh discovery metrics (metrics from {metrics_dt.strftime("%H:%M")}, run started {self.start_time.strftime("%H:%M")})'
                        })
                        print(f"   ❌ Current run did not update discovery metrics")
                    elif age_hours > 2:
                        # This is the existing age-based warning for genuinely old metrics
                        issues.append({
                            'check': 'metrics_stale',
                            'severity': 'warning',
                            'message': f'Metrics are {age_hours:.1f}h old (may be from previous run)'
                        })
                    else:
                        print(f"   ✅ Metrics recency: {age_hours:.1f}h old, from current run")

                except (ValueError, TypeError) as e:
                    # Fallback to age-only check if timestamp parsing fails
                    print(f"   ⚠️ Could not parse metrics timestamp for current-run check: {e}")
                    if age_hours > 2:
                        issues.append({
                            'check': 'metrics_stale',
                            'severity': 'warning',
                            'message': f'Metrics are {age_hours:.1f}h old (may be from previous run)'
                        })
                    else:
                        print(f"   ✅ Metrics recency: {age_hours:.1f}h old")

            # Check operation type
            operation = metrics.get('operation')
            if operation != 'discover_availability':
                issues.append({
                    'check': 'operation_type',
                    'severity': 'warning',
                    'message': f'Unexpected operation "{operation}" (expected discover_availability)'
                })

            # Check polled count
            polled = metrics.get('results', {}).get('polled', 0)
            transitions = metrics.get('results', {}).get('transitions', 0)

            if polled == 0:
                issues.append({
                    'check': 'zero_polled',
                    'severity': 'error',
                    'message': 'Discovery polled 0 movies - TMDB API may be failing'
                })
            elif polled < 100:
                issues.append({
                    'check': 'low_polled',
                    'severity': 'warning',
                    'message': f'Discovery only polled {polled} movies (expected 1000+)'
                })
            else:
                print(f"   ✅ Discovery polled: {polled} movies, {transitions} transitions")

        except json.JSONDecodeError as e:
            issues.append({
                'check': 'metrics_parse',
                'severity': 'error',
                'message': f'Failed to parse discovery metrics JSON: {e}'
            })
        except Exception as e:
            issues.append({
                'check': 'metrics_read',
                'severity': 'error',
                'message': f'Failed to read discovery metrics: {e}'
            })

        # Check intake metrics too
        if os.path.exists('metrics/intake_run.json'):
            try:
                with open('metrics/intake_run.json') as f:
                    intake = json.load(f)
                intaked = intake.get('results', {}).get('intaked', 0)
                print(f"   ✅ Intake: {intaked} new movies intaked")
            except Exception as e:
                issues.append({
                    'check': 'intake_read',
                    'severity': 'warning',
                    'message': f'Failed to read intake metrics: {e}'
                })
        else:
            issues.append({
                'check': 'intake_missing',
                'severity': 'warning',
                'message': 'intake_run.json missing - intake phase may have failed'
            })

        # Report issues
        for issue in issues:
            icon = "❌" if issue['severity'] == 'error' else "⚠️"
            print(f"   {icon} {issue['message']}")
            if issue['severity'] == 'error':
                self.failures.append({
                    'phase': 'Health Check',
                    'severity': issue['severity'],
                    'message': issue['message'],
                    'context': issue['check']
                })
            else:
                self.warnings.append({
                    'phase': 'Health Check',
                    'message': issue['message']
                })

        self.health_issues = issues

        if not issues:
            print("   ✅ All health checks passed")

    def validate_state_file(self):
        """Validate that Phase 2 created a fresh state file with today's date."""
        print("🔍 Validating enrichment state file...")
        issues = []
        today = datetime.now().strftime('%Y-%m-%d')
        state_file_path = 'metrics/newly_available.json'

        try:
            if not os.path.exists(state_file_path):
                print(f"   ⚠️ Phase 2 completed but state file is missing: {state_file_path}")
                issues.append({
                    'check': 'state_file_missing',
                    'severity': 'warning',
                    'message': f'Enrichment state file missing after Phase 2: {state_file_path}'
                })
                self.warnings.append({
                    'phase': 'Health Check',
                    'message': f'Enrichment state file missing after Phase 2: {state_file_path}'
                })
            else:
                with open(state_file_path) as f:
                    state_data = json.load(f)

                state_date = state_data.get('date')
                movie_count = state_data.get('count', 0)
                timestamp = state_data.get('timestamp')

                if state_date != today:
                    print(f"   ⚠️ Phase 2 completed but state file is stale (date={state_date}, expected={today})")
                    issues.append({
                        'check': 'state_file_stale',
                        'severity': 'warning',
                        'message': f'Enrichment state file has stale date: {state_date} (expected {today})'
                    })
                    self.warnings.append({
                        'phase': 'Health Check',
                        'message': f'Enrichment state file has stale date: {state_date} (expected {today})'
                    })
                else:
                    print(f"   ✅ State file is fresh: {movie_count} newly available movies, date={state_date}")

                # Check for timestamp/date consistency
                if timestamp and state_date:
                    try:
                        timestamp_date = timestamp.split('T')[0]  # Extract date part from ISO timestamp
                        if timestamp_date != state_date:
                            print(f"   ⚠️ State file has inconsistent date fields: date={state_date}, timestamp date={timestamp_date}")
                            issues.append({
                                'check': 'state_file_inconsistent_dates',
                                'severity': 'warning',
                                'message': f'State file date/timestamp mismatch: date={state_date}, timestamp={timestamp_date}'
                            })
                            self.warnings.append({
                                'phase': 'Health Check',
                                'message': f'State file date/timestamp mismatch: date={state_date}, timestamp={timestamp_date}'
                            })
                    except Exception as ts_error:
                        print(f"   ⚠️ Could not validate timestamp consistency: {ts_error}")

        except json.JSONDecodeError as e:
            print(f"   ❌ State file exists but is invalid JSON: {e}")
            issues.append({
                'check': 'state_file_parse',
                'severity': 'error',
                'message': f'Enrichment state file invalid JSON: {e}'
            })
            self.failures.append({
                'phase': 'Health Check',
                'severity': 'error',
                'message': f'Enrichment state file invalid JSON: {e}',
                'context': 'state_file_parse'
            })
        except Exception as e:
            print(f"   ❌ Failed to validate state file: {e}")
            issues.append({
                'check': 'state_file_read',
                'severity': 'warning',
                'message': f'Failed to validate enrichment state file: {e}'
            })
            self.warnings.append({
                'phase': 'Health Check',
                'message': f'Failed to validate enrichment state file: {e}'
            })

        # Merge issues into self.health_issues
        if not hasattr(self, 'health_issues') or self.health_issues is None:
            self.health_issues = []
        self.health_issues.extend(issues)

        return issues

    def check_for_stall(self):
        """Detect multi-day stalls - reports but never fails pipeline"""
        print("\n🔍 Checking for multi-day stalls...")

        try:
            metrics_file = 'metrics/daily.jsonl'
            if not os.path.exists(metrics_file):
                print("   ⚠️ No metrics file found - cannot detect stalls")
                return

            # Read entries from daily.jsonl
            recent_entries = []
            with open(metrics_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            recent_entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            if len(recent_entries) < 3:
                print(f"   📊 Need 3 days of data for stall detection, have {len(recent_entries)}")
                return

            # Group entries by date and select the last entry per date
            from collections import defaultdict
            entries_by_date = defaultdict(list)
            for entry in recent_entries:
                date = entry.get('date')
                if date:
                    entries_by_date[date].append(entry)

            # For each date, select the entry with the latest timestamp
            last_entry_per_date = {}
            for date, entries in entries_by_date.items():
                sorted_entries = sorted(entries, key=lambda e: e.get('timestamp', ''))
                last_entry_per_date[date] = sorted_entries[-1]

            if len(last_entry_per_date) < 3:
                print(f"   📊 Need 3 unique dates, have {len(last_entry_per_date)}")
                return

            # Get the last 3 dates (most recent first)
            sorted_dates = sorted(last_entry_per_date.keys(), reverse=True)
            last_3_dates = sorted_dates[:3]
            last_3_entries = [last_entry_per_date[date] for date in last_3_dates]

            # Check if all 3 days have transitions == 0
            stall_dates = []
            for entry in last_3_entries:
                transitions = entry.get('transitions', 0)
                date = entry.get('date')
                if transitions == 0:
                    stall_dates.append(date)

            if len(stall_dates) >= 3:
                # 3-day stall detected
                self.stall_status = {
                    'stalled': True,
                    'days': len(stall_dates),
                    'dates': sorted(stall_dates),
                    'entries': [
                        {
                            'date': e.get('date'),
                            'transitions': e.get('transitions', 0),
                            'intaked': e.get('intaked_today', 0),
                            'polled': e.get('polled', 0)
                        }
                        for e in last_3_entries
                    ]
                }

                # Add as warning (not failure - could be normal in mature system)
                self.warnings.append({
                    'phase': 'Stall Detection',
                    'message': f'3-day stall detected: no transitions since {min(stall_dates)}'
                })

                print(f"   🔴 STALL DETECTED: {len(stall_dates)} consecutive days with 0 transitions")
                print(f"   📅 Stalled dates: {', '.join(sorted(stall_dates))}")

                # Persist stall state for external monitoring
                self._persist_stall_state(stall_dates, last_3_entries)
            else:
                print(f"   ✅ No stall: {3 - len(stall_dates)}/3 recent days had transitions")
                self.stall_status = {'stalled': False, 'days_without_transitions': len(stall_dates)}

        except Exception as e:
            print(f"   ⚠️ Stall detection failed: {e}")
            self.warnings.append({
                'phase': 'Stall Detection',
                'message': f'Stall detection failed: {e}'
            })

    def _persist_stall_state(self, stall_dates, entries):
        """Persist stall detection state to metrics/stall_state.json"""
        try:
            os.makedirs('metrics', exist_ok=True)

            stall_state = {
                'timestamp': datetime.now().isoformat(),
                'stall_detected': True,
                'window_size': 3,
                'stall_dates': sorted(stall_dates),
                'entries_checked': len(entries),
                'stall_details': [
                    {
                        'date': entry.get('date'),
                        'transitions': entry.get('transitions', 0),
                        'intaked_today': entry.get('intaked_today', 0),
                        'polled': entry.get('polled', 0)
                    }
                    for entry in entries
                ]
            }

            with open('metrics/stall_state.json', 'w') as f:
                json.dump(stall_state, f, indent=2)

            print(f"   📊 Stall state saved to metrics/stall_state.json")

        except Exception as e:
            print(f"   ⚠️ Failed to persist stall state: {e}")
            self._track_error('Stall Detection', f'Failed to persist stall state: {e}', severity='warning')

    def save_run_diagnostics(self):
        """Save comprehensive diagnostics to metrics/run_diagnostics.json"""
        try:
            os.makedirs('metrics', exist_ok=True)

            diagnostics = {
                'timestamp': datetime.now().isoformat(),
                'duration_seconds': (datetime.now() - self.start_time).total_seconds(),
                'overall_success': len(self.failures) == 0,
                'failure_count': len(self.failures),
                'warning_count': len(self.warnings),

                # Phase results
                'phases': [
                    {
                        'name': r['step'],
                        'success': r['success'],
                        'duration_seconds': r['duration'].total_seconds(),
                        'error': r['error'][:1000] if not r['success'] and r.get('error') else None,
                        'output_preview': r['output'][:500] if r.get('output') else None
                    }
                    for r in self.results
                ],

                # Health check results
                'health_issues': self.health_issues,

                # Stall detection
                'stall_status': self.stall_status,

                # All failures and warnings
                'failures': self.failures,
                'warnings': self.warnings,

                # Data quality snapshot
                'data_quality': self.get_statistics(),

                # Enrichment safety metrics
                'enrichment_metrics': self._get_enrichment_metrics()
            }

            with open('metrics/run_diagnostics.json', 'w') as f:
                json.dump(diagnostics, f, indent=2)

            print(f"📊 Diagnostics saved to metrics/run_diagnostics.json")

        except Exception as e:
            print(f"⚠️ Failed to save diagnostics: {e}")
            self._track_error('Diagnostics', f'Failed to save run diagnostics: {e}', severity='warning')

    def _get_enrichment_metrics(self):
        """Read enrichment safety metrics from enrichment_run.json"""
        try:
            if os.path.exists('metrics/enrichment_run.json'):
                with open('metrics/enrichment_run.json') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to read enrichment metrics: {e}")
            self._track_error('Enrichment Metrics', f'Failed to read enrichment metrics: {e}', severity='warning')

        # Return default metrics if file doesn't exist or can't be read
        return {
            'batch_cap_triggered': None,
            'loop_timeout_triggered': None,
            'movies_processed': None,
            'movies_enriched': None,
            'enrichment_duration_seconds': None,
            'error': 'metrics file not available'
        }

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

        # State file diagnostics
        self.print_state_file_diagnostics()

        # Link source mix analysis
        link_sources = self.get_link_source_mix()
        if 'error' not in link_sources:
            print(f"\n🔗 Link Source Mix:")
            total_movies = sum(link_sources.values())
            if total_movies > 0:
                for source, count in link_sources.items():
                    pct = (count / total_movies) * 100
                    print(f"{source.replace('_', ' ').title()}: {count} ({pct:.1f}%)")

                # Log search URLs as warning (report-only)
                if link_sources['search_urls'] > 0:
                    print(f"⚠️ Warning: Found {link_sources['search_urls']} search URLs in data.json")

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

        # Failure report section
        if self.failures:
            print("\n" + "🚨" * 20)
            print("🚨 FAILURES DETECTED")
            print("🚨" * 20)
            for f in self.failures:
                print(f"❌ [{f['phase']}] {f['message']}")
                if f.get('context'):
                    # Truncate long context for display
                    context = f['context'][:200] + '...' if len(str(f['context'])) > 200 else f['context']
                    print(f"   Context: {context}")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for w in self.warnings:
                print(f"   - [{w.get('phase', 'Unknown')}] {w['message']}")

        # Stall alert
        if self.stall_status.get('stalled'):
            print("\n" + "🔴" * 20)
            print(f"🔴 STALL ALERT: {self.stall_status['days']} days with no transitions")
            print(f"🔴 Dates: {', '.join(self.stall_status['dates'])}")
            print("🔴" * 20)

        # Final status line (for easy grep in CI logs)
        print("\n" + "=" * 50)
        if self.failures:
            print(f"🔴 RUN STATUS: COMPLETED WITH {len(self.failures)} FAILURE(S)")
        elif self.warnings:
            print(f"🟡 RUN STATUS: COMPLETED WITH {len(self.warnings)} WARNING(S)")
        else:
            print(f"🟢 RUN STATUS: COMPLETED SUCCESSFULLY")
        print("=" * 50)

    def print_state_file_diagnostics(self):
        """Print state file status in the summary report"""
        state_file_path = 'metrics/newly_available.json'

        try:
            if os.path.exists(state_file_path):
                with open(state_file_path) as f:
                    state_data = json.load(f)

                date = state_data.get('date', 'unknown')
                timestamp = state_data.get('timestamp', 'unknown')
                count = state_data.get('count', 0)
                movie_ids = state_data.get('movie_ids', [])

                today = datetime.now().strftime('%Y-%m-%d')

                print(f"\n📋 State File:")
                print(f"Movies: {count}, Date: {date}, Timestamp: {timestamp}")

                # Check for discrepancies
                if date != today:
                    print(f"⚠️  State file date mismatch (expected {today})")

                # Check timestamp/date consistency
                if timestamp and timestamp.startswith(date):
                    print(f"✅ Date/timestamp consistent")
                elif timestamp and '\"' not in str(timestamp):
                    try:
                        timestamp_date = timestamp.split('T')[0]
                        if timestamp_date != date:
                            print(f"⚠️  Date/timestamp mismatch (date={date}, timestamp date={timestamp_date})")
                        else:
                            print(f"✅ Date/timestamp consistent")
                    except Exception as ts_err:
                        print(f"⚠️  Could not verify timestamp consistency: {ts_err}")
                        self._track_error('State File', f'Timestamp verification failed: {ts_err}', severity='warning')

                # Show a few movie IDs for diagnostics
                if movie_ids and len(movie_ids) > 0:
                    sample_ids = movie_ids[:3]  # Show first 3
                    sample_str = ', '.join(map(str, sample_ids))
                    if len(movie_ids) > 3:
                        sample_str += f", ... (+{len(movie_ids)-3} more)"
                    print(f"Sample IDs: {sample_str}")

            else:
                print(f"\n📋 State File: Not found ({state_file_path})")

        except json.JSONDecodeError as e:
            print(f"\n📋 State File: Invalid JSON - {e}")
            self._track_error('State File', f'Invalid JSON in state file: {e}', severity='warning')
        except Exception as e:
            print(f"\n📋 State File: Error reading - {e}")
            self._track_error('State File', f'Error reading state file: {e}', severity='warning')

    def run(self):
        """Execute the complete daily pipeline with best-effort exception handling"""
        try:
            # Acquire exclusive lock to prevent concurrent runs
            # Skip lock in CI environments (fresh container each run)
            is_ci = os.getenv('CI') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true'
            lock_file = '.nrw_orchestrator.lock'

            # PID-aware stale lock cleanup (cross-platform: works on macOS and Linux)
            if os.path.exists(lock_file):
                try:
                    with open(lock_file, 'r') as f:
                        lock_info = json.load(f)
                    pid = lock_info.get('pid')
                    if pid:
                        try:
                            os.kill(pid, 0)  # Signal 0 doesn't kill, just checks if process exists
                            print(f'❌ Active process {pid} holds lock')
                            return 1  # Hard lock conflict should fail
                        except OSError:
                            # Process doesn't exist - stale lock
                            print(f'⚠️ Removing stale lock (PID {pid} not running)')
                            os.remove(lock_file)
                    else:
                        print(f'⚠️ Removing corrupted lock (no PID)')
                        os.remove(lock_file)
                except json.JSONDecodeError:
                    print(f'⚠️ Removing corrupted lock (invalid JSON)')
                    os.remove(lock_file)
                except Exception as e:
                    print(f'⚠️ Removing lock file due to error: {e}')
                    os.remove(lock_file)

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
                 "Intake new premieres from TMDB", True, True),  # Last True indicates retry

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

            # Health checks and metrics (report-only, never fail)
            self.check_discovery_health()

            # Save consolidated daily metrics for historical tracking
            self.save_daily_metrics()

            # Check for multi-day stalls (report-only)
            self.check_for_stall()

            # Phase 3: Generate final display data with enrichment
            # NOTE: data.json uses eventual consistency model - only updated here in Phase 3
            # This means data.json may temporarily lag behind movie_tracking.json between
            # discovery (Phase 2) and final generation (Phase 3)
            print(f"\n📊 Phase 3: Data Generation")
            success = self.run_command(
                "python3 generate_data.py --enrich",
                "Enrich newly available movies with metadata",
                True
            )

            # Phase 3.5: Plex enrichment (optional - only if plex_config.json exists)
            if os.path.exists('plex_config.json'):
                self.run_command(
                    "python3 plex_enricher.py",
                    "Add Plex links for personal library",
                    critical=False  # Don't fail pipeline if Plex is unavailable
                )
            else:
                print("📝 Skipping Plex enrichment (no plex_config.json)")

            # Log data quality info (report-only, no enforcement)
            if success:
                print("\n🔍 Validating RT data...")
                self.validate_rt_data()

                print("\n🔍 Validating data quality...")
                try:
                    self.validate_data_quality()
                except Exception as e:
                    print(f"⚠️ Data quality issue: {e}")
                    self.warnings.append({
                        'phase': 'Data Quality',
                        'message': str(e)
                    })

            # Save comprehensive diagnostics for debugging
            self.save_run_diagnostics()

            # Final summary
            self.print_summary()

            # Success message
            print("\n✨ Daily update complete - diagnostics saved to metrics/run_diagnostics.json")
            return 0
        except KeyboardInterrupt:
            print("\n\n⚠️  Orchestrator interrupted by user")
            # Record the interruption as a failure
            self.failures.append({
                'phase': 'Orchestrator',
                'severity': 'error',
                'message': 'Orchestrator interrupted by user (SIGINT)',
                'context': 'KeyboardInterrupt'
            })
            try:
                self.save_run_diagnostics()
                self.print_summary()
            except Exception as diag_err:
                # If saving diagnostics fails, log WHY so we can debug later
                print(f"\n❌ Failed to save diagnostics after interruption: {diag_err}")
            return 0  # Best-effort: don't fail CI on user interruption
        except Exception as e:
            print(f"\n❌ Unexpected orchestrator error: {e}")
            # Record the unexpected exception as a failure
            self.failures.append({
                'phase': 'Orchestrator',
                'severity': 'error',
                'message': f'Unexpected exception: {e}',
                'context': str(type(e).__name__)
            })
            try:
                self.save_run_diagnostics()
                self.print_summary()
            except Exception as diag_err:
                # If saving diagnostics fails, log WHY so we can debug later
                print(f"\n❌ Failed to save diagnostics for orchestrator error: {diag_err}")
            return 0  # Best-effort: record failure but don't fail CI
        finally:
            # Always remove lock file
            lock_file = '.nrw_orchestrator.lock'
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                except Exception as lock_err:
                    print(f"⚠️  Could not remove lock file: {lock_err}")

def main():
    """Entry point - orchestrator handles all exceptions with best-effort policy"""
    orchestrator = NRWOrchestrator()
    return orchestrator.run()

if __name__ == "__main__":
    sys.exit(main())