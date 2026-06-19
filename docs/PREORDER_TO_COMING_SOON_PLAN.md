# Plan: Rename & Reframe "Pre-Order" → "Coming Soon"

> Hand-off plan for a separate Claude Code agent window. Audit done 2026-06-18.
> **Get user approval before executing any phase.** This repo's rules: never
> modify code without explicit approval, never modify data.json directly (use the
> pipeline), never touch `museum_legacy/`.

---

## 1. Why

"Pre-Order" is too narrow. It only covers VOD rent/buy listings you can purchase
before release (Amazon, Apple). The user wants the wall's forward-looking bucket
to also include **upcoming streaming premieres that have no purchase option yet**
(e.g. *Strung*, premiering on Peacock 2026-06-26). "Coming Soon" is the umbrella
term that covers both.

## 2. The key distinction — this is NOT just a find-and-replace

| | **Pre-order** (today) | **Coming soon** (target) |
|---|---|---|
| Definition | Purchasable now, before release | Anything not yet released — purchasable OR not |
| Has watch offer? | Yes (rent/buy deeplinks) | Maybe (streaming premieres have none yet) |
| In data.json today? | Yes — `_is_preorder: true` | Streaming premieres are **reverted and invisible** |
| Source of date | TMDB Type-4 digital date | TMDB Type-4 / streaming premiere date |

So there are **two layers of work**:
- **A. Display rename** (cosmetic): the "Pre-Order" badge text → "Coming Soon".
- **B. Concept expansion** (real engineering): make the bucket actually *include*
  not-yet-released streaming premieres that currently never reach the wall.

## 3. Scope boundary — coordinate with the other window

The mechanism for **surfacing not-yet-released streaming films** (capturing
JustWatch "coming soon"/scheduled data so films like *Strung* aren't silently
reverted) is being handled in a **separate session** alongside a fix to the
launch-report "Platforms" column. 

**This plan owns:** the display rename (A) + the category/naming/config/UI side of
the concept change (B). **It does NOT own** the JustWatch revert logic or the
data-surfacing plumbing — assume those produce a flag the UI can consume. Confirm
the exact flag name with the user before wiring Phase 3, so the two windows don't
collide in `pipeline/discoverer.py` / `pipeline/enricher.py`.

## 4. Current state — where "pre-order" lives (anchors, verified 2026-06-18)

**Data fields (source of truth), in data.json movie records:**
- `_is_preorder` (bool) — drives the badge
- `_buyonly_preorder`, `_preorder_source`, `pre_order_links` — supporting

**Config** — [config.yaml:495](../config.yaml):
- `preorder:` block (detection settings)
- `preorder_overrides:` — map keyed by **movie ID** (`"1320006": false`, etc.).
  Two-layer override pattern: data.json (immediate) + this config (durable). Both
  layers must move together or rebuilds silently revert.

**Detection / pipeline (Python)** — 343 refs across 14 active files (ignore the 5
in `museum_legacy/`). Core ones:
- `pipeline/enricher.py` — the pre-order link finder ("N movies within 14d window")
- `pipeline/discoverer.py`, `pipeline/generator.py`, `pipeline/display.py`
- Note the known bias: detection defaults ambiguous buy-only films to pre-order
  (Amazon CAPTCHA / Fandango SPA). See `docs/MISTAKES_LOG.md`.

**Display per device** (157 refs across the 7 — these are the starting anchors,
not the full list; do a per-device sweep):
| Device | Anchor | Current label |
|---|---|---|
| Desktop | [assets/app.js:659](../assets/app.js#L659), `.badge-preorder` in styles.css:742 | `PRE-ORDER` + date |
| Mobile | mobile.js:77-79 (desc), :699 `preorder-badge` | already says "Coming soon…" in desc |
| iOS | src/components/DateRowHeader.js:12 | `{day:'PRE-ORDER', rest:'COMING SOON'}` |
| tvOS | src/screens/HomeScreen.tvos.js, MovieCard.tvos.js | check |
| Android | ui/components/MovieCard.kt, data/Movie.kt, FilterChips.kt | check |
| Roku | components/ui/MovieCard.{xml,brs}, locale/en_US/translations.xml | check (translations.xml is the label string) |
| Newsletter | templates/ | check |

Also: the desktop/mobile **filter toggle** ("show pre-orders" exclusive view) —
`showPreorders`, `preorder-toggle`, `'preorders'` view key.

## 5. Work breakdown (staged, each gated on approval)

### Phase 1 — Display rename only (low risk, do first)
Change user-facing **label strings** "Pre-Order" → "Coming Soon" across all 7
devices + the filter toggle label. Do **not** rename internal fields/flags/CSS
classes/view-keys yet — only the text a user reads.
- Run `/check-devices` after (per `docs/DEVICE_REGISTRY.md`).
- Verify each device renders the new label and the toggle still works.

### Phase 2 — Internal naming (optional, higher risk)
Renaming `_is_preorder` → `_is_coming_soon`, `preorder_overrides` → `coming_soon_overrides`,
CSS classes, view keys, function names.
- **Recommendation: skip or defer.** It touches the data.json schema, the archive,
  every reader, and the override config keyed by movie ID. High churn, no user-visible
  benefit. Keep internal names as-is unless the user specifically wants it.
- If done: needs a data migration for existing records + a back-compat read for
  `data_archive.json`.

### Phase 3 — Concept expansion (depends on the other window)
Once the separate session surfaces not-yet-released streaming premieres (a flag on
the movie record), make the "Coming Soon" bucket include them:
- UI: the existing pre-order grouping/sort/toggle should accept the new films.
- Sort "Coming Soon" by release date ascending (nearest first) — desktop already
  does this for pre-orders (app.js:541).
- Decide badge sub-text: purchasable → "Coming Soon · <date>"; streaming premiere
  with no offer → "Coming Soon · <platform> · <date>" (platform may be blank).
- Config: extend overrides to cover the new category.

## 6. Per-device verification checklist (all 7 — none optional)
1. Desktop (`assets/`) 2. Mobile (`mobile/`) 3. iOS 4. tvOS 5. Android TV
6. Roku 7. Newsletter. Run `/check-devices`; confirm label, badge, sort, and the
filter toggle on each.

## 7. Guardrails
- Get explicit approval before editing. Present diffs first.
- Do not modify `data.json` directly — changes flow through the pipeline.
- Do not touch `museum_legacy/`.
- Coordinate the flag name for Phase 3 with the other window before wiring it.
- "Coming Soon" must not silently swallow the existing purchasable pre-orders —
  both must render correctly.

## 8. Open decisions for the user
1. Phase 2 (internal field rename): do it, or keep internal names and only change
   display? (Recommend: keep internal names.)
2. Badge wording: "Coming Soon" alone, or "Coming Soon · <date>" / with platform?
3. Should the streaming-premiere films share the *same* filter toggle as
   purchasable pre-orders, or be a distinct sub-group?
