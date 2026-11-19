---
description: Revert a film that isn't really out yet — off the wall now, back on its own the day it's really out
allowed-tools: Bash, Read, Grep
---

Revert a film that was wrongly marked as new — usually the pre-order problem (still in theaters, a pre-order listing, a premature TMDB/JustWatch signal). This is a pull → work → push operation, like `/remove`.

**Argument**: $ARGUMENTS (movie title or TMDB ID)

**Revert is the OPPOSITE of `/remove`.** Remove = a title the owner never wants on the wall: gone for good. Revert = take it off now so it comes back on its own: the film goes back to tracking as a held film, JustWatch checks it every run, and it is put back on the wall the day it's really out (never dated on or before today). Never revert a removed title, and never `/remove` a film that just isn't out yet.

---

## Step 1 — Wait out today's update, then pull

```bash
gh run list --workflow daily-check.yml --limit 1 --json status
```

If the status is anything but `completed`, today's update is still running on GitHub: stop and tell the owner to revert after it finishes (usually within the hour). A revert pushed meanwhile can collide with the update's own push, and then that day's whole update fails to publish.

```bash
git pull origin main
```

## Step 2 — Find the movie

```bash
/usr/bin/python3 -c "
import json
d = json.load(open('data.json'))
q = '$ARGUMENTS'.lower()
for m in d['movies']:
    if q == str(m.get('id')) or q in (m.get('title') or '').lower():
        print(m.get('id'), '|', m.get('title'), '|', m.get('digital_date'), '| pre-order' if m.get('_is_preorder') else '')
"
```

Confirm the right film with the owner if more than one matches.

## Step 3 — Revert it

```bash
/usr/bin/python3 scripts/revert_movie.py $TMDB_ID
```

It refuses a removed title. It changes the tracking record (held, checked daily) and hides the wall entry (the next pipeline run purges it; nothing else on the wall changes). It comes back on its own only when JustWatch shows it watchable on something new since the revert (a new streaming offer, an Amazon rental going live), or when its Amazon page, read as "Pre-order" after the revert, later shows it for rent or sale — a new store listing or TMDB's date alone never brings it back, nor does an Amazon rental that went live before the revert. A same-day release counts: an Amazon rental that goes live later the same day brings it back the next day. If the script prints a `⚠ Note:`, tell the owner: a reissue or restoration (any film the wall shows as a restoration) comes back when something new to watch shows up under the original film on JustWatch after today (now and then that is the original's listing changing, not the restoration), and a hand-added film, a watch-link override or an Apple Music Live special may never show on JustWatch. If the script says the tracking file couldn't be saved, nothing changed: run it again.

## Step 4 — Push both files

```bash
git add data.json movie_tracking.json
NRW_ALLOW_DATA_COMMIT=1 git commit -m "Revert [TITLE] — not out yet, back on its own when it is APPROVED: DELETE"
git push origin main || (git pull --rebase origin main && git push origin main)
```

## Step 5 — Report

- Title + TMDB ID reverted, and that it comes back on its own the day it's really out
- Any `⚠ Note:` the script printed, word for word
- Confirm the push succeeded

(The admin's "Revert (not out yet)" button does Steps 1, 3 and 4 itself: it refuses while today's update is running (when `gh` can't answer it goes ahead, as this command does), catches up with GitHub if today's update landed but the Mac hasn't pulled it yet (fast-forward only; if it can't, it changes nothing and says so), then saves and pushes both files, and says so — or says why it couldn't.)
