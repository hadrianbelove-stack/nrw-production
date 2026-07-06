"""Canonical provider-name handling for watch links.

THE single place where raw supplier names (JustWatch, TMDB, scrapers,
manual entries) become NRW display names, and where watch_links are
deduped. Every writer of watch_links into data.json must pass its result
through normalize_watch_links() at its exit boundary:

  - EnrichmentService.get_watch_links (all waterfall paths incl. cache)
  - Discoverer gap-fill merge
  - Display build: cache-injection + manual tracking overlay (display.py)
  - Admin panel manual edits (admin/routes/curation.py)

The duplicate guard in ValidationService.fix_data_json_schema warns on
every pipeline pass if a new writer bypasses this list.

Dedup MUST key on the simplified name: JustWatch lists ad-supported tiers
as separate offers ("Netflix" + "Netflix Standard with Ads", same URL),
which only collapse to the same name after simplification. Deduping on
raw names shipped two identical Netflix buttons (fixed Jul 2026).
"""

import re

# Fields preserved on normalized entries; anything else (e.g. JustWatch
# internals like _ptype) is dropped from data.json output.
_ENTRY_FIELDS = ('rent_price', 'buy_price', 'price')

# Ad-supported tier suffixes ("Netflix Standard with Ads", "Fawesome with
# Ads") — same service as the base tier. Stripped BEFORE the simplification
# table so tier collapse works even for services the table doesn't know.
# Anchored to "with ads$" so real bundles ("Paramount+ with Showtime") never
# match.
_ADS_TIER_RE = re.compile(r'\s+(?:standard\s+|basic\s+|premium\s+)?with\s+ads$', re.IGNORECASE)


def simplify_provider_name(provider_name):
    """Simplify provider names for display
    Examples:
    - 'Amazon Prime Video' → 'Amazon Prime Video' (streaming — different from VOD)
    - 'Amazon Video' → 'Amazon' (VOD rent/buy)
    - 'DocuramaFilms Amazon Channel' → 'DocuramaFilms' (NOT 'Amazon')
    - 'Shudder Amazon Channel' → 'Shudder'
    - 'AMC Plus Apple TV Channel' → 'AMC+'
    """
    if not provider_name:
        return provider_name

    # Strip ad-tier suffixes first — "Fawesome with Ads" is Fawesome even
    # though the table below has never heard of it
    provider_name = _ADS_TIER_RE.sub('', provider_name).strip() or provider_name

    # Strip platform channel suffixes FIRST — these are third-party channels
    # hosted on Amazon/Apple, not Amazon/Apple themselves
    provider_lower = provider_name.lower()
    channel_suffixes = ['amazon channel', 'apple tv channel']
    for suffix in channel_suffixes:
        if suffix in provider_lower:
            # Extract the actual channel name (everything before the suffix)
            idx = provider_lower.index(suffix)
            channel_name = provider_name[:idx].strip()
            if channel_name:
                # Re-run the channel name through simplification (e.g. "AMC Plus" → "AMC+")
                return simplify_provider_name(channel_name)

    # Most specific patterns first
    # NOTE: 'amazon prime' MUST come before 'amazon' — Prime Video (streaming)
    # is a different service from Amazon (VOD rent/buy) with different logos
    simplifications = [
        ('amc', 'AMC+'),
        ('netflix', 'Netflix'),
        ('disney', 'Disney+'),
        ('hulu', 'Hulu'),
        ('hbo max', 'Max'),
        ('paramount', 'Paramount+'),
        ('peacock', 'Peacock'),
        ('amazon prime', 'Amazon Prime Video'),
        ('prime video', 'Amazon Prime Video'),
        ('amazon', 'Amazon'),
        ('apple tv', 'Apple TV'),
        ('shudder', 'Shudder'),
        ('mubi', 'MUBI'),
        ('criterion', 'Criterion'),
        ('vudu', 'Vudu'),
        ('youtube', 'YouTube'),
        ('fandango', 'Fandango'),
    ]

    for pattern, simplified in simplifications:
        if pattern in provider_lower:
            return simplified

    return provider_name


def normalize_watch_links(watch_links):
    """One canonical pass over a watch_links dict, per category:

    1. coerce legacy single-dict shape to a one-element list
    2. simplify each entry's service name
    3. dedupe on the simplified name (keep first — VOD's first entry
       carries the merged HD prices; JustWatch orders by priority)

    Entries that aren't {service, ...} dicts pass through untouched, as do
    non-list/dict categories. Never drops an offer's only link: dedup only
    removes entries whose (simplified) service already appeared.
    """
    if not isinstance(watch_links, dict):
        return watch_links

    normalized = {}
    for category, entries in watch_links.items():
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            normalized[category] = entries
            continue

        kept = {}  # simplified key -> entry already in out (for backfill)
        out = []
        for item in entries:
            if not isinstance(item, dict) or 'service' not in item:
                out.append(item)
                continue
            name = simplify_provider_name(item['service'])
            key = (name or '').strip().lower()
            if key and key in kept:
                # Duplicate service: keep the first entry's position, but
                # backfill a missing link/prices from the later one so a
                # link-less first entry never shadows a real link
                first = kept[key]
                if not first.get('link') and item.get('link'):
                    first['link'] = item['link']
                for field in _ENTRY_FIELDS:
                    if not first.get(field) and item.get(field):
                        first[field] = item[field]
                continue
            entry = {'service': name, 'link': item.get('link')}
            for field in _ENTRY_FIELDS:
                if item.get(field):
                    entry[field] = item[field]
            if key:
                kept[key] = entry
            out.append(entry)
        normalized[category] = out

    return normalized
