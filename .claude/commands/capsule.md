---
description: Generate capsule descriptions — 3 variants, user edits, approve to bank + site
argument-hint: [movie title]
allowed-tools: Bash, Read, Grep, Edit, Write, AskUserQuestion
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

---

## Step 2 — Present capsules to user

Show all 3 variants clearly numbered, with word counts. Format them so the user can easily compare:

```
## Capsule Variants for [Title] ([Year])

**1.** [capsule text] _(XX words)_

**2.** [capsule text] _(XX words)_

**3.** [capsule text] _(XX words)_
```

Then ask the user: "Pick one, remix parts, or write your own version."

---

## Step 3 — Receive user's choice or rewrite

The user will either:
- Pick a number ("2" or "use 2")
- Provide their own rewrite (they'll paste text)
- Ask for more variants ("try again" / "more")

If they ask for more: re-run Step 1 with `--force`.
If they pick a number or provide text: move to Step 4.

---

## Step 4 — Approve and publish

Take the final capsule text (either the picked variant or the user's rewrite).

1. Write the capsule text to `cache/rewrite.txt`
2. Run the approve command:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 scripts/write_capsule.py approve "$MOVIE_TITLE" --file cache/rewrite.txt 2>&1
```

This does TWO things automatically:
- Adds to `cache/approved_capsules.json` (training bank — improves future generations)
- Updates `data.json` synopsis field (goes live on site)

3. Commit and push:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git add data.json cache/approved_capsules.json cache/capsule_cache.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Capsule: [TITLE] APPROVED: DELETE" && git push origin main
```

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
- This is an AUTHORIZED override of the CLAUDE.md data rule — the user is explicitly requesting data.json modification via this command.
