---
description: Codebase maintenance sweep — find and fix dead code, bloat, redundancy, and cruft
argument-hint: [everything | filename | area like "discovery" or "enrichment"]
---

You are performing **codebase maintenance** for the NRW project. Think of this as mowing the lawn — removing accumulated cruft from iterative AI-assisted development.

**Target**: $ARGUMENTS

---

## VERIFICATION-FIRST METHODOLOGY

The #1 failure mode of cleanup is **false positives** — reporting dead code that isn't dead, or CSS classes that don't exist. This wastes the user's time and erodes trust.

**MANDATORY**: For EVERY finding, you must:
1. **Read the actual file** and confirm the code/selector exists at the reported line
2. **Grep the full project** to verify nothing references it (exclude `museum_legacy/`)
3. **Only report findings at 90%+ confidence** — if uncertain, skip it

DO NOT delegate verification to a single agent pass. Use multiple targeted searches per finding. One false positive invalidates the entire sweep.

---

## WHAT TO LOOK FOR

Scan for these categories of maintenance issues:

1. **Dead code** — functions, variables, or imports that nothing calls/uses anymore
2. **Redundant logic** — two or more places doing the same thing (consolidate into one)
3. **Stale comments** — TODOs that are done, comments describing old behavior, outdated notes
4. **Leftover debug code** — print statements, console.logs, temporary logging from past sessions
5. **Unused config/data entries** — config keys that nothing reads, dead CSS variables, dead feature flags
6. **Over-engineering** — abstractions or patterns more complex than needed for what they do
7. **Orphaned files** — files that nothing imports or references

## WHAT TO IGNORE (do NOT flag these)

- Working code that could be "cleaner" but functions correctly
- Style preferences (naming, formatting) unless genuinely confusing
- Architecture decisions — those are intentional, not cruft
- Anything in `museum_legacy/` (archived on purpose)
- Comments that explain non-obvious logic (those are valuable)
- Intentional `print()` statements in pipeline code (the pipeline uses print for user-facing output with emojis by design — this is NOT debug code)
- Backwards-compatibility fallbacks (e.g., `movie.featured || movie.filters?.is_staff_pick`) — these are intentional safety nets, not redundancy

---

## WORKFLOW

### Step 1: Determine Scope

- If target is **"everything"**: scan all Python files, all JS/CSS in assets/ and mobile/, config files, and templates. Work file-by-file, heaviest first.
- If target is a **filename**: scan just that file.
- If target is an **area** (e.g., "discovery", "enrichment", "trailers", "UI"): determine which files are relevant to that area and scan those.

### Step 2: Determine Cycle Count

Before scanning, count the total lines in scope (`wc -l` on all target files). Scale the effort:

- **Under 500 lines**: 1 cycle (small file, one thorough pass is enough)
- **500–1500 lines**: 2 cycles minimum, stop if a cycle finds zero new items
- **Over 1500 lines or "everything"**: keep cycling until a full cycle produces zero new findings (no maximum)

This prevents spending 300k+ tokens on a 241-line file while still being thorough on large files where attention drift is real.

### Step 3: Multi-Pass Scanning

A single scan misses things. The fix is to run the full scan cycle **multiple times** — like filtering water through the same filter repeatedly. Each cycle catches smaller and smaller particles that previous cycles missed.

**Each cycle has 3 passes:**

#### Pass A: Broad Scan

Launch **separate, parallel agents** for different file categories:
- **Agent 1**: Python pipeline files (pipeline/*.py, generate_data.py)
- **Agent 2**: Python scripts and scrapers (scripts/*.py, gemini_scraper/*.py, *_scraper*.py, admin.py)
- **Agent 3**: Frontend files (assets/*.js, assets/*.css, mobile/*.js, mobile/*.css, index.html)

(If the target is a single file, launch 1 agent instead of 3.)

Each agent must:
- Read every file in its scope
- For each potential finding, **grep the full project** to verify it's actually dead/unused
- Report exact file path, exact line number, and the exact text found
- Only report 90%+ confidence findings

#### Pass B: Verification + Fresh Eyes

Pass B exists to **catch hallucinations from Pass A** and find what Pass A missed. Launch a second round of parallel agents with these instructions:

- Each agent re-reads **every file** in its scope from Pass A
- **First job: verify Pass A's findings.** For each item Pass A reported, confirm the code actually exists at the reported line and that the grep verification is correct. Flag any Pass A finding that is wrong.
- **Second job: find new items** that Pass A missed — unused imports, dead CSS selectors, orphaned variables, stale comments
- Agents receive the Pass A findings as a structured blocklist (exact file:line pairs) so they skip already-found items when looking for new ones
- Same verification rules apply — grep before reporting

#### Pass C: Cross-file and Connection Scan

Launch a **single agent** that looks across file boundaries:
- For every function/class found in Pass A or B: check if its **callers** have dead code too (cascade detection)
- Check for **orphaned files** — files that nothing imports or references
- Check **config.yaml keys** against all code that reads config
- Check **CSS classes in HTML/JS** against CSS definitions (both directions: unused CSS, and classes used in HTML with no CSS)
- Check **.github/workflows/** to confirm no "dead" function is actually called by CI

#### Repeat the full cycle

After completing one A→B→C cycle, **run the entire cycle again from the top** (if the cycle count from Step 2 allows more cycles). Feed all previous findings into the next cycle as a structured blocklist:

```
BLOCKLIST (do not re-report these):
- generate_data.py:115 — AGENT_SCRAPER_DEBUG dead env var
- generate_data.py:110 — dead incremental variable
...
```

Using exact file:line pairs prevents agents from re-discovering and re-litigating settled findings.

### Step 4: Merge, Deduplicate, and Verify

After all cycles complete:
1. **Merge** findings from every cycle and pass into one list
2. **Deduplicate** — if multiple passes found the same thing, keep one entry
3. **Verify every finding**: read the actual file at the reported line and confirm the code exists. If it doesn't match, discard it. This is non-negotiable — every single item in the final list must be confirmed real by reading the file.

Use this exact format:

---

### Maintenance Sweep: [target]

**Scanned**: [list of files checked]

**Found [N] items across [N] files:**

| # | File | Line(s) | Category | Plain-English Description |
|---|------|---------|----------|--------------------------|
| 1 | generator.py | 2841-2870 | Dead code | `_old_provider_check()` — replaced by JustWatch pre-verification, nothing calls it |
| 2 | assets/app.js | 44 | Unused import | `formatDate` imported but never used |
| ... | | | | |

---

**Rules for descriptions:**
- Plain English. No jargon.
- Say WHY it's dead/redundant (what replaced it, when it became unnecessary)
- If you're less than 90% sure something is dead, say "Possibly dead — verify with user"

### Step 5: Get Approval

After presenting findings, ask:

> Fix all, pick specific numbers, or skip?

- **"all"** → fix everything listed
- **Numbers** (e.g., "1, 3, 5") → fix only those
- **"skip"** → done, no changes

### Step 6: Make Changes

For approved items:
- Remove dead code cleanly (no leftover blank lines or orphaned comments)
- Consolidate redundant logic into one location
- Delete stale comments entirely
- Remove debug code
- After all changes, run a quick syntax check (`/usr/bin/python3 -c "import ast; ast.parse(open('FILENAME.py').read())"` for Python — replace FILENAME.py with the actual file)

### Step 7: Summary

After fixes:

```
Cleanup complete:
- Removed: [N] dead code blocks ([N] lines total)
- Consolidated: [N] redundant patterns
- Deleted: [N] stale comments
- Removed: [N] debug statements

No behavior changes. All existing functionality preserved.
```

---

## BATCHING (for "everything" scans)

If the total findings exceed 10 items, present them in batches of ~5-8 per file:

```
Found 23 items across 6 files:

  generator.py ........... 9 items
  assets/shared-config.js  4 items
  assets/styles.css ...... 3 items
  mobile/mobile.css ...... 3 items
  rt_scraper_playwright.py 2 items
  gemini_scraper/base.py . 2 items

Start with generator.py (heaviest)? Or pick a file.
```

Then walk through one file at a time. Get approval per batch before moving to the next.

---

## CLEANUP HISTORY (memory between runs)

After completing a cleanup (Step 7), append a record to `.claude/cleanup_history.json` so future runs know what was already cleaned:

```python
import json, os, time
history_path = '.claude/cleanup_history.json'
history = json.load(open(history_path)) if os.path.exists(history_path) else []
history.append({
    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
    "target": "[the target that was cleaned]",
    "files_scanned": ["list of files"],
    "items_found": 0,
    "items_fixed": 0
})
with open(history_path, 'w') as f:
    json.dump(history, f, indent=2)
```

At the start of a run, check this history. If a file was cleaned within the last 7 days and the target is "everything", skip it and note "(skipped — cleaned [date])". If the target is a specific file, always scan it regardless of history.

---

## SAFETY RULES

1. **NEVER change behavior.** Cleanup means removing dead weight, not rewriting logic.
2. **NEVER remove something you haven't verified is unused.** When in doubt, ask the user.
3. **NEVER touch data files** (data.json, movie_tracking.json, data_archive.json).
4. **NEVER touch config.yaml values** — only remove keys that genuinely have no code reading them.
5. **If a function is called by CI/GitHub Actions but not locally, it's NOT dead.** Check .github/workflows/ before flagging Python functions as unused.
6. **Preserve all public API behavior** — if something is exported or could be called externally, confirm before removing.
