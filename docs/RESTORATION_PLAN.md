# Restoration Plan

## Phased Restoration Strategy

### Philosophy
**Selective restoration, not full rollback**: Keep the good fixes from Nov 5-8 (branch sync, validation resilience, data rebuild) while restoring the clean architecture from Oct 19-20.

### Four-Stage Phased Approach

**Stage 1: Audit & Planning (Preparation)**
- Conduct comprehensive code audit comparing Oct 19 baseline vs current state
- Create detailed restoration blueprint identifying keep/restore/rebuild components
- Develop verification checklist and success criteria
- Set up baseline metrics and backups
- Duration: 1-2 days

**Stage 2: Core Architecture Restoration (Foundation)**
- Restore clean generate_data.py structure from Oct 19 baseline
- Verify enrichment-on-transition pattern integrity
- Ensure PlaywrightManager used consistently across all scrapers
- Fix discovery and monitoring bugs while preserving Nov 5 fixes
- Test core pipeline locally (discovery → enrichment → generation)
- Duration: 2-3 days

**Stage 3: Automation & Validation Cleanup (Integration)**
- Simplify to single-branch workflow (as README claims)
- Keep validation resilience but remove over-engineering
- Restore clean GitHub Actions workflow from Oct 20 with Nov 5 enhancements
- Clarify admin artifacts ephemeral policy
- Implement and test full orchestrator workflow locally and in CI
- Duration: 2-3 days

**Stage 4: Documentation & Testing (Polish & Verification)**
- Consolidate troubleshooting documentation
- Update all MD files to reflect actual system state
- Execute full verification checklist
- Create comprehensive testing suite (unit, integration, end-to-end)
- Document final system state and lessons learned
- Deploy and monitor first automated run
- Duration: 2-3 days

### Implementation Guidelines
- Each stage builds on the previous with clear entry/exit criteria
- Daily standups with progress reporting
- Rollback points at end of each stage
- Parallel work where possible (e.g., documentation during testing)
- Focus on one stage at a time to avoid overwhelm

### Automated Restoration Script
A scripted restoration flow is available in `ops/restore_baseline.sh`:
- Checks out main branch and creates a new restore branch
- Hard resets to the golden commit (ea10669 - Oct 19 baseline)
- Cherry-picks safe commits in documented order
- Runs verification checks and prepares for PR creation
- Usage: `./ops/restore_baseline.sh [--dry-run]`

## Executive Summary

**Project excellent on Oct 19-20, decayed Oct 25-Nov 5, recovered Nov 5-8 with some over-engineering**

Goal: Selective restoration preserving good fixes while cleaning architecture
Four stages: Audit/Planning → Core Restoration → Automation Cleanup → Documentation/Testing

## Stage 1 Details (Current Focus)

**Audit Components**: Compare generate_data.py (Oct 19 vs now), scrapers, admin.py, workflows

**Keep List**: Nov 5-8 fixes (branch sync, 7-day freshness check with 3-day stall detection per SYSTEM_ARCHITECTURE.md §6.5, data rebuild, discovery digital_date)

**Restore List**: Oct 19 clean structures (enrichment-on-transition, Playwright patterns, admin QA)

**Rebuild List**: Over-engineered validation, branch strategy confusion, doc sprawl

**Deliverables**: Detailed blueprint, verification checklist, baseline metrics

**Success Criteria**: Audit complete, plan approved, backups created

## Stage 2 Preview
- Focus: generate_data.py, playwright_manager.py, scrapers
- Goal: Clean core pipeline with verified integrations

## Stage 3 Preview
- Focus: daily_orchestrator.py, GitHub workflows, admin artifacts
- Goal: Simplified single-branch automation

## Stage 4 Preview
- Focus: All MD files, testing suite, final verification
- Goal: Documented, tested, deployable system

## Risks & Mitigations
- Scope creep: Strict stage gates
- Integration issues: Local testing per stage
- Time overruns: Daily progress checks