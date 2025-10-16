# DAILY_CONTEXT.md
**Date:** [YYYY-MM-DD]
**Previous diary entry:** diary/2025-10-15.md

---

## > AI Assistant Quick Start

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
**Next diary archive:** End of session ’ `diary/[YYYY-MM-DD].md`