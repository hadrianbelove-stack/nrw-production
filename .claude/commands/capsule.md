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

Show all 3 variants clearly numbered with word counts, then the **FACTOID PRIMER** below them, then the **SUGGESTED LINKS** block (Step 2b). This is the required format — never drop the primer or links:

```
## Capsule Variants for [Title] ([Year])

**1.** [capsule text] _(XX words)_

**2.** [capsule text] _(XX words)_

**3.** [capsule text] _(XX words)_

---

**FACTOID PRIMER**
- [bullet: production fact, director quote, BTS detail, festival context, distribution story]
- ...

---

**SUGGESTED LINKS**
- [Name](https://en.wikipedia.org/wiki/Name) — cast / role / context
- ...
```

Then ask: "Pick 1, 2, or 3 — paste a rewrite — or skip."

---

## Step 2b — Suggested Wikipedia links

Generate the SUGGESTED LINKS block shown above.

**Always include**: the top 3 cast members from `movie.crew.cast` — WebSearch each for their Wikipedia page.

**Also include**: up to 3 more linkable entities — key historical figures, events, movements, or organizations referenced by the film. Skip the director (already linked in the site header).

If a cast member has no Wikipedia page, skip them silently. If no useful non-cast links found, just show the cast links.

Wikipedia URLs with parentheses (e.g. `_(painter)`, `_(film)`): encode `(` as `%28` and `)` as `%29`.

---

## Step 3 — Receive choice, then pre-embed links

The user will either:
- Pick a number ("2" or "use 2")
- Provide their own rewrite (they'll paste text)
- Ask for more variants ("try again" / "more")

If they ask for more: re-run Step 1 with `--force`.

**Once they pick a variant or provide a rewrite:**

1. Automatically embed ALL suggested links into the chosen text:
   - Entity name appears as `**bold**` → change to `**[Name](url)**`
   - Entity name appears as plain text → change to `[Name](url)`
   - Entity name not in the capsule text → skip (still saved to cast_wiki for the metadata line)
2. Show the modified capsule with links visible in the markdown
3. Ask: "Approve with these links — or say 'remove [Name]' to drop any."
4. If user removes any: strip that link, show updated capsule again
5. When user approves: this is the final text — proceed to Step 4

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

3. Write cast wiki links for each cast member from SUGGESTED LINKS that has a Wikipedia URL:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys
title, cast_wiki_json = sys.argv[1], sys.argv[2]
cast_wiki = json.loads(cast_wiki_json)
data = json.load(open('data.json'))
for m in data['movies']:
    if m.get('title', '').lower() == title.lower():
        m.setdefault('links', {})
        m['links']['cast_wiki'] = cast_wiki
        break
json.dump(data, open('data.json', 'w'), indent=2, ensure_ascii=False)
" "$MOVIE_TITLE" '{"Actor Name": "https://en.wikipedia.org/wiki/Actor_Name"}'
```

Only include cast members (not historical figures or events).

4. Commit and push:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && git push origin main
```

Commit **only** `data.json`. Cache files are gitignored — do not `git add` them.

---

## Step 5 — Report

Tell the user:
- The approved capsule (show final text)
- Which cast wiki links were saved (e.g. "Ellie Bamber and Derek Jacobi now linked in cast metadata")
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
