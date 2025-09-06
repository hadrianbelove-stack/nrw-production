#!/bin/bash

# Enable error handling
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="/Users/hadrianbelove/Downloads/new-release-wall"
cd "$BASE_DIR"

# Activate virtual environment
source .venv/bin/activate

# Function to show menu
show_menu() {
    clear
    echo "===================================="
    echo "      NEW RELEASE WALL             "
    echo "===================================="
    echo ""
    echo "1) Update & Open Site"
    echo "2) Open Admin/Curation Interface"
    echo "3) Database Inspector"
    echo "4) Stop Server"
    echo "5) Exit"
    echo ""
    echo -n "Choose (1-5): "
}

# Function to update and open
update_and_open() {
    echo -e "${GREEN}🎬 Updating releases...${NC}"
    
    # Update tracking database
    python3 movie_tracker.py update
    
    # Check for new digital releases
    python3 movie_tracker.py check
    
    # Generate output for last 14 days
    python3 generate_from_tracker.py 14
    
    echo -e "${GREEN}✓ Update complete${NC}"
    
    # Start server and open
    start_server
}

# Function to open admin interface
open_admin() {
    echo -e "${YELLOW}🎭 Starting admin interface...${NC}"
    
    # Check if curator_admin.py exists
    if [ -f "curator_admin.py" ]; then
        # Kill any existing Flask servers
        pkill -f "curator_admin.py" 2>/dev/null || true
        
        # Start Flask admin server
        python3 curator_admin.py &
        ADMIN_PID=$!
        
        sleep 2
        open http://localhost:5000
        
        echo -e "${GREEN}✓ Admin running at http://localhost:5000${NC}"
        echo "Admin PID: $ADMIN_PID"
    else
        echo -e "${RED}Admin interface not yet built${NC}"
        echo "Would show: Grid of candidates with ✓/✗/⭐ buttons for curation"
    fi
}

# Function to inspect database
inspect_database() {
    clear
    echo -e "${YELLOW}📊 DATABASE INSPECTOR${NC}"
    echo "===================================="
    
    python3 -c "
import json
from datetime import datetime, timedelta

# Load tracking database
with open('movie_tracking.json', 'r') as f:
    db = json.load(f)

# Basic stats
total = len(db.get('movies', {}))
resolved = len([m for m in db['movies'].values() if m.get('digital_date')])
tracking = total - resolved

print(f'\n📈 OVERVIEW:')
print(f'  Total movies tracked: {total}')
print(f'  Went digital: {resolved}')
print(f'  Still tracking: {tracking}')

# Recent transitions
print(f'\n🆕 RECENT DIGITAL TRANSITIONS:')
recent = sorted(
    [(k, v) for k, v in db['movies'].items() if v.get('digital_date')],
    key=lambda x: x[1].get('digital_date', ''),
    reverse=True
)[:10]

for movie_id, movie in recent:
    title = movie.get('title', 'Unknown')
    date = movie.get('digital_date', 'Unknown')
    providers = ', '.join(movie.get('providers', [])[:3]) or 'Unknown'
    print(f'  • {title} → {date} ({providers})')

# Movies we're watching (sample)
print(f'\n👀 CURRENTLY TRACKING (sample):')
watching = [(k, v) for k, v in db['movies'].items() if not v.get('digital_date')][:10]
for movie_id, movie in watching:
    title = movie.get('title', 'Unknown')
    release = movie.get('release_date', 'Unknown')[:10]
    days_old = (datetime.now() - datetime.strptime(release, '%Y-%m-%d')).days if release != 'Unknown' else 0
    print(f'  • {title} ({release}) - {days_old} days old')

# Potential zombies (old movies still not digital)
print(f'\n🧟 POTENTIAL ZOMBIES (>180 days, no digital):')
zombies = []
for movie_id, movie in db['movies'].items():
    if not movie.get('digital_date') and movie.get('release_date'):
        try:
            release_date = datetime.strptime(movie['release_date'][:10], '%Y-%m-%d')
            days_old = (datetime.now() - release_date).days
            if days_old > 180:
                zombies.append((movie.get('title'), days_old))
        except:
            pass

zombies.sort(key=lambda x: x[1], reverse=True)
for title, days in zombies[:5]:
    print(f'  • {title} - {days} days old')

# Missing popular films check
print(f'\n❓ QUICK CHECK - Are we tracking these?')
check_titles = ['Superman', 'Smurfs', 'Mission: Impossible', 'Red Sonja']
for check in check_titles:
    found = any(check.lower() in m.get('title', '').lower() for m in db['movies'].values())
    status = '✓' if found else '✗'
    print(f'  {status} {check}')
"
    
    echo ""
    echo "Press Enter to return to menu..."
    read
}

# Function to start server
start_server() {
    echo -e "${GREEN}🌐 Starting web server...${NC}"
    
    # Kill any existing Python servers
    pkill -f "python -m http.server" 2>/dev/null || true
    
    # Start server in background
    cd output/site
    python -m http.server 8000 &
    SERVER_PID=$!
    cd ../..
    
    # Open in browser
    sleep 1
    open http://localhost:8000
    
    echo -e "${GREEN}✓ Server running at http://localhost:8000${NC}"
    echo "Server PID: $SERVER_PID"
}

# Check if tracking database needs bootstrap on first run
if [ ! -f "movie_tracking.json" ] || [ $(python3 -c "import json; db=json.load(open('movie_tracking.json')); print(len(db.get('movies', {})))") -lt 100 ]; then
    echo -e "${YELLOW}⚠️  Initializing tracking database...${NC}"
    python3 movie_tracker.py bootstrap 730
    echo -e "${GREEN}✓ Database initialized${NC}"
    sleep 2
fi

# Main loop
while true; do
    show_menu
    read choice
    
    case $choice in
        1)
            update_and_open
            ;;
        2)
            open_admin
            ;;
        3)
            inspect_database
            ;;
        4)
            echo -e "${YELLOW}Stopping servers...${NC}"
            pkill -f "python -m http.server" 2>/dev/null || true
            pkill -f "curator_admin.py" 2>/dev/null || true
            echo -e "${GREEN}✓ Servers stopped${NC}"
            ;;
        5)
            echo -e "${GREEN}Goodbye!${NC}"
            pkill -f "python -m http.server" 2>/dev/null || true
            pkill -f "curator_admin.py" 2>/dev/null || true
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            sleep 1
            ;;
    esac
    
    if [ "$choice" != "5" ] && [ "$choice" != "3" ]; then
        echo ""
        echo "Press Enter to return..."
        read
    fi
done