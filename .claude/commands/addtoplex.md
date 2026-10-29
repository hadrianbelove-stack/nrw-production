---
description: Copy a downloaded movie onto the personal Plex NAS and trigger a scan
argument-hint: [title or partial filename to find in Downloads]
allowed-tools: Bash, Read
---

Add a downloaded movie file to the owner's personal Plex library (CCCNas). This is
entirely separate from the NRW wall — it never touches data.json. It's for the
owner's own collection, and the on-site button for this is labeled "NRW", not "Plex"
(private use, not the public AVOD "Watch on Plex" platform button).

**Argument**: $ARGUMENTS (a search term to find the file in ~/Downloads, e.g. "tiny fugitives")

---

## Step 1 — Find the file(s)

```bash
ls -la ~/Downloads | grep -i "$ARGUMENTS"
```

If more than one file matches (e.g. two different scene releases of the same movie),
stop and ask the user which one to use — do not guess. Scene-release filenames are
not reliable title/year sources either; confirm the clean title and year with the
user before continuing (e.g. "Tiny Fugitives", 2026).

---

## Step 2 — Check the NAS is mounted

```bash
mount | grep -i "192.168.4.102"
```

If nothing matches, tell the user to mount the share first and stop.

---

## Step 3 — Copy, verify, scan, confirm

```bash
cd /Users/hadrianbelove/Downloads/nrw-production
/usr/bin/python3 scripts/add_to_plex.py "<full source path>" --title "<Clean Title>" --year <YYYY>
```

This copies the file into `/Volumes/Media/MOVIES/<Title> (<Year>)/`, verifies the
copy byte-for-byte, triggers a Plex library scan via the API (using `PLEX_TOKEN` /
`PLEX_SERVER` from `.env` — never prints the token), and polls for up to 60s to
confirm Plex actually picked it up.

If it reports a size mismatch, it already cleaned up the bad copy — nothing to do,
just re-run.

If it times out without confirming, tell the user the file is safely on the NAS but
Plex hasn't matched it yet — don't delete the source, suggest checking back in a
minute.

---

## Step 4 — Delete the original, only after Plex confirms it

If Step 3 printed "Confirmed in Plex", ask the user to confirm before deleting (even
though this command's whole point is to do that) — then:

```bash
rm "<full source path>"
```

Never delete before the "Confirmed in Plex" line has actually printed.

---

## Notes for future runs

- `PLEX_SERVER` in `.env` is the local LAN address (`http://192.168.4.102:32400`) —
  correct for this script, since it's a plain HTTP request from Python, not a
  browser. Do NOT reuse that address for the website or tvOS unlock screen — those
  are HTTPS pages and will silently fail to fetch an `http://` address (mixed
  content). The website/tvOS unlock flow needs the `https://…plex.direct:32400`
  address instead.
- If there are duplicate downloads of the same title (different releases), confirm
  which to keep with the user and mention the other one should probably be deleted
  from Downloads too, rather than deleting it silently.
