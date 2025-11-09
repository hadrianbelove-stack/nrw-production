# Legacy: Automation Branch Workflow (Deprecated)

> **⚠️ DEPRECATED**: This workflow has been replaced by a single-branch strategy as of November 2025. This document is kept for historical reference only.

## Overview
The NRW automation system previously used a **two-branch workflow** to separate automated commits from the main codebase. This system has been deprecated in favor of a simpler single-branch approach with admin approval gates.

## Current System
The current system uses:
- Single `main` branch for all commits
- Draft generation instead of direct data.json commits
- Admin approval gates for quality control
- Direct commits to main after admin approval

## Historical Two-Branch Architecture

```
main (protected)
  ↑
  | (manual merge after review)
  |
automation-updates (automated commits) [DEPRECATED]
```

### Main Branch
- **Purpose**: Production-ready code
- **Commits**: Manual commits only (features, fixes, docs)
- **Status**: Protected, always deployable
- **Merges From**: automation-updates (after review) [NO LONGER USED]

### Automation-Updates Branch [DEPRECATED]
- **Purpose**: Automated data updates
- **Commits**: Daily/weekly data.json updates
- **Status**: Force-pushed regularly
- **Merges To**: main (manually, after review)

## How It Worked (Historical)

### 1. Daily NRW Update Workflow

The automation would:
1. **Checkout automation-updates branch**
2. **Sync with main** (merge origin/main)
3. **Run discovery pipeline**
4. **Generate updated data.json**
5. **Commit and force-push**
6. **Create PR to main**

### 2. Manual Review Process

Admin would:
1. **Review automation PR**
2. **Check data quality**
3. **Merge to main if acceptable**
4. **Site updates automatically**

## Why It Was Deprecated

**Problems with two-branch system:**
- Branch synchronization complexity
- Risk of automation running on stale code
- 2+ hour runtime failures when branches diverged
- Merge conflicts and manual intervention required

**Current solution:**
- Single-branch workflow with draft system
- Admin approval happens before data.json updates
- No branch synchronization issues
- Consistent performance and reliability

## Migration to Single-Branch

The transition happened in November 2025:
1. Disabled automation-updates branch
2. Implemented draft generation system
3. Added admin approval gates
4. Direct commits to main after approval

For current workflow documentation, see [NRW_FULL_WORKFLOW.md](../NRW_FULL_WORKFLOW.md).