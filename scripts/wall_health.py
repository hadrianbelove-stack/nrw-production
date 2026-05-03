#!/usr/bin/env python3
"""Wall health report — shared by /launchagentreport, /nrw, and /status commands.

Reads data.json + movie_tracking.json and prints a diagnostic summary:
- Wall size, pipeline health, coverage stats
- Today's arrivals with enrichment gaps
- Last 7 days of arrivals
- Upcoming (future-dated, no links expected)
- Zero watch links (cross-referenced with tracking for root cause)
- JW reverted movies in tracking only (not on wall)
"""

import json
from collections import Counter
from datetime import date, timedelta

d = json.load(open('data.json'))
movies = d['movies']
total = len(movies)

today = date.today().isoformat()
today_dt = date.today()
arrivals = [m for m in movies if m.get('digital_date') == today]

week_ago = (date.today() - timedelta(days=7)).isoformat()
recent = [m for m in movies if (m.get('digital_date') or '') >= week_ago]
by_date = Counter(m.get('digital_date') for m in recent)

# Load tracking data for cross-referencing
tracking = {}
try:
    t = json.load(open('movie_tracking.json'))
    for mid, m in t.get('movies', {}).items():
        title = m.get('title', '')
        if title:
            tracking[title] = m
        tracking[str(mid)] = m
except:
    pass

# Zero watch links — split future releases from actual failures
zero_future = []
zero_broken = []
for m in movies:
    wl = m.get('watch_links', {})
    wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
    if wl_count == 0:
        dd = m.get('digital_date') or ''
        if dd > today:
            zero_future.append((dd, m['title'], m.get('id')))
        else:
            zero_broken.append(m)

pct = round(len(zero_broken) / total * 100, 1) if total else 0

# Coverage stats
with_rt = sum(1 for m in movies if m.get('links', {}).get('rt'))
with_wiki = sum(1 for m in movies if m.get('links', {}).get('wikipedia'))
with_trailers = sum(1 for m in movies if m.get('links', {}).get('trailer') or m.get('links', {}).get('trailer_hosted'))

# Pipeline health
try:
    diag = json.load(open('metrics/run_diagnostics.json'))
    health = diag.get('timestamp', '?') + ' — ' + ('SUCCESS' if diag.get('overall_success') else 'FAILURE')
except:
    health = 'unknown'

print('WALL: %d movies' % total)
print('PIPELINE: %s' % health)
print('COVERAGE: RT=%d  Wiki=%d  Trailers=%d (%d%%)' % (with_rt, with_wiki, with_trailers, round(with_trailers / total * 100) if total else 0))
print('TODAY (%s): %d new arrivals' % (today, len(arrivals)))
for a in arrivals:
    print('  - ' + a['title'])

# Enrichment gaps for today's arrivals
gaps_found = []
for a in arrivals:
    missing = []
    links = a.get('links', {})
    crew = a.get('crew', {})
    wl = a.get('watch_links', {})
    wl_count = sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0
    if not links.get('trailer') and not links.get('trailer_hosted'):
        missing.append('trailer')
    if not links.get('wikipedia'):
        missing.append('wikipedia')
    if wl_count == 0:
        missing.append('watch_links')
    if not a.get('rt_score'):
        missing.append('rt_score')
    if not a.get('imdb_rating'):
        missing.append('imdb_rating')
    d_name = crew.get('director', '')
    if not d_name or d_name == 'Unknown':
        missing.append('director')
    if not a.get('country'):
        missing.append('country')
    if not a.get('year'):
        missing.append('year')
    if not a.get('runtime'):
        missing.append('runtime')
    if missing:
        gaps_found.append((a['title'], missing))
if gaps_found:
    print('ENRICHMENT GAPS (%d of %d arrivals):' % (len(gaps_found), len(arrivals)))
    for title, missing in gaps_found:
        print('  %s — missing: %s' % (title, ', '.join(missing)))
elif arrivals:
    print('ENRICHMENT GAPS: 0 — all %d arrivals fully enriched' % len(arrivals))

print('LAST 7 DAYS:')
for dt in sorted(by_date):
    print('  %s: %d titles' % (str(dt), by_date[dt]))

if zero_future:
    print('UPCOMING (%d) — no links yet, not released:' % len(zero_future))
    for dd, t, mid in sorted(zero_future):
        print('  %s  %s' % (dd, t))

# Detailed zero watch links table (cross-referenced with tracking)
if len(zero_broken) == 0:
    print('ZERO WATCH LINKS: 0 — All enriched OK')
else:
    # Build detailed rows (JW reverts age out after 3 days; real failures always show)
    rows = []
    three_days_ago = (date.today() - timedelta(days=3)).isoformat()
    aged_out = 0
    for m in zero_broken:
        title = m['title']
        mid = str(m.get('id', ''))
        dd = m.get('digital_date') or '?'

        try:
            dd_date = date.fromisoformat(dd)
            days = (today_dt - dd_date).days
        except:
            days = '?'

        tk = tracking.get(title) or tracking.get(mid) or {}
        reason = tk.get('_jw_revert_reason', '')
        rev_at = tk.get('_jw_reverted_at', '')
        rev_count = tk.get('_jw_revert_count', 0)
        discovery_src = tk.get('_discovery_source', '')

        # JW reverts age out of report after 3 days
        if reason and rev_at and rev_at < three_days_ago:
            aged_out += 1
            continue

        provs = tk.get('providers', {})
        plats = []
        for cat in ['rent', 'buy', 'streaming']:
            for p in provs.get(cat, []):
                plats.append(p + ' (' + cat + ')')

        if reason == 'justwatch_no_valid_offers':
            if plats:
                status = 'Excluded platforms: ' + ', '.join(plats)
            else:
                status = 'Excluded platforms (names not recorded in tracking)'
        elif reason == 'justwatch_no_match':
            if plats:
                status = 'No JW match (TMDB saw: ' + ', '.join(p.split(' (')[0] for p in plats) + ')'
            else:
                status = 'No JW match found'
        elif reason:
            status = 'JW revert: ' + reason
        else:
            status = 'No tracking revert — possible enrichment gap'

        if discovery_src:
            src_label = {'tmdb_type4': 'Type 4', 'provider_availability_check': 'providers'}.get(discovery_src, discovery_src)
            status += ' [discovered via %s]' % src_label

        if rev_count > 1:
            status += ' [reverted %dx]' % rev_count

        rows.append((title, dd, days, status))

    def sort_key(r):
        d = r[2]
        return -d if isinstance(d, int) else 0
    rows.sort(key=sort_key)

    # Print header with filtered count
    shown = len(rows)
    if pct > 5:
        print('CRITICAL ENRICHMENT FAILURE: %d movies have zero watch links (%s%% of wall)' % (len(zero_broken), pct))
        print('   This is NOT normal. Enrichment pipeline likely broken.')
    header = 'NEW ZERO WATCH LINKS: %d' % shown
    if aged_out:
        header += ' (+%d aged out >3d)' % aged_out
    print(header)

    for title, dd, days, status in rows:
        t_display = title[:45]
        days_str = str(days) + 'd' if isinstance(days, int) else '?'
        print('  %-45s  %s  %4s  %s' % (t_display, dd, days_str, status))
    if not rows:
        print('  (all reverts aged out — no action items)')

# JW reverted movies NOT on the wall (in tracking only, not in data.json — last 3 days)
three_days_ago = (date.today() - timedelta(days=3)).isoformat()
wall_titles = set(m['title'] for m in movies)
jw_tracking_only = []
for mid, m in (json.load(open('movie_tracking.json')).get('movies', {}) if tracking else {}).items():
    rev_at = m.get('_jw_reverted_at', '')
    if rev_at >= three_days_ago and m.get('_jw_revert_reason'):
        title = m.get('title', str(mid))
        if title not in wall_titles:
            provs = m.get('providers', {})
            plats = []
            for cat in ['rent', 'buy', 'streaming']:
                for p in provs.get(cat, []):
                    plats.append(p + ' (' + cat + ')')
            reason = m['_jw_revert_reason']
            if reason == 'justwatch_no_valid_offers':
                label = 'excluded: ' + (', '.join(p.split(' (')[0] for p in plats) if plats else 'names not recorded')
            elif reason == 'justwatch_no_match':
                label = 'no JW match' + (' (TMDB: ' + ', '.join(p.split(' (')[0] for p in plats) + ')' if plats else '')
            else:
                label = reason
            jw_tracking_only.append((rev_at, title, label))

if jw_tracking_only:
    print('JW REVERTED (tracking only, not on wall) — %d in last 3 days:' % len(jw_tracking_only))
    for rev_at, title, label in sorted(jw_tracking_only):
        print('  %s  %-40s  %s' % (rev_at, title, label))
