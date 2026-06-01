---
description: Mark a movie as NOT slop — locks it visible and prevents re-classification
argument-hint: [movie title or TMDB ID]
allowed-tools: Bash, Read
---

Mark a movie as explicitly NOT slop. Sets `is_slop: false` in data.json and pushes immediately.

**`false` ≠ removing the field.** `null`/absent = unclassified (pipeline will re-classify next enrichment). `false` = human override, permanently visible. Use this when the classifier got it wrong.

Must push to GitHub — local changes to data.json are wiped by the launchagent's nightly `git checkout -- data.json`.

**This is an AUTHORIZED override of the CLAUDE.md data rule.**

**Argument**: $ARGUMENTS

---

## Why this sticks (durability)

The enricher only re-classifies when `is_slop` is `null`. Once `is_slop: false` is committed to data.json:
- CI enrichment propagates it from data.json into the new build (enricher.py lines 1178-1180)
- The slop classifier guard (`if movie_data.get('is_slop') is None`) skips re-classification
- Full rebuilds (`--full`) are also safe — same propagation logic applies
- The only thing that can undo it: a human running `/markslop`, or direct data.json edit

---

## Step 1 — Pull latest

```bash
git pull origin main
```

---

## Step 2 — Find the movie and show current status

```bash
/usr/bin/python3 -c "
import json
q = '$ARGUMENTS'.lower().strip()
data = json.load(open('data.json'))
matches = [m for m in data['movies']
           if q in m.get('title','').lower() or q == str(m.get('id',''))]
for m in matches:
    print(f\"  {m['title']} ({m.get('year','?')}) — ID:{m.get('id')} is_slop:{m.get('is_slop')} guess:{m.get('_is_slop_guess',False)} reason:{m.get('_slop_reason','none')}\")
if not matches:
    print('No match found')
"
```

If multiple matches, ask which one. If already `is_slop: false`, stop and tell the user.

---

## Step 3 — Apply the mark

```bash
/usr/bin/python3 -c "
import json
q = '$ARGUMENTS'.lower().strip()
data = json.load(open('data.json'))
matched = next((m for m in data['movies']
                if q in m.get('title','').lower() or q == str(m.get('id',''))), None)
if not matched:
    print('ERROR: movie not found')
    exit(1)
matched['is_slop'] = False
matched.pop('_is_slop_guess', None)
matched.pop('_slop_reason', None)
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f\"Marked as NOT slop: {matched['title']} (ID:{matched.get('id')})\")
"
```

---

## Step 4 — Commit and push (with conflict retry)

```bash
git add data.json
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Mark not-slop: [TITLE] APPROVED: DELETE"
```

Then push. If CI pushed between Step 1 and now, the push will be rejected. Handle it:

```bash
git push origin main || (git pull --rebase origin main && git push origin main)
```

If the rebase fails (data.json merge conflict), STOP. Do not force-push. Report the conflict to the user and ask them to re-run the command after resolving.

---

## Report

Tell the user:
- Movie title and ID marked
- Previous `is_slop` value → now `false`
- Push status (succeeded / retried and succeeded / failed with rebase conflict)
- Confirm: "Visible in all modes. CI and full rebuilds will not re-classify."
