# /curate — presentation templates

Referenced by `.claude/commands/curate.md`. **Read this file once** when you first need to present a table in a run, then render the named block. Fill from the `curate_list.py` rows + the command's *Shared blocks → Link rules*.

## Selects table
```
SELECTS — which movies are you vouching for?

| # | Title (Year) | RT | MC | IMDb | Available on | Trailer |
|---|---|---|---|---|---|---|
| 1 | [Title (Year)](wiki-url) | 85% | 72 | 7.2 | Netflix | [▶](trailer-url) |
| 2 | Title (Year) | -- | -- | -- | Amazon, Apple TV | [▶](trailer-url) |
| 3 | [Title (Year)](wiki-url) | 92% | 80 | 8.0 | MUBI | — |

★ Recommended: 1 (strong RT/MC), 3 (RT 92%, critical darling)

Reply with numbers (e.g. "1, 7, 10") or "skip".
```
Columns map to the `selects` row: title|year|rt|mc|imdb|services|wiki|trailer. `Available on` = deduped services (`—` if none).

## Sections table
```
FILTERS — check auto-detected assignments

| # | Title (Year) | Sections |
|---|--------------|----------|
| 1 | [Title (Year)](wiki-url) | Studio |
| 2 | [Title (Year)](wiki-url) | Foreign, Documentary |
| 3 | Title (Year) | Indie |
| 4 | Title (Year) | (none) |

Reply with changes (e.g. "2: remove foreign; 4: add indie") or "looks good".
```
All categories in one column so they scan vertically.

## Slop table
```
SLOP REVIEW — confirm or correct auto-classifications

| # | Title (Year) | Slop? | RT | IMDb | Trailer | Wiki | Why |
|---|--------------|-------|----|------|---------|------|-----|
| 1 | [Title (Year)](imdb-url) | ✅ Not slop | 85% | 7.2 | [▶](trailer-url) | [W](wiki-url) | score:1(good_imdb) |
| 2 | [Title (Year)](imdb-url) | 🗑 SLOP (auto) | -- | -- | [▶](trailer-url) | — | score:5(no_wiki,no_rt) |

"auto" = classifier made the call. Reply with overrides (e.g. "2: not slop; 5: slop") or "looks good".
```
Title → `movie.links.imdb` (the row's imdb_link). `Wiki` → `[W](wiki-url)` or `—`.

## Stage 4 queue
```
STAGE 4 — 35 movies to curate
  #1  [The Jealous Bride (2026)](wiki-url) · [▶ trailer](trailer-url)   RT --   — capsule+quotes
  #2  [Double Happiness (2026)](wiki-url) · [▶ trailer](trailer-url)    RT 73%  — capsule+quotes
  ...
  #35 Wetiko (2025) · [▶ trailer](trailer-url)                         RT --   — quotes   (no wiki page)
```

## Stage 4 slice header
```
STAGE 4 (this window) — working #1–3 of 35:
  #1  The Jealous Bride (2026)
  #2  Double Happiness (2026)
  #3  Kraken (2026)
```

## Suggested links
```
**SUGGESTED LINKS**
1. [Lucian Freud](https://en.wikipedia.org/wiki/Lucian_Freud) — painter, subject of film
```

## Quotes block
```
[Film Title] PULL QUOTES

**Outlet Name**
1. *"Quote text here."* — Critic Name, Outlet Name

**Another Outlet**
2. *"Another quote."* — Critic Name, Another Outlet
3. *"Third quote from same outlet."* — Critic Name, Another Outlet

**Letterboxd**
4. *"Letterboxd quote."* — @username
5. *"Another Letterboxd quote."* — @username

Pick a number — paste a trim — or skip.
```
RT/critic lines show **both** critic name and outlet (`— Critic, Outlet`); Letterboxd shows username only; Letterboxd always last; all quote text in *italics*.

## Completion summary
```
CURATION COMPLETE
- Reissues: N confirmed, M rejected
- Staff picks: N added (M total)
- Sections: N overrides applied
- Slop review: N overrides (N→slop, N→not slop)
- Capsules: N written | Pull quotes: N selected
```
