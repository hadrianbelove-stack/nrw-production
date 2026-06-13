"""Admin panel Morning Desk dashboard — overnight report + curation queue.

The dashboard is the admin front door ('/'). It mirrors the /morning workflow:
overnight pipeline report up top, then a day-grouped backlog of arrivals that
still need curation (capsule, quotes, wiki), plus a slop-review queue for
auto-flagged guesses.

Write paths reused from the existing admin (no new data.json writers here):
  - categories/slop/featured  -> POST /toggle-status (curation.py)
  - quote select/add/edit     -> /pull-quotes/* (pull_quotes.py)
  - capsule approve           -> GeminiCapsuleWriter.approve_capsule()
                                 (same path the /capsule chat command uses)
"""

import re
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify

from admin.config import (
    DATA_FILE, FEATURED_FILE, CATEGORY_OVERRIDES_FILE, PULL_QUOTES_CACHE,
)
from admin.health import load_health_status
from admin.logging_setup import logger
from admin.utils import load_json, mark_changes_pending, has_pending_changes

bp = Blueprint('today', __name__)

QUEUE_WINDOW_DAYS = 14

# Metrics files (same set /morning reads)
DIAGNOSTICS_FILE = 'metrics/run_diagnostics.json'
INTAKE_FILE = 'metrics/intake_run.json'
DISCOVERY_FILE = 'metrics/discovery_run.json'
ENRICHMENT_FILE = 'metrics/enrichment_run.json'
TRAILER_FILE = 'metrics/trailer_hosting_run.json'


def _movies_list():
    data = load_json(DATA_FILE, {})
    if isinstance(data, dict) and 'movies' in data:
        return data['movies']
    if isinstance(data, list):
        return data
    return []


def _find_movie(movies, movie_id):
    for m in movies:
        if str(m.get('id')) == str(movie_id):
            return m
    return None


def _cache_key(movie):
    return f"{movie.get('title', '')}_{movie.get('year', 0)}"


def _services(movie):
    """Flatten watch_links into a list of service names (streaming first)."""
    wl = movie.get('watch_links') or {}
    out = []
    for key in ('streaming', 'vod'):
        val = wl.get(key)
        if isinstance(val, dict):
            val = [val]
        if isinstance(val, list):
            out.extend(x.get('service', '') for x in val if isinstance(x, dict))
    return [s for s in out if s]


def _selected_quote_count(movie, quotes_cache):
    entry = quotes_cache.get(_cache_key(movie), {})
    pools = entry.get('rt_quotes', []) + entry.get('lb_quotes', [])
    return sum(1 for q in pools if q.get('selected'))


def _quote_pool_count(movie, quotes_cache):
    entry = quotes_cache.get(_cache_key(movie), {})
    return len(entry.get('rt_quotes', [])) + len(entry.get('lb_quotes', []))


def _day_label(date_str, today):
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return date_str or 'No date'
    if d == today:
        return 'Today'
    if d == today - timedelta(days=1):
        return 'Yesterday'
    return d.strftime('%A')


def _present_movie(movie, featured, overrides, quotes_cache):
    """Shape one movie for the dashboard template."""
    movie_id = str(movie.get('id'))
    filters = movie.get('filters', {}) or {}
    ovr = overrides.get(movie_id, {}) or {}
    links = movie.get('links', {}) or {}

    def cat(field):
        # Manual override wins over pipeline-computed filter flags
        return bool(ovr.get(field, filters.get(field, False)))

    selected_quotes = _selected_quote_count(movie, quotes_cache)
    services = _services(movie)
    return {
        'id': movie_id,
        'title': movie.get('title', ''),
        'year': movie.get('year', ''),
        'runtime': movie.get('runtime') or '',
        'country': movie.get('country', '') or '',
        'date': movie.get('digital_date', '') or '',
        'poster': movie.get('poster_url') or movie.get('poster') or '',
        'services': services,
        'rt': movie.get('rt_score') or '',
        'imdb': movie.get('imdb_rating') or '',
        'trailer_hosted': bool(links.get('trailer_hosted')),
        'trailer_yt': bool(links.get('trailer')),
        'wiki': bool(links.get('wikipedia')),
        'synopsis': (movie.get('synopsis') or '')[:300],
        'capsule': movie.get('capsule', '') or '',
        'capsule_done': bool(movie.get('capsule')),
        'quotes_selected': selected_quotes,
        'quotes_done': selected_quotes > 0,
        'quotes_available': _quote_pool_count(movie, quotes_cache),
        'no_links': not services,
        'plex_only': services == ['Plex'],
        'is_pick': movie_id in featured or cat('is_staff_pick'),
        'cats': {
            'indie': cat('is_indie'),
            'foreign': cat('is_foreign'),
            'documentary': cat('is_documentary'),
            'restoration': cat('is_restoration'),
            'virtual_screening': cat('is_virtual_screening'),
            'series': cat('is_series'),
        },
        'slop_guess': movie.get('_is_slop_guess'),
    }


@bp.route('/')
def today_dashboard():
    """Morning Desk — overnight report + day-grouped curation backlog."""
    movies = _movies_list()
    featured = [str(x) for x in load_json(FEATURED_FILE, [])]
    overrides = load_json(CATEGORY_OVERRIDES_FILE, {})
    quotes_cache = load_json(PULL_QUOTES_CACHE, {})

    today = date.today()
    today_str = today.isoformat()
    window_start = (today - timedelta(days=QUEUE_WINDOW_DAYS)).isoformat()

    queue = []        # needs curation (or recently curated, shown as done)
    slop_review = []  # auto-flagged guesses awaiting confirm/rescue
    for m in movies:
        dd = m.get('digital_date', '') or ''
        if not (window_start <= dd <= today_str):
            continue
        shaped = _present_movie(m, featured, overrides, quotes_cache)
        if m.get('_is_slop_guess') is not None:
            slop_review.append(shaped)
        elif not m.get('is_slop'):
            queue.append(shaped)

    queue.sort(key=lambda x: x['date'], reverse=True)
    slop_review.sort(key=lambda x: x['date'], reverse=True)

    # Group queue by digital_date (newest day first)
    day_groups = []
    for item in queue:
        if not day_groups or day_groups[-1]['date'] != item['date']:
            day_groups.append({
                'date': item['date'],
                'label': _day_label(item['date'], today),
                'films': [],
            })
        day_groups[-1]['films'].append(item)
    for g in day_groups:
        g['done'] = sum(1 for f in g['films'] if f['capsule_done'])

    done_count = sum(g['done'] for g in day_groups)

    # Overnight report from metrics files
    diagnostics = load_json(DIAGNOSTICS_FILE, {})
    intake = load_json(INTAKE_FILE, {})
    discovery = load_json(DISCOVERY_FILE, {})
    enrichment = load_json(ENRICHMENT_FILE, {})
    trailers = load_json(TRAILER_FILE, {})

    run_ts = diagnostics.get('timestamp', '')
    run_time = run_ts[11:16] if len(run_ts) >= 16 else '—'
    duration = diagnostics.get('duration_seconds')
    overnight = {
        'success': diagnostics.get('overall_success'),
        'time': run_time,
        'minutes': int(duration / 60) if duration else None,
        'failures': diagnostics.get('failure_count', 0),
        'warnings': diagnostics.get('warning_count', 0),
        'stall': (diagnostics.get('stall_status') or {}),
        'intaked': (intake.get('results') or {}).get('intaked'),
        'polled': (discovery.get('results') or {}).get('polled'),
        'transitions': (discovery.get('results') or {}).get('transitions'),
        'enriched': enrichment.get('movies_enriched'),
        'requested': enrichment.get('movies_requested'),
        'deferred': enrichment.get('movies_deferred', 0),
        'deferred_details': enrichment.get('deferred_details', []) or [],
        'trailers_hosted': trailers.get('hosted'),
        'trailers_attempted': trailers.get('movies_attempted'),
        'trailers_failed': trailers.get('failed', 0),
        'trailer_time': (trailers.get('timestamp') or '')[11:16],
    }

    # Concerns — same flags /morning surfaces
    concerns = []
    no_trailer = [f['title'] for f in queue if not f['trailer_hosted'] and not f['trailer_yt']]
    if no_trailer:
        concerns.append(f"{len(no_trailer)} film(s) missing trailers — {', '.join(no_trailer[:6])}")
    no_links = [f['title'] for f in queue if f['no_links']]
    if no_links:
        concerns.append(f"{len(no_links)} film(s) with NO watch links — {', '.join(no_links[:6])}")
    plex_only = [f['title'] for f in queue if f['plex_only']]
    if plex_only:
        concerns.append(f"Plex-only: {', '.join(plex_only[:6])}")
    if overnight['deferred']:
        concerns.append(f"{overnight['deferred']} enrichment deferral(s) — see Enriched card")
    if overnight['failures']:
        concerns.append(f"{overnight['failures']} pipeline phase failure(s) — check health report")

    return render_template(
        'today.html',
        overnight=overnight,
        concerns=concerns,
        day_groups=day_groups,
        queue_total=len(queue),
        done_count=done_count,
        slop_review=slop_review,
        wall_count=len(movies),
        window_days=QUEUE_WINDOW_DAYS,
        pending_changes=has_pending_changes(),
        health_status=load_health_status(),
    )


# ---------------------------------------------------------------------------
# Capsule API — wraps the same GeminiCapsuleWriter the /capsule command uses
# ---------------------------------------------------------------------------

def _extract_capsule_args(movie):
    """Capsule writer kwargs from a data.json movie entry.

    Mirror of scripts/write_capsule.py extract_capsule_args() — kept in sync
    manually because scripts/ is not an importable package.
    """
    crew = movie.get('crew', {}) or {}
    cats = movie.get('categories', {}) or {}
    links = movie.get('links', {}) or {}

    amazon_url = ''
    watch_links = movie.get('watch_links', {}) or {}
    vod = watch_links.get('vod')
    if isinstance(vod, dict):
        vod = [vod]
    for entry in (vod or []):
        if entry.get('service') == 'Amazon' and entry.get('link'):
            gti_match = re.search(r'gti=([^&]+)', entry['link'])
            if gti_match:
                amazon_url = f"https://www.amazon.com/gp/video/detail/{gti_match.group(1)}"
            break

    return {
        'title': movie.get('title', ''),
        'year': movie.get('year', 0),
        'director': crew.get('director') if isinstance(crew, dict) else None,
        'cast': crew.get('cast') if isinstance(crew, dict) else None,
        'genres': movie.get('genres'),
        'runtime': movie.get('runtime'),
        'synopsis': movie.get('synopsis'),
        'rt_score': movie.get('rt_score'),
        'imdb_rating': movie.get('imdb_rating'),
        'metacritic_score': movie.get('metacritic_score'),
        'country': movie.get('country'),
        'original_language': movie.get('original_language'),
        'original_title': movie.get('original_title'),
        'studio': movie.get('studio'),
        'is_restoration': cats.get('is_restoration', False),
        'is_documentary': cats.get('is_documentary', False),
        'is_foreign': cats.get('is_foreign', False),
        'is_exploitation': cats.get('is_exploitation', False),
        'is_indie': cats.get('is_indie', False),
        'wiki_url': links.get('wikipedia', ''),
        'rt_url': links.get('rt', ''),
        'mc_url': links.get('metacritic', ''),
        'amazon_url': amazon_url,
        'imdb_url': links.get('imdb', ''),
    }


@bp.route('/api/capsule/generate', methods=['POST'])
def capsule_generate():
    """Generate (or fetch cached) capsule variants for a movie.

    Slow path: fact gathering + 3 Gemini calls can take a minute or more.
    Cached results (cache/capsule_cache.json) return instantly.
    """
    payload = request.json or {}
    movie_id = payload.get('movie_id')
    force = bool(payload.get('force'))
    if not movie_id:
        return jsonify({'success': False, 'error': 'movie_id is required'})

    movie = _find_movie(_movies_list(), movie_id)
    if not movie:
        return jsonify({'success': False, 'error': 'Movie not found'})

    try:
        from gemini_scraper import GeminiCapsuleWriter
        writer = GeminiCapsuleWriter()
        result = writer.write_capsule(
            **_extract_capsule_args(movie),
            force=force,
            skip_verify=True,
            variants=3,
        )
    except Exception as e:
        logger.error(f"Capsule generation failed for {movie_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})

    if not result or not result.get('capsule'):
        return jsonify({'success': False, 'error': 'Capsule generation returned nothing'})

    capsules = result.get('capsules') or [result['capsule']]
    return jsonify({
        'success': True,
        'capsules': capsules,
        'factoid_primer': result.get('factoid_primer', ''),
        'current_capsule': movie.get('capsule', '') or '',
    })


@bp.route('/api/capsule/approve', methods=['POST'])
def capsule_approve():
    """Approve a capsule (possibly user-rewritten): training bank + data.json."""
    payload = request.json or {}
    movie_id = payload.get('movie_id')
    text = (payload.get('text') or '').strip()
    if not movie_id or not text:
        return jsonify({'success': False, 'error': 'movie_id and text are required'})

    movie = _find_movie(_movies_list(), movie_id)
    if not movie:
        return jsonify({'success': False, 'error': 'Movie not found'})

    crew = movie.get('crew', {}) or {}
    director = crew.get('director', 'Unknown') if isinstance(crew, dict) else 'Unknown'

    try:
        from gemini_scraper import GeminiCapsuleWriter
        writer = GeminiCapsuleWriter()
        writer.approve_capsule(movie.get('title', ''), movie.get('year', 0), text,
                               director=director)
    except Exception as e:
        logger.error(f"Capsule approve failed for {movie_id}: {e}")
        return jsonify({'success': False, 'error': str(e)})

    mark_changes_pending()
    logger.info(f"Capsule approved for movie {movie_id}")
    return jsonify({'success': True})
