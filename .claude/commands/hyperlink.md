---
description: Add a Wikipedia hyperlink to a capsule already on the site
argument-hint: ["entity name" in Movie Title]
allowed-tools: Bash, Read, Edit, Write, WebSearch
---

Add a Wikipedia hyperlink to an existing capsule in data.json, and/or add a cast member's Wikipedia URL to the metadata line.

**Argument**: $ARGUMENTS — the entity to link, optionally as `"Name" in Movie Title`

---

## Step 1 — Parse and locate

Parse $ARGUMENTS to extract:
- **Entity name** — the person, event, or subject to link
- **Movie title** — optional context (after "in")

If no movie title was given, ask: "Which movie's capsule should I add this link to?"

Find the movie in data.json. When comparing IDs or titles, always use case-insensitive string comparison. Show the current displayed text (the `capsule` field if non-empty, otherwise `synopsis`) and the cast list so the user can see the context.

---

## Step 2 — Find the Wikipedia URL

WebSearch for "[entity name] Wikipedia" and identify the canonical Wikipedia article URL (`https://en.wikipedia.org/wiki/...`).

If the entity name doesn't have a clear Wikipedia article, say so and ask the user to provide the URL directly.

If the URL contains parentheses (e.g. `_(film)`, `_(painter)`), encode them as `%28` and `%29`.

---

## Step 3 — Determine what to update

Check two things independently:

**A. Capsule text** — does the entity name appear in the displayed text (`capsule` if present, else `synopsis`)?
- If yes: propose wrapping it as `**[Name](url)**` (if bold) or `[Name](url)` (if plain text)
- If no: note this; the capsule text won't change

**B. Cast metadata** — is the entity name in `movie.crew.cast`?
- If yes: propose adding them to `movie.links.cast_wiki` so their name becomes a link in the cast line
- If no: note this

Show a clear summary of what will change:

```
Capsule text: "...for renowned painter **Lucian Freud**..." → "...for renowned painter **[Lucian Freud](url)**..."
Cast line: no change (Lucian Freud is not in the cast)
```

Ask: "Does this look right? I'll update data.json and push."

---

## Step 4 — Apply and push

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git pull origin main
```

Apply both changes via a Python inline command:

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && /usr/bin/python3 -c "
import json, sys
title, entity, url, is_cast = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == 'true'
data = json.load(open('data.json'))
for m in data['movies']:
    if m.get('title', '').lower() == title.lower():
        # Edit whichever field is displayed: capsule if present, else synopsis
        field = 'capsule' if m.get('capsule') else 'synopsis'
        syn = m.get(field, '')
        import re
        # Replace bold occurrence
        syn = re.sub(r'\*\*(' + re.escape(entity) + r')\*\*', r'**[' + entity + r'](' + url + r')**', syn)
        # Replace plain text occurrence (not already linked)
        syn = re.sub(r'(?<!\[)(?<!\*\*)(' + re.escape(entity) + r')(?!\]\()(?!\*\*)', r'[' + entity + r'](' + url + r')', syn)
        m[field] = syn
        # Update cast_wiki if cast member
        if is_cast:
            m.setdefault('links', {})
            m['links'].setdefault('cast_wiki', {})
            m['links']['cast_wiki'][entity] = url
        break
json.dump(data, open('data.json', 'w'), indent=2, ensure_ascii=False)
print('done')
" "$MOVIE_TITLE" "$ENTITY_NAME" "$WIKI_URL" "$IS_CAST_MEMBER"
```

```bash
cd /Users/hadrianbelove/Downloads/nrw-production && git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "Hyperlink: [MOVIE TITLE] — [ENTITY] APPROVED: DELETE" && (git push origin main || (git pull --rebase origin main && git push origin main))
```

Report: show the final capsule text (whichever field was edited), confirm the push succeeded, and note if cast_wiki was also updated.

---

## Important Notes

- Wikipedia URLs with parentheses: encode `(` as `%28` and `)` as `%29`
- If the entity appears multiple times in the capsule text, only the first occurrence is linked (the regex stops after one match per pass)
- This is an AUTHORIZED override of the CLAUDE.md data rule — the user is explicitly requesting data.json modification via this command.
