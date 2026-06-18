# NRW Cross-Device Design Audit — 2026-06-18

Snapshot of how the **past ~2 weeks of design/UI changes** sit across all 7 devices.
Goal: find changes that landed on some devices but not others, and list the exact fix per device.

**Legend:** ✅ consistent · ⚠️ gap (needs the change) · ❓ needs a closer look during implementation · ➖ N/A for this device

Devices: **Desktop** (`assets/`, `index.html`) · **Mobile** web (`mobile/`) · **iOS** · **tvOS** · **Android** TV · **Roku** · **Newsletter** (`templates/newsletter/`, light theme).

---

## Matrix

| # | Design theme | Desktop | Mobile | iOS | tvOS | Android | Roku | Newsletter |
|---|---|---|---|---|---|---|---|---|
| 1 | Full-name language ("Spanish", not "ES") | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ | ➖ |
| 2 | Multi-stream split-row watch buttons | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ | ➖ |
| 3 | Toggle row order (FESTS/PRE-ORDER on top) | ✅ | ❓ | ❓ | ✅ | ❓ | ❓ | ➖ |
| 4 | Country on the genre·date subtitle line | ❓ | ❓ | ❓ | ✅ | ❓ | ❓ | ➖ |
| 5 | Capsule newlines → line breaks | ✅ | ✅ | ✅ | ✅ | ❓ | ❓ | ❓ |
| 6 | Detail 2×2 score grid + real (un-tinted) logos | ➖* | ➖* | ❓ | ✅ | ❓ | ❓ | ➖ |
| 7 | Toggle mutual-exclusivity (one at a time) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 8 | Edge-pinned cycle/nav arrows in detail | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| 9 | SELECTS "OF NOTE" subtitle + matched size | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 10 | Section banner ~2× the date dividers | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |

\*Web detail screens have their own score styling that isn't broken; the 2×2 grid was a tvOS-specific layout fix, not a spec the web must match.

---

## Gaps that need fixing (prioritized)

### 1. Full-name language — ⚠️ on 5 devices (highest-value, easy)
Only tvOS maps `original_language` → a readable name (`languageName`/`LANGUAGE_NAMES`, e.g. "Spanish"). Desktop, Mobile, iOS, Android, Roku all still surface the raw 2-letter code ("ES").
- **Desktop/Mobile** (`assets/app.js:419`, `mobile/mobile.js:438`): add a code→name map where `original_language` is rendered.
- **iOS** (`MovieDetail.js:459-463`): same map in the Language field.
- **Android** (`DetailScreen.kt:475-479`): add a Kotlin `when`/map.
- **Roku** (`DetailScreen.brs:213`): add a BrightScript lookup.
- *(Reuse the tvOS map in `MovieDetail.tvos.js` as the source of truth.)*

### 2. Multi-stream split-row watch buttons — ⚠️ on 4 devices
"Show every free streaming service as its own button" (split row) is only on **Desktop** + **tvOS**. **Mobile, iOS, Android, Roku** appear to show a single stream button. Verify, then port the split-row treatment.

### 3. Toggle row order — ❓ verify on Mobile/iOS/Android/Roku
Desktop + tvOS were deliberately set to **FESTS/PRE-ORDER on top, SLOP/SELECTS on bottom**. The other four have the toggles but their render order wasn't confirmed — check each and reorder to match.

### 4. Capsule line-breaks on native — ❓ Android, Roku, Newsletter
Web + iOS + tvOS render `\n` as a tight line break (markdown renderers present). **Android** and **Roku** have no markdown renderer in the grep — verify whether multi-paragraph capsules collapse there. Newsletter (`pipeline/newsletter.py`) should be checked too.

### 5. Country on subtitle line — ❓ verify non-tvOS
tvOS shows "Genre · Date · Country" on the subtitle. Confirm whether the other devices show country and where.

### 6. 2×2 scores / real logos — low priority
tvOS-specific layout fix. Each web/native detail screen has its own score UI; only worth touching if you want literal visual parity.

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
