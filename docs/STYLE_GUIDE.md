# NRW Style Guide

This is the authoritative style guide for all NRW visual design. All UI work (newsletters, mockups, apps, web pages) MUST follow these specifications.

**Last Updated:** 2026-02-24

---

## Color Palette

### Core Colors
| Name | Hex | Usage |
|------|-----|-------|
| **Background Dark** | `#0a0a0a` | Gradient start |
| **Background Mid** | `#1a1a2e` | Gradient end, card backgrounds |
| **Primary Accent** | `#00d4aa` | Links, highlights, borders, interactive elements |
| **Primary Accent Hover** | `#00ffbb` | Hover states |
| **Text Primary** | `#ffffff` | Headings, important text |
| **Text Secondary** | `#bbb` | Body text, descriptions |
| **Text Muted** | `#888` | Metadata, timestamps |
| **Border Subtle** | `rgba(255,255,255,0.2)` | Card borders, dividers |

### Category Colors
| Category | Hex | Usage |
|----------|-----|-------|
| **Staff Picks** | `#dc143c` | Crimson - badges, borders, accents |
| **Studio** | `#ffffff` | White - default styling |
| **Indie** | `#00d4aa` | Teal - matches primary accent |
| **Documentary** | `#4A90D9` | Blue - informational, non-fiction |
| **Virtual Screenings** | `#FFD700` | Gold - festival/screening accent |
| **The Slop Pile** | `#888888` | Gray - muted, de-emphasized |
| **Restorations** | `#C8A951` | Antique gold - badge pill on poster |

### Service Colors
| Service | Hex |
|---------|-----|
| Netflix | `#E50914` |
| Disney+ | `#113CCF` |
| Max | `#B537F2` |
| Prime Video | `#00A8E1` |
| Hulu | `#1CE783` |
| Peacock | `#000000` |
| Purchase/Rent | `#ff9500` |
| Plex | `#E5A00D` |
| Fawesome | `#5B8DEF` |
| Apple TV | `#aaaaaa` |

### Gray Guidelines
When using grays for secondary UI elements:
- **Prefer lighter grays** - dark grays disappear into dark backgrounds
- Outline buttons: use `#888` to `#aaa` for borders, not `#555` or darker
- Muted text: `#888` minimum, `#666` is too dark
- Apple TV / generic service buttons: `#aaaaaa` (not dark gray)

### Country Display Names
Countries display as **3-letter codes** (IOC/Olympic-style, chosen for recognizability), with **USA** and **UK** kept as the two natural exceptions. The mapping lives in `assets/shared-config.js` (`countryAbbrev` map + `abbreviateCountry()`), keyed by BOTH the full name and the 2-letter ISO code.

| Data Value (either form)        | Displays As |
|---------------------------------|-------------|
| United States of America / US   | USA         |
| United Kingdom / GB             | UK          |
| Germany / DE                    | GER         |
| France / FR                     | FRA         |
| South Korea / KR                | KOR         |
| Netherlands                     | NED         |
| Switzerland                     | SUI         |
| South Africa / ZA               | RSA         |
| Chile / CL                      | CHL         |

Unmapped/new countries fall back to their first 3 letters, uppercased — add them to `countryAbbrev` when they appear. Case is handled automatically; `Unknown` shows `—`. For multiple countries, use slashes: `USA / FRA / JPN`.

---

## Movie Title Display

Foreign-language films with an English title always display as **English (Original)**:
- "The Last Viking (Den sidste viking)" ✓
- "Den sidste viking (The Last Viking)" ✗

This applies regardless of script (Latin, Cyrillic, CJK, etc.). The pipeline enforces this automatically via `_compute_display_title()` in `generator.py`. If a movie was manually corrected to the old format, it will be overwritten on the next CI run.

---

## Typography

### Font Stack
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```
Use system fonts. No custom web fonts.

### Weights & Styles
| Element | Weight | Letter-Spacing | Size |
|---------|--------|----------------|------|
| Main Header (THE NEW RELEASE WALL) | 100 (ultra-light) | 0.3em | 2.5rem |
| Section Headers | 700 (bold) | 0.1-0.15em | 1.1rem |
| Movie Titles | 600-700 | normal | 1-1.25rem |
| Body Text | 400 | normal | 0.9-1rem |
| Metadata/Labels | 400-500 | 0.05em | 0.8-0.9rem |
| Buttons | 700 | 0.1em | 0.75-0.85rem |

### Line Heights
- Body text: `1.6` to `1.7`
- Headings: `1.2` to `1.3`
- Tight (buttons, badges): `1`

---

## Synopsis / Capsule Text Formatting

Movie `synopsis` text in `data.json` may contain a tiny markdown subset:

| Marker | Meaning | Example |
|--------|---------|---------|
| `**text**` | Bold — people's names | `**Brady Corbet**` |
| `*text*`   | Italic — film titles  | `*The Brutalist*` |

Rules:
- This is the **only** field that carries markdown. Pull quotes are plain text.
- Markers must be **balanced**: every `**` opens and closes; every single `*` opens and closes.
- Canonical regex (bold matched first): `\*\*([^*]+)\*\*|\*([^*]+)\*`
- Authoring convention: `gemini_scraper/capsule_style_guide.txt` (FORMATTING section). Approval warns on unbalanced markers (`gemini_scraper/capsule.py`).

Renderers — all must match the spec above:

| Surface | Renderer |
|---------|----------|
| Desktop + Mobile web | `NRWConfig.renderMarkdown()` in `assets/shared-config.js` |
| iOS / tvOS | `renderMarkdownSpans()` in `src/utils/markdown.js` (one identical copy per app — keep in sync) |
| Android TV | `appendMarkdown()` in `ui/detail/DetailScreen.kt` |
| Roku | `MultiStyleLabel` + `MarkdownToMultiStyle()` in `components/screens/DetailScreen.brs` (italic uses bundled `fonts/Italic.ttf`) |
| Newsletter | n/a — does not display synopsis |

---

## Spacing & Layout

### Border Radius
| Element | Radius |
|---------|--------|
| Cards | `15px` |
| Buttons/Pills | `25px` (fully rounded) |
| Small buttons | `6-8px` |
| Badges | `10-12px` |

### Shadows
```css
/* Card shadow */
box-shadow: 0 8px 32px rgba(0,0,0,0.3);

/* Hover glow (accent) */
box-shadow: 0 5px 20px rgba(0,212,170,0.4);

/* Hover glow (crimson for Staff Picks) */
box-shadow: 0 0 20px rgba(220,20,60,0.3);
```

### Standard Spacing
- Card gap: `1-2rem`
- Section padding: `1.5rem` to `2rem`
- Element margins: `0.5rem` to `1rem`

### Wall Grid & Poster Captions (desktop web)
- **Grid**: fluid gallery — `grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))`. Fits as many ~320px posters as the window allows; they stretch to fill and reflow on resize. Drops to `minmax(160px, 1fr)` under 900px.
- **Caption** under each poster is locked to **2 lines** so the grid stays square:
  1. **Title** — white, bold, **one line** with ellipsis (`white-space: nowrap; text-overflow: ellipsis`).
  2. **Meta** — one teal line: `Director · Genre · Nation` (primary genre only; nation as 3-letter code). The director name ellipsizes if long, but ` · Genre · Nation` is pinned (flexbox, `flex-shrink: 0`) so it's never lost.
- The grid item (`.movie-container`) sets `min-width: 0` so a long one-line caption can't widen its column.

---

## UI Components

### Buttons
```css
/* Primary action button */
background: #00d4aa;
color: #000;
padding: 0.5rem 1rem;
border-radius: 8px;
font-weight: bold;
text-transform: uppercase;

/* Hover */
background: #00ffbb;
transform: translateY(-2px);
box-shadow: 0 5px 20px rgba(0,212,170,0.5);
```

### Filter Pills
```css
background: rgba(255,255,255,0.1);
border: 1px solid rgba(255,255,255,0.2);
border-radius: 25px;
padding: 0.5rem 1rem;

/* Active/Hover */
background: #00d4aa;
border-color: #00d4aa;
```

### Cards
- Dark gradient background
- 15px border radius
- Subtle border `rgba(255,255,255,0.2)`
- Shadow on hover
- Scale up slightly on hover (`transform: scale(1.05)`)

### Navigation Arrows (Movie Detail)
For navigating between movies on detail screens across all devices:

| Property | Value | Notes |
|----------|-------|-------|
| Character | `‹` / `›` | Unicode chevrons (U+2039, U+203A) |
| Color | `#00d4aa` | Primary accent (teal) |
| Base Opacity | 60% | Visible but not distracting |
| Flash Opacity | 100% | Visual feedback when navigating |
| Position | Vertically centered on left/right edges | |

**Device-specific sizes:**
| Device | Size | Notes |
|----------|------|-------|
| tvOS | 80px | 10-foot viewing distance |
| Android TV | 56sp | Material Design scaling |
| Roku | Large system font | ~100px at 1080p |
| iOS Mobile | 40px | Touch device, swipe primary |
| Desktop Web | 1.5rem | Button with background |

**Device-specific values:**
```css
/* Web (CSS) */
color: #00d4aa;
background: rgba(0, 212, 170, 0.1);

/* React Native (tvOS/iOS) */
color: 'rgba(0, 212, 170, 0.6)'

/* Android (Kotlin/Compose) */
color = Primary.copy(alpha = 0.6f)

/* Roku (BrightScript - RRGGBBAA format) */
color="0x00D4AA99"
```

---

## Dark vs Light Theme

### Main Site / Apps
Always use **dark theme** as specified above.

### Newsletter (Email/Substack)
Use **light theme** for better email compatibility:
- Background: `#fafafa` or `#ffffff`
- Text: `#222222`
- Accent: `#00d4aa` (keep the teal)
- Category colors: Same as above but ensure contrast

---

## Do's and Don'ts

### DO
- Use the exact hex codes specified
- Maintain consistent spacing
- Use system fonts only
- Keep the dark, premium aesthetic
- Use teal `#00d4aa` as the primary accent everywhere
- Abbreviate "International" → "Intl." in festival/screening names
- Abbreviate "Film Festival" → "Film Fest" when space is tight

### DON'T
- Add new colors without approval
- Use serif fonts (except for special editorial contexts)
- Use pure black `#000` for backgrounds (use `#0a0a0a`)
- Use pure white `#fff` for large background areas (use gradients)
- Add decorative elements, borders, or effects not in this guide
- Use cryptic abbreviations for festival names (e.g. "EBIJFF" is bad; "East Bay Intl. Jewish Film Fest" is good)

---

## Examples

### Newsletter Section Header
```html
<div style="color: #dc143c; font-weight: 700; letter-spacing: 3px;
            text-transform: uppercase; border-bottom: 2px solid #dc143c;
            padding-bottom: 8px; margin: 40px 0 20px 0;">
    STAFF PICKS
</div>
```

### Movie Card Meta Line
```html
<div style="font-size: 0.85em; color: #888; margin-bottom: 12px;">
    <strong style="color: #00d4aa;">Director:</strong> Adam Meeks ·
    <strong style="color: #00d4aa;">Country:</strong> USA · 97 min
</div>
```

---

## Changelog

### 2026-05-25 - 3-Letter Countries + Fluid Poster Grid
- Country Display Names: switched to **3-letter codes** (UK/USA kept as exceptions); rewrote the section + `countryAbbrev` in `shared-config.js` (covers all data countries + ISO-2 variants)
- Added "Wall Grid & Poster Captions": fluid `auto-fill minmax(320px,1fr)` gallery; caption locked to 2 lines (1-line title + teal `Director · Genre · Nation`)
- Added **genre** to poster captions (primary genre); director ellipsizes while genre+nation stay pinned

### 2026-05-22 - Synopsis Markdown Formatting
- Added "Synopsis / Capsule Text Formatting" section: `**bold**` names, `*italic*` titles
- Documented the one renderer per platform and the shared web helper (`NRWConfig.renderMarkdown`)
- Roku now renders bold/italic via `MultiStyleLabel` (bundled Lato italic font) instead of stripping

### 2026-04-24 - Naming Conventions
- Added DO: abbreviate "International" → "Intl.", "Film Festival" → "Film Fest"
- Added DON'T: no cryptic abbreviations for festival names

### 2026-04-17 - Added Fawesome Service Color
- Added Fawesome (`#5B8DEF`) to Service Colors table

### 2026-02-24 - Navigation Arrows Standard
- Added Navigation Arrows section for movie detail screens
- Standardized teal color (#00d4aa) at 60% opacity across all devices
- Documented device-specific sizes and code values

### 2026-02-03 - Initial Version
- Extracted from main site styles.css
- Established core colors, typography, spacing
- Defined category colors for newsletter sections
