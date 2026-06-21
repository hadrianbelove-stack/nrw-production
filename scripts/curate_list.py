#!/usr/bin/env python3
"""Build (or mark) the /curate candidate list for a given stage.

Replaces the inline Python that used to live in .claude/commands/curate.md.
One filter, one place. Output is pipe-delimited rows the command renders as a
markdown table. Behavior is identical to the old inline scripts.

Usage:
  curate_list.py --stage selects|sections|slop|capsule [--window N]
  curate_list.py --mark STAGE ID [ID ...]        # watermark films as reviewed

Pipe columns per stage (after a one-line header):
  selects   i|title|year|rt|mc|imdb|buzz|services|wiki|trailer|rt_url|id
  sections  i|title|year|sections|wiki|id
  slop      i|title|year|slop_status|rt|imdb|trailer|wiki|why|imdb_link|id
  capsule   i|title|year|rt|needs|wiki|trailer|id
"""
import argparse
import json
import os
import signal
import sys
from datetime import date, timedelta

# Don't traceback when piped into head/less (closed pipe).
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

REVIEWED = "admin/curate_reviewed.json"
CAPSULES = "cache/approved_capsules.json"

# movie.filters key -> display name, and movie.genres values we surface
FILTER_NAMES = [
    ("is_indie", "Indie"),
    ("is_foreign", "Foreign"),
    ("is_documentary", "Documentary"),
    ("is_virtual_screening", "Virtual Screening"),
    ("is_restoration", "Restoration"),
]
GENRE_NAMES = ["Horror", "Action", "Comedy", "Family", "Thriller"]


def _load(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def _services(m):
    """Deduped streaming+vod service names, in order."""
    wl = m.get("watch_links", {}) or {}

    def aslist(v):
        return v if isinstance(v, list) else ([v] if v else [])

    out = []
    for x in aslist(wl.get("streaming")) + aslist(wl.get("vod")):
        n = x.get("service") if isinstance(x, dict) else str(x)
        if n and n not in out:
            out.append(n)
    return out


def _trailer(m):
    L = m.get("links", {}) or {}
    return L.get("trailer_hosted") or L.get("trailer") or ""


_NOTAB = None
def _buzz(m):
    """0-100 internet-attention score from the notability dossier (keyed by id).
    '--' when the film isn't in the dossier yet (run scripts/notability_sandbox.py)."""
    global _NOTAB
    if _NOTAB is None:
        _NOTAB = {}
        p = os.path.join(os.path.dirname(__file__), "..", "cache", "notability_dossier_SANDBOX.json")
        try:
            with open(p) as f:
                for film in json.load(f).get("films", []):
                    _NOTAB[str(film.get("id"))] = film.get("buzz_score")
        except Exception:
            pass
    b = _NOTAB.get(str(m.get("id")))
    return str(b) if b is not None else "--"


def _in_window(m, from_date, today):
    dd = m.get("digital_date", "") or ""
    return from_date <= dd <= today


def _skip_old(m, current_year):
    """Stages 1-3 drop auto-restorations and 10+-year-old/remaster titles
    (reissues are exempt). Stage 4 does NOT call this."""
    if m.get("filters", {}).get("is_restoration") and not m.get("_reissue"):
        return True
    if m.get("_reissue"):
        return False
    t = m.get("title", "")
    y = m.get("year", 0) or 0
    if any(k in t for k in ("Remaster", "Restoration", "4K")):
        return True
    if y and current_year - int(y) >= 10:
        return True
    return False


def _sections(m):
    names = []
    f = m.get("filters", {}) or {}
    for key, label in FILTER_NAMES:
        if f.get(key):
            names.append(label)
    genres = m.get("genres", []) or []
    for g in GENRE_NAMES:
        if g in genres:
            names.append(g)
    return ", ".join(names) if names else "(none)"


def _slop_status(m):
    if m.get("is_slop"):
        return "🗑 SLOP (auto)" if m.get("_is_slop_guess") else "🗑 SLOP (manual)"
    return "✅ Not slop"


def build(stage, window):
    data = json.load(open("data.json"))
    today = str(date.today())
    from_date = str(date.today() - timedelta(days=window))
    cy = date.today().year
    rev = _load(REVIEWED, {})

    rows = []
    if stage == "capsule":
        caps = _load(CAPSULES, [])
        ct = set((c.get("title", "") if isinstance(c, dict) else "").lower() for c in caps)
        for m in data["movies"]:
            if not _in_window(m, from_date, today):
                continue
            if m.get("filters", {}).get("is_restoration") and not m.get("_reissue"):
                continue
            needs = []
            if m.get("title", "").lower() not in ct:
                needs.append("capsule")
            if "pull_quotes" not in m:
                needs.append("quotes")
            if not needs:
                continue
            row = [str(m.get("id")), m.get("title", ""), str(m.get("year", "?")),
                   str(m.get("rt_score") or "--"), "+".join(needs),
                   (m.get("links", {}) or {}).get("wikipedia", "") or "", _trailer(m)]
            rows.append((m.get("digital_date", "") or "", row))
    else:  # selects / sections / slop share one base filter + a watermark key
        for m in data["movies"]:
            if not _in_window(m, from_date, today):
                continue
            if _skip_old(m, cy):
                continue
            if stage in rev.get(str(m.get("id")), {}):
                continue
            L = m.get("links", {}) or {}
            wiki = L.get("wikipedia", "") or ""
            if stage == "selects":
                row = [str(m.get("id")), m.get("title", ""), str(m.get("year", "?")),
                       str(m.get("rt_score") or "--"), str(m.get("metacritic_score") or "--"),
                       str(m.get("imdb_rating") or "--"), _buzz(m),
                       ", ".join(_services(m)) or "—", wiki, _trailer(m), L.get("rt", "") or ""]
            elif stage == "sections":
                row = [str(m.get("id")), m.get("title", ""), str(m.get("year", "?")),
                       _sections(m), wiki]
            else:  # slop
                why = m.get("_slop_reason") or ""
                if not why:
                    rt, mc = m.get("rt_score"), m.get("metacritic_score")
                    why = f"RT {rt} / MC {mc}" if (rt or mc) else "no classifier signal"
                row = [str(m.get("id")), m.get("title", ""), str(m.get("year", "?")),
                       _slop_status(m), str(m.get("rt_score") or "--"),
                       str(m.get("imdb_rating") or "--"), _trailer(m), wiki, why,
                       L.get("imdb", "") or ""]
            rows.append((m.get("digital_date", "") or "", row))

    rows.sort(key=lambda r: r[0], reverse=True)

    headers = {
        "selects": f"Stage 1 Selects — {len(rows)} unreviewed candidate(s):",
        "sections": f"Stage 2 Sections — {len(rows)} unreviewed candidate(s):",
        "slop": f"Stage 3 Slop — {len(rows)} unreviewed candidate(s):",
        "capsule": f"STAGE 4 — {len(rows)} movie(s) to curate",
    }
    print(headers[stage])
    for i, (_dd, cols) in enumerate(rows, 1):
        # cols starts with id; emit as: i|||<rest fields...>|||id (id last, matching old output)
        mid = cols[0]
        rest = cols[1:]
        print("|||".join([str(i)] + rest + [mid]))


def mark(stage, ids):
    rev = _load(REVIEWED, {})
    for mid in ids:
        rev.setdefault(str(mid), {})[stage] = str(date.today())
    json.dump(rev, open(REVIEWED, "w"), indent=2)
    print(f"Marked {len(ids)} film(s) {stage}-reviewed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["selects", "sections", "slop", "capsule"])
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--mark", metavar="STAGE", help="mark films reviewed for STAGE")
    ap.add_argument("ids", nargs="*", help="movie ids (with --mark)")
    args = ap.parse_args()

    if args.mark:
        if args.mark not in ("selects", "sections", "slop"):
            sys.exit("--mark stage must be selects|sections|slop")
        if not args.ids:
            sys.exit("--mark needs at least one id")
        mark(args.mark, args.ids)
    elif args.stage:
        build(args.stage, args.window)
    else:
        ap.error("need --stage or --mark")


if __name__ == "__main__":
    main()
