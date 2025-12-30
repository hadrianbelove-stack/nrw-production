# Terminology Fix Plan: "Discovered" → "Intaked" for Intake Operations

## Problem
The code incorrectly uses "discovered" for both:
1. **Intake**: Finding new premieres from TMDB to add to tracking
2. **Discovery**: Detecting transitions (tracking → available) = discovering new arrivals

## Correct Terminology
- **"Intaked"**: Movies added to tracking from TMDB premiere search
- **"Discovered"**: Movies that transitioned from tracking → available (NEW ARRIVALS)

---

## Category 1: INTAKE - MUST CHANGE to "intaked"

### pipeline/generator.py
- **Line 334**: `def save_daily_metrics(self, discovered=0, newly_digital=0):`
  - Change parameter: `discovered` → `intaked`

- **Line 353**: `'discovered': discovered,`
  - Change to: `'intaked': intaked,`

- **Line 365**: `self.logger.info(f"Daily metrics saved: {discovered} discovered, {newly_digital} newly digital")`
  - Change to: `f"Daily metrics saved: {intaked} intaked, {newly_digital} newly digital"`

- **Line 394**: `discovery_avg = sum(m['discovered'] for m in last_3) / 3`
  - Change to: `intake_avg = sum(m.get('intaked', m.get('discovered', 0)) for m in last_3) / 3`
  - Note: Include fallback for backward compatibility with old metrics

- **Line 543**: `all_discovered_movies = {}`
  - Change to: `all_intaked_movies = {}`

- **Line 552**: `all_discovered_movies, existing_ids, debug`
  - Change to: `all_intaked_movies, existing_ids, debug`

- **Line 556**: `self.logger.info(f"Pass A completed: {pass_a_count} movies discovered")`
  - Change to: `f"Pass A completed: {pass_a_count} movies intaked"`

- **Line 565**: `all_discovered_movies, existing_ids, debug`
  - Change to: `all_intaked_movies, existing_ids, debug`

- **Line 569**: `self.logger.info(f"Pass B completed: {pass_b_count} movies discovered")`
  - Change to: `f"Pass B completed: {pass_b_count} movies intaked"`

- **Line 572**: `for movie_id, movie_data in all_discovered_movies.items():`
  - Change to: `for movie_id, movie_data in all_intaked_movies.items():`

- **Line 617**: `'discovered': new_movies_added,`
  - Change to: `'intaked': new_movies_added,`

- **Line 1047**: `def _run_discovery_pass(self, pass_name, pass_type, start_date, end_date, max_pages, discovered_movies, existing_ids, debug):`
  - Change method name: `_run_discovery_pass` → `_run_intake_pass`
  - Change parameter: `discovered_movies` → `intaked_movies`

- **Line 1048**: `"""Run a single discovery pass (A or B)`
  - Change to: `"""Run a single intake pass (A or B)`

- **Line 1053**: `start_date: Discovery start date`
  - Change to: `start_date: Intake start date`

- **Line 1054**: `end_date: Discovery end date`
  - Change to: `end_date: Intake end date`

- **Line 1056**: `discovered_movies: Dict to accumulate discovered movies`
  - Change to: `intaked_movies: Dict to accumulate intaked movies`

- **Line 1061**: `Number of new movies discovered in this pass`
  - Change to: `Number of new movies intaked in this pass`

- **Line 1097**: `if movie_id in existing_ids or movie_id in discovered_movies:`
  - Change to: `if movie_id in existing_ids or movie_id in intaked_movies:`

- **Line 1103**: `discovered_movies[movie_id] = {`
  - Change to: `intaked_movies[movie_id] = {`

### generate_data.py (main script)
- **Line 86**: `discovered_count = 0`
  - Change to: `intaked_count = 0`

- **Line 89**: `discovered_count = generator.discover_new_premieres(`
  - Change to: `intaked_count = generator.intake_new_premieres(`
  - Note: Method being called must also be renamed

- **Line 94**: `print(f"✅ Intake complete: {discovered_count} new movies added")`
  - Change to: `print(f"✅ Intake complete: {intaked_count} new movies added")`

### Method name in pipeline/generator.py
- **Method**: `discover_new_premieres()` → `intake_new_premieres()`
  - Must find and rename this method definition
  - Update all calls to this method

### daily_orchestrator.py
- **Line 459**: `discovered_today = 0`
  - Change to: `intaked_today = 0`

- **Line 470**: `discovered_today = results.get('discovered', 0)`
  - Change to: `intaked_today = results.get('intaked', results.get('discovered', 0))`
  - Note: Fallback for backward compatibility

- **Line 488**: `discovered_today = discovery_data.get('results', {}).get('discovered', 0)`
  - Change to: `intaked_today = discovery_data.get('results', {}).get('intaked', discovery_data.get('results', {}).get('discovered', 0))`
  - Note: Legacy support branch

- **Line 489**: `transitions = discovered_today`
  - Change to: `transitions = intaked_today`

- **Line 497**: `'discovered_today': discovered_today,`
  - Change to: `'intaked_today': intaked_today,`

- **Line 509**: `print(f"✅ Daily metrics saved: {discovered_today} discovered, {polled} polled, {transitions} transitions")`
  - Change to: `print(f"✅ Daily metrics saved: {intaked_today} intaked, {polled} polled, {transitions} transitions")`

- **Line 648**: `discovered = intake.get('results', {}).get('discovered', 0)`
  - Change to: `intaked = intake.get('results', {}).get('intaked', intake.get('results', {}).get('discovered', 0))`
  - Note: Fallback for backward compatibility

- **Line 649**: `print(f"   ✅ Intake: {discovered} new movies discovered")`
  - Change to: `print(f"   ✅ Intake: {intaked} new movies intaked")`

- **Line 841**: `'discovered': e.get('discovered_today', 0),`
  - Change to: `'intaked': e.get('intaked_today', e.get('discovered_today', 0)),`

- **Line 885**: `'discovered_today': entry.get('discovered_today', 0),`
  - Change to: `'intaked_today': entry.get('intaked_today', entry.get('discovered_today', 0)),`

### scripts/baseline_metrics.py
- **Line 48**: `discovery_avg = sum(m.get('discovered_today', 0) for m in last_3) / 3`
  - Change to: `intake_avg = sum(m.get('intaked_today', m.get('discovered_today', 0)) for m in last_3) / 3`

- **Line 59**: `print(f"  {metric['date']}: {metric.get('discovered_today', 0)} discovered, {metric.get('transitions', 0)} newly digital")`
  - Change to: `print(f"  {metric['date']}: {metric.get('intaked_today', metric.get('discovered_today', 0))} intaked, {metric.get('transitions', 0)} transitions")`

- **Line 69**: `total_discovered = sum(m.get('discovered_today', 0) for m in recent)`
  - Change to: `total_intaked = sum(m.get('intaked_today', m.get('discovered_today', 0)) for m in recent)`

- **Line 72**: `print(f"  Total discovered: {total_discovered}")`
  - Change to: `print(f"  Total intaked: {total_intaked}")`

- **Line 74**: `print(f"  Discovery rate: {total_discovered/len(recent):.1f}/day")`
  - Change to: `print(f"  Intake rate: {total_intaked/len(recent):.1f}/day")`

---

## Category 2: TRANSITIONS - KEEP AS "discovered" (CORRECT!)

These are all CORRECT and should NOT be changed:

### pipeline/generator.py
- **Line 829**: `# Newly discovered movie - always needs enrichment`
  - ✅ CORRECT: This is about transitions (tracking → available)

- **Line 872**: `# ARCHITECTURAL FIX: Immediately add newly discovered movie to data.json`
  - ✅ CORRECT: This is about transitions (new arrivals)

- **Line 1301**: `ENHANCED: Add newly discovered movie to data.json immediately upon discovery`
  - ✅ CORRECT: This is about transitions

- **Line 1409**: `'_discovered_at': datetime.now().isoformat(),`
  - ✅ CORRECT: Timestamp when movie became available (transition)

- **Line 1497**: `'_discovered_at': datetime.now().isoformat(),`
  - ✅ CORRECT: Timestamp when movie became available

- **Line 1523**: `'_discovered_at': datetime.now().isoformat(),`
  - ✅ CORRECT: Timestamp when movie became available

- **Line 2909**: `# Only enrich newly discovered movies`
  - ✅ CORRECT: This is about transitions (new arrivals)

### All `_discovered_at` field references
- ✅ CORRECT: These refer to when a movie became available (transition discovery timestamp)

### admin.py
- **Line 216**: `# Note: digital_date is our custom field (date we discovered availability)`
  - ✅ CORRECT: This is about discovering availability (transition)

---

## Category 3: Tests - UPDATE to match

### tests/test_discovery_contract.py
Review and update test names and docstrings:
- Line 66: `def test_discovery_creates_tracking_movies()`
  - Should be: `def test_intake_creates_tracking_movies()`
  - Docstring line 70: "Contract: New titles discovered should have:"
    - Change to: "Contract: New titles intaked should have:"

---

## Category 4: Metrics Files - LEGACY SUPPORT

### metrics/intake_run.json
- Current field: `"discovered": 38`
- New field: `"intaked": 38`
- Strategy: Add both fields during transition period, then phase out "discovered"

### metrics/daily.jsonl
- Current field: `"discovered_today": 38`
- New field: `"intaked_today": 38`
- Strategy: Code will write new field, but fallback to old field when reading for backward compatibility

---

## Category 5: Museum/Legacy - DO NOT TOUCH

All files in `museum_legacy/` are historical archives and should not be modified.

---

## Implementation Strategy

### Phase 1: Core Code Changes (Backward Compatible)
1. Update pipeline/generator.py with fallbacks
2. Update generate_data.py
3. Update daily_orchestrator.py with fallbacks
4. Update scripts/baseline_metrics.py with fallbacks

### Phase 2: Test Updates
1. Update test_discovery_contract.py

### Phase 3: Metrics Transition
1. New runs will write `intaked` field
2. Old runs with `discovered` field still readable (fallback logic)
3. After 7 days, remove fallbacks

### Phase 4: Verification
1. Run `python3 generate_data.py --intake` and verify metrics
2. Run `python3 daily_orchestrator.py` and verify output
3. Check metrics files have new field names
4. Run all tests

---

## Notes on Backward Compatibility

All reading of metrics includes fallback:
```python
# Example
intaked_today = results.get('intaked', results.get('discovered', 0))
```

This ensures old metrics files (with 'discovered') continue to work while new ones use 'intaked'.

---

## Files NOT Modified (Correct usage)

- NRW_DATA_WORKFLOW_EXPLAINED.md - uses "discovered" correctly for transitions
- All `_discovered_at` timestamp fields - correct
- Comments about "newly discovered" in transition context - correct
