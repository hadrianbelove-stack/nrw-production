# NRW Design Taste Profile

The owner's accumulated design preferences — the things a style guide can't hold.
`docs/STYLE_GUIDE.md` says what the design system IS; this file says what the owner LIKES.
It outranks the designer's own preferences and is read by the `site-designer` agent at
the start of every job.

**Maintenance:** hand-curated, append-only in spirit. Entries are added via `/design`
only after the owner approves the exact wording. One bolded rule per entry, with date
and source. Never bulk-rewrite. (Tracked in git on purpose — unlike `cache/`, this must
survive machines.)

Strength levels: **[hard]** never violate · **[strong]** violate only with explicit OK ·
**[lean]** default preference.

---

## Design taste

- **[strong] Fill the space.** Designs must use the full area available — no cramped
  corners, no undersized elements floating in voids. If an element looks small in
  context, it is wrong. *(2026-06, mockup feedback)*
- **[strong] Fill wide layouts by growing a real control, not by spreading gaps.**
  On a wide bar, don't relocate surplus space into gaps between small controls
  (`space-between` / equal slices) OR into a tight cluster-in-a-corner that leaves a
  center void — both just move the emptiness. Grow a real control (the search field
  into a wide bar, or a distributed track) to consume the surplus so the bar reads
  full edge-to-edge. *(2026-07-09, control-bar FILL-1 iteration)*
- **[strong] No wasted chrome or redundant labels.** Example: the desktop header toggle
  box has NO "VIEW" label header — the toggles speak for themselves. Don't reintroduce
  labels that only name a control group. *(2026-06, header iteration)*
- **[hard] System fonts only.** Never add a custom web font. The stack is
  `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`. *(STYLE_GUIDE)*
- **[hard] Colors live in `:root` vars / `assets/shared-config.js`, never inline.**
  New color = new token. *(STYLE_GUIDE)*
- **[strong] Wikipedia is ALWAYS the first link in any movie link row.** Link order is
  editorial voice, not decoration. *(2026-06, link-row feedback)*
- **[strong] Plain tone, no hype.** In reports, on the site, in microcopy. No
  exclamation-point energy, no marketing adjectives. *(standing preference)*
- **[strong] Logos over text where possible.** When a brand mark exists (score sources,
  streaming services), use it rather than a plain-text label. *(2026-07-06, lightbox
  score-row feedback)*

## Mockup process rules

- **[hard] Mockups show the WHOLE page in context, never an isolated component.** A
  header mockup includes the wall below it; a card mockup sits in the real grid.
  *(2026-06, repeated feedback)*
- **[hard] Mockups are exact reproductions.** Real masthead at real size, the real wall
  grid (`auto-fill minmax(320px,1fr)`, 160px under 900px), real records copied from
  data.json, production CSS values mirrored — never lorem ipsum, never approximated
  spacing. *(2026-06, repeated feedback)*
- **[hard] Phone viewing requires a GitHub Pages URL.** The owner cannot open LAN/
  localhost links on the phone. Commit the mockup to `mockups/`, push, and if no
  data.json change is riding along run `gh workflow run publish.yml --ref main`; then
  share `https://hadrianbelove-stack.github.io/nrw-production/mockups/<file>.html`.
  Local `http://localhost:3000/mockups/...` links are fine for desktop. *(2026-06)*

## Debugging taste

- **[hard] Screenshot to debug rendering; never reason blind from CSS.** Known trap:
  `position:fixed` is captured by `filter`/`backdrop-filter` ancestors (the lightbox
  arrow bug) — invisible in source, obvious in a screenshot. *(2026-06, lightbox bug)*

## Rejected directions (anti-patterns)

*(Append entries here when the owner rejects a proposed direction, so it is not
proposed twice. Format: date — what was proposed — why rejected.)*

---

## Changelog

### 2026-07-04 — Initial version
Seeded from standing feedback: whole-page exact mockups, fill-the-space, no "VIEW"
label, Wikipedia-first links, Pages URLs for phone viewing, plain tone, system fonts,
token colors, screenshot-first debugging.

### 2026-07-09 — Fill-by-growing-a-control corollary
Added the "fill wide layouts by growing a real control, not by spreading gaps" rule,
from the control-bar FILL-1 iteration (search field grown into a wide bar to eat the
surplus instead of `space-between` gaps or a corner cluster + void).
