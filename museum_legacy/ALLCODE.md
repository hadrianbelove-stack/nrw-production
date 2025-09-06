# ALLCODE (operator guide)

**prototype.html** — loads the page shell, CSS, and renderer, then calls `NRW.init()`.  (source of truth entry)  
**assets/nrw_styles.css** — visual grid, date cards, flip-cards, button styles.  
**assets/nrw_render.js** — client-only renderer: reads `data.json`, builds date dividers, cards, and buttons.  
**data.json** — 126 titles with `digital_date`; many fields empty. Renderer supplies smart search fallbacks.

**Watch button rule (MVP):** default to Amazon rent/buy search for "<title> <year>".  
If title is recognized as a service original (e.g., Netflix, MUBI), the link targets that service page instead.  
Future: preferences JSON to pick a default store (YouTube/Apple/Amazon).

**Museum policy:** old experiments live in `museum_legacy/` and are not part of the Working Set. Only copy code
into live files intentionally, with a short note in this guide explaining why.
