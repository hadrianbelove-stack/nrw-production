# Tests Directory

## Overview

This directory contains two types of tests:

1. **Active Tests (2 files)** - Maintained tests that should be run before deploying changes
2. **Archived Debugging Tests (10 files)** - Historical artifacts from Oct 26-27, 2025 async fix verification

⚠️ **Important**: Archived tests may not work with current code and are not maintained. They exist for historical reference only. See individual test descriptions below for status and context.

If you need to understand test purpose and status, refer to the sections below. For current testing, focus on the Active Tests section.

## Active Tests

### test_enrichment_workflow.py
- **Purpose**: Tests the complete enrichment workflow including Wikipedia, RT, and streaming platform scraping
- **What it tests**: End-to-end data enrichment process
- **When to run**: Before deploying enrichment changes
- **Status**: ACTIVE (maintained and should be run)

### test_enrichment_workflow_simple.py
- **Purpose**: Simplified version of enrichment workflow test
- **What it tests**: Core enrichment functionality with reduced complexity
- **When to run**: Quick validation of enrichment changes
- **Status**: ACTIVE (maintained and should be run)

**Note**: These are the only maintained tests. Run these before deploying changes to enrichment workflow.

## Archived Debugging Tests

> ⚠️ **WARNING**: These are historical artifacts from Oct 26-27, 2025 async fix verification.
>
> **Context**: Created during PlaywrightManager async fix to verify scrapers worked with new async architecture.
>
> **Status**: Verification was never completed. Tests were abandoned when async fix was applied.
>
> **Should you run them?** No - they are archived, may not work with current code, and are not maintained.
>
> **If you need tests**: Write new ones based on current understanding rather than trying to fix these.

### Async Fix Verification Tests

#### test_amazon_scraper_fix.py
- **Purpose**: Test Amazon scraper fix during async fix verification (Oct 26, 2025)
- **Context**: Verify Amazon scraper works with PlaywrightManager
- **Status**: **PASSED** (2/2 tests passed)
- **Results**: "The Bitter Taste" → B0FPMV1CJ6, "Armed Only With a Camera" → B0FVHK69SH
- **Documentation**: Results documented in museum_legacy/ASYNC_FIX_SUCCESS_SUMMARY.md

#### test_rt_migration.py
- **Purpose**: Test RT scraper migration from Selenium to Playwright (Oct 26, 2025)
- **Context**: Verify RT scraper works with PlaywrightManager
- **Status**: **PASSED**
- **Documentation**: Results documented in museum_legacy/ASYNC_FIX_VERIFICATION.md

#### test_platform_scraper.py
- **Purpose**: Test streaming platform scraper (Amazon, Apple TV) during async fix
- **Context**: Standalone testing of platform scrapers
- **Status**: UNKNOWN (used for debugging, results not formally documented)

### Agent Scraper Tests

#### test_agent_scraper.py
- **Purpose**: Standalone test for agent scraper (Netflix, Disney+, HBO Max, Hulu)
- **Context**: Created during initial agent scraper development (Oct 17-21, 2025)
- **Status**: **FAILED** (0/2 tests, 100% failure due to login walls)
- **Features**: Can run in visible mode with --headless flag for debugging
- **Documentation**: Results in museum_legacy/AGENT_SCRAPER_DIAGNOSTICS.md

#### test_agent_scraper_improvements.py
- **Purpose**: Test suite for agent scraper improvements (4 platforms, 6 test cases)
- **Context**: Created to test improved agent scrapers with PlaywrightManager
- **Status**: **NEVER RUN** (verification planned but never executed)
- **Expected**: >70% pass rate (4/6 tests)
- **Documentation**: Referenced in museum_legacy/RUN_VERIFICATION_CHECKLIST.md

### Event Loop Diagnostic Tests

#### test_event_loop_detection.py
- **Purpose**: Diagnostic test to pinpoint where asyncio event loop is created
- **Context**: Created to diagnose event loop conflicts during async fix (Oct 26-27, 2025)
- **Status**: **DIAGNOSTIC COMPLETE** (identified YouTube scraper as source)
- **Outcome**: Found YouTube scraper initialized first and created initial event loop, leading to PlaywrightManager solution

#### test_eventloop_in_generate.py
- **Purpose**: Test to detect event loop conflicts in generate_data.py
- **Context**: Part of PlaywrightManager async fix debugging
- **Status**: UNKNOWN (used to identify event loop issues)

### Scraper-Specific Tests

#### test_wikipedia_scraper.py
- **Purpose**: Test Wikipedia scraper during Playwright migration
- **Context**: Part of Oct 26-27 async fix verification
- **Status**: UNKNOWN (never run or documented)

#### test_wikipedia_known_movies.py
- **Purpose**: Test Wikipedia scraper with movies known to have Wikipedia pages
- **Context**: Created during async fix verification
- **Status**: UNKNOWN (never run or documented)

#### test_rt_scraper_playwright.py
- **Purpose**: Test inlined RT scraper functionality
- **Context**: Created when RT scraping was migrated into generate_data.py (Oct 17-19, 2025)
- **Status**: UNKNOWN (isolation test, results not documented)

## Test Results Summary

| Test File | Status | Pass Rate | Notes |
|-----------|--------|-----------|-------|
| **Active Tests** |
| test_enrichment_workflow.py | ACTIVE | N/A | Maintained test |
| test_enrichment_workflow_simple.py | ACTIVE | N/A | Maintained test |
| **Archived Tests** |
| test_amazon_scraper_fix.py | PASSED | 2/2 (100%) | Results documented |
| test_rt_migration.py | PASSED | N/A | Results documented |
| test_agent_scraper.py | FAILED | 0/2 (0%) | Login walls |
| test_event_loop_detection.py | COMPLETE | N/A | Diagnostic complete |
| test_agent_scraper_improvements.py | NEVER RUN | Expected 4/6 (67%) | Verification abandoned |
| test_platform_scraper.py | UNKNOWN | N/A | Standalone testing |
| test_eventloop_in_generate.py | UNKNOWN | N/A | Debugging tool |
| test_wikipedia_scraper.py | UNKNOWN | N/A | Never documented |
| test_wikipedia_known_movies.py | UNKNOWN | N/A | Never documented |
| test_rt_scraper_playwright.py | UNKNOWN | N/A | Never documented |

## Historical Context

### Why These Tests Exist
These archived tests were created during Oct 26-27, 2025 as part of async fix verification. The async fix introduced PlaywrightManager to solve event loop conflicts that were preventing multiple scrapers from running in the same process.

### What Happened
- Some tests passed (Amazon, RT scrapers)
- Some tests failed (agent scrapers hit login walls)
- Some tests were never run (verification was abandoned)
- Event loop diagnostics completed their purpose

### Outcome
The async fix was successfully applied and is working in production. These tests were left in the root directory and are now organized in tests/ for historical reference.

## Running Tests

### Active Tests (Recommended)
```bash
# Run enrichment workflow tests
python tests/test_enrichment_workflow.py
python tests/test_enrichment_workflow_simple.py

# Or use pytest if available
pytest tests/test_enrichment_workflow.py
pytest tests/test_enrichment_workflow_simple.py
```

### Archived Tests (Not Recommended)
The archived debugging tests are not maintained and may not work with current code. If they fail, **do not fix them** - they served their historical purpose.

If you need similar functionality, write new tests based on current understanding rather than trying to resurrect these archived tests.

## Future Test Development

When adding new tests to this directory:

1. **Use standard frameworks**: pytest or unittest
2. **Test critical paths**: enrichment workflow, data validation, scraper functionality
3. **Mock external dependencies**: Use mocks for API calls and web scraping
4. **Integrate with CI**: Add tests to automated build process
5. **Document purpose**: Update this README with new test descriptions

Focus on testing the core business logic and data processing rather than external integrations that can be flaky.

## References

- **Test Results**: See museum_legacy/ASYNC_FIX_SUCCESS_SUMMARY.md for detailed results
- **Debugging History**: See diary/2025-10-*.md for development context
- **Current Architecture**: See SYSTEM_ARCHITECTURE.md for system overview
- **Agent Scraper Analysis**: See museum_legacy/AGENT_SCRAPER_DIAGNOSTICS.md
- **Verification Checklist**: See museum_legacy/RUN_VERIFICATION_CHECKLIST.md

For questions about current testing approach, refer to the Active Tests section above.