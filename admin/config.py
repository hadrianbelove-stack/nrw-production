"""Admin panel configuration constants."""

import os

# Root directory of the project (one level up from admin/)
SITE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data file paths (relative to project root)
DATA_FILE = 'data.json'
STAFF_PICKS_FILE = 'admin/staff_picks.json'
FEATURED_FILE = STAFF_PICKS_FILE  # Backwards compatibility alias
RESTORATIONS_FILE = 'admin/restorations.json'
CATEGORY_OVERRIDES_FILE = 'admin/category_overrides.json'
PENDING_CHANGES_FLAG = 'admin/.pending_changes'

# Health metrics
HEALTH_METRICS_FILE = 'metrics/run_diagnostics.json'

# Pull quotes
PULL_QUOTES_CACHE = 'cache/pull_quotes_combined.json'
PULL_QUOTES_GEMINI_CACHE = 'cache/pull_quotes_cache.json'
TASTE_PROFILE_FILE = 'cache/taste_profile_pullquotes.json'

# Country to 3-letter code mapping
COUNTRY_CODES = {
    'United States of America': 'USA', 'United States': 'USA', 'US': 'USA',
    'United Kingdom': 'GBR', 'UK': 'GBR', 'Great Britain': 'GBR',
    'France': 'FRA', 'Germany': 'DEU', 'Italy': 'ITA', 'Spain': 'ESP',
    'Canada': 'CAN', 'Australia': 'AUS', 'Japan': 'JPN', 'China': 'CHN',
    'South Korea': 'KOR', 'Korea': 'KOR', 'India': 'IND', 'Brazil': 'BRA',
    'Mexico': 'MEX', 'Argentina': 'ARG', 'Russia': 'RUS', 'Poland': 'POL',
    'Netherlands': 'NLD', 'Belgium': 'BEL', 'Sweden': 'SWE', 'Norway': 'NOR',
    'Denmark': 'DNK', 'Finland': 'FIN', 'Ireland': 'IRL', 'Austria': 'AUT',
    'Switzerland': 'CHE', 'Portugal': 'PRT', 'Greece': 'GRC', 'Turkey': 'TUR',
    'Israel': 'ISR', 'South Africa': 'ZAF', 'New Zealand': 'NZL',
    'Hong Kong': 'HKG', 'Taiwan': 'TWN', 'Singapore': 'SGP', 'Thailand': 'THA',
    'Indonesia': 'IDN', 'Philippines': 'PHL', 'Malaysia': 'MYS', 'Vietnam': 'VNM',
    'Czech Republic': 'CZE', 'Czechia': 'CZE', 'Hungary': 'HUN', 'Romania': 'ROU',
    'Ukraine': 'UKR', 'Colombia': 'COL', 'Chile': 'CHL', 'Peru': 'PER',
    'Egypt': 'EGY', 'Nigeria': 'NGA', 'Kenya': 'KEN', 'Morocco': 'MAR',
    'Iran': 'IRN', 'Saudi Arabia': 'SAU', 'United Arab Emirates': 'ARE',
    'Iceland': 'ISL', 'Luxembourg': 'LUX', 'Croatia': 'HRV', 'Serbia': 'SRB',
    'Slovenia': 'SVN', 'Slovakia': 'SVK', 'Bulgaria': 'BGR', 'Estonia': 'EST',
    'Latvia': 'LVA', 'Lithuania': 'LTU', 'Georgia': 'GEO', 'Armenia': 'ARM',
    'Kazakhstan': 'KAZ', 'Pakistan': 'PAK', 'Bangladesh': 'BGD', 'Sri Lanka': 'LKA',
}
