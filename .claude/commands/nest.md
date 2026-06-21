---
description: Nest a doc — extract bulky/rare/duplicated parts behind load-on-demand pointers so the spine stays lean
allowed-tools: Bash, Read, Grep, Edit, Write, Glob, AskUserQuestion
---

# /nest

Apply **progressive disclosure with lazy-loaded references** to a markdown doc (a command file, CLAUDE.md, a docs/ file). Keep a lean always-loaded **spine**; push everything conditional, bulky, or duplicated behind a pointer that only enters context when a trigger fires.

`/nest <path>` nests one doc. `/nest all` audits every `.claude/commands/*.md` (+ root + `docs/` if asked) and reports a ranked worklist first. With no arg, ask which.

**The point:** a command file loads *whole* every invocation. In-file tidying saves attention, not tokens. Real savings are **cross-file** — see the ranking below.

## What to pull out, ranked by payoff

1. **Logic → a script** (best — the internals never enter context). Any inline `python3 -c "…"` block, especially one repeated across docs. The doc calls `scripts/foo.py`; I act on its output without reading how it works.
2. **Bulky/rare detail → a separate file read on trigger.** Output-format mockups, field references, long examples, edge-case procedures used in only some runs. Doc keeps a one-line pointer (`see X.md → Block`); I Read it only when the trigger fires.
3. **Repeated boilerplate → defined once inline.** A commit one-liner, a link rule, a filter explanation stated 3×+ → one named block, referenced by name. (Saves attention, not tokens — lowest payoff, still worth it.)

## Decision rule (per block)

- Needed **every run** → leave inline.
- **Conditional / bulky** → separate file, pointer at the decision point.
- **Logic** → script.
- Duplicated across N docs → one shared script/block; each doc points to it.

Don't over-nest: **2 hops max**. A pointer with a vague trigger is worse than inlining — the trigger must be unmissable and sit exactly where the decision is made.

## Process

1. **Audit (no edits).** Read the target. Find candidates with the heuristics below. Produce a table: *block → kind (logic/bulky/dup/boilerplate) → recommended action → est. lines saved*. For `/nest all`, rank across docs, biggest wins first. Present and wait.
2. **Approve.** User picks which to apply.
3. **Apply, one at a time:**
   - Script extraction: write `scripts/<name>.py`, then **diff its output against the old inline block** on real data — must be byte-identical (this guards "behavior unchanged"). Only then replace the inline block with the call.
   - File extraction: move the block verbatim into the new file; replace with a named pointer; add a one-line "Read it when <trigger>" note where it's used.
   - Boilerplate: define once, replace copies with references.
4. **Verify & report:** show before/after line counts, confirm the doc's behavior is unchanged, list new files. Commit only if the user asks.

**Hard rule:** nesting is a *reorganization* — end behavior must be identical. Never drop an instruction; a pointer must resolve to the exact content it replaced. When extracting logic, parity is proven by diff, not assumed.

## Heuristics (find candidates fast)

```bash
# inline python -c blocks per doc (logic → script)
for f in .claude/commands/*.md; do n=$(grep -c 'python3 -c' "$f"); [ "$n" -gt 0 ] && printf '%3s  %s\n' "$n" "$f"; done | sort -rn

# biggest docs (likely have bulky reference/template sections)
wc -l .claude/commands/*.md | sort -rn | head

# duplicated fenced blocks across docs (dup → shared script/file)
/usr/bin/python3 scripts/nest_audit.py        # if present; else hash fenced blocks ad hoc
```

Also eyeball for: long ```fenced``` output mockups / field lists, the same commit/push or filter snippet pasted 3×+, and near-identical sibling commands (e.g. a markX / marknotX pair) that should share a body.
