"""Admin panel Jinja2 template filters."""

from datetime import datetime

from admin.config import COUNTRY_CODES


def weekday_filter(date_str):
    """Convert YYYY-MM-DD to 3-letter weekday abbreviation."""
    if not date_str or date_str == 'Unknown':
        return ''
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return dt.strftime('%a')
    except (ValueError, TypeError):
        return ''


def short_date_filter(date_str):
    """Convert YYYY-MM-DD to 'Mon D' format (e.g., 'Mar 30')."""
    if not date_str or date_str == 'Unknown':
        return '\u2014'
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return dt.strftime('%b %-d')
    except (ValueError, TypeError):
        return date_str


def date_month_filter(date_str):
    """Extract month abbreviation from YYYY-MM-DD."""
    if not date_str or date_str == 'Unknown':
        return ''
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return dt.strftime('%b')
    except (ValueError, TypeError):
        return ''


def date_day_filter(date_str):
    """Extract day number from YYYY-MM-DD."""
    if not date_str or date_str == 'Unknown':
        return '\u2014'
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return str(dt.day)
    except (ValueError, TypeError):
        return ''


def country_code_filter(country):
    """Convert country name to 3-letter code."""
    if not country:
        return ''
    # Handle multiple countries separated by comma or slash
    countries = [c.strip() for c in country.replace('/', ',').split(',')]
    codes = []
    for c in countries:
        code = COUNTRY_CODES.get(c, c[:3].upper() if len(c) >= 3 else c.upper())
        codes.append(code)
    return '/'.join(codes)


def register_filters(app):
    """Register all template filters on the Flask app."""
    app.template_filter('weekday')(weekday_filter)
    app.template_filter('short_date')(short_date_filter)
    app.template_filter('date_month')(date_month_filter)
    app.template_filter('date_day')(date_day_filter)
    app.template_filter('country_code')(country_code_filter)
