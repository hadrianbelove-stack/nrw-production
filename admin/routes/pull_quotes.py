"""Admin panel pull quotes routes — curation, toggle, add, eye test."""

from datetime import datetime

from flask import Blueprint, request, jsonify, render_template

from file_lock import safe_write_json
from admin.config import (
    DATA_FILE, PULL_QUOTES_CACHE, PULL_QUOTES_GEMINI_CACHE, TASTE_PROFILE_FILE,
)
from admin.utils import load_json

bp = Blueprint('pull_quotes', __name__)


def _promote_gemini_cache(cache_key, gemini_cache, combined_cache):
    """Convert PullQuoteFinder cache entry to combined format and add it."""
    entry = gemini_cache.get(cache_key, {})
    quotes = entry.get('quotes', [])
    if not quotes:
        return {}

    rt_quotes = []
    lb_quotes = []
    for q in quotes:
        item = {
            'text': q.get('text', ''),
            'critic': q.get('critic', ''),
            'outlet': q.get('outlet', ''),
            'source': q.get('source', 'critic'),
            'verbatim': True,
            'selected': q.get('selected', False),
            'fresh': None,
            'review_url': q.get('review_url', ''),
            'added_at': q.get('added_at', datetime.now().isoformat())
        }
        if q.get('source') == 'letterboxd':
            item['source'] = 'letterboxd'
            item['pull_quote'] = q.get('text', '')
            lb_quotes.append(item)
        else:
            item['source'] = 'rt_critic'
            rt_quotes.append(item)

    result = {
        'title': entry.get('title', cache_key.rsplit('_', 1)[0]),
        'year': entry.get('year', ''),
        'rt_quotes': rt_quotes,
        'lb_quotes': lb_quotes,
        'scraped_at': entry.get('scraped_at', datetime.now().isoformat()),
        'scrape_method': 'gemini_pull_quote_finder'
    }

    # Promote to combined cache
    combined_cache[cache_key] = result
    safe_write_json(PULL_QUOTES_CACHE, combined_cache)

    return result


@bp.route('/api/pull-quotes/<movie_id>')
def pull_quotes_api(movie_id):
    """Return pull quotes as JSON for inline loading in admin spreadsheet."""
    data = load_json(DATA_FILE, {})
    if isinstance(data, dict) and 'movies' in data:
        movies_list = data['movies']
    elif isinstance(data, list):
        movies_list = data
    else:
        movies_list = []

    movie = None
    for m in movies_list:
        if str(m.get('id')) == str(movie_id):
            movie = m
            break

    if not movie:
        return jsonify({'quotes': [], 'cache_key': None})

    title = movie.get('title', '')
    year = movie.get('year', 0)
    cache_key = f"{title}_{year}"

    combined_cache = load_json(PULL_QUOTES_CACHE, {})
    movie_quotes = combined_cache.get(cache_key, {})

    rt_quotes = movie_quotes.get('rt_quotes', [])
    lb_quotes = movie_quotes.get('lb_quotes', [])

    # Merge all quotes into a flat list with source info
    quotes = []
    for i, q in enumerate(rt_quotes):
        quotes.append({
            'text': q.get('text', '') or q.get('quote', ''),
            'source': q.get('critic', '') or q.get('publication', 'RT'),
            'selected': q.get('selected', False),
            'pool': 'rt_quotes',
            'index': i
        })
    for i, q in enumerate(lb_quotes):
        quotes.append({
            'text': q.get('text', '') or q.get('quote', ''),
            'source': q.get('reviewer', '') or 'Letterboxd',
            'selected': q.get('selected', False),
            'pool': 'lb_quotes',
            'index': i
        })

    return jsonify({
        'quotes': quotes,
        'cache_key': cache_key,
        'has_quotes': bool(quotes)
    })


@bp.route('/pull-quotes/<movie_id>')
def pull_quotes_page(movie_id):
    """Pull quotes curation page for a specific movie."""
    # Find movie info from data.json
    data = load_json(DATA_FILE, {})
    if isinstance(data, dict) and 'movies' in data:
        movies_list = data['movies']
    elif isinstance(data, list):
        movies_list = data
    else:
        movies_list = []

    movie = None
    for m in movies_list:
        if str(m.get('id')) == str(movie_id):
            movie = m
            break

    # Fallback to movie_tracking.json for movies rotated off the wall
    if not movie:
        tracking = load_json('movie_tracking.json', {})
        tracked = tracking.get('movies', {}).get(str(movie_id))
        if tracked:
            movie = {
                'id': movie_id,
                'title': tracked.get('title', ''),
                'year': tracked.get('year', 0),
                'poster_url': tracked.get('poster_url', ''),
                'links': tracked.get('links', {})
            }

    if not movie:
        return "Movie not found", 404

    title = movie.get('title', '')
    year = movie.get('year', 0)
    cache_key = f"{title}_{year}"

    # Load pull quotes from combined cache
    combined_cache = load_json(PULL_QUOTES_CACHE, {})
    movie_quotes = combined_cache.get(cache_key, {})

    # Fallback: check gemini cache if not in combined
    if not movie_quotes.get('rt_quotes') and not movie_quotes.get('lb_quotes'):
        gemini_cache = load_json(PULL_QUOTES_GEMINI_CACHE, {})
        if cache_key in gemini_cache:
            movie_quotes = _promote_gemini_cache(cache_key, gemini_cache, combined_cache)

    rt_quotes = movie_quotes.get('rt_quotes', [])
    lb_quotes = movie_quotes.get('lb_quotes', [])

    # Count selected
    rt_selected = sum(1 for q in rt_quotes if q.get('selected'))
    lb_selected = sum(1 for q in lb_quotes if q.get('selected'))

    # RT URL for potential re-scraping
    rt_url = movie.get('links', {}).get('rt', '')

    return render_template('pull_quotes.html',
        movie_id=movie_id,
        movie=movie,
        cache_key=cache_key,
        rt_quotes=rt_quotes,
        lb_quotes=lb_quotes,
        rt_selected=rt_selected,
        lb_selected=lb_selected,
        rt_url=rt_url,
        has_quotes=bool(rt_quotes or lb_quotes)
    )


@bp.route('/pull-quotes/toggle', methods=['POST'])
def toggle_pull_quote():
    """Toggle selected state for a pull quote."""
    data = request.json
    cache_key = data.get('cache_key')
    source = data.get('source')  # 'rt_quotes' or 'lb_quotes'
    index = data.get('index')

    if not cache_key or source not in ('rt_quotes', 'lb_quotes') or index is None:
        return jsonify({'success': False, 'error': 'Missing or invalid parameters'})

    quotes_cache = load_json(PULL_QUOTES_CACHE, {})
    if cache_key not in quotes_cache:
        return jsonify({'success': False, 'error': 'Movie not found in cache'})

    quotes = quotes_cache[cache_key].get(source, [])
    if index < 0 or index >= len(quotes):
        return jsonify({'success': False, 'error': 'Quote index out of range'})

    # Toggle
    current = quotes[index].get('selected', False)
    quotes[index]['selected'] = not current

    # Save
    safe_write_json(PULL_QUOTES_CACHE, quotes_cache)

    # Count new totals
    total_selected = sum(1 for q in quotes if q.get('selected'))

    return jsonify({
        'success': True,
        'selected': quotes[index]['selected'],
        'total_selected': total_selected
    })


@bp.route('/pull-quotes/add', methods=['POST'])
def add_pull_quote():
    """Manually add a pull quote to the cache."""
    data = request.json
    cache_key = data.get('cache_key')
    text = (data.get('text') or '').strip()
    critic = (data.get('critic') or '').strip()
    outlet = (data.get('outlet') or '').strip()
    review_url = (data.get('review_url') or '').strip()

    if not cache_key or not text:
        return jsonify({'success': False, 'error': 'Quote text is required'})

    quotes_cache = load_json(PULL_QUOTES_CACHE, {})

    # Create movie entry if it doesn't exist
    if cache_key not in quotes_cache:
        parts = cache_key.rsplit('_', 1)
        quotes_cache[cache_key] = {
            'title': parts[0] if len(parts) > 1 else cache_key,
            'year': parts[1] if len(parts) > 1 else '',
            'rt_quotes': [],
            'lb_quotes': [],
            'scraped_at': datetime.now().isoformat(),
            'scrape_method': 'manual'
        }

    entry = {
        'text': text,
        'critic': critic,
        'outlet': outlet,
        'source': 'manual',
        'verbatim': True,
        'selected': False,
        'fresh': None,
        'review_url': review_url,
        'added_at': datetime.now().isoformat()
    }

    quotes_cache[cache_key]['rt_quotes'].append(entry)
    index = len(quotes_cache[cache_key]['rt_quotes']) - 1

    safe_write_json(PULL_QUOTES_CACHE, quotes_cache)

    return jsonify({'success': True, 'index': index})


@bp.route('/pull-quotes/edit', methods=['POST'])
def edit_pull_quote():
    """Edit (trim/rewrite) a pull quote's text in the cache.

    The cache is the source of truth — display generation reads selected
    quotes from here, so the edited text must land in the cache, not just
    data.json.
    """
    data = request.json
    cache_key = data.get('cache_key')
    source = data.get('source')  # 'rt_quotes' or 'lb_quotes'
    index = data.get('index')
    text = (data.get('text') or '').strip()

    if not cache_key or source not in ('rt_quotes', 'lb_quotes') or index is None:
        return jsonify({'success': False, 'error': 'Missing or invalid parameters'})
    if not text:
        return jsonify({'success': False, 'error': 'Quote text cannot be empty'})

    quotes_cache = load_json(PULL_QUOTES_CACHE, {})
    if cache_key not in quotes_cache:
        return jsonify({'success': False, 'error': 'Movie not found in cache'})

    quotes = quotes_cache[cache_key].get(source, [])
    if index < 0 or index >= len(quotes):
        return jsonify({'success': False, 'error': 'Quote index out of range'})

    quote = quotes[index]
    if quote.get('text') != text:
        if not quote.get('original_text'):
            quote['original_text'] = quote.get('text', '')
        quote['text'] = text
        quote['verbatim'] = False
        quote['edited_at'] = datetime.now().isoformat()
        safe_write_json(PULL_QUOTES_CACHE, quotes_cache)

    return jsonify({'success': True, 'text': text})


@bp.route('/pull-quotes/eye-test-save', methods=['POST'])
def save_eye_test():
    """Save an eye test A/B comparison result to taste profile."""
    data = request.json

    taste = load_json(TASTE_PROFILE_FILE, {})

    rounds = taste.get('rounds', [])
    round_num = len(rounds) + 1

    entry = {
        'round': round_num,
        'source': data.get('source', 'mixed'),
        'movie': data.get('movie', ''),
        'timestamp': datetime.now().isoformat()
    }

    if data.get('winner'):
        entry['winner'] = data['winner']
        entry['loser'] = data['loser']
    else:
        entry['winner'] = None
        entry['loser_a'] = data.get('option_a')
        entry['loser_b'] = data.get('option_b')

    if data.get('note'):
        entry['note'] = data['note']

    rounds.append(entry)
    taste['rounds'] = rounds
    taste['updated_at'] = datetime.now().isoformat()

    safe_write_json(TASTE_PROFILE_FILE, taste)

    return jsonify({
        'success': True,
        'round': round_num,
        'total_rounds': len(rounds)
    })
