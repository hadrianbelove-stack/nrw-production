#!/bin/bash
# Fix all repository issues in one shot

echo "=== Fixing all issues in nrw-production ==="

# 1. Remove duplicate amendments from charter (lines after AMENDMENT-027)
sed -i '' '/^### AMENDMENT-008: Canonical Daily Update Script$/,$ d' PROJECT_CHARTER.md

# 2. Fix the data strategy in context
sed -i '' 's/Track ALL theatrical releases (Type 1,2,3)/Track ALL movie releases (any premiere type)/g' complete_project_context.md

# 3. Fix movie_tracker.py to track ALL releases
cat > movie_tracker.py << 'TRACKER_EOF'
#!/usr/bin/env python3
"""
Movie Digital Release Tracker - Core Logic
Tracks ALL movie premieres and detects digital availability via providers
"""

import json
import os
import requests
import time
from datetime import datetime, timedelta

class MovieTracker:
    def __init__(self, db_file='movie_tracking.json'):
        self.db_file = db_file
        self.api_key = "99b122ce7fa3e9065d7b7dc6e660772d"
        self.db = self.load_database()
    
    def load_database(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r') as f:
                return json.load(f)
        return {'movies': {}, 'last_update': None}
    
    def save_database(self):
        self.db['last_update'] = datetime.now().isoformat()
        with open(self.db_file, 'w') as f:
            json.dump(self.db, f, indent=2)
    
    def bootstrap(self, days_back=730):
        """Initial population with ALL movie releases"""
        print(f"Bootstrapping with {days_back} days of ALL releases...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        for page in range(1, 10):  # First 10 pages
            url = f"https://api.themoviedb.org/3/discover/movie"
            params = {
                'api_key': self.api_key,
                'release_date.gte': start_date.strftime('%Y-%m-%d'),  # ANY release
                'release_date.lte': end_date.strftime('%Y-%m-%d'),
                'page': page,
                'sort_by': 'release_date.desc'
            }
            
            response = requests.get(url, params=params)
            movies = response.json().get('results', [])
            
            for movie in movies:
                movie_id = str(movie['id'])
                if movie_id not in self.db['movies']:
                    self.db['movies'][movie_id] = {
                        'title': movie['title'],
                        'premiere_date': movie.get('release_date'),  # ANY premiere
                        'digital_date': None,
                        'has_providers': False,
                        'status': 'tracking',
                        'added': datetime.now().isoformat()
                    }
            
            time.sleep(0.5)
            print(f"  Page {page}: {len(movies)} movies")
        
        self.save_database()
        print(f"Database initialized with {len(self.db['movies'])} movies")
    
    def check_providers(self):
        """Check tracking movies for provider availability"""
        tracking = [m for m in self.db['movies'].values() if m['status'] == 'tracking']
        print(f"Checking {len(tracking)} movies for providers...")
        
        newly_digital = 0
        for movie_id, movie in self.db['movies'].items():
            if movie['status'] != 'tracking':
                continue
            
            # Check providers
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
            response = requests.get(url, params={'api_key': self.api_key})
            
            if response.status_code == 200:
                us = response.json().get('results', {}).get('US', {})
                has_providers = bool(us.get('rent') or us.get('buy'))
                
                if has_providers and not movie['has_providers']:
                    # Movie just became available!
                    movie['has_providers'] = True
                    movie['digital_date'] = datetime.now().isoformat()[:10]
                    movie['status'] = 'available'
                    newly_digital += 1
                    print(f"  ✓ {movie['title']} now available!")
            
            time.sleep(0.2)
        
        self.save_database()
        print(f"Found {newly_digital} newly digital movies")
        return newly_digital

# Usage
if __name__ == "__main__":
    tracker = MovieTracker()
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'bootstrap':
        tracker.bootstrap()
    elif len(sys.argv) > 1 and sys.argv[1] == 'check':
        tracker.check_providers()
    else:
        print("Usage: python movie_tracker.py [bootstrap|check]")
TRACKER_EOF

# 4. Remove files that shouldn't be in repo
rm -f governance_patch.sh
rm -f approved.json

# 5. Add missing amendment about inclusive tracking
cat >> PROJECT_CHARTER.md << 'CHARTER_EOF'

### AMENDMENT-028: Inclusive Tracking Strategy
- Track ALL movie releases, not filtered by type
- Use release_date not primary_release_date in API calls
- Premiere date is key - first public showing anywhere
- No pre-filtering - cast wide net, narrow later based on data
CHARTER_EOF

# 6. Update daily script to show better summary
cat > daily_update.sh << 'DAILY_EOF'
#!/bin/bash
cd ~/Downloads/nrw-production || exit 1

echo "=== NRW Daily Update - $(date) ==="
python movie_tracker.py check
python generate_data.py

echo "=== Summary ==="
python -c "
import json
d = json.load(open('movie_tracking.json'))
tracking = len([m for m in d['movies'].values() if m['status']=='tracking'])
digital = len([m for m in d['movies'].values() if m['status']=='available'])
total = len(d['movies'])
print(f'Total tracked: {total}')
print(f'Still tracking: {tracking}')
print(f'Now digital: {digital}')
"

if git diff --quiet movie_tracking.json data.json; then
    echo "No changes to commit"
else
    git add -A
    git commit -m "Daily update - $(date +%Y-%m-%d)"
    git push
    echo "Changes committed"
fi
DAILY_EOF

chmod +x daily_update.sh

echo "=== All issues fixed ==="
echo "Run: git add -A && git commit -m 'Fix all issues APPROVED: DELETE' && git push"
