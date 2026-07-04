#!/usr/bin/env python3
"""Pull-quote helper for /curate Stage 4 Step B.

Replaces the ad-hoc reading/editing of cache/pull_quotes_combined.json (3.5MB)
that used to happen inline. Prints one film's quotes presentation-ready
(matches .claude/curate_templates.md → Quotes block), and saves the pick.

Usage:
  get_quotes.py "TITLE" YEAR
      Print the film's quotes: RT/critic quotes grouped by outlet (cache
      order), then up to 10 Letterboxd. Numbered, wrapped to 72 cols.

  get_quotes.py --select "TITLE" YEAR --num N [--text-file F] [--keep-url]
      Mark quote N selected in the cache (text overridden by F if given —
      the user's trim IS the final version) and inject it into the movie's
      pull_quotes in data.json. The review_url is verified first
      (gemini_scraper.pull_quotes.verify_quote_url); bad/unloadable links
      are saved as null with a ⚠ line. --keep-url skips verification and
      keeps the URL (the "keep link" escape hatch — also for short titles,
      where the verifier false-flags; see memory verify-quote-url-short-title-bug).

  get_quotes.py --select "TITLE" YEAR --custom --critic C --outlet O \
      --text-file F [--url U]
      Save a quote that isn't in the cache (creates the cache entry too).

  get_quotes.py --skip "TITLE" YEAR
      Write pull_quotes: [] to data.json (reviewed-and-skipped). Refuses if
      the movie already has quotes unless --force is passed.

Numbering is deterministic: display and --select build the same ordered list,
so the number shown is the number saved.
"""
import argparse
import json
import os
import signal
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.json_io import data_lock, atomic_dump

signal.signal(signal.SIGPIPE, signal.SIG_DFL)

CACHE = "cache/pull_quotes_combined.json"
DATA = "data.json"
LB_MAX = 10  # Letterboxd quotes to show (all if fewer)
WRAP = 72
SPOILER_PREFIX = "This review may contain spoilers"


def _atomic_write(path, obj):
    """Torn-write guard; see pipeline/json_io.py. Callers that read-modify-write
    must also hold data_lock() so concurrent windows can't erase each other."""
    atomic_dump(obj, path)


def _find_entry(cache, title, year):
    """Find the cache entry for title/year. Exact key first, then fuzzy."""
    key = f"{title}_{year}"
    if key in cache:
        return key
    tl = title.lower()
    matches = [k for k, e in cache.items()
               if str(e.get("title", "")).lower() == tl
               and str(e.get("year", "")) == str(year)]
    if not matches:
        matches = [k for k, e in cache.items()
                   if str(e.get("title", "")).lower() == tl]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous title — {len(matches)} cache entries match:")
        for k in matches:
            print(f"  • {k}")
        sys.exit(1)
    return None


def _ordered_quotes(entry):
    """One flat numbered list: RT/critic quotes grouped by outlet (first-seen
    order, cache order within), then up to LB_MAX Letterboxd. Each item is
    (group_label, quote_dict). Empty-text quotes are dropped."""
    items = []
    by_outlet = {}
    for q in entry.get("rt_quotes", []):
        if not (q.get("text") or "").strip():
            continue
        by_outlet.setdefault(q.get("outlet") or "Unknown outlet", []).append(q)
    for outlet, qs in by_outlet.items():
        for q in qs:
            items.append((outlet, q))
    lb = [q for q in entry.get("lb_quotes", []) if (q.get("text") or "").strip()]
    for q in lb[:LB_MAX]:
        items.append(("Letterboxd", q))
    return items, max(0, len(lb) - LB_MAX)


def _fmt_quote(n, group, q):
    text = q.get("text", "").strip()
    prefix = f"{n}. "
    indent = " " * len(prefix)
    if group == "Letterboxd":
        attribution = f"— @{(q.get('critic') or '?').lstrip('@')}"
    else:
        attribution = f"— {q.get('critic') or '?'}, {q.get('outlet') or group}"
    if q.get("selected"):
        attribution += "   ✓ selected"
    if text.startswith(SPOILER_PREFIX):
        url = q.get("review_url") or ""
        return f"{prefix}{attribution} → [read review]({url})"
    body = textwrap.fill(f'*"{text}"*', width=WRAP,
                         initial_indent=prefix, subsequent_indent=indent)
    return f"{body}\n{indent}{attribution}"


def display(title, year):
    cache = json.load(open(CACHE))
    key = _find_entry(cache, title, year)
    if key is None:
        print("⚠ No pull quotes in cache — morning batch may have missed this "
              "movie. Check Concerns in tomorrow's launchagent report.")
        return
    entry = cache[key]
    items, lb_hidden = _ordered_quotes(entry)
    if not items:
        print(f"⚠ Cache entry for {entry.get('title')} ({entry.get('year')}) "
              "exists but holds 0 quotes — treat as missing (skip quotes).")
        return
    print(f"{entry.get('title')} PULL QUOTES\n")
    prev_group = None
    for n, (group, q) in enumerate(items, 1):
        if group != prev_group:
            if prev_group is not None:
                print()
            print(f"**{group}**")
            prev_group = group
        print(_fmt_quote(n, group, q))
    if lb_hidden:
        print(f"\n({lb_hidden} more Letterboxd quote(s) in cache not shown — cap is {LB_MAX})")


def _verify_url(url, title, critic):
    """Run the standard review-URL check. Returns ok/no_url/bad_link/error."""
    if not url:
        return "no_url"
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from gemini_scraper.pull_quotes import verify_quote_url
        return verify_quote_url(url, title, critic)
    except Exception:
        return "error"


def _write_to_data(title, year, picked):
    """Inject/replace the quote in the movie's pull_quotes in data.json."""
    with data_lock():
        data = json.load(open(DATA))
        movies = data if isinstance(data, list) else data.get("movies", [])
        tl = title.lower()
        for m in movies:
            if m.get("title", "").lower() == tl and str(m.get("year", "")) == str(year):
                quotes = m.get("pull_quotes") or []
                # Re-picking the same critic+outlet replaces (a re-trim), else append.
                quotes = [q for q in quotes
                          if not (q.get("critic") == picked["critic"]
                                  and q.get("outlet") == picked["outlet"])]
                quotes.append(picked)
                m["pull_quotes"] = quotes
                _atomic_write(DATA, data)
                return True
    return False


def select(title, year, args):
    final_text = None
    if args.text_file:
        final_text = open(args.text_file).read().strip()

    # Cache read-modify-write happens under the lock; the (slow) URL
    # verification below runs after release so other windows aren't blocked.
    with data_lock():
        cache = json.load(open(CACHE))
        key = _find_entry(cache, title, year)

        if args.custom:
            if not (args.critic and args.outlet and final_text):
                print("--custom needs --critic, --outlet and --text-file")
                sys.exit(1)
            q = {"text": final_text, "critic": args.critic, "outlet": args.outlet,
                 "source": "manual", "verbatim": False, "selected": True,
                 "review_url": args.url or None}
            if key is None:
                key = f"{title}_{year}"
                cache[key] = {"title": title, "year": year,
                              "rt_quotes": [], "lb_quotes": []}
            bucket = "lb_quotes" if args.outlet.lower() == "letterboxd" else "rt_quotes"
            cache[key].setdefault(bucket, []).append(q)
        else:
            if key is None:
                print("No cache entry for this movie — use --custom to add a quote by hand.")
                sys.exit(1)
            items, _ = _ordered_quotes(cache[key])
            if not args.num or not (1 <= args.num <= len(items)):
                print(f"--num must be 1–{len(items)} (as displayed by this script)")
                sys.exit(1)
            q = items[args.num - 1][1]
            q["selected"] = True
            if final_text:
                q["text"] = final_text

        _atomic_write(CACHE, cache)

    real_title = cache[key].get("title", title)
    url = None if args.no_url else q.get("review_url")
    if url and not args.keep_url and not args.custom:
        status = _verify_url(url, real_title, q.get("critic"))
        if status == "bad_link":
            print(f"⚠ Review link doesn't appear to be this movie/critic ({url}) "
                  "— saving quote without URL. If the user says \"keep link\", "
                  "re-run this exact command with --keep-url.")
            url = None
        elif status == "error":
            print(f"⚠ Review link couldn't be loaded ({url}) — saving without "
                  "URL. Re-run with --keep-url to keep it anyway.")
            url = None

    picked = {"text": q["text"], "critic": q.get("critic"),
              "outlet": q.get("outlet"), "review_url": url}
    if _write_to_data(real_title, cache[key].get("year", year), picked):
        print(f'Saved: "{picked["text"][:60]}..." — {picked["critic"]}, {picked["outlet"]}')
        print(f"  cache: selected=true  |  data.json: pull_quotes updated"
              f"  |  review_url: {picked['review_url'] or 'null'}")
    else:
        print(f"⚠ Saved to cache, but no movie titled {title!r} ({year}) in data.json "
              "— fix the title/year and re-run.")
        sys.exit(1)


def skip(title, year, force):
    with data_lock():
        data = json.load(open(DATA))
        movies = data if isinstance(data, list) else data.get("movies", [])
        tl = title.lower()
        for m in movies:
            if m.get("title", "").lower() == tl and str(m.get("year", "")) == str(year):
                if m.get("pull_quotes") and not force:
                    print(f"⚠ {m['title']} already has {len(m['pull_quotes'])} quote(s) "
                          "— skipping would delete them. Re-run with --force to wipe.")
                    sys.exit(1)
                m["pull_quotes"] = []
                _atomic_write(DATA, data)
                print(f"{m['title']} ({year}): pull_quotes set to [] (reviewed, skipped).")
                return
    print(f"⚠ No movie titled {title!r} ({year}) in data.json.")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("year")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--skip", action="store_true", dest="skip_mode")
    ap.add_argument("--num", type=int)
    ap.add_argument("--text-file")
    ap.add_argument("--no-url", action="store_true")
    ap.add_argument("--keep-url", action="store_true")
    ap.add_argument("--custom", action="store_true")
    ap.add_argument("--critic")
    ap.add_argument("--outlet")
    ap.add_argument("--url")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.select:
        select(args.title, args.year, args)
    elif args.skip_mode:
        skip(args.title, args.year, args.force)
    else:
        display(args.title, args.year)


if __name__ == "__main__":
    main()
