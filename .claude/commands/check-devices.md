---
description: Check a style/UX change across all 7 NRW devices
---

# Cross-Device Consistency Check

Review the recent style or UX change and check consistency across ALL 7 devices.

## Devices to Check

| # | Device | Colors File | Detail Screen |
|---|----------|-------------|---------------|
| 1 | Desktop Website | `assets/styles.css` | Lightbox in index.html |
| 2 | Mobile Website | `mobile/mobile.css` | Flip cards |
| 3 | iOS App | `NRWApp-iOS/src/constants/colors.js` | `src/screens/MovieDetail.js` |
| 4 | tvOS App | `NRWApp-tvOS/src/constants/colors.js` | `src/screens/MovieDetail.tvos.js` |
| 5 | Android TV | `NRWApp-Android/app/.../ui/theme/Color.kt` | `ui/detail/DetailScreen.kt` |
| 6 | Roku | `NRWApp-Roku/source/constants/Colors.brs` | `components/screens/DetailScreen.xml` |
| 7 | Newsletter | `templates/newsletter/*.html` | N/A (email format) |

**Note:** Newsletter uses LIGHT theme (white background, dark text) per STYLE_GUIDE.md.

## Color Format Reference

| Device | Format | Example (teal) |
|----------|--------|----------------|
| CSS | Hex | `#00d4aa` |
| React Native | String | `'#00d4aa'` |
| Kotlin/Compose | Color() | `Color(0xFF00D4AA)` |
| Roku BrightScript | RRGGBBAA | `0x00D4AAFF` |

## Your Task

1. **Identify the change** - What was modified? (color, spacing, nav pattern, component style)
2. **Check each device** - Read the equivalent file on each device
3. **Report status** for each:
   - ✅ **Consistent** - Already matches
   - ⚠️ **Needs update** - Specify exact change needed
   - ➖ **N/A** - Doesn't apply to this device (e.g., hover states on mobile)
4. **Provide code** - For any needed updates, show the exact edit

## Device-Specific Constraints

| Feature | Desktop | Mobile Web | iOS | tvOS | Android TV | Roku |
|---------|---------|------------|-----|------|------------|------|
| Nav arrows | `← →` | None | `‹ ›` + swipe | `‹ ›` | `‹ ›` | `‹ ›` |
| Hover states | Yes | No | No | Focus | Focus | Focus |
| Input | Mouse/keys | Touch | Touch | Remote | Remote | Remote |

## Output Format

```
## Change Identified
[Description of what changed]

## Device Status

| Device | Status | Action |
|--------|--------|--------|
| Desktop Web | ✅/⚠️/➖ | ... |
| Mobile Web | ✅/⚠️/➖ | ... |
| iOS | ✅/⚠️/➖ | ... |
| tvOS | ✅/⚠️/➖ | ... |
| Android TV | ✅/⚠️/➖ | ... |
| Roku | ✅/⚠️/➖ | ... |
| Newsletter | ✅/⚠️/➖ | ... |

## Updates Needed
[Code changes for each device that needs updating]
```
