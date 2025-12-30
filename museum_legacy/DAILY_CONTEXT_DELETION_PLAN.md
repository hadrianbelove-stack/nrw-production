# DAILY_CONTEXT Deletion Plan - Complete Removal

**Date:** 2025-12-29
**Action:** Delete DAILY_CONTEXT.md system entirely + Remove all 7-day retry logic
**Awaiting:** User approval to proceed

---

## Part 1: Delete DAILY_CONTEXT.md System

### File Deletions

**1. Delete main file**
```bash
rm DAILY_CONTEXT.md
```

**2. Delete archive script**
```bash
rm ops/archive_daily_context.sh
```

**3. Update .gitignore (if DAILY_CONTEXT is mentioned)**
```bash
# Check first
grep DAILY_CONTEXT .gitignore
# If found, remove the line
```

---

### PROJECT_CHARTER.md Changes

**Change 1: Remove from Active Amendment Table (Line 53)**

FIND:
```markdown
| 012-013 | Context | Rolling daily context & three-file loading pattern | Session management | DAILY_CONTEXT.md |
```

DELETE entire line

---

**Change 2: Remove Amendment 012 (Lines 166-170)**

FIND:
```markdown
### 012: Rolling Daily Context
**Decision:** Rolling daily context replaces PROJECT_LOG.md to reduce token usage
**Status:** ✅ Active
**Spec:** DAILY_CONTEXT.md is a living document, overwritten each session and archived to diary/ at end-of-session
```

DELETE entire section

---

**Change 3: Remove Amendment 013 (Lines 172-175)**

FIND:
```markdown
### 013: Daily Context System (Three-File Loading Pattern)
**Decision:** Three-file loading pattern for efficient session handoffs
**Status:** ✅ Active - AI reads DAILY_CONTEXT.md + PROJECT_CHARTER.md + NRW_DATA_WORKFLOW_EXPLAINED.md
**Scope:** DAILY_CONTEXT.md (primary), PROJECT_CHARTER.md (governance), NRW_DATA_WORKFLOW_EXPLAINED.md (technical). Archive via ops/archive_daily_context.sh.
```

DELETE entire section

---

**Change 4: Update File Loading Pattern Section (Lines 37-44)**

FIND:
```markdown
## File Loading Pattern
**Three-file loading pattern for token-efficient session handoffs:**
1. `DAILY_CONTEXT.md` (primary) — Current state, what we did, issues, priorities, files changed
2. `PROJECT_CHARTER.md` (governance) — This charter with critical AI instructions and amendments
3. `NRW_DATA_WORKFLOW_EXPLAINED.md` (technical) — Detailed data flow documentation
**Session Start:** Read these three files → run `./launch_all.sh`
**Session End:** Update `DAILY_CONTEXT.md` → run `./ops/archive_daily_context.sh` → commit changes
Archive via `diary/YYYY-MM-DD.md` (immutable end-of-session snapshots)
```

REPLACE WITH:
```markdown
## Documentation Loading Pattern
**Two-file loading pattern for AI assistant context:**
1. `PROJECT_CHARTER.md` (governance) — This charter with critical AI instructions and core rules
2. `NRW_DATA_WORKFLOW_EXPLAINED.md` (technical) — Detailed data flow and pipeline documentation

**Session Start:** Read PROJECT_CHARTER.md → Read NRW_DATA_WORKFLOW_EXPLAINED.md → Begin work
**Current Status:** Check recent git commits and metrics files for current system state
**Session End:** Commit changes with clear commit messages
```

---

### README.md Changes

**Change 1: Remove from Documentation Section (Line 27)**

FIND:
```markdown
- 📅 **[DAILY_CONTEXT.md](DAILY_CONTEXT.md)** - Rolling diary of recent work
```

DELETE entire line

---

**Change 2: Update Daily Workflow Session Start (Lines 133-135)**

FIND:
```markdown
1. **Load context**: Read DAILY_CONTEXT.md → PROJECT_CHARTER.md → NRW_DATA_WORKFLOW_EXPLAINED.md
2. **Start services**: Run `./launch_all.sh` (select option 3 for full stack)
3. **Check status**: Review daily automation results and any issues in DAILY_CONTEXT.md
```

REPLACE WITH:
```markdown
1. **Load context**: Read PROJECT_CHARTER.md → NRW_DATA_WORKFLOW_EXPLAINED.md
2. **Start services**: Run `./launch_all.sh` (select option 3 for full stack)
3. **Check status**: Review recent git log and metrics/discovery_run.json for current state
```

---

**Change 3: Remove from Session End (Line 152)**

FIND:
```markdown
1. **Archive context**: Run `./ops/archive_daily_context.sh`
2. **Update diary**: Creates immutable snapshot in `diary/YYYY-MM-DD.md`
3. **Commit changes**: Git add/commit any modifications made during session
```

REPLACE WITH:
```markdown
1. **Commit changes**: Git add/commit any modifications made during session
2. **Write clear commit message**: Describe what was changed and why
```

---

**Change 4: Remove from Documentation Discipline (Line 197)**

FIND:
```markdown
- `DAILY_CONTEXT.md` - Current session state
```

DELETE line (or remove from list if in bullet points)

---

### SYSTEM_ARCHITECTURE.md Changes

**Change 1: Update Reading Order Section (Line 16)**

FIND:
```markdown
6. DAILY_CONTEXT.md - Daily operational context
```

DELETE line

---

**Change 2: Update Reading Order List (Line 1122)**

FIND:
```markdown
- [DAILY_CONTEXT.md](./DAILY_CONTEXT.md) - Daily operational context
```

DELETE line

---

**Change 3: Update Questions Section (Line 1134)**

FIND:
```markdown
**Questions**: See DAILY_CONTEXT.md or create GitHub issue
```

REPLACE WITH:
```markdown
**Questions**: Check recent git commits, metrics files, or create GitHub issue
```

---

### Other Documentation Files

**Search and Remove:**
```bash
# Find any other references
grep -r "DAILY_CONTEXT" --include="*.md" . | grep -v museum_legacy | grep -v diary

# Remove references from:
# - docs/AUDIT_2025-11-10.md
# - docs/VERIFICATION_CHECKLIST.md
# - docs/pipeline_extraction_2025-11-10/*.md
# - docs/troubleshooting/*.md
# - CHIEF_ENGINEER_AUDIT.md
# - PROPOSED_DOC_UPDATES.md
```

**Action for each:**
- If just a reference, delete the line
- If explaining the old system, add note: "(DEPRECATED: DAILY_CONTEXT.md removed 2025-12-29)"

---

## Part 2: Remove All 7-Day Retry Logic

### pipeline/generator.py Changes

**Change 1: Remove Catch-Up Logic (Lines 815-833)**

FIND:
```python
                    elif has_providers and movie['status'] == 'available':
                        # Already available movie - check if it needs enrichment
                        is_enriched = self.enrichment_state.is_enriched(movie_id)

                        if not is_enriched:
                            # Never been enriched - check if it became available recently
                            digital_date_str = movie.get('digital_date', '')
                            if digital_date_str:
                                try:
                                    digital_date = datetime.strptime(digital_date_str, '%Y-%m-%d')
                                    days_since_available = (datetime.now() - digital_date).days

                                    if days_since_available <= 7:
                                        # Available in last 7 days and never enriched
                                        needs_enrichment = True
                                        print(f"  🔄 {movie['title']} available {days_since_available} days ago, needs enrichment")
                                except ValueError:
                                    # Invalid date format, skip
                                    pass
```

DELETE entire block (lines 815-833)

REPLACE WITH:
```python
                    # Catch-up logic removed 2025-12-29:
                    # Only enrich on transition day (one attempt), no 7-day retry window
```

---

**Change 2: Verify No Other "7 days" References**

```bash
# Search for any remaining 7-day logic
grep -n "7 days\|days_since_available\|last.*days" pipeline/generator.py

# Check config.yaml for any 7-day settings
grep -n "retry.*days\|catchup.*days\|window.*days" config.yaml
```

If found, review and remove if related to enrichment retry logic.

---

## Part 3: Verification Checklist

After all deletions, verify:

**1. No DAILY_CONTEXT references remain:**
```bash
grep -r "DAILY_CONTEXT" --include="*.md" --include="*.py" . | grep -v museum_legacy | grep -v diary
# Expected: Only matches in CHIEF_ENGINEER_AUDIT.md and PROPOSED_DOC_UPDATES.md (historical)
```

**2. No 7-day retry logic remains:**
```bash
grep -n "days_since_available\|7 days.*enrich" pipeline/generator.py
# Expected: No matches
```

**3. Amendment numbers renumbered if needed:**
```bash
# PROJECT_CHARTER.md amendments should be sequential
# After removing 012-013, check if 014+ need renumbering
grep "^### [0-9]" PROJECT_CHARTER.md
```

**4. Archive script deleted:**
```bash
ls ops/archive_daily_context.sh
# Expected: No such file or directory
```

**5. Documentation cross-references intact:**
```bash
# Verify docs still cross-reference correctly
grep -n "PROJECT_CHARTER\|NRW_DATA_WORKFLOW" README.md
# Should find references to the 2-file loading pattern
```

**6. Git status clean except for intentional deletions:**
```bash
git status
# Expected:
#   deleted: DAILY_CONTEXT.md
#   deleted: ops/archive_daily_context.sh
#   modified: PROJECT_CHARTER.md
#   modified: README.md
#   modified: SYSTEM_ARCHITECTURE.md
#   modified: pipeline/generator.py
```

---

## Part 4: Testing After Deletion

**1. Syntax Check:**
```bash
# Verify Python syntax
python3 -m py_compile pipeline/generator.py
# Expected: No errors
```

**2. Documentation Links Check:**
```bash
# Verify all markdown links work
# (Manual check - open each doc and verify cross-references)
```

**3. Run Discovery Phase:**
```bash
python3 generate_data.py --discover
# Should work without DAILY_CONTEXT references
# Check that catch-up logic is gone (no "available X days ago" messages)
```

---

## Summary

**Files to Delete (2):**
1. DAILY_CONTEXT.md
2. ops/archive_daily_context.sh

**Files to Modify (4):**
1. PROJECT_CHARTER.md (remove amendments 012-013, update file loading)
2. README.md (remove 3-4 references)
3. SYSTEM_ARCHITECTURE.md (remove 3 references)
4. pipeline/generator.py (remove lines 815-833 catch-up logic)

**Documentation Files to Clean (8+):**
- docs/AUDIT_2025-11-10.md
- docs/VERIFICATION_CHECKLIST.md
- docs/pipeline_extraction_2025-11-10/*.md
- docs/troubleshooting/*.md
- CHIEF_ENGINEER_AUDIT.md
- PROPOSED_DOC_UPDATES.md
- Any others found in grep

**Total Changes:** ~20-25 lines deleted/modified across 12+ files

**Estimated Time:** 45 minutes (careful, methodical work)

**Risk:** Low (documentation only, plus one code cleanup)

**Rollback:** `git checkout .` if issues arise

---

## Ready to Proceed?

Awaiting user approval to execute all changes listed above.
