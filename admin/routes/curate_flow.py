"""Morning curation flow — the /curate homework as a click-through website.

/flow            → combined review page (Selects · Sections · Slop, one submit)
/flow/movie/<id> → one page per queued film: capsule writing area + quote
                   checklist with inline trims; Save & Next
/flow/done       → completion summary

Saves run the same canonical scripts as the chat flow (write_capsule.py approve,
get_quotes.py --select/--skip) via subprocess under /usr/bin/python3, so locking,
URL verification, bank appends, and cache behavior are identical to /curate.
Slop verdicts + data.json edits go through pipeline.json_io.json_edit (flock +
atomic replace) — never bare json.dump on shared files.
"""
import os
import re
import subprocess
import sys
import tempfile

from flask import Blueprint, current_app, jsonify, render_template, request

from admin.config import (
    SITE_ROOT, DATA_FILE, STAFF_PICKS_FILE, RESTORATIONS_FILE,
    CATEGORY_OVERRIDES_FILE,
)
from admin.utils import load_json, mark_changes_pending

sys.path.insert(0, SITE_ROOT)
sys.path.insert(0, os.path.join(SITE_ROOT, 'scripts'))
from pipeline.json_io import json_edit  # noqa: E402
from curate_list import (  # noqa: E402
    capsule_queue, review_rows, mark as mark_reviewed,
    _services, _trailer, _sections, _buzz,
)
from get_quotes import _find_entry, _ordered_quotes, SPOILER_PREFIX  # noqa: E402
from slop_classifier import classify_slop  # noqa: E402

bp = Blueprint('curate_flow', __name__)

PY = '/usr/bin/python3'  # scripts' canonical interpreter (has all packages)
OVERRIDES_FILE = 'admin/overrides.json'
CAPSULE_CACHE = 'cache/capsule_cache.json'
QUOTES_CACHE = 'cache/pull_quotes_combined.json'


# ---------------------------------------------------------------- helpers

def _movie_by_id(mid):
    data = load_json(DATA_FILE, {})
    for m in data.get('movies', []):
        if str(m.get('id')) == str(mid):
            return m
    return None


def _capsule_entry(title, year):
    """Cache entry by exact key, then title/year scan (same as the doc renderer)."""
    cache = load_json(CAPSULE_CACHE, {})
    key = f"{title}_{year}"
    if key in cache:
        return cache[key]
    tl = (title or '').lower()
    for e in cache.values():
        if isinstance(e, dict) and str(e.get('title', '')).lower() == tl \
                and str(e.get('year', '')) == str(year):
            return e
    return None


def _quote_items(title, year):
    """The film's quotes in canonical --select order. Numbering here IS the
    numbering get_quotes.py saves by — both use _ordered_quotes."""
    cache = load_json(QUOTES_CACHE, {})
    try:
        key = _find_entry(cache, title, year)
    except SystemExit:  # ambiguous-title guard exits; treat as missing
        key = None
    if key is None:
        return []
    items, _hidden = _ordered_quotes(cache[key])
    out = []
    for n, (group, q) in enumerate(items, 1):
        text = (q.get('text') or '').strip()
        out.append({
            'num': n,
            'group': group,
            'critic': (q.get('critic') or '?').lstrip('@') if group == 'Letterboxd' else (q.get('critic') or '?'),
            'outlet': q.get('outlet') or group,
            'text': text,
            'url': q.get('review_url') or '',
            'spoiler': text.startswith(SPOILER_PREFIX),
            'selected': bool(q.get('selected')),
        })
    return out


def _encode_parens(url):
    return (url or '').replace('(', '%28').replace(')', '%29')


_LINK_SPAN_RE = re.compile(r'\[[^\]]*\]\([^)]*\)')


def _embed_links(text, link_map):
    """Mechanical Wikipedia-link embedding: for each known name appearing in the
    final text, wrap it as a markdown link (preserving bold). No AI — these are
    known strings. Two corruption guards: names are processed LONGEST FIRST
    ("Emma Stone" before "Emma"), and replacement only happens in text segments
    OUTSIDE existing markdown links (so a name inside an inserted link/URL is
    never re-wrapped into nested broken markdown)."""
    for name, url in sorted(link_map.items(), key=lambda kv: -len(kv[0] or '')):
        if not name or not url:
            continue
        if f'[{name}]' in text:  # already linked
            continue
        url = _encode_parens(url)
        segments, last, done = [], 0, False
        for span in _LINK_SPAN_RE.finditer(text):
            segments.append((text[last:span.start()], True))
            segments.append((span.group(0), False))
            last = span.end()
        segments.append((text[last:], True))
        out = []
        for seg, plain in segments:
            if plain and not done and name in seg:
                if f'**{name}**' in seg:
                    seg = seg.replace(f'**{name}**', f'**[{name}]({url})**', 1)
                else:
                    seg = seg.replace(name, f'[{name}]({url})', 1)
                done = True
            out.append(seg)
        text = ''.join(out)
    return text


def _run(cmd, timeout=90):
    """Run a canonical script from SITE_ROOT; return (ok, output). Timeouts are
    caught — a hung Playwright URL-verify must degrade to a warning, not a 500
    that drops the rest of the save."""
    try:
        result = subprocess.run(
            cmd, cwd=SITE_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f'timed out after {timeout}s: {" ".join(cmd[:3])}…'
    out = (result.stdout or '') + (result.stderr or '')
    return result.returncode == 0, out.strip()


def _git(args, timeout=60, env=None):
    try:
        r = subprocess.run(['git', *args], cwd=SITE_ROOT, capture_output=True,
                           text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return 1, f'git {args[0]} timed out after {timeout}s'


def _git_commit_push(files, message):
    """The COMMIT block from curate.md, hardened for headless use. Guards that
    the chat flow gets for free from an observing agent:
    - refuses when the repo is mid-rebase (conflict markers would be committed)
    - refuses off-main (the shared folder's HEAD gets flipped by other windows;
      committing here would strand work / rebase the wrong branch)
    - commits with an explicit pathspec so another session's staged work is
      never swept into this save
    - aborts a conflicted auto-rebase instead of leaving the repo wedged
    Returns None on success, else a warning/error string with the git output.
    """
    if os.path.exists(os.path.join(SITE_ROOT, '.git', 'rebase-merge')) or \
       os.path.exists(os.path.join(SITE_ROOT, '.git', 'rebase-apply')):
        return ('SAVED TO FILES but NOT committed: the repo is mid-rebase '
                '(another save hit a conflict). Fix it in a chat window '
                '(`git rebase --abort`) — do not keep saving until then.')
    rc, branch = _git(['branch', '--show-current'])
    if rc != 0 or branch.strip() != 'main':
        return (f'SAVED TO FILES but NOT committed: repo is on branch '
                f'"{branch.strip() or "?"}", not main. Switch back to main '
                f'(another window may have flipped it), then re-save.')

    env = {**os.environ, 'NRW_ALLOW_DATA_COMMIT': '1'}
    _git(['add', '--', *files])
    # Pathspec commit: only these files, regardless of what else is staged.
    rc, out = _git(['commit', '-m', f'{message} APPROVED: DELETE', '--', *files],
                   env=env)
    if rc != 0:
        if 'nothing to commit' in out or 'no changes added to commit' in out:
            return None
        return f'commit failed: {out[-300:]}'

    rc, out = _git(['push', 'origin', 'main'])
    if rc == 0:
        return None
    rc, rebase_out = _git(['pull', '--rebase', 'origin', 'main'], timeout=90)
    if rc != 0:
        low = rebase_out.lower()
        if ('unstaged changes' in low or 'uncommitted changes' in low
                or 'cannot pull with rebase' in low):
            # Routinely-dirty shared tree: the rebase never started, so this
            # is a stand-down, not a conflict — don't scare the user.
            return ('push raced another window and the tree has uncommitted '
                    'work, so auto-rebase stood down. Your save is committed '
                    'on local main and will push with the next clean save.')
        _git(['rebase', '--abort'])
        return ('push rejected and the auto-rebase hit a conflict (aborted '
                'cleanly — your commit is safe on local main). Resolve in a '
                f'chat window. git said: {rebase_out[-300:]}')
    rc, out = _git(['push', 'origin', 'main'], env=env)
    if rc != 0:
        return f'push failed — committed locally; next push will carry it. git said: {out[-200:]}'
    return None


def _queue_ids():
    return [str(m.get('id')) for m, _needs in capsule_queue()]


def _next_movie_id(after_mid=None):
    """First film still in the queue, preferring the one after after_mid in the
    snapshot order. Queue is rebuilt live, so drained films just disappear."""
    ids = _queue_ids()
    if not ids:
        return None
    if after_mid and str(after_mid) in ids:
        i = ids.index(str(after_mid))
        return ids[(i + 1) % len(ids)] if len(ids) > 1 else ids[0]
    return ids[0]


# ---------------------------------------------------------------- review page

def _notability_facts(m):
    nb = m.get('notability') or {}
    facts = []
    for k in ('festival', 'awards', 'yearend_lists'):
        v = nb.get(k)
        if v and v != 'none found':
            facts.append(v)
    return facts


_REASON_WORDS = {
    'no_wiki': 'no Wikipedia', 'no_rt': 'no RT score', 'no_imdb': 'no IMDb rating',
    'low_imdb': 'low IMDb', 'mid_imdb': 'middling IMDb', 'good_imdb': 'good IMDb',
    'no_rt_link': 'no RT page', 'no_lb': 'no Letterboxd',
}


def _human_reason(reason):
    """Turn classifier reason codes into plain English for the review page."""
    if not reason:
        return ''
    if reason.startswith('indian_cinema_no_crossover'):
        return ('Indian cinema rule — slop unless a crossover hit '
                '(needs Wikipedia + Letterboxd + RT≥60 + IMDb≥7)')
    if reason.startswith('indian_crossover_hit'):
        return 'Indian cinema crossover hit — clears the RRR bar'
    if reason.startswith('slop_streaming'):
        return 'Crunchyroll rule — always slop unless you override'
    m = re.match(r'score:(-?\d+)\((.*)\)', reason)
    if m:
        parts = [(_REASON_WORDS.get(p.split(':')[0], p.replace('_', ' ')) +
                  (f" ({p.split(':', 1)[1]})" if ':' in p else ''))
                 for p in m.group(2).split(',') if p]
        return ' · '.join(parts)
    return reason.replace('_', ' ').replace(':', ': ')


def _slop_advice(m):
    """The rule-based recommendations chat used to add by hand. Two sources:
    (1) the LIVE classifier disagrees strongly with the stored verdict (stored
    verdicts go stale when rules are added later); (2) a slop-flagged film with
    real pedigree (festival facts / Wikipedia) looks like a false positive.
    Recommendations only — the user flips the radio, nothing auto-applies."""
    tips = []
    stored = bool(m.get('is_slop'))
    try:
        fresh, reason, confidence = classify_slop(m)
        if confidence == 'strong' and fresh != stored:
            tips.append(('flip to ' + ('SLOP' if fresh else 'NOT slop'),
                         _human_reason(reason)))
    except Exception as e:
        current_app.logger.warning(
            'slop advice: classify_slop failed for %s: %s', m.get('title'), e)
    if stored:
        facts = _notability_facts(m)
        wiki = bool((m.get('links') or {}).get('wikipedia'))
        if facts:
            tips.append(('possible false positive', facts[0]))
        elif wiki:
            tips.append(('possible false positive', 'has a Wikipedia page'))
    return tips


@bp.route('/flow')
def flow_home():
    selects, sections, slop = (review_rows('selects'), review_rows('sections'),
                               review_rows('slop'))
    cat_over = load_json(CATEGORY_OVERRIDES_FILE, {})
    resto = load_json(RESTORATIONS_FILE, [])

    def base(m):
        L = m.get('links') or {}
        return {
            'id': str(m.get('id')), 'title': m.get('title', '?'),
            'year': m.get('year', '?'),
            'rt': m.get('rt_score') or '--', 'mc': m.get('metacritic_score') or '--',
            'imdb': m.get('imdb_rating') or '--', 'buzz': _buzz(m),
            'services': ', '.join(_services(m)) or '—',
            'wiki': L.get('wikipedia') or '', 'trailer': _trailer(m),
            'rt_url': L.get('rt') or '', 'imdb_url': L.get('imdb') or '',
        }

    def _rec(m):
        rt = str(m.get('rt_score') or '').replace('%', '')
        return bool(_notability_facts(m)) or (rt.isdigit() and int(rt) >= 90)

    selects_rows = sorted(
        ({**base(m), 'facts': _notability_facts(m), 'recommend': _rec(m)}
         for m in selects),
        key=lambda r: int(r['buzz']) if str(r['buzz']).isdigit() else -1,
        reverse=True)
    sections_rows = [{**base(m), 'sections': _sections(m),
                      'is_indie': bool((cat_over.get(str(m.get('id'))) or {}).get('is_indie')
                                       or (m.get('filters') or {}).get('is_indie')),
                      'is_restoration': str(m.get('id')) in [str(x) for x in resto]}
                     for m in sections]
    slop_rows = [{**base(m), 'is_slop': bool(m.get('is_slop')),
                  'why': _human_reason(m.get('_slop_reason')) or
                         (f"RT {m.get('rt_score')} / MC {m.get('metacritic_score')}"
                          if (m.get('rt_score') or m.get('metacritic_score'))
                          else 'no classifier signal'),
                  'advice': _slop_advice(m)}
                 for m in slop]

    return render_template(
        'flow_review.html',
        selects=selects_rows, sections=sections_rows, slop=slop_rows,
        queue_len=len(_queue_ids()),
        all_clear=not (selects_rows or sections_rows or slop_rows))


@bp.route('/flow/review', methods=['POST'])
def flow_review_save():
    payload = request.get_json(force=True) or {}
    picks = [str(x) for x in payload.get('selects', [])]
    slop_flips = {str(k): bool(v) for k, v in (payload.get('slop') or {}).items()}
    indie_flips = {str(k): bool(v) for k, v in (payload.get('indie') or {}).items()}
    resto_flips = {str(k): bool(v) for k, v in (payload.get('restorations') or {}).items()}
    shown = payload.get('shown') or {}

    # movie_tracking.json rides along like flow_movie_save's commit: the
    # pre-commit hook stages its export, and a pathspec commit that omits it
    # leaves that staged copy for the next unrelated commit to sweep up.
    changed_files = ['admin/curate_reviewed.json', 'movie_tracking.json']

    if picks:
        with json_edit(STAFF_PICKS_FILE) as sp:
            have = {str(x) for x in sp}
            for mid in picks:
                if mid not in have:
                    sp.append(mid)
                    have.add(mid)
        changed_files.append(STAFF_PICKS_FILE)

    if indie_flips:
        with json_edit(CATEGORY_OVERRIDES_FILE) as co:
            for mid, val in indie_flips.items():
                co.setdefault(mid, {})['is_indie'] = val
        changed_files.append(CATEGORY_OVERRIDES_FILE)

    if resto_flips:
        with json_edit(RESTORATIONS_FILE) as ro:
            have = {str(x) for x in ro}
            for mid, on in resto_flips.items():
                if on and mid not in have:
                    ro.append(mid)
                    have.add(mid)
                elif not on and mid in have:
                    ro[:] = [x for x in ro if str(x) != mid]
                    have.discard(mid)
        changed_files.append(RESTORATIONS_FILE)

    if slop_flips:
        with json_edit(OVERRIDES_FILE) as ov:
            for mid, val in slop_flips.items():
                ov.setdefault(mid, {}).setdefault('set', {})['is_slop'] = val
        with json_edit(DATA_FILE) as data:
            for m in data['movies']:
                mid = str(m.get('id'))
                if mid in slop_flips:
                    m['is_slop'] = slop_flips[mid]
        changed_files += [OVERRIDES_FILE, DATA_FILE]

    # Drain: every film SHOWN this run counts as reviewed (picks and skips).
    for stage in ('selects', 'sections', 'slop'):
        ids = [str(x) for x in shown.get(stage, [])]
        if ids:
            mark_reviewed(stage, ids)

    mark_changes_pending()
    warning = _git_commit_push(
        sorted(set(changed_files)), 'Curation review: selects/sections/slop (flow)')

    return jsonify({'success': True, 'warning': warning,
                    'next_id': _next_movie_id()})


# ---------------------------------------------------------------- movie pages

VARIANT_LABELS = ['premise', 'detail', 'reception']


@bp.route('/flow/movie/<mid>')
def flow_movie(mid):
    queue = capsule_queue()
    ids = [str(qm.get('id')) for qm, _n in queue]
    needs_map = {str(qm.get('id')): nd for qm, nd in queue}
    m = _movie_by_id(mid)
    if m is None:
        return render_template('flow_done.html', remaining=len(ids),
                               next_id=ids[0] if ids else None, drained=True)

    # Already-curated wall film (e.g. "← back" after a save): render it in
    # revisit mode so a typo'd capsule or wrong quote can be fixed in place.
    revisit = str(mid) not in ids
    if revisit:
        needs = ['capsule', 'quotes']
        pos, prev_id = None, None
        next_id = ids[0] if ids else None
    else:
        needs = needs_map.get(str(mid), [])
        pos = ids.index(str(mid)) + 1
        prev_id = ids[pos - 2] if pos > 1 else None
        next_id = ids[pos % len(ids)] if len(ids) > 1 else None
    entry = _capsule_entry(m.get('title'), m.get('year'))
    L = m.get('links') or {}
    crew = m.get('crew') or {}

    variants = []
    if entry and entry.get('capsules'):
        for i, cap in enumerate(entry['capsules'], 1):
            variants.append({'n': i, 'raw': cap,
                             'label': VARIANT_LABELS[(i - 1) % 3],
                             'words': len((cap or '').split())})
    if revisit and (m.get('capsule') or '').strip():
        variants.insert(0, {'n': '★', 'raw': m['capsule'],
                            'label': 'current live capsule (links embedded)',
                            'words': len(m['capsule'].split())})

    primer = [l.lstrip('• ').strip()
              for l in ((entry or {}).get('factoid_primer') or '').split('\n')
              if l.strip()]
    slinks = (entry or {}).get('suggested_links')
    links_cached = entry is not None and 'suggested_links' in (entry or {})

    return render_template(
        'flow_movie.html',
        pos=pos, total=len(ids), prev_id=prev_id, next_id=next_id,
        revisit=revisit,
        movie={
            'id': str(m.get('id')), 'title': m.get('title'), 'year': m.get('year'),
            'director': crew.get('director') if isinstance(crew, dict) else None,
            'genres': ', '.join((m.get('genres') or [])[:2]),
            'runtime': m.get('runtime'), 'country': m.get('country'),
            'services': ', '.join(_services(m)),
            'keywords': ' · '.join((m.get('keywords') or [])[:6]),
            'is_slop': bool(m.get('is_slop')),
            'poster': m.get('poster') or '',
            'wiki': L.get('wikipedia') or '', 'trailer': _trailer(m),
            'rt_url': L.get('rt') or '', 'rt': m.get('rt_score') or '--',
            'imdb_url': L.get('imdb') or '', 'imdb': m.get('imdb_rating') or '--',
        },
        needs=needs, variants=variants, primer=primer,
        slinks=slinks or [], links_cached=links_cached,
        quotes=_quote_items(m.get('title'), m.get('year')))


@bp.route('/flow/movie/<mid>/save', methods=['POST'])
def flow_movie_save(mid):
    m = _movie_by_id(mid)
    if m is None:
        return jsonify({'success': False, 'error': 'movie not found in data.json'})
    title, year = m.get('title'), m.get('year')
    payload = request.get_json(force=True) or {}
    capsule_text = (payload.get('capsule') or '').strip()
    quotes = payload.get('quotes') or []          # [{num, text}]
    skip_quotes = bool(payload.get('skip_quotes'))
    links_off = set(payload.get('links_off') or [])

    warnings = []
    committed_capsule = False

    if capsule_text:
        # Mechanical link pass: director + cast (silent) + cached suggested
        # links the user didn't untick. Known strings only — no searching.
        L = m.get('links') or {}
        link_map = {}
        if L.get('director_wiki') and (m.get('crew') or {}).get('director'):
            link_map[m['crew']['director']] = L['director_wiki']
        for name, url in (L.get('cast_wiki') or {}).items():
            link_map[name] = url
        entry = _capsule_entry(title, year)
        for sl in (entry or {}).get('suggested_links') or []:
            if sl.get('name') and sl['name'] not in links_off:
                link_map[sl['name']] = sl.get('url')
        final_text = _embed_links(capsule_text, link_map)

        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False,
                                         dir=os.path.join(SITE_ROOT, 'cache')) as f:
            f.write(final_text)
            tmp = f.name
        try:
            ok, out = _run([PY, 'scripts/write_capsule.py', 'approve', title,
                            '--id', str(mid), '--file', tmp])
            if not ok:
                return jsonify({'success': False,
                                'error': f'capsule approve failed: {out[-400:]}'})
            committed_capsule = True
        finally:
            os.unlink(tmp)

        # Persist cast wiki links used in the text (merge, cast only).
        cast_used = {n: _encode_parens(u) for n, u in (L.get('cast_wiki') or {}).items()
                     if n in final_text}
        if cast_used:
            with json_edit(DATA_FILE) as data:
                for rec in data['movies']:
                    if str(rec.get('id')) == str(mid):
                        links = rec.setdefault('links', {})
                        merged = links.get('cast_wiki', {})
                        merged.update(cast_used)
                        links['cast_wiki'] = merged
                        break

    # Re-resolve each quote's number against the CURRENT cache state — the
    # page's numbering can drift if another window edited this film's quotes
    # between render and save. Identity = critic + outlet (what --select's
    # replace logic keys on too).
    current = _quote_items(title, year)
    for q in quotes:
        num = int(q.get('num', 0))
        critic = (q.get('critic') or '').strip()
        outlet = (q.get('outlet') or '').strip()
        match = next((c for c in current if c['num'] == num
                      and c['critic'] == critic and c['outlet'] == outlet), None)
        if match is None:
            match = next((c for c in current if c['critic'] == critic
                          and c['outlet'] == outlet), None)
            if match:
                warnings.append(f'quote list changed since the page loaded — '
                                f'"{critic}" saved as #{match["num"]} (was #{num})')
                num = match['num']
        if match is None:
            warnings.append(f'quote #{num} ({critic}, {outlet}) no longer in the '
                            'cache — skipped; reload the page to see current quotes')
            continue
        trim = (q.get('text') or '').strip()
        if match['spoiler'] and not trim:
            warnings.append(f'quote #{num} is spoiler-protected boilerplate — '
                            'skipped (open the review and paste the line you want '
                            'as a trim)')
            continue
        cmd = [PY, 'scripts/get_quotes.py', '--select', title, str(year),
               '--num', str(num)]
        tmp = None
        if trim:
            with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False,
                                             dir=os.path.join(SITE_ROOT, 'cache')) as f:
                f.write(trim)
                tmp = f.name
            cmd += ['--text-file', tmp]
        try:
            ok, out = _run(cmd)
            for line in out.split('\n'):
                if line.strip().startswith('⚠'):
                    warnings.append(f'quote {num}: {line.strip()}')
            if not ok:
                warnings.append(f'quote {num} failed: {out[-200:]}')
        finally:
            if tmp:
                os.unlink(tmp)

    # Unselects: quotes the page loaded as selected and the user unchecked.
    unselects = payload.get('unselect') or []
    for q in unselects:
        critic = (q.get('critic') or '').strip()
        outlet = (q.get('outlet') or '').strip()
        if not critic or not outlet:
            continue
        ok, out = _run([PY, 'scripts/get_quotes.py', '--unselect', title,
                        str(year), '--critic', critic, '--outlet', outlet])
        if not ok:
            warnings.append(f'unselect ({critic}, {outlet}) failed: {out[-200:]}')

    if skip_quotes and not quotes:
        ok, out = _run([PY, 'scripts/get_quotes.py', '--skip', title, str(year)])
        if not ok:
            warnings.append(f'quote skip failed: {out[-200:]}')

    mark_changes_pending()
    files = ['data.json', 'movie_tracking.json']
    if committed_capsule:
        files.append('admin/approved_capsules.json')
    label = ('Capsule + pull quotes'
             if committed_capsule and (quotes or skip_quotes or unselects)
             else 'Capsule' if committed_capsule else 'Pull quotes')
    warn = _git_commit_push(files, f'{label}: {title} (flow)')
    if warn:
        warnings.append(warn)

    return jsonify({'success': True, 'warnings': warnings,
                    'next_id': _next_movie_id(after_mid=mid)})


@bp.route('/flow/done')
def flow_done():
    ids = _queue_ids()
    return render_template('flow_done.html', remaining=len(ids),
                           next_id=ids[0] if ids else None, drained=False)
