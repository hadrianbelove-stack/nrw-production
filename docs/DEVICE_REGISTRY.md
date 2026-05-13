# NRW Device Registry

Master reference for all NRW device targets. Use this when applying style/UX changes across devices.

**Quick command:** Run `/check-devices` to verify consistency after any change.

---

## Device Index (7 Total)

| # | Device | Folder | Language | Build Tool |
|---|----------|--------|----------|------------|
| 1 | Desktop Website | `assets/` | HTML/CSS/JS | None (static) |
| 2 | Mobile Website | `mobile/` | HTML/CSS/JS | None (static) |
| 3 | iOS App | `NRWApp-iOS/` | React Native | Xcode |
| 4 | tvOS App | `NRWApp-tvOS/` | React Native | Xcode |
| 5 | Android TV App | `NRWApp-Android/` | Kotlin/Compose | Android Studio |
| 6 | Roku App | `NRWApp-Roku/` | BrightScript | Roku Dev |
| 7 | Newsletter | `templates/newsletter/` | HTML (email) | `pipeline/newsletter.py` |

---

## Key Files by Device

### Desktop Website
| Purpose | File |
|---------|------|
| Styles | `assets/styles.css` |
| Main page | `index.html` |
| Lightbox (detail view) | In index.html + styles.css |

### Mobile Website
| Purpose | File |
|---------|------|
| Styles | `mobile/mobile.css` |
| Main page | `mobile/index.html` |
| Detail view | Flip cards (tap to flip) |

### iOS App
| Purpose | File |
|---------|------|
| Colors | `src/constants/colors.js` |
| Typography | `src/constants/colors.js` (includes Typography, Spacing) |
| Home screen | `src/screens/HomeScreen.js` |
| Detail screen | `src/screens/MovieDetail.js` |
| Movie card | `src/components/MovieCard.js` |

### tvOS App
| Purpose | File |
|---------|------|
| Colors | `src/constants/colors.js` |
| Typography | `src/constants/colors.js` |
| Home screen | `src/screens/HomeScreen.tvos.js` |
| Detail screen | `src/screens/MovieDetail.tvos.js` |
| Movie card | `src/components/MovieCard.tvos.js` |

### Android TV App
| Purpose | File |
|---------|------|
| Colors | `app/src/main/java/com/nrw/app/ui/theme/Color.kt` |
| Theme | `app/src/main/java/com/nrw/app/ui/theme/Theme.kt` |
| Home screen | `app/src/main/java/com/nrw/app/ui/home/HomeScreen.kt` |
| Detail screen | `app/src/main/java/com/nrw/app/ui/detail/DetailScreen.kt` |

### Roku App
| Purpose | File |
|---------|------|
| Colors | `source/constants/Colors.brs` |
| Home screen | `components/screens/HomeScreen.xml` + `.brs` |
| Detail screen | `components/screens/DetailScreen.xml` + `.brs` |
| Movie card | `components/ui/MovieCard.xml` + `.brs` |

### Newsletter (Email)
| Purpose | File |
|---------|------|
| Base template | `templates/newsletter/newsletter_base.html` |
| Full template | `templates/newsletter/newsletter_full.html` |
| Generator | `pipeline/newsletter.py` |
| Output | `output/newsletter.html` |

**Important:** Newsletter uses **LIGHT theme** (white background, dark text) for email compatibility. See STYLE_GUIDE.md "Dark vs Light Theme" section.

---

## Color Format Conversion

When applying a color change, convert the hex value for each device:

| Device | Format | Example: Teal `#00d4aa` |
|----------|--------|-------------------------|
| CSS | Hex | `#00d4aa` |
| CSS (with alpha) | RGBA | `rgba(0, 212, 170, 0.6)` |
| React Native | String | `'#00d4aa'` |
| React Native (alpha) | RGBA string | `'rgba(0, 212, 170, 0.6)'` |
| Kotlin/Compose | Color() | `Color(0xFF00D4AA)` |
| Kotlin (with alpha) | .copy() | `Color(0xFF00D4AA).copy(alpha = 0.6f)` |
| Roku BrightScript | RRGGBBAA | `0x00D4AAFF` (FF = 100%) |
| Roku (60% alpha) | RRGGBBAA | `0x00D4AA99` (99 ≈ 60%) |

---

## Device-Specific Constraints

### Navigation Patterns

| Device | Detail View Navigation | Input Method |
|----------|------------------------|--------------|
| Desktop Web | `← →` arrow buttons + keyboard | Mouse, arrow keys |
| Mobile Web | None (flip cards) | Touch tap |
| iOS App | `‹ ›` arrows + swipe gestures | Touch swipe |
| tvOS App | `‹ ›` arrows + D-pad | Remote D-pad |
| Android TV | `‹ ›` arrows + D-pad | Remote D-pad |
| Roku | `‹ ›` arrows + remote | Remote arrows |

### Hover/Focus States

| Device | Has Hover? | Has Focus State? |
|----------|------------|------------------|
| Desktop Web | Yes | No |
| Mobile Web | No | No |
| iOS App | No | No |
| tvOS App | No | Yes (focus glow) |
| Android TV | No | Yes (focus border) |
| Roku | No | Yes (focus highlight) |

### Sizing Considerations

| Device | Viewing Distance | Typical Font Scale |
|----------|------------------|-------------------|
| Desktop Web | 2 feet | 1rem = 16px |
| Mobile Web | 1 foot | 1rem = 16px |
| iOS App | 1 foot | System default |
| tvOS App | 10 feet | 80px+ for nav |
| Android TV | 10 feet | 56sp+ for nav |
| Roku | 10 feet | Large system font |

---

## Quick Checklist Template

When applying a change to all devices, copy this checklist:

```
[ ] Desktop Web: assets/styles.css
[ ] Mobile Web: mobile/mobile.css
[ ] iOS: NRWApp-iOS/src/constants/colors.js
[ ] tvOS: NRWApp-tvOS/src/constants/colors.js
[ ] Android TV: NRWApp-Android/app/.../ui/theme/Color.kt
[ ] Roku: NRWApp-Roku/source/constants/Colors.brs
[ ] Newsletter: templates/newsletter/*.html (LIGHT theme - may need inversion)
```

---

## Changelog

### 2026-02-24 - Initial Version
- Created device registry with all 6 devices
- Added color format conversion table
- Documented device-specific constraints

### 2026-05-13 - Terminology Update
- Renamed from PLATFORM_REGISTRY to DEVICE_REGISTRY
- "Platform" now reserved for streaming/VOD services (Netflix, Amazon, etc.)
- "Device" = distribution target (Desktop, Mobile, iOS, tvOS, Android TV, Roku, Newsletter)
