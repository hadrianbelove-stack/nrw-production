"""Skeptic verification (round 2d review, tests lens): my own scenarios for R2D-TP-01, -02, -03,
-07, written independently of the reviewer's proposed tests. They use the test_step1_preorders.py
harness: the real daily phases in a throw-away sandbox, real Wicker / Beware Boiuna records from
78303fd6, only the network (TMDB, JustWatch, store pages) and the clock faked.

Each test prints what it observed (run with -s to see) and asserts what the owner's rules require.
A failing assertion here = the finding reproduces on this code."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_step1_preorders import (  # noqa: E402
    WICKER, TODAY, scenario, run_daily, final, after, only, on_main_wall, brief, brief_rec, fixtures,
    offer, amazon_rent_from, _wicker_buyonly_node, _MISSING, head_code_root, run_daily_with_code, jw_titles,
)

APPLE_WICKER = 'https://tv.apple.com/us/movie/wicker/umc.cmc.verify'
# A store page reading "Pre-order" (the page check's own signal words), and a live one.
PREORDER_PAGE = 'Wicker  Available to pre-order. Releases soon. Pre-order HD $19.99'
LIVE_PAGE = 'Wicker  Rent now $19.99  Buy now $24.99'


def _apple_rent(start='2026-10-23T07:00:00Z', created='2026-11-14T07:00:00Z'):
    """VERIFY-STAGED: an Apple TV Store RENT whose offer start is Wicker's theatrical date (justwatch.py
    comment: Apple's RENT offer appears with the theatrical date as its offer start)."""
    return offer('RENT', 'Apple TV Store', 'itunes', APPLE_WICKER, '$19.99', start, created)


def _type4(day):
    return dict(fixtures()['tmdb'][WICKER], release_dates={'id': int(WICKER), 'results': [
        {'iso_3166_1': 'US', 'release_dates': [{'type': 4, 'release_date': f'{day}T00:00:00.000Z', 'note': ''}]}]})


def _show(tag, res):
    end = final(res)
    print(f'\n[{tag}] END wall={brief(only(end["wall"][WICKER]))} main_wall={on_main_wall(only(end["wall"][WICKER]))}'
          f' trk={brief_rec(end["tracking"][WICKER])} pages={res["pages"]}')
    for line in res['log'].splitlines():
        if 'Wicker' in line:
            print(f'[{tag}] LOG {line.strip()}')


# ---------------------------------------------------------------------------------------------
# R2D-TP-01: tracking says buy-only, the wall entry does not (Wicker / The Social Reckoning on main)
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('wall_flag', ['wall_unflagged_as_on_main', 'wall_flagged'])
def test_v01a_gap_fill_buy_only_rule_reads_only_the_wall_flag(wall_flag, tmp_path):
    node = _wicker_buyonly_node()
    node['offers'].append(_apple_rent())
    wall_over = {WICKER: {'digital_date': TODAY}}
    if wall_flag == 'wall_flagged':
        wall_over[WICKER]['_buyonly_preorder'] = True
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'digital_date': TODAY}}, wall_over=wall_over)
    assert spec['tracking'][WICKER]['_buyonly_preorder'] is True
    res = run_daily(spec, str(tmp_path / 'sbx'))
    _show(f'v01a/{wall_flag}', res)
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert entry.get('_is_preorder') and not on_main_wall(entry), f'graduated on an Apple rental: {brief(entry)} {brief_rec(rec)}'
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)


def _v01b_spec(page):
    node = _wicker_buyonly_node()
    node['offers'].append(_apple_rent())
    pages = {'apple_page_reads_preorder': [('tv.apple.com', PREORDER_PAGE)],
             'pages_unreadable': [],
             'apple_page_reads_available': [('tv.apple.com', LIVE_PAGE)]}[page]
    # TMDB moves Wicker's digital date to today (it really moved 12-01 -> 11-24 on main).
    return scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, tmdb_over={WICKER: _type4(TODAY)},
                    pages=pages)


@pytest.mark.parametrize('page', ['apple_page_reads_preorder', 'pages_unreadable', 'apple_page_reads_available'])
def test_v01b_full_day_discovery_refutes_today_then_enrichment_publishes(page, tmp_path):
    res = run_daily(_v01b_spec(page), str(tmp_path / 'sbx'))
    disc = after(res, 'discover')
    d_rec, d_entry = disc['tracking'][WICKER], only(disc['wall'][WICKER])
    print(f'\n[v01b/{page}] AFTER DISCOVER trk={brief_rec(d_rec)} wall={brief(d_entry)}')
    enr = after(res, 'enrich')
    print(f'[v01b/{page}] AFTER ENRICH  trk={brief_rec(enr["tracking"][WICKER])} wall={brief(only(enr["wall"][WICKER]))}')
    _show(f'v01b/{page}', res)
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    # Round 2f+: TMDB's digital date (today) has arrived and stores list it -> out by the pre-order
    # labeler when the page can't be read too; only a page reading 'Pre-order' still holds it.
    if page in ('apple_page_reads_available', 'pages_unreadable'):
        # control: the store page says it is out -> discovery graduates it today
        assert d_rec['status'] == 'available' and on_main_wall(entry) and entry['digital_date'] == TODAY
        return
    assert d_rec['status'] == 'tracking' and d_rec.get('_jw_last_refuted') == TODAY, 'precondition: discovery held it'
    # rule 3: never dated on a day a check proved it unavailable; rule 2: JustWatch + store page decide
    assert not on_main_wall(entry), (f'on the main wall the day discovery held it: wall={brief(entry)} '
                                     f'trk={brief_rec(rec)}')


@pytest.mark.parametrize('case', ['gap_fill_only', 'full_day_page_preorder', 'full_day_unreadable'])
def test_v01c_production_same_scenarios(case, head_code_root, tmp_path):
    """Not an assertion test: what production (78303fd6) does on the same scenarios."""
    if case == 'gap_fill_only':
        node = _wicker_buyonly_node()
        node['offers'].append(_apple_rent())
        spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                        tracking_over={WICKER: {'digital_date': TODAY}}, wall_over={WICKER: {'digital_date': TODAY}})
    else:
        spec = _v01b_spec('apple_page_reads_preorder' if case == 'full_day_page_preorder' else 'pages_unreadable')
    res = run_daily_with_code(head_code_root, spec, str(tmp_path / 'prod'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    print(f'\n[v01c/{case}] PRODUCTION main_wall={on_main_wall(entry)} wall={brief(entry)} trk={brief_rec(rec)}')
    for k in res['phases']:
        st = res['phases'][k]
        print(f'[v01c/{case}] after {k}: trk={brief_rec(st["tracking"][WICKER])} wall={brief(only(st["wall"][WICKER]))}')


# ---------------------------------------------------------------------------------------------
# R2D-TP-02: a future pending pre-order whose Amazon rental is past its offer start, page "Pre-order"
# ---------------------------------------------------------------------------------------------

def _v02_spec(phases, page_text, start='2026-11-13T05:00:00Z'):
    node = _wicker_buyonly_node()
    # VERIFY-STAGED: Amazon RENT recorded ON its offer-start day (as the live captures show), start passed.
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', start, created=start, price='$19.99'))
    return scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=phases,
                    pages=[('amazon.com', page_text)])


@pytest.mark.parametrize('phases', [('gap_fill',), ('discover', 'enrich', 'gap_fill')], ids=['gap_fill_only', 'full_day'])
@pytest.mark.parametrize('page', ['amazon_page_preorder', 'amazon_page_live'])
def test_v02_gap_fill_graduates_on_amazon_offer_start_without_the_page(phases, page, tmp_path):
    res = run_daily(_v02_spec(phases, PREORDER_PAGE if page == 'amazon_page_preorder' else LIVE_PAGE),
                    str(tmp_path / 'sbx'))
    _show(f'v02/{page}/{"-".join(phases)}', res)
    if 'discover' in phases:
        print(f'[v02] JustWatch asked in discovery: {jw_titles(res, "discover")}')
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    if page == 'amazon_page_live':
        return   # control: printed only
    assert not on_main_wall(entry) and entry.get('_is_preorder'), (
        f'graduated while Amazon page reads Pre-order: wall={brief(entry)} trk={brief_rec(rec)} pages={res["pages"]}')


def test_v02c_production_same_scenario(head_code_root, tmp_path):
    for phases in (('gap_fill',), ('discover', 'enrich', 'gap_fill')):
        res = run_daily_with_code(head_code_root, _v02_spec(phases, PREORDER_PAGE), str(tmp_path / ('p' + str(len(phases)))))
        entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
        print(f'\n[v02c/{"-".join(phases)}] PRODUCTION main_wall={on_main_wall(entry)} wall={brief(entry)} '
              f'trk={brief_rec(rec)} pages={res["pages"]}')


# ---------------------------------------------------------------------------------------------
# R2D-TP-03: the gap fill leaves a HELD film to discovery (M07 removes `and not _is_held(_trk)`)
# ---------------------------------------------------------------------------------------------

def test_v03_gap_fill_leaves_a_held_preorder_entry_to_discovery(tmp_path):
    """Wicker held yesterday by the store page (`_rent_preorder_held`, a 'not out yet' day), its
    wall entry still in the PRE-ORDER lane; today JustWatch shows Amazon's rental past its offer
    start. The gap fill must not graduate it (discovery checks the page and dates it)."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', '2026-11-12T05:00:00Z', created='2026-11-12T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'_rent_preorder_held': '2026-11-13', '_jw_last_refuted': '2026-11-13'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    _show('v03', res)
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert entry.get('_is_preorder') and not on_main_wall(entry), brief(entry)
    assert rec['status'] == 'tracking', brief_rec(rec)


# ---------------------------------------------------------------------------------------------
# R2D-TP-07: the gap fill's dating rules
# ---------------------------------------------------------------------------------------------

def test_v07a_still_tracking_preorder_with_a_passed_wall_date_is_dated_today(tmp_path):
    """M08c: Wicker still 'tracking' (never out), its pre-order date 11-10 passed; Amazon's rental
    live today. Graduates in the gap fill dated TODAY, never its old pre-order date."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', f'{TODAY}T05:00:00Z', created=f'{TODAY}T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'digital_date': '2026-11-10'}}, wall_over={WICKER: {'digital_date': '2026-11-10'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    _show('v07a', res)
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
    assert rec['status'] == 'available' and rec['digital_date'] == TODAY, brief_rec(rec)


def test_v07b_a_film_tracking_has_out_keeps_its_date(tmp_path):
    """M08e: tracking has Wicker out since 10-24 (status available, no later 'not out yet' day),
    its wall entry still carries a stale pre-order flag; JustWatch shows Amazon live. The gap fill
    clears the flag and keeps 10-24 (Carolina Caroline: re-stamping today makes an old film new)."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', '2026-10-24T05:00:00Z', created='2026-10-24T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'status': 'available', 'digital_date': '2026-10-24'}},
                    wall_over={WICKER: {'digital_date': '2026-10-24'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    _show('v07b', res)
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == '2026-10-24', brief(entry)
    assert rec['digital_date'] == '2026-10-24', brief_rec(rec)


def test_v07c_buy_only_flagged_by_the_gap_fill_is_dated_the_day_its_rental_goes_live(tmp_path):
    """M09b: an ordinary wall film (Wicker, dated 11-10, tracking available, no TMDB digital date)
    that JustWatch shows buy-only on 11-14: the gap fill flags it a buy-only pre-order and sends it
    back to tracking. 11-15 Amazon's rental goes live: discovery graduates it dated 11-15."""
    live = _wicker_buyonly_node()
    live['offers'].append(amazon_rent_from('B0WICKERVERIFY', '2026-11-15T05:00:00Z', created='2026-11-15T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_buyonly_node()},
                    phases=('gap_fill', ['2026-11-15', 'discover']), jw_days={'2026-11-15': {WICKER: live}},
                    tracking_over={WICKER: {'status': 'available', 'digital_date': '2026-11-10', '_buyonly_preorder': _MISSING,
                                            '_type4_pending': _MISSING, '_is_preorder': _MISSING}},
                    wall_over={WICKER: {'digital_date': '2026-11-10', '_is_preorder': _MISSING, 'pre_order_links': _MISSING}},
                    tmdb_over={WICKER: {'details': fixtures()['tmdb'][WICKER]['details'],
                                        'release_dates': {'id': int(WICKER), 'results': []}}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    gf = after(res, 'gap_fill')
    print(f'\n[v07c] AFTER GAP FILL trk={brief_rec(gf["tracking"][WICKER])} wall={brief(only(gf["wall"][WICKER]))}')
    _show('v07c', res)
    assert gf['tracking'][WICKER]['status'] == 'tracking', 'precondition: flagged and back to tracking'
    rec = final(res)['tracking'][WICKER]
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-11-15', brief_rec(rec)


def test_v01d_three_days_on_the_main_wall_while_tracking_still_waits(tmp_path):
    """R2D-TP-01 consequence over three daily runs (2d): 11-14 and 11-15 JustWatch lists Apple's
    rental only and its page reads "Pre-order" (each a 'not out yet' day in tracking); 11-16
    Amazon's rental goes live. Prints the wall and tracking after each day."""
    from test_step1_preorders import two_days
    node = _wicker_buyonly_node()
    node['offers'].append(_apple_rent())
    live = _wicker_buyonly_node()
    live['offers'] += [_apple_rent(), amazon_rent_from('B0WICKERVERIFY', '2026-11-16T05:00:00Z',
                                                      created='2026-11-16T05:00:00Z', price='$19.99')]
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, tmdb_over={WICKER: _type4(TODAY)},
                    pages=[('tv.apple.com', PREORDER_PAGE), ('amazon.com', LIVE_PAGE)],
                    jw_days={'2026-11-16': {WICKER: live}},
                    phases=two_days(TODAY, '2026-11-15', '2026-11-16'))
    res = run_daily(spec, str(tmp_path / 'sbx'))
    rows = []
    for k, st in res['phases'].items():
        e, r = only(st['wall'][WICKER]), st['tracking'][WICKER]
        rows.append((k, on_main_wall(e), (e or {}).get('digital_date'), r['status'], r.get('_jw_last_refuted')))
        print(f'[v01d] {k:28} main_wall={on_main_wall(e)!s:5} wall_date={(e or {}).get("digital_date")} '
              f'trk={brief_rec(r)}')
    # on the main wall on 11-14 and 11-15 while tracking recorded both days as 'not out yet'
    assert not any(main and status == 'tracking' and refuted == k.split(':')[1]
                   for k, main, _d, status, refuted in rows), rows


def _v07d_spec():
    node = _wicker_buyonly_node()
    node['offers'].append(offer('FLATRATE', 'Netflix', 'nfx', 'https://www.netflix.com/title/8100verify', None,
                                f'{TODAY}T07:00:00Z', f'{TODAY}T07:00:00Z'))
    # VERIFY-STAGED: the shape of the 35 'coming soon' pre-orders on main -- tracking 'available',
    # wall entry a FUTURE-dated pre-order (12-01), _transitioned_at in the past (fixture: 10-24).
    return scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'status': 'available', '_type4_pending': _MISSING,
                                            '_buyonly_preorder': _MISSING}})


def test_v07d_future_preorder_tracking_calls_available_is_dated_the_day_it_streams(tmp_path):
    """Related to R2D-TP-07 (kept-old-date rule): streaming appears today, before the wall date
    12-01. The film became watchable today; its 10-24 transition day was a pre-order placement."""
    res = run_daily(_v07d_spec(), str(tmp_path / 'sbx'))
    _show('v07d', res)
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)


def test_v07d_production(head_code_root, tmp_path):
    res = run_daily_with_code(head_code_root, _v07d_spec(), str(tmp_path / 'prod'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    print(f'\n[v07d] PRODUCTION main_wall={on_main_wall(entry)} wall={brief(entry)} trk={brief_rec(rec)}')
