#!/bin/bash
#
# Simulation script for testing admin approval gate scenarios
#
# Usage: ./ops/simulate_scenarios.sh <scenario>
#
# Scenarios:
#   low-coverage    - Inject low link coverage by nulling watch_links
#   missing-approval - Remove approval file to test orchestrator waiting
#   stale-approval  - Create approval with old timestamp
#   dry-run        - Run orchestrator with validation only
#
# See docs/troubleshooting/admin_diagnostics.md for usage guide
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 <scenario>"
    echo ""
    echo "Available scenarios:"
    echo "  low-coverage     - Test low watch links coverage validation"
    echo "  missing-approval - Test missing approval.json behavior"
    echo "  stale-approval   - Test stale approval timestamp validation"
    echo "  dry-run         - Run orchestrator validation without changes"
    echo "  restore         - Restore original data.json backup"
    echo ""
    echo "Examples:"
    echo "  $0 low-coverage"
    echo "  $0 missing-approval"
    echo "  $0 restore"
    echo ""
    echo "For detailed usage: see docs/troubleshooting/admin_diagnostics.md"
    exit 1
}

log() {
    echo -e "${BLUE}[SIMULATE]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check if we're in the project root
check_project_root() {
    if [[ ! -f "$PROJECT_ROOT/data.json" ]] || [[ ! -f "$PROJECT_ROOT/daily_orchestrator.py" ]]; then
        error "Must be run from NRW project root directory"
    fi
}

# Create backup of original data.json
backup_data() {
    if [[ -f "$PROJECT_ROOT/data.json" ]] && [[ ! -f "$PROJECT_ROOT/data.json.sim_backup" ]]; then
        log "Creating backup of original data.json"
        cp "$PROJECT_ROOT/data.json" "$PROJECT_ROOT/data.json.sim_backup"
    fi
}

# Restore original data.json
restore_data() {
    if [[ -f "$PROJECT_ROOT/data.json.sim_backup" ]]; then
        log "Restoring original data.json from backup"
        cp "$PROJECT_ROOT/data.json.sim_backup" "$PROJECT_ROOT/data.json"
        rm "$PROJECT_ROOT/data.json.sim_backup"
        success "Original data.json restored"
    else
        warning "No backup found to restore"
    fi
}

# Simulate low coverage scenario
simulate_low_coverage() {
    log "Simulating low watch links coverage scenario"
    backup_data

    # Create a modified version of data.json with nulled watch_links
    python3 -c "
import json

# Load current data
with open('data.json', 'r') as f:
    data = json.load(f)

movies = data.get('movies', [])
modified_count = 0

# Null watch_links for 80% of movies to trigger low coverage
for i, movie in enumerate(movies):
    if i % 5 != 0:  # Keep every 5th movie's links
        if 'watch_links' in movie:
            movie['watch_links'] = {}
            modified_count += 1
        if 'providers' in movie:
            movie['providers'] = {}

print(f'Modified {modified_count} movies to have no watch links')

# Save modified data
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)
"

    success "Low coverage scenario prepared"
    warning "data.json modified - run '$0 restore' to restore original"
    echo ""
    echo "Next steps:"
    echo "1. Run: python3 daily_orchestrator.py"
    echo "2. Observe validation failure due to low coverage"
    echo "3. Run: $0 restore"
}

# Simulate missing approval scenario
simulate_missing_approval() {
    log "Simulating missing approval scenario"

    # Remove approval file if it exists
    if [[ -f "$PROJECT_ROOT/admin/approval.json" ]]; then
        if [[ ! -f "$PROJECT_ROOT/admin/approval.json.sim_backup" ]]; then
            log "Backing up existing approval.json"
            cp "$PROJECT_ROOT/admin/approval.json" "$PROJECT_ROOT/admin/approval.json.sim_backup"
        fi
        rm "$PROJECT_ROOT/admin/approval.json"
    fi

    success "Missing approval scenario prepared"
    warning "admin/approval.json removed (if existed)"
    echo ""
    echo "Next steps:"
    echo "1. Run: python3 daily_orchestrator.py"
    echo "2. Observe approval waiting behavior"
    echo "3. In another terminal: python3 admin.py --full-review"
    echo "4. Approve changes to continue"
}

# Simulate stale approval scenario
simulate_stale_approval() {
    log "Simulating stale approval scenario"

    # Create approval with old timestamp (4 hours ago)
    mkdir -p "$PROJECT_ROOT/admin"

    # Backup existing approval if present
    if [[ -f "$PROJECT_ROOT/admin/approval.json" ]] && [[ ! -f "$PROJECT_ROOT/admin/approval.json.sim_backup" ]]; then
        log "Backing up existing approval.json"
        cp "$PROJECT_ROOT/admin/approval.json" "$PROJECT_ROOT/admin/approval.json.sim_backup"
    fi

    # Create stale approval (4 hours ago)
    python3 -c "
import json
from datetime import datetime, timezone, timedelta

stale_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=4)
approval = {
    'timestamp': stale_time.isoformat().replace('+00:00', 'Z'),
    'reviewer': 'simulation-test',
    'tracking_digest': 'simulation-digest',
    'delta': {
        'edits': 0,
        'additions': 0,
        'hidden': 0,
        'featured': 0,
        'ordered': 0,
        'movies_reviewed': 0,
        'issues': {}
    }
}

with open('admin/approval.json', 'w') as f:
    json.dump(approval, f, indent=2)

print(f'Created stale approval dated: {stale_time.isoformat()}Z')
"

    success "Stale approval scenario prepared"
    warning "admin/approval.json created with 4-hour-old timestamp"
    echo ""
    echo "Next steps:"
    echo "1. Run: python3 daily_orchestrator.py"
    echo "2. Observe approval validation failure due to staleness"
    echo "3. Create fresh approval to continue"
}

# Run orchestrator in dry-run mode
simulate_dry_run() {
    log "Running orchestrator validation (dry-run mode)"
    warning "This will run actual validation but not commit changes"
    echo ""

    # Set environment variable to indicate dry run
    export NRW_DRY_RUN=1

    log "Starting daily_orchestrator.py..."
    if python3 "$PROJECT_ROOT/daily_orchestrator.py"; then
        success "Orchestrator validation completed successfully"
    else
        error "Orchestrator validation failed - check output above"
    fi
}

# Restore all simulation artifacts
restore_all() {
    log "Restoring all simulation artifacts"

    # Restore data.json
    if [[ -f "$PROJECT_ROOT/data.json.sim_backup" ]]; then
        log "Restoring data.json"
        cp "$PROJECT_ROOT/data.json.sim_backup" "$PROJECT_ROOT/data.json"
        rm "$PROJECT_ROOT/data.json.sim_backup"
    fi

    # Restore approval.json
    if [[ -f "$PROJECT_ROOT/admin/approval.json.sim_backup" ]]; then
        log "Restoring admin/approval.json"
        cp "$PROJECT_ROOT/admin/approval.json.sim_backup" "$PROJECT_ROOT/admin/approval.json"
        rm "$PROJECT_ROOT/admin/approval.json.sim_backup"
    elif [[ -f "$PROJECT_ROOT/admin/approval.json" ]]; then
        # Remove simulation-created approval
        if grep -q "simulation-test" "$PROJECT_ROOT/admin/approval.json" 2>/dev/null; then
            log "Removing simulation-created approval.json"
            rm "$PROJECT_ROOT/admin/approval.json"
        fi
    fi

    success "All simulation artifacts restored"
}

# Main execution
main() {
    if [[ $# -eq 0 ]]; then
        usage
    fi

    check_project_root
    cd "$PROJECT_ROOT"

    scenario="$1"

    case "$scenario" in
        "low-coverage")
            simulate_low_coverage
            ;;
        "missing-approval")
            simulate_missing_approval
            ;;
        "stale-approval")
            simulate_stale_approval
            ;;
        "dry-run")
            simulate_dry_run
            ;;
        "restore")
            restore_all
            ;;
        *)
            error "Unknown scenario: $scenario"
            usage
            ;;
    esac
}

# Run main function
main "$@"