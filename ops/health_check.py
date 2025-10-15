#!/usr/bin/env python3
"""Health check for NRW system"""

import json
import os
from datetime import datetime, timedelta

def check_system_health():
    issues = []
    
    # Check tracking database exists and is recent
    if not os.path.exists('movie_tracking.json'):
        issues.append("❌ No tracking database found")
    else:
        with open('movie_tracking.json', 'r') as f:
            db = json.load(f)
            last_update = datetime.fromisoformat(db.get('last_update', '2000-01-01'))
            if (datetime.now() - last_update).days > 2:
                issues.append(f"⚠️ Database stale: last updated {last_update}")
    
    # Check data.json exists and has content
    if not os.path.exists('data.json'):
        issues.append("❌ No display data found")
    else:
        with open('data.json', 'r') as f:
            data = json.load(f)
            if len(data.get('movies', [])) < 10:
                issues.append(f"⚠️ Only {len(data['movies'])} movies in display")
    
    # Check cache directory
    if not os.path.exists('cache'):
        issues.append("❌ Cache directory missing")
    
    if issues:
        print("System Health Issues:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("✅ System healthy")
        return True

if __name__ == "__main__":
    check_system_health()