"""Skeptic verification (round 2d review, tests lens): my own scenarios for R2D-TP-04, -05, -06,
-08, -09, written independently of the reviewer's proposed tests. Harness: the `world` fixture of
tests/test_step1_holds_and_dates.py (the real v2 pipeline in a pytest tmp dir, network + clock
faked, write guard on every NRW checkout). Records: verbatim 78303fd6 (Harlem, Liberation); offers
a test adds are marked VERIFY-STAGED."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_step1_holds_and_dates import (  # noqa: E402,F401  (world: the fixture)
    world, real, day, TODAY, HARLEM, HARLEM_AMAZON, putback, jw_offer, jw_node, harlem_store_offers,
    FakeStorePages, OWNER_REVERT, _harlem_on_the_wall_by_mistake, tmdb_details, WORKTREE, MISTLETOE,
)

Q = 'Once Upon a Time in Harlem'
UNREADABLE = 'Once Upon a Time in Harlem  Sign in to see your options'   # neither signal -> None


def _cinema(node):
    return [o for o in node['offers'] if o['monetizationType'] == 'CINEMA']


def _hold(rec):
    return {k: rec.get(k) for k in ('status', '_jw_revert_reason', '_jw_revert_count', '_jw_reverted_at',
                                    '_reverted_by_owner', 'enriched', '_jw_last_refuted')}


# ---------------------------------------------------------------------------------------------
# R2D-TP-04: enrichment's per-film skip of a reverted film (M01)
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('page', ['unreadable', 'available'])
def test_v04_enrich_id_keeps_a_reverted_films_hold_and_it_keeps_waiting(world, page):
    node = _harlem_on_the_wall_by_mistake(world)
    # VERIFY-STAGED: the store listings that put it on by mistake, Amazon's rental starting day 10
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = UNREADABLE if page == 'unreadable' else FakeStorePages.AVAILABLE
    before = _hold(world.tracking()[HARLEM])
    world._phase(lambda: world.enrichment_generator().enrich_newly_available_movies(target_id=HARLEM),
                 'enrichment', 1)
    after_enrich = _hold(world.tracking()[HARLEM])
    print(f'\n[v04/{page}] hold before {before}\n[v04/{page}] hold after --enrich-id {after_enrich}')
    # day 3: TMDB lists a rental (VERIFY-STAGED); nothing new on JustWatch
    world.tmdb.set_providers(HARLEM, rent=['Apple TV Store'])
    world.run(on_day=3)
    rec = world.tracking()[HARLEM]
    print(f'[v04/{page}] day 3 tracking status={rec.get("status")} date={rec.get("digital_date")} '
          f'source={rec.get("_digital_date_source")} wall={ {k: (world.wall().get(HARLEM) or {}).get(k) for k in ("hidden", "digital_date", "_enrichment_status")} }')
    assert after_enrich == before, f'the hold was rewritten by --enrich-id: {before} -> {after_enrich}'
    assert rec['status'] == 'tracking', f'back on day 3 with nothing new on JustWatch: {rec.get("digital_date")}'


# ---------------------------------------------------------------------------------------------
# R2D-TP-05: catch-up never queues a reverted film (M02 / M02a / M02b)
# ---------------------------------------------------------------------------------------------

def test_v05_stale_reverted_entry_never_takes_the_genuine_films_catch_up_slot(world):
    import pipeline.enricher as enricher_mod
    _harlem_on_the_wall_by_mistake(world)
    movies = world.tracking()
    gen = real(MISTLETOE)   # a genuine film, here already out (VERIFY-STAGED status) and waiting hidden
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        gen.pop(k, None)
    gen.update({'status': 'available', 'digital_date': day(-1), 'enriched': False})
    movies[MISTLETOE] = gen
    world.save_tracking(movies)
    world.tmdb.details[MISTLETOE] = tmdb_details(MISTLETOE, gen)
    title = gen['title']
    world.jw.edges[title] = [jw_node(MISTLETOE, title, gen.get('year') or 2026, [
        jw_offer('FLATRATE', 'Hallmark+', 'https://www.hallmarkplus.com/verify', created=day(-1))])]
    # the stale write: Harlem's pre-revert entry (hidden, waiting for its check) FIRST in data.json
    world.save_wall([
        {'id': HARLEM, 'title': Q, 'year': 2026, 'digital_date': day(-1), '_enrichment_status': 'completed',
         'status': 'available', 'hidden': True, '_jw_unconfirmed': day(-1),
         'watch_links': {'vod': [{'service': 'Amazon Video', 'link': HARLEM_AMAZON}]}},
        {'id': MISTLETOE, 'title': title, 'year': 2026, 'digital_date': day(-1), '_enrichment_status': 'pending',
         'status': 'available', 'hidden': True, '_jw_unconfirmed': day(-1)},
    ])
    world._mp.setattr(enricher_mod, 'MAX_ENRICHMENT_BATCH', 1)
    world.enrich(on_day=1)
    wall = world.wall()
    print(f'\n[v05] harlem on wall: {HARLEM in wall}; genuine film: '
          f'{ {k: wall.get(MISTLETOE, {}).get(k) for k in ("hidden", "_jw_unconfirmed", "_enrichment_status")} }')
    assert HARLEM not in wall
    assert not wall[MISTLETOE].get('hidden'), f'the genuine film lost its slot: {wall[MISTLETOE]}'


# ---------------------------------------------------------------------------------------------
# R2D-TP-06: TMDB's date alone never brings a reverted film back -- page unreadable (M42)
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('variant', ['pending', 'fresh'])
def test_v06_tmdb_date_alone_never_brings_it_back_when_the_page_cannot_be_read(world, variant):
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = UNREADABLE
    for n in range(1, 10):
        if (variant == 'pending' and n == 1) or (variant == 'fresh' and n == 3):
            world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, day(3), ''))
        world.run(on_day=n)
        rec = world.tracking()[HARLEM]
        assert rec['status'] == 'tracking', f'back on day {n}: {rec.get("digital_date")} {rec.get("_digital_date_source")}'
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=10)
    rec = world.tracking()[HARLEM]
    assert (rec['status'], rec['digital_date']) == ('available', day(10)), rec


# ---------------------------------------------------------------------------------------------
# R2D-TP-08: the PENDING Type-4 path's store-page check (M11a)
# ---------------------------------------------------------------------------------------------

def test_v08_held_pending_preorder_waits_on_its_arrived_date_while_the_page_reads_preorder(world):
    rec = real(HARLEM)   # real 2-check hold; VERIFY-STAGED: a stored pending date that arrives today
    rec.update({'_type4_pending': True, 'digital_date': TODAY, '_discovery_source': 'tmdb_type4'})
    world.seed({HARLEM: rec})
    world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, TODAY, ''))
    world.jw.use_real(Q)
    node = world.jw.node(Q, HARLEM)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(-1)}T07:00:00Z', created=day(-1))
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=0)
    r = world.tracking()[HARLEM]
    print(f'\n[v08] day 0: {_hold(r)} date={r.get("digital_date")} held={r.get("_rent_preorder_held")}')
    assert r['status'] == 'tracking' and r.get('_jw_last_refuted') == TODAY, r
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=1)
    r = world.tracking()[HARLEM]
    print(f'[v08] day 1: status={r["status"]} date={r.get("digital_date")} source={r.get("_digital_date_source")}')
    assert r['status'] == 'available' and r['digital_date'] == day(1), r


# ---------------------------------------------------------------------------------------------
# R2D-TP-09: page cache (M21), add_movie ends a revert (M26), a 2nd revert clears the page flag (M20a)
# ---------------------------------------------------------------------------------------------

def test_v09a_the_store_page_is_rendered_once_on_a_put_back_day(world):
    _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    world.pages.text = FakeStorePages.AVAILABLE
    seen = len(world.pages.visited)
    world.run(on_day=2)
    print(f'\n[v09a] day 2 renders: {world.pages.visited[seen:]}; status {world.tracking()[HARLEM]["status"]}')
    assert world.tracking()[HARLEM]['status'] == 'available'
    assert len(world.pages.visited) - seen == 1, world.pages.visited[seen:]


def _add_movie(world, on_day):
    world._mp.syspath_prepend(os.path.join(WORKTREE, 'scripts'))
    import add_movie
    assert os.path.realpath(add_movie.__file__).startswith(WORKTREE)
    world._mp.setattr(sys, 'argv', ['add_movie.py', HARLEM, '--date', day(on_day)])
    world._phase(add_movie.main, 'add movie', on_day)


def test_v09b_a_hand_readd_ends_the_owners_revert(world):
    _harlem_on_the_wall_by_mistake(world)
    _add_movie(world, 1)
    rec = world.tracking()[HARLEM]
    print(f'\n[v09b] after re-add: status={rec["status"]} _reverted_by_owner={rec.get("_reverted_by_owner")}')
    assert rec['status'] == 'available' and '_reverted_by_owner' not in rec, rec
    # a later pull back to tracking (e.g. enrichment's PVOD revert) must not count as the owner's revert
    rec.update({'status': 'tracking', '_jw_revert_count': 1, '_jw_revert_reason': 'justwatch_theatrical_pvod'})
    assert not putback.is_owner_reverted(rec)


def test_v09c_owner_revert_drops_an_old_page_reading(world):
    rec = real(HARLEM)
    rec.update({'status': 'available', '_revert_page_preorder': day(-3)})
    assert putback.owner_revert(rec, today=TODAY)
    assert '_revert_page_preorder' not in rec, rec


def test_v09d_second_revert_waits_on_a_page_that_read_available_at_that_revert(world):
    _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    assert world.tracking()[HARLEM]['_revert_page_preorder'] == day(1)
    _add_movie(world, 2)
    movies = world.tracking()
    assert putback.owner_revert(movies[HARLEM], today=day(3))
    world.save_tracking(movies)
    site = {'movies': list(world.wall().values())}
    putback.revert_wall_entry(site, HARLEM)
    world.save_wall(site['movies'])
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=4)
    rec = world.tracking()[HARLEM]
    print(f'\n[v09d] day 4 after the 2nd revert: status={rec["status"]} date={rec.get("digital_date")}')
    assert rec['status'] == 'tracking', rec


# ---------------------------------------------------------------------------------------------
# R2D-TP-09: the pre-order link finder's budget (M23) and soonest-first order (M23b)
# ---------------------------------------------------------------------------------------------

def test_v09e_link_finder_spends_at_most_its_budget_soonest_release_first(world):
    import time as real_time
    import types
    import pipeline.enricher as enricher_mod
    from test_step1_holds_and_dates import FakeVodScraper
    # four PRE-ORDER entries inside the 14-day window, stored latest-first, none with store links
    films = [('9200004', 'Fourth', 12), ('9200003', 'Third', 9), ('9200002', 'Second', 6), ('9200001', 'First', 3)]
    world.seed({}, wall=[{'id': mid, 'title': t, 'year': 2026, 'digital_date': day(n), '_is_preorder': True,
                          '_enrichment_status': 'completed'} for mid, t, n in films])
    clock = {'t': 1_900_000_000.0}
    fake_time = types.SimpleNamespace(**{k: getattr(real_time, k) for k in dir(real_time) if not k.startswith('_')})
    fake_time.time = lambda: clock['t']
    world._mp.setattr(enricher_mod, 'time', fake_time)
    asked = []

    def find_amazon_link(self, title, year, director=None):
        asked.append(title)
        clock['t'] += 6 * 60     # each Amazon lookup: 6 minutes
        return None
    world._mp.setattr(FakeVodScraper, 'find_amazon_link', find_amazon_link)
    world.enrich(on_day=0)
    print(f'\n[v09e] asked: {asked}')
    assert asked == ['First', 'Second', 'Third'], asked
    assert '15-min budget used; 1 film(s) wait for the next run' in world.last_output, world.last_output[-600:]


# ---------------------------------------------------------------------------------------------
# R2D-TP-11: is the gap fill's owner-reverted skip (M16) really without effect?
# ---------------------------------------------------------------------------------------------

def test_v11_gap_fill_leaves_a_reverted_films_tracking_record_alone(world):
    """Harlem reverted while TMDB dates it in the future (day 10: kept by owner_revert); a stale
    write left its old MAIN-wall entry on the wall; JustWatch shows it buy-only (VERIFY-STAGED:
    an Amazon purchase). The gap fill must not touch the reverted film's tracking record."""
    node = _harlem_on_the_wall_by_mistake(world)
    movies = world.tracking()
    movies[HARLEM]['digital_date'] = day(10)
    world.save_tracking(movies)
    world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, day(10), ''))
    node['offers'] = _cinema(node) + [jw_offer('BUY', 'Amazon Video', HARLEM_AMAZON, '$19.99', created=day(-1))]
    world.save_wall([{'id': HARLEM, 'title': Q, 'year': 2026, 'digital_date': day(-1), '_enrichment_status': 'completed',
                      'status': 'available', 'watch_links': {'vod': [{'service': 'Amazon Video', 'link': HARLEM_AMAZON}]}}])
    before = dict(world.tracking()[HARLEM])
    world._phase(lambda: world.gen.daily_gap_fill(), 'gap fill', 1)
    rec = world.tracking()[HARLEM]
    changed = {k: (before.get(k), rec.get(k)) for k in set(before) | set(rec) if before.get(k) != rec.get(k)}
    assert not changed, f'the gap fill rewrote a reverted film\'s tracking record: {changed}'
