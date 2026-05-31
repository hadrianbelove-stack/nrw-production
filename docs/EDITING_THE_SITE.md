# Editing the Site (data.json) — Canonical Workflow

The wall is driven by `data.json` (one big file, ~800 movies). This is the
single reference for editing it safely — adding a quote, fixing a trailer or
poster, correcting a field, adding/removing a movie. Follow it and you will
not get merge conflicts or silently lose curated data.

## Why edits conflict (the root cause)

`data.json` is **rewritten in full by CI every morning** (new `generated_at`,
reordered keys, new arrivals, archived movies). So a local copy that's a few
hours old has diverged across the *whole file*. Two failure modes follow:

1. **Stale edit → merge conflict.** You edit an old `data.json`, try to push,
   and git can't reconcile thousands of reformatted lines.
2. **Full-rewrite → data loss.** Running `generate_data.py` locally re-dumps
   all movies and can **wipe curated pull quotes** (the inject rebuilds them
   from gitignored local caches; a cache-less checkout deletes them). This
   actually happened on 2026-05-21 — a single stale run blanked 38 quotes.

## The three golden rules

1. **Pull first, push immediately.** `git pull origin main` right before you
   edit, and push the moment you're done. Never let a local `data.json` sit
   across a CI run.
2. **Surgical, never wholesale.** Change only the target record(s) on top of
   fresh `origin/main`. Never commit a full pipeline re-dump for a small edit.
3. **Never merge `data.json`.** On conflict, re-apply your change onto fresh
   `origin/main`. Do **not** `git checkout --ours/--theirs` — it silently
   loses `status=available` transitions (see CLAUDE.md).

And: **one writer at a time.** Don't run a second agent (or a long pipeline)
that touches `data.json` in the same working directory simultaneously. For
parallel work, use an isolated `git worktree`.

## Which tool for which edit

Prefer the purpose-built tools over hand-editing. They pull-first and commit
atomically (data.json + companion caches together), which is what prevents the
quote-wipe landmine.

| You want to… | Use |
|---|---|
| Add/edit **pull quotes** | `/curate` (pull-quotes stage) — keeps the cache in sync |
| Write/rewrite a **capsule** (editorial text — stored in `capsule` field, shown instead of TMDB synopsis) | `/capsule` |
| Fix a **trailer, poster, TMDB synopsis, links, TMDB ID**, or any field | `/correct`, or `scripts/edit_movie.py` |
| **Add / remove** a movie | `/add-movie` / `/remove` |
| Re-enrich **one** movie | `generate_data.py --enrich-id <id>` (single record) |
| Re-enrich a **fresh** batch (the daily job) | let CI run, or `/daily-update` |

> Never use a bare `generate_data.py --enrich` (no id) on a local checkout to
> fix one movie — it re-runs the whole display pass and risks the side effects
> above. Use `--enrich-id` or `edit_movie.py`.

## The one-command helper: `scripts/edit_movie.py`

For any small field edit, this does pull → surgical single-record change →
commit (with the data-commit token) → push, atomically. It refuses to run on a
dirty `data.json`, and on a rejected push it rebases and retries once. It never
re-dumps the whole file, so it can't wipe quotes or re-categorize other movies.

```bash
# change a trailer
/usr/bin/python3 scripts/edit_movie.py "Miroirs No. 3" --trailer <youtube-url>

# fix arbitrary fields (dotted keys for nested)
/usr/bin/python3 scripts/edit_movie.py 1178602 --set rt_score=95% --set links.wikipedia=<url>

# set poster / synopsis
/usr/bin/python3 scripts/edit_movie.py "Strange Creatures" --poster <url>
/usr/bin/python3 scripts/edit_movie.py "Strange Creatures" --synopsis "New synopsis."

# add a pull quote (writes data.json AND the cache so it survives re-runs)
/usr/bin/python3 scripts/edit_movie.py "Normal" \
    --add-quote "A quietly devastating debut." --critic "Jane Doe" --outlet "IndieWire"

# preview without writing, or commit without pushing
/usr/bin/python3 scripts/edit_movie.py "Normal" --trailer <url> --dry-run
/usr/bin/python3 scripts/edit_movie.py "Normal" --trailer <url> --no-push
```

- Movie lookup: exact TMDB id, else case-insensitive title substring. Ambiguous
  titles list candidates and stop.
- IDs are compared with `str()` (data.json mixes int/string ids).

## When you must hand-edit (rare)

If no tool fits, replicate the surgical pattern by hand: `git pull`, load
`data.json`, change only the target record, write with
`json.dumps(data, indent=2, ensure_ascii=False)` (no trailing newline), then
`git add data.json && NRW_ALLOW_DATA_COMMIT=1 git commit -m "… APPROVED: DELETE"
&& git push`. The `APPROVED: DELETE` token is required by the pre-commit hook
whenever the edit removes lines.
