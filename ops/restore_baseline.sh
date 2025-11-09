#!/bin/bash
# Baseline Restoration Script
#
# This script implements the restoration strategy documented in docs/RESTORATION_PLAN.md
# It checks out main, creates a restore branch, resets to golden baseline, and cherry-picks safe commits.
#
# COMMIT REFERENCE:
# Golden Baseline: ea10669 (Session end - 2025-10-19: Documentation finalization and archive)
# Safe Commits to Cherry-pick (in order):
#   1. 18f86f3 - Fix data corruption: rebuilt clean data.json
#   2. e50d793 - Comprehensive repository cleanup: Remove 1.0 GB of obsolete files
#   3. feb0b9e - Fix workflow: unique-day stall detection and approval context capture
#   4. f01d85f - Fix YAML syntax error in workflow: properly escape multi-line bash strings
#
# Usage: ./ops/restore_baseline.sh [--dry-run]

set -euo pipefail

# Configuration
GOLDEN_BASELINE="ea10669"
SAFE_COMMITS=(
    "18f86f3"  # Fix data corruption: rebuilt clean data.json
    "e50d793"  # Comprehensive repository cleanup: Remove 1.0 GB of obsolete files
    "feb0b9e"  # Fix workflow: unique-day stall detection and approval context capture
    "f01d85f"  # Fix YAML syntax error in workflow: properly escape multi-line bash strings
)
RESTORE_BRANCH="baseline-restore-$(date +%Y%m%d-%H%M%S)"

# Parse arguments
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN MODE - No changes will be made"
fi

# Helper functions
log() {
    echo "$(date '+%H:%M:%S') $1"
}

error() {
    echo "❌ ERROR: $1" >&2
    exit 1
}

run_cmd() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  [DRY RUN] $*"
    else
        eval "$@"
    fi
}

# Preflight checks
log "🔍 Running preflight checks..."

# Check we're in a git repository
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    error "Not in a git repository"
fi

# Check we have a clean working directory
if ! git diff --quiet && ! git diff --cached --quiet; then
    error "Working directory is not clean. Please commit or stash changes."
fi

# Check we're on main branch
current_branch=$(git branch --show-current)
if [[ "$current_branch" != "main" ]]; then
    log "⚠️  Currently on branch '$current_branch', switching to main..."
    run_cmd "git checkout main"
fi

# Check that golden baseline commit exists
if ! git cat-file -e "$GOLDEN_BASELINE" 2>/dev/null; then
    error "Golden baseline commit $GOLDEN_BASELINE not found"
fi

# Verify safe commits exist
for commit in "${SAFE_COMMITS[@]}"; do
    if ! git cat-file -e "$commit" 2>/dev/null; then
        error "Safe commit $commit not found"
    fi
done

log "✅ Preflight checks passed"

# Step 1: Create and switch to restore branch
log "🌿 Creating restore branch: $RESTORE_BRANCH"
run_cmd "git checkout -b $RESTORE_BRANCH"

# Step 2: Hard reset to golden baseline
log "⏪ Resetting to golden baseline: $GOLDEN_BASELINE"
if [[ "$DRY_RUN" == "false" ]]; then
    git reset --hard "$GOLDEN_BASELINE"

    # Show what the baseline looks like
    echo ""
    echo "📊 Golden Baseline State:"
    echo "Commit: $(git log --oneline -1)"
    echo "Files changed from current main: $(git diff --name-only main | wc -l)"
    echo ""
fi

# Step 3: Run baseline metrics
log "📊 Running baseline metrics..."
if [[ -f "generate_data.py" && "$DRY_RUN" == "false" ]]; then
    echo "Checking pipeline integrity..."
    # Test basic functionality without full runs
    if python3 generate_data.py --help >/dev/null 2>&1; then
        echo "✅ generate_data.py loads successfully"
    else
        echo "⚠️ Warning: generate_data.py failed to load"
    fi

    if python3 -c "from daily_orchestrator import DailyOrchestrator; print('✅ daily_orchestrator imports successfully')" 2>/dev/null; then
        echo "✅ daily_orchestrator imports successfully"
    else
        echo "⚠️ Warning: daily_orchestrator failed to import"
    fi
else
    echo "[DRY RUN] Would test baseline metrics"
fi

# Step 4: Cherry-pick safe commits in order
log "🍒 Cherry-picking safe commits..."
failed_commits=()

for i in "${!SAFE_COMMITS[@]}"; do
    commit="${SAFE_COMMITS[$i]}"
    log "Cherry-picking $((i+1))/${#SAFE_COMMITS[@]}: $commit"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  [DRY RUN] git cherry-pick $commit"
        continue
    fi

    # Show what this commit does
    echo "  $(git log --oneline -1 "$commit")"

    # Attempt cherry-pick
    if git cherry-pick "$commit" --no-edit; then
        log "  ✅ Cherry-pick successful"
    else
        log "  ❌ Cherry-pick failed for $commit"
        failed_commits+=("$commit")

        # Show conflict status
        echo "  Conflicts in:"
        git diff --name-only --diff-filter=U | sed 's/^/    /'

        # Abort the cherry-pick to continue
        git cherry-pick --abort
        log "  Aborted cherry-pick, continuing with next commit..."
    fi
done

# Step 5: Run verification
log "🔍 Running verification checks..."
if [[ "$DRY_RUN" == "false" ]]; then
    echo ""
    echo "📊 Final State Analysis:"
    echo "Current HEAD: $(git log --oneline -1)"
    echo "Commits since baseline: $(git rev-list --count "$GOLDEN_BASELINE..HEAD")"
    echo "Files different from main: $(git diff --name-only main | wc -l)"

    if [[ ${#failed_commits[@]} -eq 0 ]]; then
        echo "✅ All safe commits applied successfully"
    else
        echo "⚠️ Failed to apply commits: ${failed_commits[*]}"
        echo "These will need manual resolution"
    fi

    # Test critical paths
    echo ""
    echo "🧪 Critical Path Tests:"

    # Check if discovery contract tests pass
    if [[ -f "tests/test_discovery_contract.py" ]]; then
        echo "Running discovery contract tests..."
        if python3 -m pytest tests/test_discovery_contract.py -v --tb=short; then
            echo "✅ Discovery contract tests pass"
        else
            echo "⚠️ Discovery contract tests failed"
        fi
    fi

    # Check if data.json can be validated
    if [[ -f "data.json" ]]; then
        if python3 -c "import json; json.load(open('data.json')); print('✅ data.json is valid JSON')"; then
            echo "✅ data.json is valid JSON"
        else
            echo "⚠️ data.json validation failed"
        fi
    fi

else
    echo "[DRY RUN] Would run verification checks"
fi

# Step 6: Prepare for PR creation
log "📝 Preparing for PR creation..."
if [[ "$DRY_RUN" == "false" ]]; then
    echo ""
    echo "🎯 Next Steps:"
    echo "1. Review the restored state: git log --oneline $GOLDEN_BASELINE..HEAD"
    echo "2. Run full local tests: python3 daily_orchestrator.py"
    echo "3. Create PR: gh pr create --title 'Baseline Restoration $(date +%Y-%m-%d)'"
    echo "4. Branch ready for push: git push -u origin $RESTORE_BRANCH"
    echo ""
    echo "🔧 Manual Resolution Needed:"
    if [[ ${#failed_commits[@]} -gt 0 ]]; then
        echo "The following commits failed to cherry-pick and need manual attention:"
        for commit in "${failed_commits[@]}"; do
            echo "  - $commit: $(git log --oneline -1 "$commit")"
        done
        echo ""
        echo "To resolve manually:"
        echo "1. git cherry-pick $commit"
        echo "2. Resolve conflicts in editor"
        echo "3. git add . && git cherry-pick --continue"
        echo "4. Repeat for each failed commit"
    else
        echo "All commits applied successfully - ready for PR!"
    fi

else
    echo "[DRY RUN] Restoration completed successfully in dry-run mode"
    echo "Run without --dry-run to execute the restoration"
fi

log "🎉 Baseline restoration script completed"
echo ""
echo "📖 For more details, see docs/RESTORATION_PLAN.md and docs/VERIFICATION_CHECKLIST.md"