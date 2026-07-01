# Plan: Distributor Release-Calendar Tracking for NRW

> Status: **proposed subproject** (multi-session). Not yet started.
> Owner: TBD (hand off to a dedicated agent window + branch).
> Last updated: 2026-06-30.

## Goal
Proactively surface new releases from a curated set of arthouse / restoration
distributors (Kino Lorber, Criterion, GKIDS, Janus, Grasshopper, Film Movement…)
so their restorations and new titles land in NRW automatically — instead of being
caught only reactively once TMDB happens to expose them. This is the
"cool restorations this site exists for" lane.

Plus a **verification alert**: if a film we put on our own calendar for a given
date is *not* found/available on that date, the user is told in that morning's
report. The calendar becomes a self-checking harness, not just a feed.

---

## Background — read before building

**The problem is the data source, not a missing query.** Do not restart from
"just query TMDB by company."

### Verified dead-end — DO NOT re-test
TMDB Discover `with_companies` is **not** a viable distributor-discovery source.
- Kino Lorber (TMDB company `39134`) returns only **48 total films**, mostly
  documentaries, and **misses every restoration**.
- Cause: TMDB models *production* companies, not *distributors*. Kino *distributes*
  a restoration but isn't its production company, so TMDB never links them. Same
  limitation for Criterion / GKIDS.
- TMDB also keeps a film's *original* `primary_release_date`, so date-windowed
  Discover can't surface old-film restorations at all. (This is exactly why intake
  Pass D reads `/release_dates` *events* instead.)
- Tested 2026-06-21.

### The real source = distributors' own calendars + press releases
Verified for Kino Lorber (these pages exist, found via search 2026-06-21):
- Calendar/listing: `kinolorber.com/list/new-and-recent-releases`,
  `/list/new-theatrical-releases`, `/list/view/code/now-playing-amp-coming-soon`
- **Press releases** (often the *better* source — title + date + format per film,
  cleaner than the calendar grid): `kinolorber.com/press/...`
  e.g. "Kino Lorber Announces its September 2023 Home Video Releases"

**Critical caveat + the fix (fetch-tested 2026-06-22):** A plain fetch — even WITH a full
browser User-Agent — gets **HTTP 403** from Kino Lorber and Criterion (real Cloudflare-style
protection; the ~5.7KB body is a challenge page). A header/session tweak does NOT work.
**BUT headless Playwright DOES** — tested live on Kino's own calendar
(`kinolorber.com/list/new-and-recent-releases`): HTTP 200, full rendered page, no challenge,
462KB, real "New and Upcoming Releases" content with per-title availability (home
video / theatrical / educational). Playwright is **already installed and used** in the
codebase (`pipeline/enrichment.py`, `discoverer.py`, `enricher.py`). So **the distributors'
own calendars ARE reachable** — and richer than the disc aggregators (theatrical + home-video
+ availability, not disc-only). Remaining work is ordinary: parse each label's card layout
(Kino renders JS product cards; a naive "Availability:" selector hit the filter UI, not the
films). This makes the own-site scrape a *real authoritative option*, not a last resort.

**Other backdoors tested 2026-06-22 (so they're not retried):** socials — Letterboxd accounts
are fetchable (200 + per-account RSS) and real, but **dormant** (Kino's last activity Nov 2024,
logged films not a calendar) → dud; IG/X/FB auth-walled → dud. Wayback Machine → only a stale
2024 snapshot of the Kino calendar, no recent captures → dud. sitemap.xml + own RSS feeds →
Cloudflare 403 → dead.

### Lower-friction sources (verified 2026-06-21 — try these BEFORE headless scraping)
The 403 only applies to the distributors' *own* sites. Two ways around it entirely:

1. **Aggregator piggyback (best lead — verified, no 403).** `physicalmedia.news/upcoming/`
   returns to a **plain fetch**, is organized by date, and lists **title + year + label**
   for exactly the restoration labels NRW wants — in one place: Criterion, Kino Lorber,
   Arrow, Radiance, Severin, Powerhouse/Indicator, Shout! Factory, Cohen Media,
   Vinegar Syndrome. It explicitly flags "4K Restoration" / "Limited Edition" (the reissue
   hook). **One plain-HTML scrape covers ~9 labels** → collapses the per-label-scraper
   brittleness. Caveats: (a) single point of failure — if its layout changes, all labels
   break at once (but that's one parser to fix, not six headless scrapers); (b) it's
   **home-video (disc) focused**, so it's ideal for the restoration lane but won't catch
   digital-first / VOD-only arthouse titles — *complementary to, not a replacement for,*
   normal digital discovery. Other working no-403 source (fetch-tested 2026-06-22):
   `blu-ray.com/movies/movies.php?studioid=<id>` — per-distributor disc catalog, 200 via a
   browser UA (Kino Lorber = `studioid=280`). **Disproven fallbacks (fetch-tested 2026-06-22,
   do NOT relist):** `criterionforum.org/calendar/` → 403, `dvdbeaver.com/.../release-calendar`
   → empty (492 bytes), Fandom "List of Kino Lorber releases" → 403. (These were found via web
   search but never fetched; only physicalmedia.news and blu-ray.com actually return content.)

2. **Google News RSS keyword feed (verified, no 403 — label-agnostic).** A plain-XML feed:
   `news.google.com/rss/search?q="4K restoration"`. Returns dated articles naming specific
   titles + labels (verified 2026-06-21: Criterion's *Charade*, Scream Factory's *Day of the
   Dead*, Fun City Editions' *The Fan*, etc.). Strength the aggregator lacks: it's
   **label-agnostic** — catches restorations from *any* source, including labels not on the
   curated list. Weakness: **noisy** — headlines mix disc, VOD, and theatrical-only re-runs,
   and titles must be parsed out of prose (fuzzy), so this NEEDS the taste/match gate below.
   "Going backwards" for historical backfill = older RSS pages / Wayback; a daily poll
   suffices going forward. Treat each hit as a discovery *signal* (a restoration exists),
   then normal discovery/defer decides when it's actually watchable. Other keyword queries
   ("new restoration", "<label> announces") can widen the net.

3. **Newsletters (dodges bot protection entirely).** Subscribe a dedicated inbox to each
   label's release-announcement list and parse the *emails* instead of fighting the site.
   Distributors *want* these read. Trade-off: depends on each label emailing
   structured-enough content, and email parsing is its own mess — but no 403, no headless.
   Best used to fill gaps the aggregator/news feed miss for a specific label.

**Fetch-ease ranking (which is easiest to retrieve, ≠ which is most valuable):** aggregator
(physicalmedia.news) ≈ Google News RSS (both verified plain fetch, no 403) > newsletters
(dodge 403) > per-label calendar/press pages (need headless, last resort) > socials.
Socials (IG/Twitter) are the worst scrape (auth/API walls, noisy, unstructured) —
lowest priority, optional later. **For *value* ranking, see the Signal model below** — the
news feed carries the major signals; the disc aggregator is a lead pool.

> **These three verified no-403 sources largely remove the headless-scrape 403 fight from
> the critical path.** It drops to a fallback for a specific label the lighter sources miss.

### Signal model — leads vs. major signals, with cross-confirmation
Prototyped both sources end-to-end 2026-06-22 (`pipeline/distributors/physicalmedia.py`,
`pipeline/distributors/googlenews.py`, dry-run only). The key lesson: **these aren't
interchangeable "engines" — they're signals of different strength, and they stack.**

1. **Theatrical re-release of an old film = a MAJOR signal.** Rare and deliberate — a
   distributor only spends to put an old film back in *theaters* when it's worth it, so it's
   high-precision and frequently *precedes* the VOD/streaming drop (gives NRW lead time).
   Often strong enough to act on **alone**. Lives in the Google News feed ("returns to
   theaters", "back in theaters", festival restorations).
2. **Explicit restoration announcement** (4K/2K, "newly restored") = strong. Also the news feed.
3. **Blu-ray / disc release = a LEAD, not a trigger.** Far more discs exist than noteworthy
   restorations, so most are routine catalog (the prototype: 558 rows → 119 matched → only
   ~67 on-brand by hand). Low precision alone. Its value is **corroboration** (a disc lead
   that *also* appears as a theatrical re-release / restoration announcement is confirmed)
   and as a quiet **watch-list** that activates when a stronger signal arrives.

**Rule:** a lone disc lead is **parked, not intaked**; a major signal (theatrical re-release)
is surfaced. Stacking signals = confidence. This also dissolves the disc-≠-digital problem —
leads just wait until something digital/theatrical confirms them.

**Per-source prototype findings (2026-06-22):**
- *physicalmedia.news* (lead pool): clean structured rows `Title (Year) - Label`; easy TMDB
  match; but disc-only over-generates and ~half the curated-label rows are mainstream catalog
  4K already streaming (Troy, JFK, Cloud Atlas) — not NRW discoveries.
- *Google News* (signals): catches theatrical/digital events the disc calendar can't (*The
  Devils*, *Amores Perros*, *Ninja Scroll*, *Sunrise*, GKIDS' *Utena*). Keep the clean
  keywords (`"4K restoration"`, `"2K restoration"`, `"film restoration"`, `"newly restored"`);
  drop/qualify the noisy ones (`"re-release"`, `"rerelease"`, `"new restoration"` → games,
  sneakers, ecology). New hard part: **title extraction from headlines** (titles are in prose,
  often quoted) — quoted-title-first + an LLM fallback; leans on the unmatched review sink.

### Empirical findings — restoration → VOD conversion (measured 2026-06-30)
Ran a grounded web-research agent over **50 genuine restorations that premiered
10–30 months before 2026-06-30** (old enough to have converted if they were going
to). Spreadsheet: `~/Downloads/restoration_conversion_study.xlsx`.

- **Conversion is only 20/50 = 40%.** The rest as of today: 38% still
  theatrical-touring, 20% disc-only, 2% announced-not-out. A theatrical/festival
  premiere presages VOD **less than half the time** on this horizon — so a parked
  restoration must never be treated as a guaranteed future arrival.
- **When they do convert, it's fast: median 4 months** premiere→VOD (11 of 20
  within 6 months, only 1 past 12). Conversion is bimodal — quick, or stalled
  indefinitely; there's little slow trickle.
- **Boutique/festival restorations — the lane's target — convert worst:** MoMA
  To Save & Project 1/7 (14%), UCLA Festival of Preservation 3/8 (38%), Cannes
  Classics 5/14 (36%); broader Google News 11/21 (52%). More time doesn't rescue
  them — the oldest cohort (28-month UCLA) mostly landed disc-only.
- **44% old-transfer false-positive rate.** 22 of 50 restorations have an *older
  transfer* streaming on JustWatch while the restoration itself is NOT on VOD
  (Gold Rush, Bend of the River, Pink Narcissus, Diva, Curse of Frankenstein…).
  A naive "JW says available → surface it" catch would be **wrong 44% of the
  time** — hard proof the catch must be *version-aware*, not a presence check.
- **Festival-intake noise: 9 of 59 (15%)** queued titles were *new* films/docs
  Cannes Classics programs alongside restorations (My Mom Jayne, Welcome to
  Lynchland, I Love Peru…). Festival scrapers need an "is this actually a
  restoration" filter at intake.

**Design consequences:**
- "Theatrical-only" is a **provisional, keep-watching** state, not a verdict —
  store `{status, last_confirmed}` and re-check; never conclude a title will stall.
- **Park clock ≈ 12 months.** Converters land within ~6 months, so a title still
  theatrical-only after ~12 months is almost certainly disc-only-or-never →
  downgrade to a low-priority list (don't drop — a late disc→digital move still
  happens), rather than re-researching it at full cadence forever.
- **Monthly re-check cadence** matches the 4-month median lag.

### What already exists (reuse, don't reinvent)
- `admin/distributor_sources.json` — curated label → `{wikipedia_*page, tmdb_company_id}`.
  Already includes **Kino Lorber (39134)**, A24, NEON, IFC, Magnolia, Film Movement,
  Roadside, Greenwich, etc. **This is the home for the curated list.**
- `scripts/build_distributor_lookup.py` → `cache/distributor_lookup.json`
  ({title_year → distributor}). Reactive labeling only.
- `admin/restoration_config.json` `restoration_distributors[]` → restoration-section
  detection ([pipeline/display.py:557]) + reissue research green-flags
  ([pipeline/reissue_research.py:143]).
- **Intake Pass D** (`pipeline/intake.py` → `collect_reissue_candidates`) — finds OLD
  films (10+ yrs) that just had a new release *event* via TMDB `/release_dates`.
  Mirror its dedup guard (`mid in existing_ids or mid in queue`) and per-item
  try/except isolation.
- **Reissue confirm/defer/reject** (`scripts/confirm_reissue.py`):
  - `--confirm` → to wall now.
  - `--defer` → intake to tracking; normal discovery surfaces it when a digital
    release lands. Uses **change-detection** against a baseline captured at defer
    time (a new Type-4 digital date, or a provider outside the baseline set) so an
    old film with stale availability doesn't false-transition. Built 2026-06-21.
  - `--reject` → not a real reissue.

So the missing piece is narrow: **a discovery SOURCE that reads each distributor's
own calendar/press releases and feeds the existing pipeline.**

---

## Architecture (agreed flow)

```
[per-label scraper: get past 403 → fetch calendar/press release]
   → normalize to {title, year, release_date, release_kind, distributor, source_url}
   → match to a TMDB id (search by title+year; the fuzzy step)
   → dedupe against tracking + reissue queue
   → INTAKE into the tracking DB (status='tracking') with:
        _discovery_source='distributor_calendar'
        _expected_distributor=<label>
        _expected_source_url=<url>
        _expected_digital_date=<date>     # only if the listing is a digital/disc/VOD release
        _expected_theatrical_date=<date>  # only if the listing is theatrical-only
        + reissue flags if it's an old-film restoration (badge/not-slop)
   → NORMAL discovery/verify (TMDB type-4 / providers / JustWatch) transitions it
        when actually available → NORMAL enrichment (RT/Wiki/trailer/links)
   → theatrical-only entries ride the --defer change-detection path until digital
```

Key point (user's correction, and it's the right one): once *we* build the calendar
from a trusted label, the entry is inherently wall-worthy, so it goes straight into
intake and rides the existing pipeline. The `/curate` Stage 0 manual confirm becomes
**optional** — keep a lightweight taste gate only if desired, not as a hard step.

**Quality gate (user: "we probably will have to do a /curate pass eventually… but let's
see").** A trusted *aggregator/label* row is clean enough to auto-intake. The *Google
News keyword feed* is noisier (fuzzy title-from-prose + off-target articles), so its rows
are the ones most likely to need a human pass. Plan: start auto-intake, watch the
false-match / off-taste rate, and add a `/curate`-style review pass over intaked rows
**when the noise warrants it** — not preemptively. The TMDB-match "skip + log → human
review" sink (below) is the natural home for that pass.

- Add a `release_calendar` block per entry in `admin/distributor_sources.json`
  (e.g. `{ "calendar_url": "...", "press_url": "...", "scraper": "kino_lorber" }`)
  so the source list stays the single config.
- New package `pipeline/distributors/` — one small module per label, each exposing a
  function returning a normalized list. One label failing must never abort the rest.
- Wire as a new intake pass ("Pass E: distributor calendars") in `pipeline/intake.py`,
  gated by a config flag (`enable_pass_e`), run in the daily CI orchestrator.

---

## The verification alert (the twist)

The calendar is a *promise* ("Label X releases Title Y on date D"). We check whether
reality kept it.

- On intake, the tracking entry carries `_expected_digital_date` and/or
  `_expected_theatrical_date` + `_expected_distributor` + `_expected_source_url`.
- Each daily run, after discovery, scan tracking for entries where
  **`_expected_digital_date <= today`** AND the film has **not** transitioned to
  `available` (i.e. discovery/JW still can't find it).
- **Only the digital date arms an alert.** A theatrical date is typically months ahead of
  any VOD/disc release NRW would ever show, so alerting on it would false-nag every
  theatrical-only entry from the day after its premiere. Theatrical-only rows (no digital
  date yet) ride the `--defer` change-detection *silently* until a digital release appears;
  if a later scrape learns the digital date, set `_expected_digital_date` and the alert
  arms then.
- Flag each in the **morning report Concerns** section:
  `⚠ Expected from <Distributor> on <date>, not found: <Title> (<source_url>)`
- Meaning of the alert (for the user): a slipped release date, a bad/stale scrape,
  or a real release we should chase manually. It is a signal, not an error.
- **Resolution / noise control:**
  - When the film transitions to `available`, clear the expectation (alert stops).
  - Keep alerting from the expected date onward while unfound, but cap the noise:
    after N days unfound (e.g. 14), downgrade from a daily Concern to a single
    "still missing" line, or move to a separate `admin/distributor_misses.json`
    the user can review on demand. (Decide N with the user.)
  - The `--defer` change-detection keeps watching regardless — the alert layer is
    independent of the transition logic.
- Implementation home: `scripts/morning_report.py` (new `--section` check or fold
  into the existing Concerns inputs). The morning skill already renders Concerns.

---

## The catch: detecting when a parked restoration reaches VOD (multiple discovery methods)

Separate problem from the verification alert above. A parked restoration is
tracked *before* it's watchable; the **catch** is knowing when its *specific new
version* actually reaches US VOD.

The design intent is **several independent discovery methods, each a real avenue on
its own** — built out deliberately for **coverage**, because no single method sees
every release (mainstream vs boutique, disc vs digital, heavily-covered vs
obscure). They **compound**: each catches releases the others miss. This is the
*opposite* of one gatekeeper with subordinate helpers — a growing portfolio of
peers, and we expect to keep adding methods as new avenues surface.

One hazard cuts across all of them — **version-blindness:** JustWatch/TMDB report
availability at the **film** level, not the **version** level, so they can't tell a
2025 4K restoration from a 2009 transfer on the same title (measured 2026-06-30:
**44% of parked restorations have an old transfer already streaming** while the
restoration itself is not on VOD). So any method that keys on bare *availability*
adds a version check before surfacing; a method that already reads the version
doesn't. That's a per-method refinement — not a rule that routes everything through
one catch.

Methods so far (peers; the list will grow):

- **News / press monitoring** — the news-gap "second cluster" (below) plus the
  Google News keyword feed. Event-driven and cheap; catches well-covered releases
  as they ship; blind on obscure titles.
- **JustWatch / provider change detection** — a new provider or a new digital `_4K`
  offer on a tracked title. Broad reach; version-blind, so it adds a version check.
- **Listing-description scan** — Playwright-read the Amazon/Apple synopsis for
  restoration credits. Version-aware when the listing spells it out (absence is
  inconclusive).
- **Grounded per-film research** — reads the restored cut's runtime, 4K/Dolby
  Vision specs, and the credited lab to decide *restoration vs old transfer*, with
  sources (`gemini_scraper/restoration_vod.py`, per the catch plan under
  `.claude/plans/`). A strong standalone method — validated 2026-06-28/30 on every
  hard case (Gold Rush, Fight Club, Yi Yi) — that also runs as a periodic sweep to
  catch silent/obscure releases nothing else flagged.
- **Verification alert** — a calendar promise coming due (see above).

Each method has different coverage gaps (obscure vs mainstream, disc vs digital,
cheap-continuous vs expensive-periodic) — which is the whole reason to run several.

### News-gap "second cluster" method (added 2026-06-30 — one discovery method among several)
Idea (user, 2026-06-30): a restoration that reaches VOD throws **two separated
bursts** of press — an announcement cluster (Cannes Classics / "4K restoration
premieres"), a gap of months, then a home-release cluster ("now on 4K UHD /
digital / streaming"). Watching each parked title's Google News timeline for that
**second cluster** is a cheap, event-driven "something shipped — look now" trigger.

Tested 2026-06-30 — windowed monthly Google News RSS over 13 films spanning
outcomes (`/tmp/news_timeline.py`, sandbox). Vocab buckets per month: **ANN**
(restoration/Cannes/premiere), **THE** (theatrical/screening), **DISC**
(Blu-ray/UHD/SteelBook), **DIG** (digital/VOD/streaming/rent/buy/platforms).

- **Confirmed directionally.** Converters show announcement → gap → a late **DIG**
  burst; disc-only show a late **DISC** burst with no digital; stallers show only
  ANN/THE chatter, no second cluster. E.g. Gold Rush (staller): `ANN×8` at Cannes,
  then 13 months of only ANN/THE. Hard Boiled (converter): `ANN×6` May → `DIG`
  June = its actual VOD date. Second-cluster timing matched the ~4-month median
  lag, so a **monthly** re-check is the right cadence.
- **Caveat 1 — blind on obscure titles.** 7th Heaven, Shoulder Arms generate
  `n≈1/month` — too little press for any cluster. These archival/boutique
  restorations are exactly the lane's target, so news-gap has good precision but
  **low recall on the obscure end**; it cannot be the sole catch.
- **Caveat 2 — "digital" is leaky + version-blind.** It fires when a digital
  release is *announced*, not when it's live (Dogma: `DIG` in June, actual VOD
  December), and it fires for a disc-only title's *old transfer* being digital
  (Return of the Living Dead). So a "digital" burst here isn't proof the
  restoration is on VOD — this method adds the version check before surfacing, the
  same safeguard the JW method uses.

Role: a standalone, event-driven discovery method for the ~half of titles with real
press coverage; it doesn't need to see everything — the obscure/silent half is
covered by other methods (e.g. the periodic research sweep). Reuse the Google News
RSS windowed-sweep machinery already prototyped (`pipeline/distributors/googlenews.py`);
per-title timeline + vocab tagging is `/tmp/news_timeline.py`.

## Data model

- `admin/distributor_sources.json` — extend each label with scrape targets.
- Tracking entry (via `get_tracking_db()` — never write `movie_tracking.json` raw):
  `status='tracking'`, `_discovery_source='distributor_calendar'`,
  `_expected_digital_date`, `_expected_theatrical_date`, `_expected_distributor`,
  `_expected_source_url`, plus reissue flags (`_reissue`, `reissue_label`, and the defer
  baseline fields) for old-film restorations.
- Optional `admin/distributor_calendar.json` — raw scraped rows (audit trail +
  re-match without re-scraping). Decide whether the tracking entry alone is enough.

## TMDB matching (the hard part)
Calendar rows are title strings; the queue needs a TMDB id. Reuse the generator's
existing TMDB search. Match on title + release year. **Prefer "unmatched → skip + log"
over a bad auto-match** — a wrong id pollutes tracking.

**Named sink for low-confidence rows: `admin/distributor_unmatched.json`.** Anything that
doesn't clear the auto-match confidence bar (no match, multiple plausible matches, or a
title-only match with a year mismatch) is written here as a row — `{source_title, year,
distributor, source_url, candidates:[{tmdb_id,title,year}], reason}` — instead of being
silently intaked or buried in a log. This file is the human-review queue: the eventual
`/curate`-style pass reads it, and a confirmed match gets promoted into intake. Without a
named destination, "surface for human review" has nowhere to surface to.

---

## Phasing
1. **Prototype the aggregator first (cheapest, no 403).** Parse one month of
   `physicalmedia.news/upcoming` → normalize → TMDB-match → intake with expectation
   fields → confirm normal discovery picks it up. Proves the whole pipeline end-to-end
   without touching bot protection.
2. **Add the Google News RSS feed** (`"4K restoration"`) for label-agnostic coverage; route
   its noisier rows through the taste/match gate (see Quality gate above).
3. **Verification alert.** Wire the expected-date check into the morning report.
4. **Fill gaps per label** — newsletters first, then headless per-label calendar/press
   pages only for labels the lighter sources miss. *This is where the 403 work lives, if
   ever* — no longer the gating first step.
5. **Wire Pass E** into the daily orchestrator behind `enable_pass_e`; verify in CI.
6. **Tune** the curated label list, taste gate, and alert thresholds with the user.

> **Each source is a gate, not a guaranteed step.** This is exploratory: if a source doesn't
> pan out (unparseable, too noisy, coverage gap), log what was learned *in this doc* and
> check with the user for the next source to try before building further on it. Sources will
> be added/dropped through that back-and-forth — the plan expects it.

## Subproject structure
- Branch: `distributor-tracking`.
- Code: `pipeline/distributors/` (one module per label) + `pipeline/intake.py` Pass E.
- This doc is the living plan — the owning agent updates it as it learns each site's
  quirks (403 method, parser selectors, match edge cases).

## Open questions / risks
- **403 / bot protection per site** — *demoted* from gating unknown to fallback risk now
  that three no-403 sources are verified. Only relevant if a specific label is missed by
  the aggregator + news feed + newsletter and we fall back to scraping its own site.
- **Aggregator single point of failure** — `physicalmedia.news` covers ~9 labels in one
  scrape, so one layout change breaks them all at once. Mitigation: it's one parser to fix
  (not six), the Google News feed is an independent backstop, and failures log to the
  morning report. Confirm the page is reliably parseable before depending on it.
- **News-feed noise / taste** — the "4K restoration" feed mixes disc, VOD, theatrical-only
  re-runs, and marketing; titles are buried in prose. Needs fuzzy title extraction + the
  taste/match gate. Watch the false-positive rate; this is the trigger for the /curate pass.
- **Historical backfill ("going backwards")** — Google News RSS returns recent items only;
  older restorations need paginated queries / Wayback. Decide whether a one-time backfill is
  worth it or forward-only tracking is enough.
- **Maintenance** — scrapers break when sites change. Keep isolated; log failures
  into the morning report so breakage is visible.
- **Theatrical-only vs digital** — calendars often list theatrical first. Fine:
  `--defer` parks those in tracking until the digital release.
- **Dedup** — skip films already in tracking or the reissue queue.
- **Alert noise threshold (N days)** — decide with the user.
- **Curated label scope** — start: Kino Lorber, Criterion, GKIDS, Janus,
  Grasshopper Film, Film Movement. Confirm with user.
- **TMDB mismatch** — wrong id pollutes tracking; bias toward skip+log.

## Key files
- `admin/distributor_sources.json` — curated label config (extend)
- `pipeline/intake.py` — `collect_reissue_candidates` (Pass D pattern); add Pass E
- `pipeline/distributors/` — new per-label scrapers (to create)
- `scripts/morning_report.py` — verification alert (Concerns)
- `pipeline/reissue_research.py` — downstream enrichment (already distributor-aware)
- `scripts/confirm_reissue.py` — `--defer` change-detection (home for theatrical-only)
- `scripts/build_distributor_lookup.py` — existing reactive labeling (reference)

## Out of scope
- Replacing TMDB/JustWatch discovery for normal new releases.
- TMDB company-ID-based distributor discovery (verified non-viable above).
- Social-media scraping (optional, later, lowest priority).
