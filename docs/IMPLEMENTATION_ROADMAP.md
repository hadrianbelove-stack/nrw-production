# IMPLEMENTATION_ROADMAP.md

> Canonical tactical plan for NRW. Rebuilt 2026-03-10 after Chief Engineer review.
> Governance lives in PROJECT_CHARTER.md. This file is **what to build and when**.

## Current State (as of 2026-03-10)

- **Pipeline:** Automated daily, 14,544 movies tracked, 472 on the wall, ~7.5 arrivals/day
- **Platforms:** 7 active (Desktop, Mobile, iOS, tvOS, Android TV, Roku, Newsletter)
- **Core vision:** Curation as a product. The wall runs itself — now make the editorial layer shine.

---

## Phase 1: Newsletter Launch (Substack)
**Priority: HIGHEST — Ship first**

| Item | Details |
|------|---------|
| Cadence | Weekly roundup |
| Model | All free (build audience first) |
| Content | Best new digital releases, staff picks, weekly trailer playlist, editorial descriptions |
| Links | Point to mobile site (primary audience is phone users) |
| Editorial | AI drafts descriptions, Creative Director edits/approves |

**What exists:** `pipeline/newsletter.py` (data query), `generate_newsletter.py` (CLI), HTML/MD templates in `templates/newsletter/`, email-safe inline styling.

**To build:**
1. Newsletter generation command — pull the week's arrivals + staff picks
2. AI-generated editorial descriptions per featured film (Gemini)
3. Export-to-Substack workflow (HTML copy or API draft)
4. Weekly trailer playlist link integration
5. Mobile site deep links for each movie

---

## Phase 2: Admin Panel — Deep Browse Curation
**Priority: HIGH — Enables newsletter quality**

The admin panel works as a QA tool today. It needs to become a **leisurely editorial browsing experience** — scroll through posters and trailers, check links without disrupting flow, write descriptions with context at hand.

**What exists:** Flask app (`admin.py`), grid layout, inline editing, search/filter, staff pick toggles, trailer modals. Review system backend (`/update-review`, `/delete-review`) exists but isn't wired into the UI.

**To build:**
1. **Side panel detail view** — click a card, drawer opens with: large poster, embedded trailer, all links (RT/Wiki/watch), synopsis editor, review editor. Grid stays visible
2. **Curation mode toggle** — switch between "QA mode" (missing data focus) and "Curation mode" (editorial focus, larger posters, breathing room)
3. **Wire up review system** — `admin/movie_reviews.json` backend already supports reviews. Surface in side panel
4. **Context links** — RT, Wikipedia, trailer open in panel or adjacent tab without losing grid position
5. **AI description drafts** — "Generate description" button → Gemini drafts editorial copy → user edits in-place

---

## Phase 3: Better Descriptions
**Priority: HIGH — Core to curation quality**

Current synopses are TMDB marketing copy — generic, missing context, sometimes empty. Need editorial descriptions that mention director's previous work, festival history, why the film matters.

**What exists:** `gemini_scraper.py` already calls Gemini with Google Search grounding. Can extend with editorial prompt.

**To build:**
1. **Gemini editorial description generator** — uses movie metadata (director, cast, festival_info, RT score, synopsis) to write 2-3 sentence editorial description
2. **Admin integration** — one-click generate, inline edit, save
3. **Batch generation** — for newsletter prep, generate descriptions for all featured films at once
4. **Template variations** — newsletter description vs. site description (different lengths/tones)

---

## Phase 4: Discovery Expansion
**Priority: MEDIUM — Ongoing improvement**

Currently TMDB-only for primary discovery (3 passes: direct-to-digital, theatrical, festival). Need more unusual/international/arthouse/restored titles.

**What exists:** 26 festival configs, `hidden_gems_scraper.py` (Vimeo/YouTube/Letterboxd/Patreon), Gemini-powered enrichment.

**Expansion opportunities (ranked by impact):**
1. **Criterion Collection** — highest-quality arthouse/restoration catalog
2. **Mubi** — daily-curated international cinema
3. **Studio/label feeds** — A24, Neon, IFC Films, Magnolia, Kino Lorber (restoration specialists)
4. **Award tracking** — Oscar/BAFTA/Spirit Award nominees as discovery signal
5. **BFI/TIFF platforms** — year-round arthouse access beyond festival windows
6. **Documentary sources** — ARTE, Hot Docs catalog

---

## Phase 5: Platform Polish
**Priority: LOWER — Ongoing**

- Android TV app buildout (scaffolded, not built)
- Roku app buildout (scaffolded, early stage)
- iOS app continued development
- Tracking DB prune strategy (archive movies tracking 12+ months with no digital release)

---

## Recently Completed (Reference)

| Feature | Date | Notes |
|---------|------|-------|
| Festival system | Feb 2026 | Badges, ribbons, filter — all 7 platforms |
| ~~Pre-order detection~~ | Feb 2026 | Removed Apr 2026 — Amazon pre-order detector never worked reliably |
| Self-hosted trailers | Feb 2026 | B2 infrastructure built, CI fix applied Mar 10 |
| Gemini enrichment | Feb 2026 | AI-powered RT scores, Wikipedia, trailers |
| Lightbox redesign | Feb 2026 | Service colors, streaming hierarchy |
| Cross-platform metadata parity | Feb 2026 | All detail views show same info |
| Filter descriptions | Mar 2026 | Slide-down explainers for each filter |
| Enrichment metrics fix | Mar 2026 | Restored stale metrics writer |
