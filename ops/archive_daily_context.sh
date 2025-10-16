#!/bin/bash

# Archive daily context script for NRW project
# Archives current DAILY_CONTEXT.md and creates fresh template for next session
# Part of the rolling daily context system established in AMENDMENT-036

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ Error: $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️ $1${NC}"; }
print_info() { echo -e "${BLUE}📁 $1${NC}"; }

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run    Show what would be done without making changes"
    echo "  --force      Skip overwrite confirmation"
    echo "  --help       Show this help message"
    echo ""
    echo "Archives current DAILY_CONTEXT.md to diary/YYYY-MM-DD.md and creates fresh template."
}

# Parse command line arguments
DRY_RUN=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

echo "🚀 Daily Context Archive Script"
echo "==============================="

# Validate prerequisites
echo ""
echo "📋 Validating prerequisites..."

# Check if we're in the correct directory (look for PROJECT_CHARTER.md as anchor)
if [[ ! -f "PROJECT_CHARTER.md" ]]; then
    print_error "Not in repo root. Please run from the NRW project root directory."
    echo "   Tip: Look for PROJECT_CHARTER.md to confirm you're in the right place."
    exit 1
fi

# Check if DAILY_CONTEXT.md exists
if [[ ! -f "DAILY_CONTEXT.md" ]]; then
    print_error "DAILY_CONTEXT.md not found. Are you in the repo root?"
    echo "   Expected file: ./DAILY_CONTEXT.md"
    exit 1
fi

print_success "Prerequisites validated"

# Generate timestamp
DATE=$(date +%Y-%m-%d)
echo ""
echo "📅 Archive date: $DATE"

# Create diary directory if needed
echo ""
echo "📂 Checking diary directory..."

if [[ ! -d "diary" ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
        print_info "[DRY RUN] Would create diary/ directory"
    else
        mkdir -p diary
        print_info "Created diary/ directory"
    fi
else
    print_info "diary/ directory already exists"
fi

# Check if archive already exists
ARCHIVE_PATH="diary/$DATE.md"
echo ""
echo "📦 Preparing to archive..."

if [[ -f "$ARCHIVE_PATH" ]]; then
    print_warning "Archive already exists: $ARCHIVE_PATH"
    if [[ "$FORCE" == "false" && "$DRY_RUN" == "false" ]]; then
        # Check if we're in a non-interactive environment
        if [[ ! -t 0 ]]; then
            print_error "Non-interactive environment detected and archive exists."
            echo "   Use --force to overwrite existing archive: $ARCHIVE_PATH"
            exit 1
        fi
        echo -n "Overwrite existing archive? (y/N): "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "Archive cancelled by user."
            exit 1
        fi
    elif [[ "$DRY_RUN" == "true" ]]; then
        print_info "[DRY RUN] Would overwrite existing archive"
    fi
fi

# Archive current context
if [[ "$DRY_RUN" == "true" ]]; then
    print_info "[DRY RUN] Would copy DAILY_CONTEXT.md to $ARCHIVE_PATH"
else
    if cp DAILY_CONTEXT.md "$ARCHIVE_PATH"; then
        print_success "Archived today's context to $ARCHIVE_PATH"
    else
        print_error "Failed to archive context. Check permissions."
        exit 1
    fi
fi

# Create fresh template
echo ""
echo "📄 Creating fresh template..."

if [[ "$DRY_RUN" == "true" ]]; then
    print_info "[DRY RUN] Would create fresh DAILY_CONTEXT.md template"
else
    cat > DAILY_CONTEXT.md << EOF
# DAILY_CONTEXT.md
**Date:** [YYYY-MM-DD]
**Previous diary entry:** diary/$DATE.md

---

## AI Assistant Quick Start

**READ THESE FILES FIRST WHEN STARTING A NEW SESSION:**

1. **This file (DAILY_CONTEXT.md)** - Current state, recent changes, active issues
2. **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance rules, amendments, API keys, architectural decisions
3. **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline mechanics, how everything fits together

**What is this rolling context system?**

This is a **living document** that gets overwritten each session with current information. At the end of each session, we archive it to `diary/YYYY-MM-DD.md` (immutable historical record). This approach:
- **Avoids token waste** from loading months of PROJECT_LOG.md history
- **Provides fresh context** without stale information
- **Maintains audit trail** in the diary/ folder
- **Reduces AI confusion** by keeping focus on current state

See [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context) for governance rules.

---

## Current State

### What's Working
[Fill in during session - describe operational systems and their status]

### Architecture
[Fill in during session - describe runtime components and data flow]

---

## What We Did Today ([YYYY-MM-DD])

[Fill in during session - document major changes, commits, and implementations]

---

## Conversation Context (Key Decisions)

[Fill in during session - record important decisions and their rationale]

---

## Known Issues

[Fill in during session - document current problems and their status]

---

## Next Priorities

### Immediate (This Session)
[Fill in during session - list current tasks and their completion status]

### Next Phase
[Fill in during session - list upcoming tasks for next session]

### Subsequent Phase
[Fill in during session - list future improvements]

### Short-term (Next Few Days)
[Fill in during session - list near-term tasks]

### Long-term (Ongoing)
[Fill in during session - list ongoing maintenance tasks]

---

## Archive Instructions

**End-of-session workflow (automated via `ops/archive_daily_context.sh`):**

1. Run archive script: `./ops/archive_daily_context.sh`
   - Archives current context to `diary/YYYY-MM-DD.md`
   - Creates fresh template for next session
   - Use `--dry-run` to preview changes without executing

2. **Testing:** `./ops/archive_daily_context.sh --dry-run` shows what would happen

3. **Troubleshooting:**
   - Permission error: `chmod +x ops/archive_daily_context.sh`
   - Missing file error: Ensure you're in repo root
   - Directory issues: Script creates `diary/` automatically

4. **Next session starts fresh:**
   - AI reads new DAILY_CONTEXT.md template
   - Historical context available in `diary/` if needed
   - No token waste from stale information

**Current status:** Archive script created and ready to use

---

## Files Changed Today

### Created
[Fill in during session - list new files]

### Modified
[Fill in during session - list changed files with brief descriptions]

### Archived
[Fill in during session - list files moved to museum_legacy/]

---

## Quick Reference

### Daily Workflow
```bash
# Morning: View the wall
./launch_NRW.sh

# Automation runs automatically at 9 AM UTC
# (No manual intervention needed)
```

### Manual Pipeline (if needed)
```bash
# Check for new digital releases
python3 movie_tracker.py check

# Regenerate data.json
python3 generate_data.py

# Add new theatrical releases (weekly)
python3 movie_tracker.py bootstrap
```

### Context Files (Read These First)
- **Daily:** This file (DAILY_CONTEXT.md) - Current state and recent changes
- **Governance:** [PROJECT_CHARTER.md](PROJECT_CHARTER.md) - Rules, amendments, API keys
- **Pipeline:** [NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md) - How data flows
- **History:** `diary/YYYY-MM-DD.md` - End-of-session archives (when needed)

---

**Last updated:** [End of session]
**Next diary archive:** End of session -> \`diary/[YYYY-MM-DD].md\`
EOF

    if [[ $? -eq 0 ]]; then
        print_success "Fresh template created"
    else
        print_error "Failed to create fresh template. Check disk space."
        exit 1
    fi
fi

# Summary report
echo ""
echo "🎉 Archive Complete!"
echo "==================="
echo ""
if [[ "$DRY_RUN" == "true" ]]; then
    echo "📋 DRY RUN SUMMARY:"
    echo "   📦 Would archive: DAILY_CONTEXT.md → diary/$DATE.md"
    echo "   📄 Would create: Fresh DAILY_CONTEXT.md template"
    echo ""
    echo "   Run without --dry-run to execute these changes."
else
    echo "📦 Archive created: diary/$DATE.md"
    echo "📄 Fresh template ready: DAILY_CONTEXT.md"
    echo "🚀 Next session: AI will read the new template"
    echo ""
    echo "💡 Remember: Fill in DAILY_CONTEXT.md during your next session"
    echo "💡 Next steps: Add diary/$DATE.md to git and commit with other changes"
fi

echo ""
echo "✨ Ready for next development session!"