#!/usr/bin/env python3
"""
NRW Daily Orchestrator - Coordinates all daily update tasks
"""

import subprocess
import json
import sys
import os
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

    def get_statistics(self):
        """Extract statistics from tracking database"""
        try:
            with open('movie_tracking.json', 'r') as f:
                db = json.load(f)

            movies = db.get('movies', {})
            tracking = len([m for m in movies.values() if m.get('status') == 'tracking'])
            available = len([m for m in movies.values() if m.get('status') == 'available'])
            total = len(movies)

            return {
                'total': total,
                'tracking': tracking,
                'available': available
            }
        except Exception as e:
            return {
                'total': 0,
                'tracking': 0,
                'available': 0,
                'error': str(e)
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
        
        # Pipeline steps - based on daily_update.sh
        pipeline = [
            # Phase 1: Discovery + Monitoring
            ("python3 movie_tracker.py daily",
             "Discover new premieres and check for digital availability", True),

            # Phase 2: Enrichment (DISABLED - RT scraping now automatic in generate_data.py)
            # ("python3 update_rt_data.py",
            #  "Update Rotten Tomatoes links", False),

            # Phase 3: Verification (DISABLED - date_verification.py archived to museum_legacy/)
            # ("python3 date_verification.py",
            #  "Verify premiere dates", False),

            # Phase 4: Generate final display data
            ("python3 generate_data.py",
             "Generate data.json for website", True),
        ]
        
        # Execute pipeline
        for cmd, description, critical in pipeline:
            success = self.run_command(cmd, description, critical)
            # If generate_data.py succeeded, validate RT data
            if success and "generate_data.py" in cmd:
                print("\n🔍 Validating RT data...")
                self.validate_rt_data()

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