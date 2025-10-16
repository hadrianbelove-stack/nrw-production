# DEPRECATED: complete_project_context.md

**Date of deprecation:** 2025-10-15
**Superseded by:** Rolling Daily Context System (AMENDMENT-036)

---

## ⚠️ This file has been deprecated

This document has been superseded by the **rolling daily context system** established in [AMENDMENT-036](PROJECT_CHARTER.md#amendment-036-rolling-daily-context). The old approach led to stale documents (last updated Sept 6, 2025) and wasted AI tokens loading outdated information.

## 📍 New Context Locations

### Current Session Context
- **[DAILY_CONTEXT.md](DAILY_CONTEXT.md)** - Always up-to-date, overwritten each session
- Contains: Current state, recent changes, active issues, next priorities

### Historical Archives
- **`diary/YYYY-MM-DD.md`** - Immutable end-of-session snapshots
- Created automatically when archiving daily context

### Full Historical Archive
- **[museum_legacy/complete_project_context.md](museum_legacy/complete_project_context.md)** - Last version before deprecation

## 🚀 Session Start Instructions

**AI assistants should read these files first:**
1. **[PROJECT_CHARTER.md](PROJECT_CHARTER.md)** - Governance rules, amendments, API keys
2. **[NRW_DATA_WORKFLOW_EXPLAINED.md](NRW_DATA_WORKFLOW_EXPLAINED.md)** - Data pipeline mechanics
3. **[DAILY_CONTEXT.md](DAILY_CONTEXT.md)** - Current state and recent changes

**To start working:**
```bash
./launch_NRW.sh  # Pull latest data and start server
```

## 🔄 Why the Change?

The new rolling daily context system provides:
- **Fresh context** without stale information
- **Token efficiency** - no more loading months of PROJECT_LOG.md history
- **Audit trail** via immutable diary archives
- **Reduced confusion** by focusing on current state

## 📋 Validation Note

**AMENDMENT-021** still references this file but will be updated in a subsequent governance amendment to remove the requirement and point to the new system.

---

*For questions about this deprecation, see DAILY_CONTEXT.md or PROJECT_CHARTER.md*