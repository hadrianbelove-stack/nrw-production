---
description: Generate capsule descriptions — 3 variants, user edits, approve to bank + site
argument-hint: [movie title]
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion, WebSearch
---

Write an editorial capsule for a movie on the NRW wall. This is an interactive workflow.

**Argument**: $ARGUMENTS (movie title — partial match OK)

---

## Step 1 — Find the movie and generate 3 capsule variants

Run the capsule writer to generate 3 variants:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py "$ARGUMENTS" --force --variants 3 --skip-verify 2>&1
```

If "No movie found" or "Multiple matches": report and stop.

Also read the movie's cast from data.json (`movie.crew.cast`) — you'll need it for Step 2b.

---

## Step 2 — Present capsules to user

Show all 3 variants clearly numbered with word counts, then the **FACTOID PRIMER** below them, then the **SUGGESTED LINKS** block (Step 2b). This is the required format — never drop the primer or links. **This is the single source of truth for capsule presentation — `/curate` defers to this format.**

```
## Capsule Variants for [Title] ([Year])

*directed by [Director] | [Genres, up to 2] | [Runtime] min | [Country] | [Platform(s)]*
[Keywords up to 6, space-separated with · — then badges: [SLOP] if is_slop=true, [VIRTUAL SCREENING] if is_virtual_screening=true, [PREORDER] if digital_date is in the future — omit this line entirely if no keywords and no badges apply]

**1.** [capsule text] _(XX words — hook)_

**2.** [capsule text] _(XX words — filmmaker)_

**3.** [capsule text] _(XX words — critical)_

---

**FACTOID PRIMER**
- [8-12 bullets minimum — production facts, director quotes, BTS details, festival context,
   distribution story, shooting conditions, budget, years-in-making, cast surprises,
   cultural context, audience reactions, comparisons, awards. More is better — the editor
   picks what to use. Every bullet should be SPECIFIC: a number, a name, a place, a date.
   Vague bullets ("the film explores themes of identity") are useless.]
- ...

---

**SUGGESTED LINKS**
1. [Name](https://en.wikipedia.org/wiki/Name) — cast / role / context
2. ...
```

Each variant takes a different approach: one anchored in premise/hook, one in filmmaker/production context, one in critical reception. Label the approach after the word count as shown above.

Then ask: "Pick 1, 2, or 3 — paste a rewrite — or skip."

---

## Step 2b — Suggested Wikipedia links

**Director and cast links:**
Read `movie.links.director_wiki` and `movie.links.cast_wiki` from data.json. Embed whatever is there wherever their names appear in the capsule text — no user approval needed. If a name has no URL, skip it silently (many actors don't have Wikipedia pages).

**SUGGESTED LINKS — for user approval only:**
Identify non-cast/non-director named entities that appear in the capsule text: historical figures, referenced filmmakers, organizations, other works. Up to 3. WebSearch each for a Wikipedia page. Present only these to the user (numbered). If none exist, omit the SUGGESTED LINKS block entirely.

Wikipedia URLs with parentheses (e.g. `_(painter)`, `_(film)`): encode `(` as `%28` and `)` as `%29`.

---

## Step 3 — Receive choice, then pre-embed links

The user will either:
- Pick a number ("2" or "use 2")
- Provide their own rewrite (they'll paste text)
- Ask for more variants ("try again" / "more")

If they ask for more: re-run Step 1 with `--force`.

**Once they pick a variant or provide a rewrite:**

1. Silently embed director/cast links from data.json (`director_wiki`, `cast_wiki`) wherever their names appear in the text — bold names become `**[Name](url)**`, plain text becomes `[Name](url)`.
2. Embed any approved SUGGESTED LINKS the same way.
3. Show the modified capsule with all links visible.
4. Ask: "Approve with these links — or say 'remove [Name]' to drop any."
5. If user removes any: strip that link, show updated capsule again.
6. When user approves: proceed to Step 4.

---

## Step 4 — Approve and publish

Take the final capsule text (with embedded links).

**First, pull latest** so you publish onto current data:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git pull origin main
```

1. Write the capsule text to `cache/rewrite.txt`
2. Run the approve command:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "$MOVIE_TITLE" --file cache/rewrite.txt 2>&1
```

This does TWO things automatically:
- Adds to `cache/approved_capsules.json` (training bank — improves future generations)
- Updates `data.json` **capsule** field (goes live on site — NOT synopsis, which is the TMDB fallback text and gets overwritten by the daily pipeline)

3. Commit and push:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))
```

Commit **only** `data.json`. Cache files are gitignored — do not `git add` them.

---

## Step 5 — Report

Tell the user:
- The approved capsule (show final text)
- Confirmed it's in the training bank (show count)
- Confirmed it's live in data.json
- Push status

---

## Important Notes

- ALWAYS generate with `--force` so the user gets fresh variants every time
- ALWAYS use `--skip-verify` during the interactive flow (faster iteration)
- The style guide at `gemini_scraper/capsule_style_guide.txt` governs voice. If the user gives feedback about tone, update the style guide.
- Names should be **bold**, film titles should be *italic* in the capsule text (markdown formatting).
- If the user's rewrite doesn't have bold names or italic titles, add them before approving.
- Wikipedia URLs with parentheses: encode `(` as `%28` and `)` as `%29` — Wikipedia resolves these correctly.
- This is an AUTHORIZED override of the CLAUDE.md data rule — the user is explicitly requesting data.json modification via this command.
