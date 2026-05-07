"""Admin panel main routes — index page and health dismissal."""

from collections import OrderedDict
from datetime import date as date_type

from flask import Blueprint, render_template, session, jsonify

from admin.config import (
    DATA_FILE, FEATURED_FILE, RESTORATIONS_FILE, CATEGORY_OVERRIDES_FILE,
)
from admin.utils import load_json
from admin.health import load_health_status

bp = Blueprint('main', __name__)


@bp.route('/')
def index() -> str:
    """Main admin panel page.

    Displays all movies in a grid with filtering, search, and inline editing.
    Shows statistics (total, featured, missing data counts).
    """
    data = load_json(DATA_FILE, {})
    featured = load_json(FEATURED_FILE, [])
    restorations = load_json(RESTORATIONS_FILE, [])

    # Handle different data shapes from data.json
    if data and isinstance(data, dict) and 'movies' in data and isinstance(data['movies'], list):
        movies_list = data['movies']
    elif isinstance(data, list):
        movies_list = data
    else:
        movies_list = []

    # Process all movies and build dict keyed by movie ID
    processed_movies = {}

    for movie in movies_list:
        movie_id = str(movie.get('id'))
        movie_copy = dict(movie)

        # Normalize movie fields expected by template
        # Set rt_url from links.rt if available
        if movie_copy.get('links', {}).get('rt'):
            movie_copy['rt_url'] = movie_copy['links']['rt']

        # Set director from crew.director if available
        if movie_copy.get('crew', {}).get('director'):
            movie_copy['director'] = movie_copy['crew']['director']

        # Build provider_list from providers or watch_links
        providers = set()
        if movie_copy.get('providers'):
            for category in ['streaming', 'vod']:
                if category in movie_copy['providers']:
                    providers.update(movie_copy['providers'][category])
        # Normalize watch_links so template only handles one format:
        #   streaming → dict {service, link} or None
        #   vod → list of dicts [{service, link}, ...]
        wl = movie_copy.get('watch_links')
        if wl:
            s = wl.get('streaming')
            if isinstance(s, list):
                wl['streaming'] = s[0] if s else None
            v = wl.get('vod')
            if isinstance(v, dict):
                wl['vod'] = [v]
            elif not isinstance(v, list):
                wl['vod'] = []

        if movie_copy.get('watch_links'):
            for category_data in movie_copy['watch_links'].values():
                if isinstance(category_data, dict) and 'service' in category_data:
                    providers.add(category_data['service'])
                elif isinstance(category_data, list):
                    for item in category_data:
                        if isinstance(item, dict) and 'service' in item:
                            providers.add(item['service'])
        movie_copy['provider_list'] = ', '.join(sorted(providers)) if providers else ''

        # Handle poster URLs
        if movie_copy.get('poster') and not movie_copy.get('poster_url'):
            movie_copy['poster_url'] = movie_copy['poster']

        # Normalize rt_score to integer for template comparisons
        if movie_copy.get('rt_score'):
            rt_score_str = str(movie_copy['rt_score']).strip().replace('%', '')
            try:
                movie_copy['rt_score'] = int(rt_score_str)
            except (ValueError, TypeError):
                movie_copy['rt_score'] = None

        # Add bootstrap date and manually corrected flags for display
        movie_copy['bootstrap_date'] = movie_copy.get('bootstrap_date', False)
        movie_copy['manually_corrected'] = movie_copy.get('manually_corrected', False)

        processed_movies[movie_id] = movie_copy

    # Calculate stats
    total_count = len(movies_list)
    featured_count = len(featured)

    # Calculate missing data count
    missing_data_count = sum(
        1 for movie in processed_movies.values()
        if not movie.get('links', {}).get('trailer')
        or not (movie.get('poster_url') or movie.get('poster'))
        or not movie.get('director')
        or movie.get('director') == 'Unknown'
        or not movie.get('country')
    )

    # Calculate bootstrap movies count
    bootstrap_count = sum(1 for movie in processed_movies.values() if movie.get('bootstrap_date'))

    # Load health status for banner
    health_status = load_health_status()

    # Load category overrides for template
    category_overrides = load_json(CATEGORY_OVERRIDES_FILE, {})

    # Split movies into pre-orders (future dates) and wall (today/past)
    today_str = date_type.today().isoformat()

    # Sort movies by digital_date descending
    sorted_movies = sorted(
        processed_movies.values(),
        key=lambda m: m.get('digital_date', '') or '',
        reverse=True
    )

    preorder_movies = []
    wall_movies = []
    for movie in sorted_movies:
        dd = movie.get('digital_date', '') or ''
        if dd > today_str:
            preorder_movies.append(movie)
        else:
            wall_movies.append(movie)

    # Also keep legacy movies_by_date for backwards compat
    date_groups = OrderedDict()
    for movie in sorted_movies:
        date = movie.get('digital_date', 'Unknown')
        if date not in date_groups:
            date_groups[date] = []
        date_groups[date].append(movie)

    return render_template(
        'index.html',
        movies=processed_movies,
        movies_by_date=list(date_groups.items()),
        preorder_movies=preorder_movies,
        wall_movies=wall_movies,
        preorder_count=len(preorder_movies),
        wall_count=len(wall_movies),
        featured=featured,
        restorations=restorations,
        category_overrides=category_overrides,
        featured_count=featured_count,
        missing_data_count=missing_data_count,
        bootstrap_count=bootstrap_count,
        health_status=health_status
    )


@bp.route('/dismiss-health', methods=['POST'])
def dismiss_health():
    """Dismiss health banner for this session."""
    session['health_dismissed'] = True
    return jsonify({'success': True})
