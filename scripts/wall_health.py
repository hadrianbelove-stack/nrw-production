#!/usr/bin/env python3
"""Wall health report — shared by /launchagentreport, /nrw, and /status commands.

Reads data.json, movie_tracking.json, and metrics files to produce a
detailed, scannable diagnostic report with:
- Dashboard header with coverage stats
- 14-day pipeline trend (intake + transitions)
- Today's arrivals with enrichment coverage + service names
- Zero watch links (cross-referenced with tracking for root cause)
- JW revert pattern analysis (grouped by reason, excluded platforms, repeat offenders)
- Pre-orders & upcoming (merged, sorted by date, with TMDB platforms + link status)
- Enrichment gaps (movies missing poster, synopsis, or watch links)
- Trailer hosting failures
"""

import json
import os
from collections import Counter
from datetime import date, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
today_dt = date.today()
today = today_dt.isoformat()
three_days_ago = (today_dt - timedelta(days=3)).isoformat()

# ── Load data sources ────────────────────────────────────────────────────────

d = json.load(open(os.path.join(BASE, 'data.json')))
movies = d['movies']
total = len(movies)

tracking_raw = {}
tracking = {}
try:
    t = json.load(open(os.path.join(BASE, 'movie_tracking.json')))
    tracking_raw = t.get('movies', {})
    for mid, m in tracking_raw.items():
        title = m.get('title', '')
        if title:
            tracking[title] = m
        tracking[str(mid)] = m
except Exception:
    pass

# ── Helper: get watch link services for a movie ─────────────────────────────

def get_services(m):
    """Return compact service name list from watch_links."""
    wl = m.get('watch_links', {})
    if not isinstance(wl, dict):
        return []
    services = set()
    for cat_links in wl.values():
        for link in cat_links:
            svc = link.get('service', '') if isinstance(link, dict) else ''
            if svc:
                # Shorten common names for display
                SHORT_NAMES = {'Fandango At Home': 'Fandango', 'Apple TV Store': 'Apple TV',
                               'Amazon Video': 'Amazon', 'Google Play Movies': 'Google Play'}
                short = SHORT_NAMES.get(svc, svc)
                services.add(short)
    return sorted(services)

def get_watch_link_count(m):
    wl = m.get('watch_links', {})
    return sum(len(v) for v in wl.values()) if isinstance(wl, dict) else 0

# ── Section 1: DASHBOARD ────────────────────────────────────────────────────

with_rt = sum(1 for m in movies if m.get('links', {}).get('rt'))
with_mc = sum(1 for m in movies if m.get('metacritic_score'))
with_wiki = sum(1 for m in movies if m.get('links', {}).get('wikipedia'))
with_trailers = sum(1 for m in movies if m.get('links', {}).get('trailer') or m.get('links', {}).get('trailer_hosted'))
with_imdb = sum(1 for m in movies if m.get('imdb_rating'))
with_links = sum(1 for m in movies if get_watch_link_count(m) > 0)

try:
    diag = json.load(open(os.path.join(BASE, 'metrics/run_diagnostics.json')))
    ts = diag.get('timestamp', '?')
    # Show time only (HH:MM)
    time_part = ts[11:16] if len(ts) > 16 else ts
    status = 'SUCCESS' if diag.get('overall_success') else 'FAILURE'
    pipeline_str = '%s %s' % (status, time_part)
except Exception:
    pipeline_str = 'unknown'

pct = lambda n: round(n / total * 100) if total else 0

print('=' * 78)
print('WALL HEALTH REPORT — %s' % today)
print('=' * 78)
print()
print('WALL: %d movies | PIPELINE: %s' % (total, pipeline_str))
print('COVERAGE: RT %d%% (%d) | MC %d%% (%d) | Wiki %d%% (%d) | Trailers %d%% (%d) | IMDb %d%% (%d) | Links %d%% (%d)' % (
    pct(with_rt), with_rt, pct(with_mc), with_mc, pct(with_wiki), with_wiki,
    pct(with_trailers), with_trailers, pct(with_imdb), with_imdb, pct(with_links), with_links))

# ── Section 2: PIPELINE TREND ───────────────────────────────────────────────

print()
print('─' * 78)
print('PIPELINE TREND (14 days)')
print('─' * 78)

daily_path = os.path.join(BASE, 'metrics/daily.jsonl')
trend_rows = []
if os.path.exists(daily_path):
    with open(daily_path) as f:
        lines = f.readlines()
    for line in lines[-14:]:
        try:
            entry = json.loads(line.strip())
            trend_rows.append(entry)
        except Exception:
            pass

if trend_rows:
    print('  %-12s  %7s  %12s' % ('Date', 'Intake', 'Transitions'))
    print('  ' + '─' * 35)
    for row in trend_rows:
        d_str = row.get('date', '?')
        intake = row.get('intaked_today', 0)
        trans = row.get('transitions', 0)
        flag = '  !! STALL' if trans == 0 else ''
        print('  %-12s  %7d  %12d%s' % (d_str, intake, trans, flag))
    print('  ' + '─' * 35)
    avg_intake = sum(r.get('intaked_today', 0) for r in trend_rows) / len(trend_rows)
    avg_trans = sum(r.get('transitions', 0) for r in trend_rows) / len(trend_rows)
    print('  %-12s  %7.0f  %12.0f' % ('14-day avg', avg_intake, avg_trans))
    # Flag today vs average
    if trend_rows:
        last = trend_rows[-1]
        t_intake = last.get('intaked_today', 0)
        t_trans = last.get('transitions', 0)
        notes = []
        if avg_intake > 0 and t_intake < avg_intake * 0.3:
            notes.append('intake well below avg')
        if avg_trans > 0 and t_trans < avg_trans * 0.3:
            notes.append('transitions well below avg')
        if avg_trans > 0 and t_trans == 0:
            notes.append('ZERO transitions today')
        if notes:
            print('  !! %s' % ' | '.join(notes))
else:
    print('  (no daily.jsonl data found)')

# ── Section 3: TODAY'S ARRIVALS ──────────────────────────────────────────────

arrivals = [m for m in movies if m.get('digital_date') == today]

print()
print('─' * 78)
print("TODAY'S ARRIVALS: %d (%s)" % (len(arrivals), today))
print('─' * 78)

if arrivals:
    col_w = 38
    print('  %-*s  %-3s %-3s %-4s %-7s %-4s %-4s  %s' % (col_w, 'Movie', 'RT', 'MC', 'Wiki', 'Trailer', 'IMDb', 'Links', 'Services'))
    print('  ' + '─' * (col_w + 55))
    gaps_count = 0
    for a in arrivals:
        links = a.get('links', {})
        wl_count = get_watch_link_count(a)
        has_rt = 'yes' if a.get('rt_score') else '--'
        has_mc = 'yes' if a.get('metacritic_score') else '--'
        has_wiki = 'yes' if links.get('wikipedia') else '--'
        has_trailer = 'yes' if (links.get('trailer') or links.get('trailer_hosted')) else '--'
        has_imdb = 'yes' if a.get('imdb_rating') else '--'
        has_links = 'yes' if wl_count > 0 else 'NONE'
        svcs = get_services(a)
        svc_str = ', '.join(svcs) if svcs else ''
        title_display = a['title'][:col_w]
        has_gap = '--' in (has_rt, has_mc, has_wiki, has_trailer, has_imdb) or has_links == 'NONE'
        if has_gap:
            gaps_count += 1
        print('  %-*s  %-3s %-3s %-4s %-7s %-4s %-4s  %s' % (
            col_w, title_display, has_rt, has_mc, has_wiki, has_trailer, has_imdb, has_links, svc_str))
    print('  ' + '─' * (col_w + 55))
    if gaps_count:
        print('  Gaps: %d of %d arrivals have missing fields' % (gaps_count, len(arrivals)))
    else:
        print('  All %d arrivals fully enriched' % len(arrivals))
else:
    print('  (no arrivals today)')

# ── Section 4: ZERO WATCH LINKS ─────────────────────────────────────────────

zero_future = []
zero_broken = []
for m in movies:
    if get_watch_link_count(m) == 0:
        if m.get('_is_preorder'):
            continue  # Pre-orders are expected to have no watch links
        dd = m.get('digital_date') or ''
        if dd > today:
            zero_future.append(m)
        else:
            zero_broken.append(m)

zero_pct = round(len(zero_broken) / total * 100, 1) if total else 0

print()
print('─' * 78)
if zero_pct > 5:
    print('!! CRITICAL: %d movies have zero watch links (%.1f%% of wall)' % (len(zero_broken), zero_pct))
    print('!! Enrichment pipeline likely broken.')
else:
    print('ZERO WATCH LINKS (released, should have links)')
print('─' * 78)

if not zero_broken:
    print('  None — all released movies have links')
else:
    rows = []
    aged_out = 0
    for m in zero_broken:
        title = m['title']
        mid = str(m.get('id', ''))
        dd = m.get('digital_date') or '?'
        try:
            days = (today_dt - date.fromisoformat(dd)).days
        except Exception:
            days = '?'

        tk = tracking.get(title) or tracking.get(mid) or {}
        reason = tk.get('_jw_revert_reason', '')
        rev_at = tk.get('_jw_reverted_at', '')
        rev_count = tk.get('_jw_revert_count', 0)
        discovery_src = tk.get('_discovery_source', '')

        _age_ref = rev_at or dd
        if _age_ref and _age_ref != '?' and _age_ref < three_days_ago:
            aged_out += 1
            continue

        provs = tk.get('providers', {})
        plat_names = []
        for cat in ['rent', 'buy', 'streaming']:
            for p in provs.get(cat, []):
                plat_names.append(p)

        if reason == 'justwatch_no_valid_offers':
            status = 'Excluded: ' + (', '.join(plat_names) if plat_names else '(not recorded)')
        elif reason == 'justwatch_no_match':
            status = 'No JW match' + (' — TMDB: ' + ', '.join(plat_names) if plat_names else '')
        elif reason == 'zero_watch_links':
            status = 'Enriched, zero links' + (' — TMDB: ' + ', '.join(plat_names) if plat_names else '')
        elif reason:
            status = 'JW revert: ' + reason
        else:
            status = 'No revert — possible enrichment gap'

        if discovery_src:
            src_label = {'tmdb_type4': 'Type4', 'provider_availability_check': 'providers'}.get(discovery_src, discovery_src)
            status += ' [via %s]' % src_label
        if rev_count > 1:
            status += ' [%dx]' % rev_count

        rows.append((title, dd, days, status))

    rows.sort(key=lambda r: -r[2] if isinstance(r[2], int) else 0)

    shown = len(rows)
    if shown:
        print('  %d active (+ %d aged out >3d)' % (shown, aged_out) if aged_out else '  %d active' % shown)
        print()
        for title, dd, days, status in rows:
            days_str = '%dd' % days if isinstance(days, int) else '?'
            print('  %-42s  %s  %4s  %s' % (title[:42], dd, days_str, status))
    else:
        if aged_out:
            print('  All %d aged out (>3 days) — no action items' % aged_out)
        else:
            print('  None')

# ── Section 5: JW REVERTS (tracking only, not on wall) ──────────────────────

wall_titles = set(m['title'] for m in movies)
jw_reverts = []
repeat_offenders = []

for mid, m in tracking_raw.items():
    rev_at = m.get('_jw_reverted_at', '')
    reason = m.get('_jw_revert_reason', '')
    title = m.get('title', str(mid))
    rev_count = m.get('_jw_revert_count', 0)

    # Repeat offenders: any movie reverted 2+ times (regardless of recency or wall status)
    if rev_count >= 2:
        provs = m.get('providers', {})
        plat_names = []
        for cat in ['rent', 'buy', 'streaming']:
            for p in provs.get(cat, []):
                plat_names.append(p)
        repeat_offenders.append((rev_count, title, reason, plat_names))

    # Recent reverts not on wall
    if rev_at >= three_days_ago and reason and title not in wall_titles:
        provs = m.get('providers', {})
        plat_names = []
        for cat in ['rent', 'buy', 'streaming']:
            for p in provs.get(cat, []):
                plat_names.append(p)
        jw_reverts.append((rev_at, title, reason, plat_names))

print()
print('─' * 78)
print('JW REVERTS (tracking only, not on wall) — %d in last 3 days' % len(jw_reverts))
print('─' * 78)

if jw_reverts:
    # Reason summary
    reason_counts = Counter()
    excluded_platforms = Counter()
    for rev_at, title, reason, plat_names in jw_reverts:
        if reason == 'justwatch_no_valid_offers':
            reason_counts['excluded platform'] += 1
            for p in plat_names:
                excluded_platforms[p] += 1
        elif reason == 'justwatch_no_match':
            reason_counts['no JW match'] += 1
        else:
            reason_counts[reason] += 1

    print()
    print('  REASON SUMMARY:')
    for reason, count in reason_counts.most_common():
        print('    %-30s %d' % (reason, count))

    if excluded_platforms:
        print()
        print('  EXCLUDED PLATFORMS (which services caused reverts):')
        for plat, count in excluded_platforms.most_common():
            print('    %-30s %d %s' % (plat, count, 'movie' if count == 1 else 'movies'))

    # Full list
    print()
    print('  FULL LIST:')
    print('  %-12s %-45s %s' % ('Date', 'Title', 'Reason / TMDB Platforms'))
    print('  ' + '─' * 72)
    for rev_at, title, reason, plat_names in sorted(jw_reverts):
        if reason == 'justwatch_no_valid_offers':
            label = 'excluded: ' + (', '.join(plat_names) if plat_names else '(not recorded)')
        elif reason == 'justwatch_no_match':
            label = 'no JW match' + (' — TMDB: ' + ', '.join(plat_names) if plat_names else '')
        else:
            label = reason
        print('  %-12s %-45s %s' % (rev_at, title[:45], label))
else:
    print('  None in last 3 days')

# Repeat offenders (separate from recent — these span all time)
if repeat_offenders:
    repeat_offenders.sort(key=lambda r: -r[0])
    print()
    print('  REPEAT OFFENDERS (reverted 2+ times — investigate for pipeline fixes):')
    print('  %-4s %-45s %s' % ('Count', 'Title', 'TMDB Platforms'))
    print('  ' + '─' * 72)
    for rev_count, title, reason, plat_names in repeat_offenders[:20]:  # Cap at 20
        plat_str = ', '.join(plat_names) if plat_names else '(none)'
        print('  %-4s %-45s %s' % ('%dx' % rev_count, title[:45], plat_str))
    if len(repeat_offenders) > 20:
        print('  ... and %d more' % (len(repeat_offenders) - 20))

# ── Section 6: PRE-ORDERS & UPCOMING ────────────────────────────────────────

# Merge: pre-order flagged movies + future-dated zero-link movies
preorder_set = set()
merged = []

for m in movies:
    if m.get('_is_preorder'):
        preorder_set.add(m['title'])
        dd = m.get('digital_date', '?')
        mid = str(m.get('id', ''))
        pol = m.get('pre_order_links', [])
        svcs = [p.get('service', '?') for p in pol] if isinstance(pol, list) else []
        # Cross-reference tracking for TMDB platforms
        tk = tracking.get(m['title']) or tracking.get(mid) or {}
        provs = tk.get('providers', {})
        tmdb_plats = []
        for cat in ['rent', 'buy', 'streaming']:
            for p in provs.get(cat, []):
                SHORT_NAMES = {'Fandango At Home': 'Fandango', 'Apple TV Store': 'Apple TV',
                               'Amazon Video': 'Amazon', 'Google Play Movies': 'Google Play'}
                tmdb_plats.append(SHORT_NAMES.get(p, p))
        tmdb_str = ', '.join(sorted(set(tmdb_plats))) if tmdb_plats else ''
        buyonly = ' (buy-only)' if m.get('_buyonly_preorder') else ''
        merged.append((dd, m['title'], len(svcs), ', '.join(svcs) if svcs else 'NONE', tmdb_str, buyonly))

# Add future-dated zero-link movies not already in pre-order set
for m in zero_future:
    title = m['title']
    if title not in preorder_set:
        dd = m.get('digital_date', '?')
        mid = str(m.get('id', ''))
        tk = tracking.get(title) or tracking.get(mid) or {}
        provs = tk.get('providers', {})
        tmdb_plats = []
        for cat in ['rent', 'buy', 'streaming']:
            for p in provs.get(cat, []):
                SHORT_NAMES = {'Fandango At Home': 'Fandango', 'Apple TV Store': 'Apple TV',
                               'Amazon Video': 'Amazon', 'Google Play Movies': 'Google Play'}
                tmdb_plats.append(SHORT_NAMES.get(p, p))
        tmdb_str = ', '.join(sorted(set(tmdb_plats))) if tmdb_plats else ''
        merged.append((dd, title, 0, 'NONE', tmdb_str, ''))

merged.sort(key=lambda r: r[0] if r[0] != '?' else '9999')

print()
print('─' * 78)
print('PRE-ORDERS & UPCOMING — %d movies' % len(merged))
print('─' * 78)

if merged:
    col_w = 38
    print('  %-12s %-*s %-6s %-20s %s' % ('Date', col_w, 'Title', 'Links', 'Pre-order Services', 'TMDB Platforms'))
    print('  ' + '─' * (col_w + 55))
    no_link_count = 0
    for dd, title, n_links, services, tmdb_str, buyonly in merged:
        link_str = str(n_links) if n_links > 0 else 'NONE'
        if n_links == 0:
            no_link_count += 1
        display_title = (title[:col_w - 10] + buyonly) if buyonly else title[:col_w]
        svc_display = services if n_links > 0 else ''
        print('  %-12s %-*s %-6s %-20s %s' % (dd, col_w, display_title, link_str, svc_display, tmdb_str))
    print('  ' + '─' * (col_w + 55))
    has_links = len(merged) - no_link_count
    print('  Links found: %d of %d | No links: %d' % (has_links, len(merged), no_link_count))
else:
    print('  None')

# ── Section 7: ENRICHMENT GAPS ──────────────────────────────────────────────

gap_no_poster = []
gap_no_synopsis = []
gap_no_links = []

for m in movies:
    title = m.get('title', '?')
    dd = m.get('digital_date', '?')
    mid = str(m.get('id', ''))
    e_status = m.get('_enrichment_status', '?')
    if not m.get('poster'):
        gap_no_poster.append((title, dd, e_status, mid))
    if not m.get('synopsis'):
        gap_no_synopsis.append((title, dd, e_status, mid))
    # Only flag missing links on released non-preorder movies
    if get_watch_link_count(m) == 0 and not m.get('_is_preorder') and dd <= today:
        gap_no_links.append((title, dd, e_status, mid))

total_gaps = len(set(r[0] for r in gap_no_poster + gap_no_synopsis + gap_no_links))

print()
print('─' * 78)
print('ENRICHMENT GAPS — %d movies with missing data' % total_gaps)
print('─' * 78)

if total_gaps == 0:
    print('  None — all movies fully enriched')
else:
    col_w = 42
    if gap_no_poster:
        print()
        print('  NO POSTER (%d):' % len(gap_no_poster))
        print('  %-*s %-12s %s' % (col_w, 'Title', 'Date', 'Enrichment'))
        print('  ' + '─' * (col_w + 25))
        for title, dd, e_status, mid in sorted(gap_no_poster, key=lambda r: r[1] or '', reverse=True):
            print('  %-*s %-12s %s' % (col_w, title[:col_w], dd, e_status))

    if gap_no_synopsis:
        print()
        print('  NO SYNOPSIS (%d):' % len(gap_no_synopsis))
        print('  %-*s %-12s %s' % (col_w, 'Title', 'Date', 'Enrichment'))
        print('  ' + '─' * (col_w + 25))
        for title, dd, e_status, mid in sorted(gap_no_synopsis, key=lambda r: r[1] or '', reverse=True):
            print('  %-*s %-12s %s' % (col_w, title[:col_w], dd, e_status))

    if gap_no_links:
        print()
        print('  NO WATCH LINKS — released, non-preorder (%d):' % len(gap_no_links))
        print('  %-*s %-12s %s' % (col_w, 'Title', 'Date', 'Enrichment'))
        print('  ' + '─' * (col_w + 25))
        for title, dd, e_status, mid in sorted(gap_no_links, key=lambda r: r[1] or '', reverse=True):
            print('  %-*s %-12s %s' % (col_w, title[:col_w], dd, e_status))

    print()
    print('  Summary: %d movies (%d no poster, %d no synopsis, %d no links)' % (
        total_gaps, len(gap_no_poster), len(gap_no_synopsis), len(gap_no_links)))

# ── Section 8: TRAILER FAILURES ─────────────────────────────────────────────

host_fail_path = os.path.join(BASE, 'cache', 'trailer_host_failures.json')
if os.path.exists(host_fail_path):
    try:
        hf = json.load(open(host_fail_path))
        cutoff = three_days_ago
        recent_fails = [(v['recorded_at'][:10], v['title'], v.get('reason', '?'))
                        for v in hf.values() if v.get('recorded_at', '') >= cutoff]
        if recent_fails:
            print()
            print('─' * 78)
            print('TRAILER HOSTING FAILURES — %d in last 3 days' % len(recent_fails))
            print('─' * 78)
            for fail_date, title, reason in sorted(recent_fails):
                print('  %-12s %-42s %s' % (fail_date, title[:42], reason))
    except Exception:
        pass

print()
print('=' * 78)
