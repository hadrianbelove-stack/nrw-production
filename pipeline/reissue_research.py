#!/usr/bin/env python3
"""
Reissue research — Gemini + Google Search pass over the reissue candidate queue.

For each pending candidate in admin/reissue_candidates.json (written by intake Pass D),
ask Gemini (grounded with Google Search) whether the OLD film is genuinely getting a
new reissue / restoration / re-release right now, who the distributor is, and a one-line
summary with a source article URL. Results are cached back into the candidate record so
the "Confirm Reissues" curation stage can present a pre-sorted, link-dense table.

Distributor green-flag: if the identified distributor is one of the known reissue labels
in admin/restoration_config.json (Kino Lorber, Janus, Criterion, ...), the verdict is
forced to "likely" — a new Kino Lorber release of an old film jumps to the top.

Verdict buckets: likely | maybe | unlikely  (every candidate is still shown to the user;
this only pre-sorts the list).

Usage:
    GEMINI_API_KEY=... python3 pipeline/reissue_research.py [--limit N] [--all] [--file PATH]
"""

import os
import re
import sys
import json
import time
import argparse
import requests

CANDIDATES_FILE = 'admin/reissue_candidates.json'
RESTORATION_CONFIG = 'admin/restoration_config.json'


def resolve_grounding_url(redirect_url):
    """Resolve a Gemini grounding redirect URL to the actual article URL."""
    try:
        resp = requests.head(
            redirect_url, allow_redirects=False, timeout=5,
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
        if resp.status_code in (301, 302, 303, 307, 308):
            return resp.headers.get('Location', '')
    except Exception:
        pass
    return ''


def _load_restoration_distributors():
    try:
        with open(RESTORATION_CONFIG) as f:
            return json.load(f).get('restoration_distributors', [])
    except Exception:
        return []


def _extract_json(text):
    """Pull the first JSON object out of a model response."""
    if not text:
        return {}
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def research_candidate(client, gconfig, cand, distributors):
    """Run one Gemini+Search lookup. Returns a research dict."""
    title = cand.get('title', '')
    year = cand.get('year', '')
    note = (cand.get('recent_release') or {}).get('note', '')

    prompt = (
        f'The film "{title}" ({year}) appears to have a new theatrical or digital release '
        f'event recently (release note: "{note or "none"}"). Using current web sources, '
        f'determine whether this is a genuine reissue / 4K restoration / anniversary '
        f're-release / new theatrical run of the OLD film (NOT a remake or a different '
        f'film of the same name). Identify the distributor or label handling the '
        f're-release if any.\n\n'
        f'Respond ONLY with a JSON object, no other text:\n'
        f'{{"is_reissue": "yes|no|maybe", "distributor": "<name or empty>", '
        f'"release_kind": "<e.g. 4K restoration, 40th anniversary re-release, festival '
        f'revival, or empty>", "summary": "<one sentence of evidence>"}}'
    )

    text = ''
    source_url = ''
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', contents=prompt, config=gconfig)
        text = (response.text or '').strip()
        if response.candidates:
            gm = response.candidates[0].grounding_metadata
            if gm and gm.grounding_chunks:
                for chunk in gm.grounding_chunks:
                    if chunk.web and chunk.web.uri:
                        actual = resolve_grounding_url(chunk.web.uri) or chunk.web.uri
                        if actual:
                            source_url = actual
                            break
    except Exception as e:
        return {'verdict': 'maybe', 'distributor': '', 'release_kind': '',
                'summary': f'(research error: {e})', 'source_url': '', 'error': True}

    parsed = _extract_json(text)
    is_reissue = (parsed.get('is_reissue') or '').lower()
    distributor = (parsed.get('distributor') or '').strip()
    release_kind = (parsed.get('release_kind') or '').strip()
    summary = (parsed.get('summary') or text[:240]).strip()

    verdict = {'yes': 'likely', 'no': 'unlikely', 'maybe': 'maybe'}.get(is_reissue, 'maybe')

    # Distributor green-flag: known reissue label → force "likely"
    distributor_flag = False
    if distributor:
        for d in distributors:
            if d.lower() in distributor.lower() or distributor.lower() in d.lower():
                verdict = 'likely'
                distributor_flag = True
                break

    return {
        'verdict': verdict,
        'distributor': distributor,
        'distributor_greenflag': distributor_flag,
        'release_kind': release_kind,
        'summary': summary,
        'source_url': source_url,
    }


def run_research(candidates_file=CANDIDATES_FILE, limit=None, redo_all=False):
    """Research pending candidates that have no research yet (or all, with --all)."""
    if not os.path.exists(candidates_file):
        print(f"No candidate file at {candidates_file} — nothing to research.")
        return 0

    with open(candidates_file) as f:
        data = json.load(f)
    queue = data.get('candidates', {})

    distributors = _load_restoration_distributors()

    todo = [c for c in queue.values()
            if c.get('status') == 'pending' and (redo_all or not c.get('research'))]
    if limit:
        todo = todo[:limit]

    if not todo:
        print("Reissue research: nothing to do (all pending candidates already researched).")
        return 0

    from google import genai
    from google.genai import types

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    gconfig = types.GenerateContentConfig(tools=[grounding_tool])

    print(f"Reissue research: {len(todo)} candidate(s) to look up...")
    done = 0
    for i, cand in enumerate(todo, 1):
        res = research_candidate(client, gconfig, cand, distributors)
        cand['research'] = res
        flag = ' [DIST★]' if res.get('distributor_greenflag') else ''
        print(f"  [{i}/{len(todo)}] {cand['title']} ({cand.get('year')}) -> "
              f"{res['verdict']}{flag}  {res.get('release_kind') or res.get('distributor') or ''}")
        done += 1
        time.sleep(1)  # rate limit

    # Persist
    import datetime
    data['last_researched'] = datetime.datetime.now().isoformat()
    tmp = candidates_file + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, candidates_file)
    print(f"Reissue research complete: {done} researched.")
    return done


def main():
    ap = argparse.ArgumentParser(description="Gemini+Search research over reissue candidates")
    ap.add_argument('--limit', type=int, default=None, help='Max candidates to research this run')
    ap.add_argument('--all', action='store_true', help='Re-research even already-researched candidates')
    ap.add_argument('--file', default=CANDIDATES_FILE, help='Candidate queue path')
    args = ap.parse_args()
    run_research(args.file, limit=args.limit, redo_all=args.all)


if __name__ == '__main__':
    main()
