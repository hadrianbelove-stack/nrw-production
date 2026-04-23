---
description: Run the full daily NRW pipeline (intake → discovery → enrichment)
---

Run the full daily NRW pipeline with verification:

1. Run intake phase: `python3 generate_data.py --intake`
2. Run discovery phase: `python3 generate_data.py --discover`
3. Run enrichment phase: `python3 generate_data.py --enrich`
4. Run health check: `python3 ops/health_check.py`

After each phase, report:
- Intake: how many new movies added to tracking
- Discovery: how many movies transitioned to available
- Enrichment: how many movies enriched with metadata

If health check passes, suggest a commit message in format:
"Daily NRW Update - YYYY-MM-DD, new_arrivals=N"

If any phase fails, STOP and report the error. Do not continue to next phase.
