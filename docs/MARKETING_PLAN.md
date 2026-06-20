# NRW Marketing Plan

*Working draft — last updated 2026-06-20*

## Goal & constraints

- **Primary goal:** grow the audience (reach-first).
- **Bandwidth:** ~2 hours/day. Maximize systems and automation without sacrificing quality. Hadrian writes the newsletter himself.
- **Core principle:** marketing is mostly *distributing assets NRW already produces* (capsules, pull quotes, posters, trailer clips, slop verdicts) — not making new ones from scratch. Automation packages; the human decides and writes.

## Positioning

NRW's edge is **taste**, not "new releases" (everyone has those). The differentiator is curation plus an honest anti-slop stance — most sites would never publish their rejections.

One promise the whole brand hangs on:

> **The good new movies, the day they hit streaming — and an honest word on the rest.**

*(Draft line — to be sharpened.)*

## The funnel

Three layers, each with one job:

| Layer | Job |
|---|---|
| **Socials** | Reach. Make strangers feel the taste and click. |
| **Site / apps** | The product. Where people browse the wall. |
| **Newsletter (Substack)** | Capture. Convert a one-time visitor into an owned subscriber. |

Every social post must point somewhere (site or Substack). Dead-end posts kill growth. Even though the goal is reach, the newsletter is what makes reach *compound* — it is not a side project.

## Channels (start few, do them well)

Start with these three. Resist adding more until they hum.

- **Substack** — weekly, written by Hadrian. The anchor.
- **Letterboxd** — highest-fit film audience on the internet; lists/reviews map 1:1 onto NRW output. Best targeting, low effort.
- **Instagram** — posters + pull quotes are native to it. Best top-of-funnel reach.

**Phase 2:** Reels / TikTok (trailer clip + one-line capsule). Biggest reach multiplier but most time — add only once the above are on rhythm.

Skip the rest for now. "Basic socials everywhere" burns a one-person operation's hours on nothing.

## Automation strategy

The pipeline already produces, per movie: poster, capsule, pull quote, RT/IMDb, trailer clip, slop verdict, watch links. That's a finished social post already sitting in `data.json` — it just isn't *packaged* for posting.

**High-leverage build #1 — daily content-pack generator.**
A script reads the day's new arrivals from `data.json` and outputs ready-to-post assets: poster sized per platform, capsule as caption, pull quote as hook, link attached. Each morning you open a folder, pick the one or two worth posting, post them. Time goes to judgment and writing, not resizing and link-hunting. *(To be spec'd and approved before any code is written.)*

**Build #2 — Letterboxd CSV export** (see below).

**What stays human, always:** the newsletter prose, and the final yes/no on every post. Automation drafts; the human decides. That's how quality survives scale.

## Letterboxd specifics

Letterboxd is deliberately *not* automation-friendly. Three ways to interact, ranked by realism:

1. **CSV list import — the one real automation seam.** Import a CSV straight into a list/watchlist/diary via Settings → Import. Format takes title + year or IMDb/TMDB ID — all already in `data.json`. Workflow: a script generates the CSV, you upload it, the list updates (e.g. "NRW — New on Streaming"). Upload is a manual click (no API); lists must be <1 MB (non-issue at our volume).
2. **Official API — don't count on it.** Request-only beta. They explicitly decline access for recommendation projects and "LLM or GPT-related use" — i.e. exactly NRW. Plan as if the answer is no.
3. **Manual posting — the actual growth engine.** Reach comes from reviews and lists, not bulk imports. The capsule *is* the review. A few capsule-as-reviews per week on films worth a real take is what earns followers.

**Recommended Letterboxd pattern:**
- *Automate:* generate Letterboxd CSV from `data.json` → upload weekly to keep an "NRW — New on Streaming" list current.
- *By hand:* post a few capsule-as-reviews/week on the standouts.
- *For free:* every account emits RSS of its activity — can later syndicate to other channels or into the newsletter.

*(Read-only scraper libraries like `letterboxdpy` exist if we ever want to pull Letterboxd ratings back into enrichment — separate idea from posting.)*

## Weekly rhythm (fits ~2 hrs/day)

- **Mon–Fri (20–30 min/day):** review the content pack, post 1 to Letterboxd + IG, reply to comments. Early-stage engagement is what actually grows you.
- **One focused block:** write the week's newsletter — curate the 5–8 arrivals worth a reader's evening, in your voice. The slop you *rejected* is great material too ("what we skipped and why").
- The daily site curation you already do **is** the content engine — you're routing existing work to new places, not making new work.

## Recurring formats (never face a blank page)

- **"5 that quietly hit streaming this week"** — the newsletter spine.
- **"Slop or not?"** — most ownable, most shareable. Nobody else publishes their rejections.
- **Pull quote of the week** over a poster — pure Instagram.

## First steps (in order)

1. **Claim names everywhere now** — Substack, Letterboxd, Instagram, TikTok, Bluesky — even channels not used yet. Cheap insurance.
2. **Nail the positioning line.** Everything hangs on it. Sharpen the draft above.
3. **Set up the Substack** + add a signup prompt on the site.
4. **Spec the content-pack generator** for approval — the multiplier for everything else.
5. **Spec the Letterboxd CSV export** — small, low-risk pipeline add.

## Sources (Letterboxd, verified 2026-06)

- [Do you have an API? — Letterboxd](https://support.letterboxd.com/hc/en-us/articles/15269070369551-Do-you-have-mobile-apps-or-an-API)
- [Importing data — Letterboxd](https://letterboxd.com/about/importing-data/)
- [Can I import films/ratings/lists? — Letterboxd](https://support.letterboxd.com/hc/en-us/articles/15268993752719-Can-I-import-films-ratings-or-lists-from-other-services)
- [API beta — Letterboxd](https://letterboxd.com/api-beta/)
