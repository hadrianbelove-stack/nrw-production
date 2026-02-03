# Phased Verification Checklist

## Stage 1: Audit & Planning Verification
- [ ] Code audit complete for core files (generate_data.py, scrapers, admin.py)
- [ ] Restoration blueprint created and reviewed
- [ ] Keep/restore/rebuild decisions documented
- [ ] Baseline metrics captured (runtime, coverage, API calls)
- [ ] Full system backup created
- [ ] Stage 1 plan approved

## Stage 2: Core Architecture Verification
- [ ] generate_data.py restored to Oct 19 structure with Nov 5 fixes integrated
- [ ] Enrichment-on-transition validated (processes 5-10 movies, no corruption)
- [ ] PlaywrightManager singleton confirmed across all scrapers
- [ ] Discovery & monitoring bugs fixed (digital_date handling)
- [ ] Local pipeline test: discovery → check → generation (<30s runtime)
- [ ] No event loop conflicts in scrapers
- [ ] Stage 2 complete, ready for automation

## Stage 3: Automation & Validation Verification
- [ ] Single-branch workflow implemented in daily-check.yml
- [ ] Validation policy per SYSTEM_ARCHITECTURE.md §6.5
- [ ] Optional admin review mode tested (local and CI)
- [ ] Ephemeral artifacts policy enforced
- [ ] Full orchestrator run successful (report-only validation)
- [ ] GitHub Actions manual trigger passes
- [ ] Stage 3 complete, automation ready

## Stage 4: Documentation & Testing Verification
- [ ] All MD files updated and consistent
- [ ] Troubleshooting consolidated in TROUBLESHOOTING.md
- [ ] Admin workflow docs match implementation
- [ ] Full test suite: unit (scrapers), integration (pipeline), E2E (orchestrator)
- [ ] Performance benchmarks met (30s daily, <5min full)
- [ ] Watch links coverage >50%
- [ ] First automated run monitored successfully
- [ ] Lessons learned documented in diary
- [ ] Project fully restored and operational

## General Testing Guidelines
- Run tests in isolation per stage
- Use --test mode where available
- Capture logs and metrics for each test
- Verify no regressions from golden state
- Document any deviations in diary/YYYY-MM-DD.md or create GitHub issue