---
description: UI sandbox — create or resume an HTML mockup with a local server link for phone testing
argument-hint: [description of what to mockup, or filename to resume]
allowed-tools: Bash, Read, Grep, Edit, Write, Glob, WebSearch
---

You are building a **UI sandbox** — a self-contained HTML mockup for rapid design iteration. The user tests on their phone; you iterate until they're happy.

## Step 1 — Determine Scope

**Argument**: $ARGUMENTS

- If `$ARGUMENTS` matches an existing file in `mockups/` (e.g. `mobile_3view.html`), **resume** that mockup (skip to Step 5)
- Otherwise, treat it as a description of a **new mockup** to build

## Step 2 — Read the Style Guide

```bash
cat docs/STYLE_GUIDE.md
```

Use NRW design system values (colors, fonts, spacing, radii) for all new mockups. Key values:
- Background: `#0a0a0a` gradient to `#1a1a2e`
- Accent: `#00d4aa` (teal)
- Text: `#ffffff` / `#bbb` / `#888`
- Font: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- Border radius: 15px (cards), 25px (pills)

## Step 3 — Build the Mockup

Create a **self-contained HTML file** in `mockups/`:

- **Filename**: descriptive kebab-case (e.g. `newsletter-header-options.html`, `badge-redesign.html`)
- **Format**: Single file with inline `<style>` and `<script>` — no external dependencies (except TMDB image URLs if needed)
- **Viewport**: `<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">`
- **Data**: If movie data is needed, extract sample entries from `data.json` and embed as a JS array
- **Interactivity**: Add basic JS for any interactive elements (tap, swipe, toggle, etc.)

### Hard Rules
- NEVER touch production files (`index.html`, `assets/*`, `data.json`, pipeline code)
- Self-contained — no external CSS/JS libraries
- Mobile-first — design for phone screens, test in portrait

## Step 4 — Start Server & Get Link

```bash
# Kill stale servers on mockup ports
lsof -ti:8090 -ti:8091 2>/dev/null | xargs kill 2>/dev/null || true

# Start server in background
cd /Users/hadrianbelove/Downloads/nrw-production && python3 -m http.server 8090 &

# Get local IP for phone testing
ipconfig getifaddr en0
```

Build the URL: `http://[LOCAL_IP]:8090/mockups/[FILENAME]`

## Step 5 — Report to User

Present:
1. The **phone-testable URL** (clickable)
2. Brief description of what was built or what the current state is

If resuming an existing mockup, read the file first, start the server, show the link, and ask what changes the user wants.

## Step 6 — Iterate

After each round of user feedback:
1. Make the requested changes to the mockup file
2. Confirm the server is still running (restart if needed)
