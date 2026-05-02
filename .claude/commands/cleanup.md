---
description: Codebase maintenance sweep — find and fix dead code, bloat, redundancy, and cruft
argument-hint: [everything | filename | area like "discovery" or "enrichment"]
---

You are performing **codebase maintenance** for the NRW project. Think of this as mowing the lawn — removing accumulated cruft from iterative AI-assisted development.

**Target**: $ARGUMENTS

---

## WHAT TO LOOK FOR

Scan for these categories of maintenance issues:

1. **Dead code** — functions, variables, or imports that nothing calls/uses anymore
2. **Redundant logic** — two or more places doing the same thing (consolidate into one)
3. **Stale comments** — TODOs that are done, comments describing old behavior, outdated notes
4. **Leftover debug code** — print statements, console.logs, temporary logging from past sessions
5. **Unused config/data entries** — config keys that nothing reads, dead feature flags
6. **Over-engineering** — abstractions or patterns more complex than needed for what they do
7. **Orphaned files** — files that nothing imports or references

## WHAT TO IGNORE (do NOT flag these)

- Working code that could be "cleaner" but functions correctly
- Style preferences (naming, formatting) unless genuinely confusing
- Architecture decisions — those are intentional, not cruft
- Anything in `museum_legacy/` (archived on purpose)
- Comments that explain non-obvious logic (those are valuable)

---

## WORKFLOW

### Step 1: Determine Scope

- If target is **"everything"**: scan all Python files, all JS/CSS in assets/ and mobile/, config files, and templates. Work file-by-file, heaviest first.
- If target is a **filename**: scan just that file.
- If target is an **area** (e.g., "discovery", "enrichment", "trailers", "UI"): determine which files are relevant to that area and scan those.

### Step 2: Scan and Catalog

For each file in scope:
- Read the file
- Identify maintenance items from the categories above
- For dead code: verify it's actually dead by grepping for calls/references across the project
- For redundancy: confirm both copies exist and do the same thing

**CRITICAL**: Do NOT flag something as dead code unless you have VERIFIED nothing references it. Grep the full project. False positives waste the user's time.

### Step 3: Present Findings

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

### Step 4: Get Approval

After presenting findings, ask:

> Fix all, pick specific numbers, or skip?

- **"all"** → fix everything listed
- **Numbers** (e.g., "1, 3, 5") → fix only those
- **"skip"** → done, no changes

### Step 5: Make Changes

For approved items:
- Remove dead code cleanly (no leftover blank lines or orphaned comments)
- Consolidate redundant logic into one location
- Delete stale comments entirely
- Remove debug code
- After all changes, run a quick syntax check (`python3 -c "import ast; ast.parse(open('file').read())"` for Python, or equivalent)

### Step 6: Summary

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
  gemini_scraper.py ...... 2 items

Start with generator.py (heaviest)? Or pick a file.
```

Then walk through one file at a time. Get approval per batch before moving to the next.

---

## SAFETY RULES

1. **NEVER change behavior.** Cleanup means removing dead weight, not rewriting logic.
2. **NEVER remove something you haven't verified is unused.** When in doubt, ask the user.
3. **NEVER touch data files** (data.json, movie_tracking.json, data_archive.json).
4. **NEVER touch config.yaml values** — only remove keys that genuinely have no code reading them.
5. **If a function is called by CI/GitHub Actions but not locally, it's NOT dead.** Check .github/workflows/ before flagging Python functions as unused.
6. **Preserve all public API behavior** — if something is exported or could be called externally, confirm before removing.
