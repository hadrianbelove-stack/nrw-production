#!/bin/bash
# Comprehensive governance and consistency patch for NRW
set -e

echo "=== Applying consolidated governance updates ==="

# 1. Fix PROJECT_CHARTER.md - Add missing amendments
cat >> PROJECT_CHARTER.md << 'CHARTER_EOF'

### AMENDMENT-008: Canonical Daily Update Script
- `daily_update.sh` is the binding daily workflow
- Executes: check → generate → summary → git commit
- Run manually or via cron until GitHub Actions restored
- Located in repo root, not Downloads folder

### AMENDMENT-026: Repository Migration Record
- Migrated from new-release-wall to nrw-production on 2025-09-05
- Due to GitHub Actions account flag on original repo
- All future work in nrw-production repository
- GitHub support ticket filed for account reinstatement

### AMENDMENT-027: Bootstrap Data Integrity
- Bootstrap movies (discovered already-digital) marked with bootstrap_digital flag
- Only show movies caught transitioning in real-time for pure tracking
- Filter option in generate_data.py to exclude bootstrap batch
- Integrity over appearance: no fake dates
CHARTER_EOF

# 2. Update complete_project_context.md
cat > complete_project_context.md << 'CONTEXT_EOF'
# NRW - Current State (2025-09-06)

## Purpose
A "Blockbuster Wall for the streaming age." Reverse-chronological display of digital releases.

## Current Implementation
- **Repository:** nrw-production (migrated from new-release-wall on 2025-09-05)
- `index.html` → loads `assets/styles.css` + `assets/app.js`
- `data.json` → Movie database (30 movies displayed, 107 available, 73 tracking)
- Display works: date dividers, flip cards, Watch buttons
- **Issue:** All 107 bootstrap movies show Sept 5 (discovery date, not actual digital date)

## Data Pipeline Status
- `movie_tracker.py`: ✓ Working - tracks 180 movies total
- `generate_data.py`: ✓ Working - generates display from tracking
- `daily_update.sh`: ✓ Created - canonical update script
- **GitHub Actions:** ❌ Blocked - account flagged, support ticket filed

## Data Strategy (Learned from Museum)
1. Track ALL theatrical releases (Type 1,2,3)
2. Check daily for provider availability
3. First day with providers = actual digital release date
4. This catches movies that never get Type 4 flag

## Current Data State
- **Total tracked:** 180 movies
- **Already digital:** 107 (marked Sept 5 - bootstrap issue)
- **Still tracking:** 73 (waiting for providers)
- **Display limit:** 30 most recent

## Known Issues
1. **Bootstrap movies:** All show Sept 5 (when discovered, not when went digital)
2. **GitHub Actions:** Account flagged, using local automation
3. **Design issues:** Date markers small, no hover states, grid alignment

## Automation Status
- **Local:** cron job for daily checks
- **GitHub:** Awaiting account reinstatement
- **Script:** daily_update.sh runs check → generate → commit

## API Credentials
### TMDB (The Movie Database)
- **API Key:** 99b122ce7fa3e9065d7b7dc6e660772d
- **Read Access Token:** [token preserved as-is]

### OMDb API  
- **API Key:** 539723d9

## Next Steps
1. Wait for GitHub reinstatement
2. Fix design issues with current data
3. Consider filtering bootstrap movies or accepting clustered dates
4. Daily checks will gradually improve data quality
CONTEXT_EOF

# 3. Fix daily_update.sh with correct path and full workflow
cat > daily_update.sh << 'SCRIPT_EOF'
#!/bin/bash
# Daily Update Script - Canonical workflow for NRW updates

# Navigate to correct repository location
cd ~/Downloads/nrw-production || exit 1

echo "=== NRW Daily Update - $(date) ==="

# Step 1: Check for new digital releases
echo "Checking for new digital releases..."
python movie_tracker.py check

# Step 2: Generate display data
echo "Generating data.json..."
python generate_data.py

# Step 3: Show summary
echo "=== Summary ==="
python -c "
import json
d = json.load(open('movie_tracking.json'))
tracking = len([m for m in d['movies'].values() if m['status']=='tracking'])
digital = len([m for m in d['movies'].values() if m['status']=='available'])
today = len([m for m in d['movies'].values() if m.get('digital_date')=='$(date +%Y-%m-%d)'])
bootstrap = len([m for m in d['movies'].values() if m.get('digital_date')=='2025-09-05'])
print(f'Tracking: {tracking} movies')
print(f'Digital: {digital} movies')
print(f'New today: {today} movies')
print(f'Bootstrap batch: {bootstrap} movies')
"

# Step 4: Git commit if changes
if git diff --quiet movie_tracking.json data.json; then
    echo "No changes to commit"
else
    git add movie_tracking.json data.json
    git commit -m "Daily update - $(date +%Y-%m-%d)"
    git push
    echo "Changes committed and pushed"
fi

echo "=== Update complete ==="
SCRIPT_EOF

chmod +x daily_update.sh

# 4. Update PROJECT_LOG.md with current session
cat >> PROJECT_LOG.md << 'LOG_EOF'

## 2025-09-06 - Repository Migration & Bootstrap

### Major Changes
- **Repository Migration:** Moved from new-release-wall to nrw-production
- **GitHub Actions Issue:** Account flagged, preventing workflow execution
- **Bootstrap Complete:** 180 movies tracked, 107 marked digital on discovery
- **Support Ticket:** Filed for GitHub account reinstatement

### Data Pipeline Status
- movie_tracker.py: Functional, tracking 180 movies
- generate_data.py: Functional, showing 30 most recent
- daily_update.sh: Created with canonical workflow
- GitHub Actions: Blocked pending reinstatement

### Issues Identified
- All bootstrap movies show Sept 5 (discovery date, not digital date)
- No way to retroactively determine actual digital dates
- GitHub Actions blocked at account level
- Design issues: small date markers, no hover states

### Amendments Added
- AMENDMENT-025: Database Update Cadence
- AMENDMENT-026: Repository Migration Record  
- AMENDMENT-027: Bootstrap Data Integrity
- AMENDMENT-008: Canonical Daily Update Script

### Next Session Focus
- Await GitHub reinstatement decision
- Fix design issues with current data
- Implement bootstrap movie filtering if needed
LOG_EOF

# 5. Add option to generate_data.py to filter bootstrap movies
cat >> generate_data.py << 'GENDATA_EOF'

# Add this function after imports
def filter_bootstrap_movies(movies_dict, cutoff_date='2025-09-05'):
    """Option to exclude movies discovered during bootstrap"""
    bootstrap_count = len([m for m in movies_dict.values() 
                          if m.get('digital_date') == cutoff_date])
    
    # If more than 50 movies on same date, likely bootstrap batch
    if bootstrap_count > 50:
        print(f"Filtering {bootstrap_count} bootstrap movies from {cutoff_date}")
        return {k: v for k, v in movies_dict.items() 
                if v.get('digital_date') != cutoff_date}
    return movies_dict

# To use: uncomment this line after loading db
# db['movies'] = filter_bootstrap_movies(db['movies'])
GENDATA_EOF

echo "=== Governance patch complete ==="
echo "Files updated:"
echo "  ✓ PROJECT_CHARTER.md (3 missing amendments)"
echo "  ✓ complete_project_context.md (current state)"
echo "  ✓ daily_update.sh (correct path and workflow)"
echo "  ✓ PROJECT_LOG.md (current session)"
echo "  ✓ generate_data.py (bootstrap filter option)"
echo ""
echo "Run: git add -A && git commit -m 'Governance update APPROVED: CONTEXT-EDIT' && git push"
