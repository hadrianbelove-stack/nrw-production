# NRW Cross-Device Design Audit — 2026-06-18

Snapshot of how the **past ~2 weeks of design/UI changes** sit across all 7 devices.
Goal: find changes that landed on some devices but not others, and list the exact fix per device.

**Legend:** ✅ consistent · ⚠️ gap (needs the change) · ❓ needs a closer look during implementation · ➖ N/A for this device

Devices: **Desktop** (`assets/`, `index.html`) · **Mobile** web (`mobile/`) · **iOS** · **tvOS** · **Android** TV · **Roku** · **Newsletter** (`templates/newsletter/`, light theme).

---

## Matrix

| # | Design theme | Desktop | Mobile | iOS | tvOS | Android | Roku | Newsletter |
|---|---|---|---|---|---|---|---|---|
| 1 | Full-name language ("Spanish", not "ES") | ➖ | ➖ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 2 | Multi-stream split-row watch buttons | ✅ | ✅ | ✅ | ✅ | ✅ | ✅* | ➖ |
| 3 | Toggle row order (FESTS/PRE-ORDER on top) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 4 | Country on the genre·date subtitle line | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 5 | Capsule newlines → line breaks | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 6 | Detail 2×2 score grid + real (un-tinted) logos | ➖* | ➖* | ❓ | ✅ | ❓ | ❓ | ➖ |
| 7 | Toggle mutual-exclusivity (one at a time) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 8 | Edge-pinned cycle/nav arrows in detail | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 9 | SELECTS "OF NOTE" subtitle + matched size | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 10 | Section banner ~2× the date dividers | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |

\*Web detail screens have their own score styling that isn't broken; the 2×2 grid was a tvOS-specific layout fix, not a spec the web must match.
\*Roku #2: split-row is present (one button per stream) but capped at 2 static button nodes — see resolution below.

---

## Resolution — 2026-06-18 (implementation pass)

All themes worked end-to-end across the 7 devices. Outcome per theme:

### 1. Full-name language — RESOLVED
tvOS/iOS/Android/Roku all map `original_language` → readable name (commit `e8d2b76e`).
**Desktop + Mobile don't display language anywhere** (they only use `original_language` in
filter/search logic, `app.js:419` / `mobile.js:438`) — nothing to convert, so N/A (➖), not a gap.

### 2. Multi-stream split-row watch buttons — ALREADY CONSISTENT (no change)
The audit premise was wrong on inspection. **Every interactive device already renders one
button per free streaming service** (split row):
- Desktop ✅, tvOS ✅ (`getWatchLinks` loops `watch_links.streaming`).
- iOS ✅ — `WatchButtonGroup` maps each link to its own `WatchButton` (`maxButtons=6`, then "+N more").
- Mobile ✅ — `getStreamingProviders` returns all services; `streamingList.map(renderProviderBadge)`.
- Android ✅ — `Movie.getWatchOptions()` loops streaming ("one button per streaming service"); `streamOptions.forEach { WatchButton(...) }`.
- Roku ✅* — `GetStreamingServices` → `streamButton` + `streamButton2` (2 static nodes), one per stream.
**Roku 2-cap deliberately left as-is:** of 756 catalog films, 0 have 3 streaming services and exactly
1 has 4 (a reality-TV title: Max/YouTube/Investigation Discovery/Discovery+). The 2-cap covers
755/756. Adding dynamic/extra static nodes is untestable (no Roku emulator), risks button-row
overflow, and gold-plates a single low-value edge case — not worth it.

### 3. Toggle row order — RESOLVED (real gap, fixed)
Mobile, iOS, Android, Roku all led with SLOP/SELECTS; reordered to FESTS/PRE-ORDER first to match
Desktop+tvOS (commit `1ec534f4`). Pure reorder — IDs/handlers/state unchanged. Roku reordered both
the XML nodes and the `m.filterIds` focus array in lockstep. Verified on Android emulator.

### 4. Country on the subtitle/detail line — ALREADY CONSISTENT (one fix)
Country already shows on every detail screen: Desktop ("Country · Genre · Date"), Mobile (genre ·
country), iOS (country · genre · date), tvOS (genre · date · country), Android (country • year •
runtime), Roku (country • year • runtime). Only fix: **Roku showed the raw country name** while all
others abbreviate — reused the existing `FormatCountry()` helper (commit `f880182c`).

### 5. Capsule newlines → line breaks — ALREADY CONSISTENT (no change)
The audit's grep missed the native renderers. **Android** `appendMarkdown` appends non-marker text
(incl. `\n`) verbatim → Compose `Text` renders the break. **Roku** `MarkdownToMultiStyle` preserves
`\n` and the synopsis `MultiStyleLabel` has `wrap="true"`. **Newsletter** has no live generator —
the only newsletter code is deprecated in `museum_legacy/`, so it's not a target.

### 6. 2×2 scores / real logos — low priority, untouched
tvOS-specific layout fix; each web/native detail has its own score UI. Not pursued.

### New issue found (not in original audit, NOT fixed)
Editorial capsules contain markdown **links** (`[text](url)`). Web/tvOS/iOS render them; **Android
(`appendMarkdown`) and Roku (`MarkdownToMultiStyle`) handle only bold/italic**, so a capsule link
shows as raw `[text](url)` on those two. Affects only curated films with linked capsules. Left for
a separate decision.

---

## Already consistent across all 7 (no action)
- **Toggle mutual-exclusivity** — exclusivity logic present on all interactive devices.
- **Edge-pinned nav/cycle arrows** — Desktop, Mobile, iOS, tvOS, Android (chevrons at `DetailScreen.kt:242-255`), Roku all have them.
- **SELECTS "OF NOTE" subtitle + size** — explicitly synced all-platforms (commit `e1b537ff`).
- **Section banner ~2× the date dividers** — present everywhere.

---

## Notes & caveats
- I can **test** Desktop/Mobile (local server), tvOS + Android (emulators). I **cannot test iOS or Roku** here — those fixes would be code-confirmed only until run on a real device/emulator.
- ❓ cells are honest "needs a closer read during implementation," not assumed-broken.
- Source-of-truth for the language map and multi-stream pattern: the tvOS implementation (most recently refreshed).
