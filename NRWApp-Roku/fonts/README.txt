Italic.ttf — Lato Italic (Regular Italic), by Łukasz Dziedzic.
Licensed under the SIL Open Font License v1.1: https://scripts.sil.org/OFL

Used by the synopsis MultiStyleLabel to render *italic* film titles, because
Roku provides no system italic font (system fonts cover default + bold only).
See docs/STYLE_GUIDE.md "Synopsis / Capsule Text Formatting".

To swap fonts: drop a replacement .ttf here as Italic.ttf and keep the
`pkg:/fonts/Italic.ttf` reference in components/screens/DetailScreen.brs.
