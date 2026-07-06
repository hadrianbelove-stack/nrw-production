---
description: Site designer — review the live site, generate design options, implement an approved design, or audit the style guide (desktop + mobile web ONLY)
argument-hint: [review|options|implement|guide-audit] [what to look at / build / the approved spec]
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, Task
---

Dispatch the **site-designer** agent for design work on THE SITE ONLY (desktop web `assets/` + `index.html`, mobile web `mobile/`). Not the native apps, not the newsletter — redirect those to `/check-devices` or the newsletter workflow.

## Step 1 — Parse the mode

**Argument**: $ARGUMENTS

- Starts with `review` / `options` / `implement` / `guide-audit` → that mode; the rest is the brief.
- Free text with a clear intent ("critique the lightbox" → review; "give me 3 versions of the header" → options; "make the approved teal-border version live" → implement) → infer it and SAY which mode you inferred.
- No arguments or ambiguous → ask, in plain language:
  1. **Review** — designer looks at the live site and critiques it
  2. **Options** — designer builds 2-3 full-page mockups to choose from
  3. **Implement** — designer makes an already-approved design real
  4. **Guide audit** — check the style guide against what actually shipped

## Step 2 — Preflight

1. **Server**: `curl -s -o /dev/null -w '%{http_code}' http://localhost:3000` — if not 200, run `./launch_all.sh` in the background (NEVER a bare `python3 -m http.server`), poll until :3000 answers, tell the user it was started (note: it git-pulls and restarts any running servers).
2. **Taste file**: confirm `docs/DESIGN_TASTE.md` exists. If missing, stop and tell the user it needs to be restored from git before design work.
3. **IMPLEMENT only**: there must be a concrete approved spec — a mockup filename in `mockups/`, a variant from a previous `/design options` report, or an explicit description the user approved in this chat. No spec → STOP and ask. Dispatching implement IS the approval, so never dispatch it speculatively. Also run `git status --porcelain -- index.html assets/ mobile/` and warn the user if those files already have uncommitted changes (before/after diffs would blur together).
4. Build the slug: `<YYYY-MM-DD>-<2-4-word-kebab-topic>` (e.g. `2026-07-04-lightbox-title`).

## Step 3 — Dispatch site-designer (Task tool, subagent_type: site-designer)

Fill this brief exactly:

```
MODE: <review|options|implement|guide-audit>
BRIEF: <what to look at / build, restated concretely — which pages, which states (wall top, scrolled, lightbox open, filter active), both surfaces unless the user narrowed it>
SLUG: <slug>   → screenshots go to screenshots/design/<slug>/
VIEWPORTS: default per your protocol; <plus any the request implies>
APPROVED SPEC (implement only): <the exact spec, verbatim>
CONSTRAINTS: <anything the user said this session — deadlines, "don't touch X", taste remarks>
```

One dispatch per mode. Do not dispatch implement and review in the same call.

## Step 4 — Present the report (the user is a non-coder — translate)

- Lead with the VERDICT in plain words. No jargon, no hype.
- `open screenshots/design/<slug>/<key-shot>.png` the 1-3 shots that matter (macOS Preview). For implement, open the AFTER next to the BEFORE.
- Findings as a short list: what's wrong visually → what the fix looks like. Keep file:line available but don't lead with it.
- **Options mode**: give the local URL per variant (`http://localhost:3000/mockups/<file>.html`) for desktop viewing. For PHONE viewing the user cannot open LAN links — the mockup must be committed to `mockups/` and pushed, then viewed at `https://hadrianbelove-stack.github.io/nrw-production/mockups/<file>.html`. Pages IS production and publish only auto-runs on data.json changes, so a code-only push needs `gh workflow run publish.yml --ref main`. Do this only with the user's OK.
- **Implement mode**: summarize the diff in plain language, confirm the ?v= bumps and the before/after pair, then remind: changes are UNCOMMITTED. Offer a commit message; commit only if the user says yes (append `APPROVED: DELETE` if any lines were removed — the hook requires it). Deploying to the live site afterwards also needs `gh workflow run publish.yml --ref main`.
- **Guide-audit mode**: show the drift table; for each AMBIGUOUS row ask the user to rule (guide wins or site wins); apply approved guide edits to `docs/STYLE_GUIDE.md` yourself (main chat, normal approval flow) and add a Changelog entry, matching the guide's existing changelog style.

## Step 5 — Taste capture (every run)

If the user reacts with a durable preference ("I hate the cramped corner", "always show the full title") or the agent returned TASTE CANDIDATES:
1. Draft the entry in the DESIGN_TASTE.md format — one bolded rule sentence, dated, with source.
2. Show it and ask: "Add this to your taste profile?"
3. On yes, append to the right section of `docs/DESIGN_TASTE.md`. Never add without asking; never reword an existing entry without asking.
One-off remarks ("this particular mockup, make it bluer") are iteration feedback, not taste — don't bank those.

## Step 6 — Iterate

Options mode is usually a loop: feedback → re-dispatch site-designer with the same SLUG plus the feedback in CONSTRAINTS → present again. Keep every rejected variant's file — rejections become taste-profile candidates.
