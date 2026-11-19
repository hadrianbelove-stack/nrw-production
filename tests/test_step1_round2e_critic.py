"""Round 2e completeness critic: interactions between the 2e changes nobody tested.

Runs only in the critic's own copy (round2e/verify/critic/wt) through the Step 1 harnesses:
  * World (tests/test_step1_holds_and_dates.py): real v2 pipeline in a tmp dir, network + clock faked.
  * run_daily (tests/test_step1_preorders.py): real daily phases in a sandbox.
Real records: 78303fd6 (2001: A Space Odyssey, Harlem) and origin/main (The History of Concrete,
round2d/review/preorders-verify/my_records.json, copied next to this copy). JustWatch offers a test
adds are SYNTHETIC and say what they stand for.
"""
import copy
import json
import os
import sys

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_step1_holds_and_dates import (  # noqa: E402,F401
    world, real, day, TODAY, HARLEM, HARLEM_AMAZON, putback, jw_offer, jw_node,
    harlem_store_offers, FakeStorePages, FIRST_OFFER, CONFIRMED, _harlem_on_the_wall_by_mistake,
    _revert_script, discoverer_mod,
)
from test_step1_preorders import (  # noqa: E402,F401
    _worktree_write_audit, run_daily, final, only, offer,
)

CRITIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'step1_fixtures')  # real records (origin/main)
AFTER_HOLD = putback.AFTER_HOLD
OFFER_START = putback.OFFER_START


def _on_main_wall(e):
    return bool(e) and not e.get('hidden') and not e.get('_is_preorder')


def _cinema(node):
    return [o for o in node['offers'] if o['monetizationType'] == 'CINEMA']


# ---------------------------------------------------------------------------------------------
# C1. R2D-REV-1's fix keys on the TRACKING reissue flags. 15 of the 17 films in the live wall's
#     Restorations section are auto-detected by year gap (display.py:569-583) and carry none.
# ---------------------------------------------------------------------------------------------

ODYSSEY = '62'


def _odyssey_on_the_wall(world):
    """2001: A Space Odyssey -- the real 78303fd6 tracking record and wall entry (1968 film, on the
    wall 2026-10-19 via the AFI Fest intake + provider check, in the Restorations section by the
    year gap; no _reissue / reissue_label). JustWatch: the ORIGINAL film's old listings (SYNTHETIC:
    HBO Max since 2020, Amazon / Apple rentals since 2015). The owner reverts it: the restoration
    isn't out (the REV-1 situation)."""
    src = json.load(open(os.path.join(CRITIC, 'odyssey_62.json')))
    rec, entry = copy.deepcopy(src['tracking']), copy.deepcopy(src['wall'])
    rec.update({'digital_date': day(-1), '_transitioned_at': day(-1)})
    entry['digital_date'] = day(-1)
    world.seed({ODYSSEY: rec}, wall=[entry])
    world.tmdb.set_dates(ODYSSEY, (3, '1968-04-02', ''))
    amz = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.92a9f688-d43b-4e9a-b14d-6394c8b616c9'
    apple = 'https://tv.apple.com/us/movie/2001-a-space-odyssey/umc.cmc.1au04fbnh3q5i2p6sy0ik4rkz'
    node = jw_node(ODYSSEY, '2001: A Space Odyssey', 1968, [
        jw_offer('FLATRATE', 'HBO Max', 'https://play.hbomax.com/show/2001', created='2020-05-27'),
        jw_offer('RENT', 'Amazon Video', amz, '$3.99', '2015-01-01T08:00:00Z', created='2015-01-01'),
        jw_offer('RENT', 'Apple TV Store', apple, '$3.99', '2015-01-01T08:00:00Z', created='2015-01-01')])
    world.jw.edges['2001: A Space Odyssey'] = [node]
    world.pages.text = FakeStorePages.AVAILABLE
    code, out = _revert_script(world, ODYSSEY)
    assert code == 0, out
    return node, out


def test_c1_year_gap_restoration_reverted_comes_back_on_the_originals_catalog_churn(world):
    """Round 2f (RV-F1/ENR-2): the revert reads the wall entry -- a restoration by the year gap --
    and marks the tracking record (_revert_restoration), so its note explains the original film's
    listing can bring it back. Owner, Nov 2026 (no "re-add it yourself"): checked daily, it comes
    back on the original's new streaming home, dated that day."""
    node, out = _odyssey_on_the_wall(world)
    assert putback.is_reissue(world.tracking()[ODYSSEY])              # the REV-1 guard applies
    assert world.tracking()[ODYSSEY].get('_revert_restoration') is True
    assert 'A reissue or restoration' in out and 'Note:' in out, out
    world.run(on_day=1)
    world.enrich(on_day=1)
    assert world.tracking()[ODYSSEY]['status'] == 'tracking'
    # Day 5 (SYNTHETIC churn of the ORIGINAL 1968 film): a free streaming home records it.
    node['offers'].append(jw_offer('FREE', 'Pluto TV', 'https://pluto.tv/movies/2001', created=day(5)))
    world.run(on_day=5)
    rec = world.tracking()[ODYSSEY]
    print('REVERT OUTPUT:', out)
    print('DAY 5:', rec['status'], rec.get('digital_date'), rec.get('_digital_date_source'))
    assert (rec['status'], rec['digital_date']) == ('available', day(5)), rec


# ---------------------------------------------------------------------------------------------
# C2. R2D-REV-4: the revert gate now reads AMAZON's page, but the pre-order guard right after it
#     (_is_held_rent_preorder, provider and Type-4 paths) still reads the FIRST store's page.
# ---------------------------------------------------------------------------------------------

HARLEM_APPLE = 'https://tv.apple.com/us/movie/once-upon-a-time-in-harlem/umc.cmc.harlem'


@pytest.mark.parametrize('apple_page', ['pre-order', None])
def test_c2_gate_reads_amazon_but_the_guard_reads_the_first_store(world, apple_page):
    """Harlem reverted today. JustWatch lists Apple's rental FIRST, then Amazon's (both SYNTHETIC,
    recorded and live since day -5, before the revert: nothing new). Amazon's page reads
    'Pre-order' on day 1 and 'available' on day 2 -- the 2e rule: back on day 2. Apple's page
    reads 'Pre-order' (or is unreadable: the control)."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + [
        jw_offer('RENT', 'Apple TV Store', HARLEM_APPLE, '$5.99', f'{day(-5)}T07:00:00Z', created=day(-5)),
        jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$5.99', f'{day(-5)}T07:00:00Z', created=day(-5)),
        jw_offer('BUY', 'Amazon Video', HARLEM_AMAZON, '$14.99', f'{day(-5)}T07:00:00Z', created=day(-5))]
    verdict = {'amazon': 'pre-order', 'apple': apple_page}
    read = []

    def fake_read(self, url, title):
        v = verdict['amazon'] if 'amazon.' in url else verdict['apple'] if 'apple.com' in url else None
        read.append((world.clock.days, url.split('/')[2], v))
        return v

    world._mp.setattr(discoverer_mod.ProviderDiscoverer, '_read_preorder_page', fake_read)
    world.run(on_day=1)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'tracking' and rec.get('_revert_page_preorder') == day(1), rec
    verdict['amazon'] = 'available'
    world.run(on_day=2)
    rec = world.tracking()[HARLEM]
    print('PAGES READ (day, host, verdict):', read)
    print('DAY 2:', {k: rec.get(k) for k in ('status', 'digital_date', '_digital_date_source',
                                             '_rent_preorder_held', '_jw_last_refuted')})
    assert rec['status'] == 'available', (
        f"Amazon's page read 'available' on day 2 but the film is still held: "
        f"_rent_preorder_held={rec.get('_rent_preorder_held')} _jw_last_refuted={rec.get('_jw_last_refuted')}; "
        f'pages read: {read}')


# ---------------------------------------------------------------------------------------------
# C3. CRIT-1 end to end (sanity): the moment comparison through discovery's real flow.
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('start, expect', [('20:00:00Z', 'back'), ('09:00:00Z', 'waits')])
def test_c3_same_day_release_after_a_morning_revert_end_to_end(world, start, expect):
    """Reverted at TODAY ~12:00 UTC (the harness clock). Amazon's rental (SYNTHETIC) goes live
    at 20:00 UTC that day (after the revert) or at 09:00 UTC (before it)."""
    node = _harlem_on_the_wall_by_mistake(world)
    assert putback._utc(world.tracking()[HARLEM]['_reverted_by_owner_at']).hour == 12
    node['offers'] = _cinema(node) + harlem_store_offers(f'{TODAY}T{start}', created=day(-1))
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=1)
    rec = world.tracking()[HARLEM]
    print('DAY 1:', rec['status'], rec.get('digital_date'), rec.get('_digital_date_source'))
    if expect == 'back':
        assert (rec['status'], rec['digital_date'], rec['_digital_date_source']) == ('available', day(1), AFTER_HOLD), rec
    else:
        assert rec['status'] == 'tracking', rec


# ---------------------------------------------------------------------------------------------
# C4. R2D-TP-07's dating change x festival-screening pre-orders (the PO-5 class). The PO-5
#     skeptic showed dating these 'today' re-stamps them daily (enrichment's display pass
#     re-flags them as pre-orders each night). 2e's _was_available needs a PAST wall date; a
#     festival pre-order's wall date is its future screening start.
# ---------------------------------------------------------------------------------------------

HOC = '1596296'
AMZ = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.2374f108-5581-493e-bfad-a9f556b56ed6'
APPLE = 'https://tv.apple.com/us/movie/the-history-of-concrete/umc.cmc.o9kd0vzwieh2hnjdmhs5yhm9'
PLEX = 'https://watch.plex.tv/movie/the-history-of-concrete'
DRIVER = '999999001'


def _hoc_node(amazon_start=None):
    """As round2d/review/preorders-verify/wt/tests/test_verify_po.py hoc_node (STAGED)."""
    c = '2026-11-02T00:00:00Z'
    offers = [offer('RENT', 'Amazon Video', 'amazon', AMZ, '$6.99', amazon_start, c),
              offer('BUY', 'Amazon Video', 'amazon', AMZ, '$16.99', amazon_start, c),
              offer('RENT', 'Apple TV Store', 'itunes', APPLE, '$6.99', None, c),
              offer('BUY', 'Apple TV Store', 'itunes', APPLE, '$16.99', None, c),
              offer('RENT', 'Plex', 'plex', PLEX, '$7.99', None, c)]
    return {'id': 'tm' + HOC, 'objectId': int(HOC), 'objectType': 'MOVIE',
            'content': {'title': 'The History of Concrete', 'originalReleaseYear': 2026,
                        'fullPath': '/us/movie/the-history-of-concrete', 'externalIds': {'tmdbId': HOC},
                        'credits': [{'role': 'DIRECTOR', 'name': 'John Wilson'}]},
            'offers': offers}


def _full_day_spec(node, days):
    """As test_verify_po.py full_day_spec('hoc_main', ...): the state origin/main published."""
    r = json.load(open(os.path.join(CRITIC, 'my_records.json')))['hoc_main']
    driver_wall = {'id': DRIVER, 'title': 'Filler Film', 'year': 2026, 'digital_date': '2026-11-10',
                   'release_date': '2026-11-10', '_enrichment_status': 'failed', '_enrichment_attempts': 1,
                   'watch_links': {}, 'links': {}, 'crew': {'director': 'Nobody'}, 'genres': [], 'providers': {}}
    driver_trk = {'title': 'Filler Film', 'year': 2026, 'status': 'available', 'digital_date': '2026-11-10',
                  'enriched': False, '_transitioned_at': '2026-11-10'}
    waiting = {'title': 'Waiting Film', 'year': 2026, 'status': 'tracking'}
    return {'ids': [HOC, DRIVER], 'tracking': {HOC: copy.deepcopy(r['tracking']), DRIVER: driver_trk,
                                                '999999002': waiting},
            'wall': [copy.deepcopy(r['wall']), driver_wall], 'tmdb': {}, 'jw': {HOC: node},
            'jw_days': {}, 'jw_outage': {}, 'jw_malformed': [], 'tmdb_fail': [], 'pages': [],
            'phases': [(d, p) for d in days for p in ('discover', 'enrich', 'gap_fill')],
            'today': days[0], 'phase_patches': {}, 'queue_ahead': [DRIVER]}


def test_c4_festival_preorder_graduated_by_the_gap_fill_is_restamped_every_day(tmp_path):
    """Two real days (11-14, 11-15) from the state production published, Amazon's offer start
    passed (2026-10-30, STAGED): v2's own graduation path. Round 2d published 10-14 both days
    (test_fix_po5_alone_restamps_daily_on_v2_live_amazon_path: V2 == ['2026-10-14', '2026-10-14'])."""
    spec = _full_day_spec(_hoc_node(amazon_start='2026-10-30T05:00:00Z'), ['2026-11-14', '2026-11-15'])
    res = run_daily(spec, str(tmp_path / 'v2e'))
    ends, trk = [], []
    for k, st in res['phases'].items():
        e = only(st['wall'][HOC])
        print(k, 'wall:', e.get('digital_date'), 'pre' if e.get('_is_preorder') else 'graduated',
              '| tracking:', st['tracking'][HOC].get('digital_date'))
        if k.endswith(':gap_fill'):
            ends.append(e.get('digital_date'))
            trk.append(st['tracking'][HOC].get('digital_date'))
    print('published digital_date after each day:', ends, 'tracking:', trk)
    assert ends[0] == ends[1], f'the published date moves with the calendar: {ends} (tracking {trk})'


from test_step1_preorders import head_code_root, run_daily_with_code  # noqa: E402,F401


def test_c4b_same_two_days_on_round_2d_and_production(tmp_path, head_code_root):
    """The same scenario on round 2d's pipeline (snap2d copy) and production's (78303fd6)."""
    spec = _full_day_spec(_hoc_node(amazon_start='2026-10-30T05:00:00Z'), ['2026-11-14', '2026-11-15'])
    out = {}
    for name, code in (('2D', os.path.join(CRITIC, 'code2d')), ('PRODUCTION', head_code_root)):
        res = run_daily_with_code(code, spec, str(tmp_path / name))
        out[name] = [only(st['wall'][HOC]).get('digital_date') for k, st in res['phases'].items()
                     if k.endswith(':gap_fill')]
    print('published digital_date after each day:', out)
    assert out['2D'] == ['2026-10-14', '2026-10-14'] and out['PRODUCTION'] == ['2026-10-14', '2026-10-14'], out


# ---------------------------------------------------------------------------------------------
# C5. R2D-PO-3 closes the TMDB-listing graduation only when JustWatch answers purchase-only. A
#     TMDB-listed rental + a JustWatch store rental that is NOT live (an Apple pre-order rental,
#     page unreadable) still graduates the buy-only pre-order; without TMDB's listing the daily
#     buy-only check keeps it waiting (another store's rental counts only on an 'available' page).
# ---------------------------------------------------------------------------------------------

from test_step1_preorders import scenario, after, on_main_wall, GALAXYMPHONY  # noqa: E402

GX_APPLE = 'https://tv.apple.com/us/movie/galaxymphony-the-final-odyssey/umc.cmc.staged'


def _gx_spec(tmdb_lists_stream):
    F_node = None
    spec = scenario([GALAXYMPHONY], wall_ids=[GALAXYMPHONY])
    node = spec['jw'][GALAXYMPHONY]
    # SYNTHETIC: Apple's store lists a pre-order RENTAL (its offer start ahead), page unreadable.
    node['offers'].append(offer('RENT', 'Apple TV Store', 'itunes', GX_APPLE, '$5.99',
                                '2026-11-28T08:00:00Z', '2026-11-13T00:00:00Z'))
    if not tmdb_lists_stream:
        spec['tmdb'][GALAXYMPHONY]['watch_providers']['results']['US'].pop('flatrate', None)
    return spec


@pytest.mark.parametrize('tmdb_lists_stream', [True, False])
def test_c5_tmdb_listing_still_decides_for_a_buyonly_preorder_with_a_store_prerental(tmp_path, tmdb_lists_stream):
    res = run_daily(_gx_spec(tmdb_lists_stream), str(tmp_path / 'sbx'))
    disc = after(res, 'discover')
    rec = disc['tracking'][GALAXYMPHONY]
    ends = only(final(res)['wall'][GALAXYMPHONY])
    print('TMDB lists a stream:', tmdb_lists_stream, '| after discovery:', rec['status'], rec.get('digital_date'),
          'buyonly' if rec.get('_buyonly_preorder') else '-', '| end of day on main wall:', on_main_wall(ends),
          {k: ends.get(k) for k in ('digital_date', '_is_preorder', '_buyonly_preorder', 'hidden')})
    # JustWatch shows no way to watch it now (an Apple pre-order rental): it must not end the day
    # on the main wall, whatever TMDB lists (rule 2).
    assert not on_main_wall(ends), 'TMDB\'s listing put it on the main wall'


def test_c5b_same_shape_on_production(tmp_path, head_code_root):
    """The regression bar for c5: production (78303fd6) doesn't end the day with it on the main wall
    either (its enrichment reverts the still-flagged entry: zero watch links). (The critic's run also
    showed round 2d putting it there, like 2e; that comparison needs a 2d tree and is not kept.)"""
    out = {}
    for name, code in (('PRODUCTION', head_code_root),):
        res = run_daily_with_code(code, _gx_spec(True), str(tmp_path / name))
        for k, st in res['phases'].items():
            e = only(st['wall'][GALAXYMPHONY])
            print(name, k, 'trk:', st['tracking'][GALAXYMPHONY].get('status'), 'wall:',
                  None if e is None else {x: e.get(x) for x in ('digital_date', '_is_preorder', '_buyonly_preorder', 'hidden', '_enrichment_status')})
        e = only(final(res)['wall'][GALAXYMPHONY])
        out[name] = (on_main_wall(e), (e or {}).get('digital_date'))
        for line in res['log'].splitlines():
            if 'Galaxymphony' in line or '######' in line:
                print('   ', name, 'LOG |', line.strip()[:220])
    print('end of day on the main wall:', out)
    assert not out['PRODUCTION'][0], out


# ---------------------------------------------------------------------------------------------
# C6. R2D-REV-1 x the morning report: what the owner reads about a reverted reissue a week on.
# ---------------------------------------------------------------------------------------------

from test_step1_revert import _killer_on_the_wall_by_mistake, KILLER  # noqa: E402


def test_c6_morning_report_wording_for_a_reverted_reissue(world):
    node, out = _killer_on_the_wall_by_mistake(world)
    asked = len(world.jw.queries)
    for n in (1, 8):
        world.run(on_day=n)
    report = world.morning_report(day(8))
    print(report)
    assert 'The Killer' in world.jw.queries[asked:]              # checked on JustWatch daily
    held_line = [l for l in report.splitlines() if l.startswith('Held, checked daily')]
    assert held_line and ': 1' in held_line[0], held_line        # counted: it IS checked daily
    assert 're-add' not in report, report


# ---------------------------------------------------------------------------------------------
# C7. R2D-TP-02's gap-fill store check reads the FIRST listed store's page. The graduation it
#     guards rests on AMAZON's live rental; with another store listed first, Amazon's 'Pre-order'
#     page is never read (same first-store read as C2).
# ---------------------------------------------------------------------------------------------

from test_step1_preorders import WICKER, amazon_rent_from, _wicker_buyonly_node  # noqa: E402

WICKER_APPLE = 'https://tv.apple.com/us/movie/wicker/umc.cmc.critic'
WICKER_PREORDER_PAGE = 'Wicker  Available to pre-order. Releases soon. Pre-order HD $19.99'


@pytest.mark.parametrize('order', ['amazon_first', 'apple_first'])
def test_c7_gap_fill_store_check_reads_the_first_store_not_amazons(tmp_path, order):
    """As round 2d's test_v02 (Wicker on main, a future pending pre-order; Amazon's rental recorded
    and live from 11-13, its page reading 'Pre-order'), plus an Apple TV Store rental (SYNTHETIC,
    page unreadable) listed before or after Amazon's."""
    node = _wicker_buyonly_node()
    amz = amazon_rent_from('B0WICKERVERIFY', '2026-11-13T05:00:00Z', created='2026-11-13T05:00:00Z', price='$19.99')
    apple = offer('RENT', 'Apple TV Store', 'itunes', WICKER_APPLE, '$19.99', '2026-10-23T07:00:00Z',
                  '2026-11-13T05:00:00Z')
    node['offers'] = ([apple, amz] if order == 'apple_first' else [amz, apple]) + node['offers']
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    pages=[('amazon.com', WICKER_PREORDER_PAGE)])
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry = only(final(res)['wall'][WICKER])
    print(order, 'pages read:', res['pages'], '| main wall:', on_main_wall(entry),
          {k: entry.get(k) for k in ('digital_date', '_is_preorder')})
    assert not on_main_wall(entry), f"graduated while Amazon's page reads Pre-order (pages read: {res['pages']})"
