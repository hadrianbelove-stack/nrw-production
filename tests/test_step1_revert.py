"""Step 1 v2, round 2d: the owner's Revert holds until the film is really out.

Owner (Nov 15): Revert = a film wrongly marked new, usually the pre-order problem -- off the
wall now, back on its own the day it's really out. The opposite of Remove (gone for good).
The owner's rules: JustWatch decides availability (TMDB never); a film is dated the day it
actually became available, never on a day a check proved it unavailable; a JustWatch error
never counts against a film and never publishes an unconfirmed one.

Round 2d fixes under test, each from the round-2c review and its verification
(scratchpad/round2c-verify/):
  * enrichment never re-checks a reverted film -- its catch-up undid a Revert (f1);
  * the purge drops a reverted film's entry even when a stale write brought it back (f3);
  * a reverted film comes back only on something NEW since the revert that shows it watchable
    now (a streaming offer, an Amazon rental going live), or its store page turning from
    "Pre-order" to "available": never on TMDB's date alone (critic N3), never on a new store
    listing alone (f2 / fix-checker NEW-1), and a reissue too (critic N2);
  * a day it only waits is not a "not out yet" day (fix-checker NEW-3);
  * an Apple Music Live special (JustWatch can't see these) comes back on TMDB's date after
    the revert (f4); the morning report names a reverted film that may not come back by itself;
  * a reverted festival film is never let through by its screening (f6);
  * a held film TMDB first dates in the future is checked on JustWatch that run, and listed for
    enrichment once (f7); a held film going back on TMDB's date gets the store-page check (N3).

Harness: tests/test_step1_holds_and_dates.py's World -- the real v2 pipeline in a pytest tmp dir,
only the network and the clock faked, a write guard on every NRW checkout. Records: verbatim from
`git show 78303fd6:movie_tracking.json` / data.json (Harlem, Liberation via that file; The Killer,
Apple Music Live: Troye Sivan and River below). JustWatch offers a test adds are SYNTHETIC and say
what they stand for.

Run: cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_revert.py -q -p no:cacheprovider
"""
import copy
import json
import os
import sys

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_step1_holds_and_dates import (  # noqa: E402,F401  (world: the fixture)
    world, real, day, TODAY, HARLEM, HARLEM_AMAZON, LIBERATION, LIBERATION_AMAZON, putback, jw_offer, jw_node,
    harlem_store_offers, FakeStorePages, OWNER_REVERT, FIRST_OFFER, EVIDENCE, CONFIRMED, DataGenerator,
    _harlem_on_the_wall_by_mistake, _revert_script,
)

Q = 'Once Upon a Time in Harlem'
OFFER_START = putback.OFFER_START
INCONCLUSIVE = 'Once Upon a Time in Harlem  Sign in to see your options'   # neither signal: None
HARLEM_FAH = 'https://athome.fandango.com/content/browse/details/Once-Upon-a-Time-in-Harlem/5301120'
HARLEM_APPLE = 'https://tv.apple.com/us/movie/once-upon-a-time-in-harlem/umc.cmc.harlem'

KILLER, TROYE, RIVER = '10835', '1814862', '1520592'
# Verbatim 78303fd6 movie_tracking.json records, and River's data.json entry (trimmed to the
# fields the pipeline reads).
REAL = json.loads(r'''
{"10835": {"title": "The Killer", "year": 1990, "status": "available", "intake_date": "2026-06-20", "digital_date": "2026-04-05", "providers": {}, "intake_pass": "D", "_reissue": true, "reissue_label": "4K Restoration", "enriched": true, "enrichment_date": "2026-06-20", "_enrichment_attempts": 0, "_added_manually": true, "_added_at": "2026-06-20"},
 "1814862": {"title": "Apple Music Live: Troye Sivan", "year": 2026, "status": "tracking", "intake_date": "2026-11-02", "digital_date": "2026-10-13", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "AML", "_apple_music_live": true, "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_transitioned_at": "2026-11-13", "_jw_revert_count": 10, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-11-13"},
 "1520592": {"title": "River", "year": 2026, "status": "available", "intake_date": "2026-09-08", "digital_date": "2026-11-13", "providers": {"rent": ["Eventive"], "buy": [], "streaming": []}, "intake_pass": "C", "festival": "Toronto/TIFF", "has_providers": true, "_virtual_screening": true, "_discovery_source": "provider_availability_check", "enriched": true, "enrichment_date": "2026-11-12", "_transitioned_at": "2026-11-12"}}
''')
RIVER_ENTRY = json.loads(r'''
{"id": "1520592", "title": "River", "year": 2027, "digital_date": "2026-11-13", "_enrichment_status": "completed", "_discovery_source": "provider_availability_check", "providers": {"rent": [], "buy": [], "streaming": []}, "watch_links": {"vod": [{"service": "Eventive", "link": "https://watch.eventive.org/2026lvifsf/play/6af34dc0eab6ce56ed0e7db0"}]}, "virtual_screening_info": {"platform": "Eventive", "screening_slug": "2026lvifsf", "screening_name": "2026 Las Vegas International Film & Screenwriting Festival", "available_start": "2026-11-13", "available_end": "2026-11-27", "discovered": "2026-11-12", "last_checked": "2026-11-13", "status": "active"}, "filters": {"is_indie": true, "is_foreign": false, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": true, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "status": "available"}
''')


def _cinema(node):
    return [o for o in node['offers'] if o['monetizationType'] == 'CINEMA']


def _owner_reverts(world, mid, on_day=0):
    """What the admin's Revert button and scripts/revert_movie.py do: these two calls."""
    movies = world.tracking()
    assert putback.owner_revert(movies[mid], today=day(on_day))
    world.save_tracking(movies)
    site = {'movies': list(world.wall().values())}
    found = putback.revert_wall_entry(site, mid)
    world.save_wall(site['movies'])
    return found


def _on_main_wall(e):
    """What the site shows on the main wall: hidden entries and pre-orders are off it."""
    return bool(e) and not e.get('hidden') and not e.get('_is_preorder')


def _archive(world):
    path = os.path.join(world.tmp, 'data_archive.json')
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {str(m.get('id')): m for m in json.load(f).get('movies', [])}


# ===========================================================================
# f1. Enrichment never undoes a Revert
# ===========================================================================

@pytest.mark.parametrize('cut', ['justwatch_error', 'tmdb_details_failure'])
def test_revert_of_a_put_back_waiting_hidden_holds_through_enrichment(world, cut):
    """Harlem's real hold; day 0 discovery puts it back (JustWatch lists store rentals, SYNTHETIC:
    recorded day -1, Amazon's offer start day 10 -- the pre-order problem). Enrichment can't check
    it (a JustWatch error, or TMDB's details failing), so it waits hidden (`_jw_unconfirmed`). The
    owner reverts it. Round 2c: day-1 catch-up re-checked the hidden entry, the check passed on the
    same store listing, the hold was erased and the film went back on the main wall, dated before
    the revert, never checked again. Now enrichment never re-checks a reverted film: purged, still
    held, checked on JustWatch the next day."""
    world.seed({HARLEM: real(HARLEM)})
    world.tmdb.use_real(HARLEM)
    world.jw.use_real(Q)
    world.jw.node(Q, HARLEM)['offers'] += harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=0)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'available' and rec['_put_back_on'] == TODAY, 'precondition: put back on day 0'

    if cut == 'justwatch_error':
        world.jw.errors[Q] = 'connection_error'
    else:
        details = world.tmdb.details.pop(HARLEM)
    world.enrich(on_day=0)
    world.jw.errors.pop(Q, None)
    if cut == 'tmdb_details_failure':
        world.tmdb.details[HARLEM] = details
    entry = world.wall()[HARLEM]
    assert entry['hidden'] is True and entry['_jw_unconfirmed'] == TODAY, entry

    assert _owner_reverts(world, HARLEM, 0)

    world.run(on_day=1)
    world.enrich(on_day=1)
    rec = world.tracking()[HARLEM]
    assert HARLEM not in world.wall(), f'reverted entry revived, not purged: {world.wall().get(HARLEM)}'
    assert (rec['status'], rec['_jw_revert_reason'], rec['_jw_revert_count'], rec['_reverted_by_owner']) == (
        'tracking', OWNER_REVERT, 1, TODAY), rec

    asked = len(world.jw.queries)
    world.run(on_day=2)
    assert Q in world.jw.queries[asked:] and world.tracking()[HARLEM]['status'] == 'tracking'


def test_a_manual_readd_after_a_revert_is_enriched(world):
    """The guard is a film still WAITING after the owner's revert (status 'tracking'): a film the
    owner re-adds by hand afterwards (status 'available') is enriched as usual -- even with the
    revert flag left on it, as scripts/add_movie.py did before round 2d."""
    _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=1)
    world.enrich(on_day=1)
    assert HARLEM not in world.wall()

    movies = world.tracking()
    movies[HARLEM].update({'status': 'available', 'digital_date': day(1), 'enriched': False, '_added_manually': True})
    assert movies[HARLEM]['_reverted_by_owner'] == TODAY
    world.save_tracking(movies)
    world.save_wall(list(world.wall().values()) + [
        {'id': HARLEM, 'title': Q, 'year': 2026, 'digital_date': day(1), '_added_manually': True}])
    world._phase(lambda: world.enrichment_generator().enrich_newly_available_movies(target_id=HARLEM),
                 'enrichment', 1)
    assert world.wall()[HARLEM]['_enrichment_status'] == 'completed', world.wall()[HARLEM]


def test_enrich_id_never_enriches_a_reverted_film_still_waiting(world):
    """`--enrich-id` (or a stale newly_available.json) on a film the owner reverted: skipped --
    enriching it would show it again before it's out."""
    _harlem_on_the_wall_by_mistake(world)
    world._phase(lambda: world.enrichment_generator().enrich_newly_available_movies(target_id=HARLEM),
                 'enrichment', 1)
    assert 'sent back by the owner' in world.last_output
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'tracking' and rec['_reverted_by_owner'] == TODAY
    entry = world.wall().get(HARLEM)
    assert entry is None or not _on_main_wall(entry), entry


# ===========================================================================
# f3. A stale write never leaves a reverted film's entry on the wall
# ===========================================================================

def _stale_unmarked_entry(lane):
    """The entry as a process that loaded data.json BEFORE the revert writes it back after."""
    if lane == 'main_wall':
        return {'id': HARLEM, 'title': Q, 'year': 2026, 'digital_date': day(-1), '_enrichment_status': 'completed',
                'status': 'available', 'watch_links': {'vod': [{'service': 'Amazon Video', 'link': HARLEM_AMAZON}]}}
    return {'id': HARLEM, 'title': Q, 'year': 2026, 'digital_date': day(10), '_enrichment_status': 'completed',
            '_is_preorder': True, 'status': 'tracking',
            'pre_order_links': [{'service': 'Amazon', 'link': HARLEM_AMAZON}]}


@pytest.mark.parametrize('lane', ['main_wall', 'preorder_lane'])
def test_reverted_film_whose_entry_a_stale_write_brought_back_is_purged_as_a_shell(world, lane):
    """The owner reverts Harlem; then a process that had loaded data.json before the revert writes
    it back, so the entry is on the wall again, unmarked (round 2c: it stayed visible, and the
    gap fill could even graduate it). The next run purges it -- and archives a shell, never a
    full copy that would later block its real entry from the archive."""
    _harlem_on_the_wall_by_mistake(world)
    if lane == 'preorder_lane':
        movies = world.tracking()
        movies[HARLEM].update({'digital_date': day(10), '_type4_pending': True})
        world.save_tracking(movies)
    world.save_wall([_stale_unmarked_entry(lane)])
    world.pages.text = FakeStorePages.AVAILABLE

    world.run(on_day=1)
    world.enrich(on_day=1)
    rec = world.tracking()[HARLEM]
    assert HARLEM not in world.wall(), world.wall().get(HARLEM)
    assert rec['status'] == 'tracking' and rec['_reverted_by_owner'] == TODAY, rec
    arch = _archive(world).get(HARLEM)
    assert arch and arch['_enrichment_status'] == 'reverted' and arch['hidden'] is True, arch


def test_gap_fill_never_graduates_a_stale_entry_of_a_reverted_film(world):
    """The same stale pre-order entry reaching the daily gap fill before any purge, on a day
    JustWatch shows it streaming: the gap fill leaves it alone (tracking still waiting) --
    discovery is what puts a reverted film back, dated from evidence."""
    node = _harlem_on_the_wall_by_mistake(world)
    world.save_wall([_stale_unmarked_entry('preorder_lane')])
    node['offers'].append(jw_offer('FLATRATE', 'Peacock', 'https://www.peacocktv.com/watch/harlem', created=day(1)))
    world._phase(lambda: world.gen.daily_gap_fill(), 'gap fill', 1)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'tracking' and rec['_reverted_by_owner'] == TODAY, rec
    assert world.wall()[HARLEM].get('_is_preorder'), world.wall()[HARLEM]


def test_purge_keeps_a_preorder_entry_of_a_film_that_is_simply_tracking(world):
    """Control: 20 real pre-order-lane entries on main are backed by tracking 'tracking' -- the
    purge's new rule is the owner's revert, never "tracking"."""
    rec = real(LIBERATION)
    assert rec['status'] == 'tracking' and not rec.get('_reverted_by_owner')
    entry = {'id': LIBERATION, 'title': 'Liberation', 'year': 2026, 'digital_date': '2026-11-17',
             '_is_preorder': True, '_enrichment_status': 'completed'}
    world.seed({LIBERATION: rec}, wall=[entry])
    kept = world.gen.purge_removed_movies([copy.deepcopy(entry)])
    assert [m['id'] for m in kept] == [LIBERATION]


# ===========================================================================
# What brings a reverted film back -- and how it is dated
# ===========================================================================

@pytest.mark.parametrize('variant', ['pending', 'fresh'])
def test_tmdbs_date_alone_never_brings_a_reverted_film_back(world, variant):
    """Critic N3: TMDB lists a digital date after the revert (day 3, SYNTHETIC -- a premature
    TMDB date, listed on day 1 ('pending') or on day 3 ('fresh')) while JustWatch still shows
    Amazon's rental starting day 10 and Amazon's page reads "Pre-order". Round 2c put it back on
    day 3, seven days early. JustWatch decides: back on day 10, dated by Amazon's offer start."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    for n in range(1, 11):
        if (variant == 'pending' and n == 1) or (variant == 'fresh' and n == 3):
            world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, day(3), ''))
        if n == 10:
            world.pages.text = FakeStorePages.AVAILABLE
        world.run(on_day=n)
        rec = world.tracking()[HARLEM]
        if n < 10:
            assert rec['status'] == 'tracking', f'back on day {n} ({rec.get("digital_date")}, {rec.get("_digital_date_source")})'
    assert (rec['status'], rec['digital_date'], rec['_digital_date_source']) == ('available', day(10), OFFER_START), rec


def test_new_store_listings_after_a_revert_neither_bring_it_back_nor_date_it(world):
    """f2 / fix-checker NEW-1: after the revert, stores add listings (SYNTHETIC, day 2: a Fandango
    At Home 4K pre-order tier, an Apple 4K rental, Amazon's 4K tier starting day 10), pages
    unreadable. Round 2c put it back on day 2 on those records -- dated day 2, eight days early.
    Now a new store listing alone proves nothing: it waits, and on day 10, when Amazon's rental
    goes live, it is back dated day 10."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = INCONCLUSIVE
    for n in range(1, 10):
        if n == 2:
            node['offers'] += [
                jw_offer('RENT', 'Fandango At Home', HARLEM_FAH, '$5.99', ptype='4K', created=day(2)),
                jw_offer('RENT', 'Apple TV Store', HARLEM_APPLE, '$5.99', '2026-10-16T07:00:00Z', ptype='4K',
                         created=day(2)),
                jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$5.99', f'{day(10)}T07:00:00Z', ptype='4K',
                         created=day(2)),
            ]
        world.run(on_day=n)
        assert world.tracking()[HARLEM]['status'] == 'tracking', f'back on day {n}'
    assert world.tracking()[HARLEM]['_jw_last_refuted'] == TODAY, 'an unreadable page proves nothing'
    world.run(on_day=10)
    rec = world.tracking()[HARLEM]
    assert (rec['status'], rec['digital_date'], rec['_digital_date_source']) == ('available', day(10), OFFER_START), rec


@pytest.mark.parametrize('page_before', ['preorder', 'available'])
def test_reverted_film_comes_back_when_its_store_page_turns_from_preorder_to_available(world, page_before):
    """Fix-checker NEW-2: JustWatch already showed Amazon's rental as live when the owner reverted
    it (offer start day -5, SYNTHETIC -- an offer start doesn't always mark the go-live: The Last
    Blossom), but its page read "Pre-order". Nothing new ever shows on JustWatch when it really
    goes live: round 2c left it waiting for good. Now the store page decides then: read
    "Pre-order" days 1-3 (each a "not out yet" day), "available" on day 4 -> back, dated day 4.
    A page that read "available" all along is no news: the owner's revert stands."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(-5)}T07:00:00Z', created=day(-5))
    world.pages.text = FakeStorePages.AMAZON_PREORDER if page_before == 'preorder' else FakeStorePages.AVAILABLE
    for n in (1, 2, 3):
        world.run(on_day=n)
        rec = world.tracking()[HARLEM]
        assert rec['status'] == 'tracking', f'back on day {n}'
        assert rec['_jw_last_refuted'] == (day(n) if page_before == 'preorder' else TODAY), rec
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=4)
    rec = world.tracking()[HARLEM]
    if page_before == 'preorder':
        assert rec['status'] == 'available' and rec['digital_date'] == day(4), rec
        assert rec['_digital_date_source'] in (CONFIRMED, EVIDENCE) and not rec.get('_date_needs_review'), rec
        assert _on_main_wall(world.wall()[HARLEM])
    else:
        assert rec['status'] == 'tracking', rec


def test_waiting_days_after_a_no_offer_day_never_push_its_date_later(world):
    """Fix-checker NEW-3: day 1 JustWatch has it with no way to watch it (a real "not out yet"
    day); days 2-5 it lists the old Fandango record again (the film waits -- nothing new). Round
    2c stamped each waiting day as checked under the no-offer reason, so its "not out yet" day
    slid to day 5. Day 6 JustWatch first shows Amazon's rental, whose own offer start is day 3
    (JustWatch picked it up late): dated day 3, the day after the last real "not out yet" day."""
    node = _harlem_on_the_wall_by_mistake(world)
    cinema = _cinema(node)
    world.pages.text = INCONCLUSIVE
    node['offers'] = list(cinema)
    world.run(on_day=1)
    rec = world.tracking()[HARLEM]
    assert rec['_jw_revert_reason'] == 'justwatch_no_valid_offers' and rec['_jw_last_refuted'] == day(1), rec
    node['offers'] = cinema + [jw_offer('RENT', 'Fandango At Home', HARLEM_FAH, '$5.99', created=day(-1))]
    for n in (2, 3, 4, 5):
        world.run(on_day=n)
        rec = world.tracking()[HARLEM]
        assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == OWNER_REVERT, rec
        assert putback.last_refuted_day(rec, day(n)) == day(1), rec
    node['offers'].append(jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$5.99', f'{day(3)}T07:00:00Z',
                                   created=day(6)))
    world.run(on_day=6)
    rec = world.tracking()[HARLEM]
    assert (rec['status'], rec['digital_date'], rec['_digital_date_source']) == ('available', day(3), OFFER_START), rec


def _killer_on_the_wall_by_mistake(world):
    """The Killer (real record: a '4K Restoration' reissue, a manual add) on the wall yesterday on
    the ORIGINAL film's old store listings (SYNTHETIC: Apple / Fandango At Home, recorded
    2019-03-01) while the restoration was theatrical-only; the owner reverts it with
    scripts/revert_movie.py. TMDB: only the original's theatrical date."""
    rec = copy.deepcopy(REAL[KILLER])
    rec.update({'digital_date': day(-1), '_discovery_source': 'provider_availability_check',
                '_transitioned_at': day(-1)})
    apple = 'https://tv.apple.com/us/movie/the-killer/umc.cmc.3s50u6f75gpt2ztlml4nvm26h'
    fah = 'https://athome.fandango.com/content/browse/details/The-Killer/staged'
    entry = {'id': KILLER, 'title': 'The Killer', 'year': 1990, 'digital_date': day(-1), '_reissue': True,
             'reissue_label': '4K Restoration', '_enrichment_status': 'completed',
             'watch_links': {'vod': [{'service': 'Apple TV', 'link': apple}]}}
    world.seed({KILLER: rec}, wall=[entry])
    world.tmdb.set_dates(KILLER, (3, '1990-04-13', ''))
    node = jw_node(KILLER, 'The Killer', 1990, [
        jw_offer('RENT', 'Apple TV Store', apple, '$5.99', '2019-03-01T07:00:00Z', created='2019-03-01'),
        jw_offer('BUY', 'Apple TV Store', apple, '$14.99', '2019-03-01T07:00:00Z', created='2019-03-01'),
        jw_offer('RENT', 'Fandango At Home', fah, '$5.99', created='2019-03-01')])
    world.jw.edges['The Killer'] = [node]
    world.pages.text = FakeStorePages.AVAILABLE
    code, out = _revert_script(world, KILLER)
    assert code == 0, out
    return node, out


@pytest.mark.parametrize('churn', ['streaming_rotation', 'amazon_relisting'])
def test_reverted_reissue_waits_for_the_owner_whatever_the_original_does(world, churn):
    """Round 2e (R2D-REV-1): JustWatch lists a reissue under the ORIGINAL film, so the original's
    catalog churn -- landing on Tubi (a FREE offer recorded day 5), or an Amazon re-listing going
    live day 5 (both SYNTHETIC; real captures show such churn for 20 of 75 older streaming films and
    6 of 73 Amazon ones in 60 days) -- looks the same as the restoration coming out. Round 2d put
    The Killer back on either. Owner, Nov 2026 (no "re-add it yourself"): a reverted reissue is
    checked daily like any reverted film and comes back on the first new way to watch it after the
    revert -- even when that is the original's listing (the revert's note says so)."""
    node, out = _killer_on_the_wall_by_mistake(world)
    assert 'A reissue' in out and 'original film' in out, out     # the note explains it
    world.run(on_day=1)
    world.enrich(on_day=1)
    assert world.tracking()[KILLER]['status'] == 'tracking' and KILLER not in world.wall()
    if churn == 'streaming_rotation':
        node['offers'].append(jw_offer('FREE', 'Tubi TV', 'https://tubitv.com/movies/the-killer', created=day(5)))
    else:
        node['offers'].append(jw_offer('RENT', 'Amazon Video', 'https://www.amazon.com/gp/video/detail/B0KILLER',
                                       '$3.99', f'{day(5)}T07:00:00Z', created=day(5)))
    asked = len(world.jw.queries)
    world.run(on_day=5)
    rec = world.tracking()[KILLER]
    assert 'The Killer' in world.jw.queries[asked:], world.jw.queries[asked:]   # checked daily
    assert (rec['status'], rec['digital_date']) == ('available', day(5)), \
        (rec.get('status'), rec.get('digital_date'), rec.get('_digital_date_source'))


# ===========================================================================
# f4. JustWatch-blind titles; the morning report
# ===========================================================================

def _troye_on_the_wall(world):
    rec = copy.deepcopy(REAL[TROYE])
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    rec.update({'status': 'available', 'enriched': True})
    entry = {'id': TROYE, 'title': rec['title'], 'year': 2026, 'digital_date': '2026-10-13',
             '_enrichment_status': 'completed', 'watch_links': {}}
    world.seed({TROYE: rec}, wall=[entry])
    world.tmdb.set_dates(TROYE, (4, '2026-10-13', ''))
    return rec


def test_reverted_apple_music_live_special_comes_back_on_tmdbs_date_after_the_revert(world):
    """f4: an Apple Music Live special (Troye Sivan, real record) is a JustWatch blind spot --
    JustWatch lists no Apple Music offers, so a reverted one never came back (round 2c). It waits
    while TMDB's date is the old one (10-13, before the revert), never asking JustWatch; when TMDB
    dates its release on day 4, it is back on the wall, dated day 4 -- and stays after enrichment
    (curator exemption). The revert warned the owner how it comes back."""
    rec = _troye_on_the_wall(world)
    code, out = _revert_script(world, TROYE)
    assert code == 0 and 'Apple Music Live' in out, out
    for n in (1, 2, 3):
        asked = len(world.jw.queries)
        world.run(on_day=n)
        r = world.tracking()[TROYE]
        assert r['status'] == 'tracking' and r['_jw_last_checked'] == day(n), r
        assert rec['title'] not in world.jw.queries[asked:], 'JustWatch asked about an Apple Music Live special'
    world.enrich(on_day=3)
    assert TROYE not in world.wall()
    assert '1 you sent it back (not out yet)' in world.morning_report(day(3))

    world.tmdb.set_dates(TROYE, (4, day(4), ''))
    world.run(on_day=4)
    r = world.tracking()[TROYE]
    assert (r['status'], r['digital_date'], r['_digital_date_source']) == ('available', day(4), EVIDENCE), r
    assert '_reverted_by_owner' not in r
    world.enrich(on_day=4)
    entry = world.wall()[TROYE]
    assert _on_main_wall(entry) and entry['digital_date'] == day(4), entry


def test_morning_report_names_a_reverted_film_that_may_not_come_back_by_itself(world):
    """The held count keeps a reverted film under "you sent it back" whatever its latest check
    said (round 2c relabelled it "JustWatch can't find it"), and the report names a reverted film
    JustWatch can't find -- it may never come back by itself -- or one a week past its date with
    nothing new, so the owner can /add-movie it."""
    node = _harlem_on_the_wall_by_mistake(world)
    saved = world.jw.edges[Q]
    world.jw.edges[Q] = []                        # JustWatch can't find it
    world.run(on_day=1)
    report = world.morning_report(day(1))
    assert 'Held, checked daily until they come out: 1 (1 you sent it back (not out yet))' in report, report
    assert 'Sent back by you, still waiting' in report and "JustWatch can't find it" in report, report

    world.jw.edges[Q] = saved                     # found again: the same old listings
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(20)}T07:00:00Z', created=day(-1))
    world.pages.text = INCONCLUSIVE
    world.run(on_day=3)
    report = world.morning_report(day(3))
    assert 'Sent back by you, still waiting' not in report, report     # 3 days: nothing to say yet
    world.run(on_day=8)
    report = world.morning_report(day(8))
    assert 'Sent back by you, still waiting' in report and 'waiting 8 days' in report, report


# ===========================================================================
# f6. A reverted festival film is never let through by its screening
# ===========================================================================

def test_reverted_festival_screening_waits_for_justwatch_not_its_screening(world, monkeypatch):
    """f6: River (real records), on the wall in Fests on a live Eventive screening (11-13..11-27).
    The owner reverts it. Round 2c: the next run's live-link check confirmed the screening and
    the festival bypass put it straight back. JustWatch decides for a reverted film: its
    screening page is never fetched, it is checked on JustWatch, and it keeps waiting."""
    world.seed({RIVER: copy.deepcopy(REAL[RIVER])}, wall=[copy.deepcopy(RIVER_ENTRY)])
    link = RIVER_ENTRY['watch_links']['vod'][0]['link']
    os.makedirs(os.path.join(world.tmp, 'overrides'), exist_ok=True)
    with open(os.path.join(world.tmp, 'overrides', 'watch_links_overrides.json'), 'w') as f:
        json.dump({RIVER: {'vod': [{'service': 'Eventive', 'link': link}]}}, f)
    fetched = []
    monkeypatch.setattr(DataGenerator, '_fetch_eventive_play_info',
                        lambda self, url: fetched.append(url) or {'is_available': True, 'available_end': '2026-11-27'})
    assert _owner_reverts(world, RIVER, 0)
    asked = len(world.jw.queries)
    world.run(on_day=1)
    rec = world.tracking()[RIVER]
    assert rec['status'] == 'tracking' and rec['_reverted_by_owner'] == TODAY, rec
    assert 'River' in world.jw.queries[asked:] and fetched == [], fetched
    assert not _on_main_wall(world.wall().get(RIVER))


# ===========================================================================
# f7 / N3. Held films on the Type-4 paths
# ===========================================================================

def test_held_film_tmdb_first_dates_in_the_future_is_checked_that_run_and_listed_once(world):
    """f7: Liberation (real hold) the first run TMDB lists its digital date (11-17, ahead), with an
    Amazon rental live today (SYNTHETIC). Round 2c parked it in the pre-order lane without asking
    JustWatch that run. Now it is checked: live today, so it is put back today -- out of the
    pre-order lane -- and listed for enrichment once (it was listed twice)."""
    rec = real(LIBERATION)
    for k in ('_type4_pending', '_is_preorder', 'digital_date'):
        rec.pop(k, None)
    rec.update({'_jw_last_checked': day(-1), '_jw_last_refuted': day(-1)})
    world.seed({LIBERATION: rec})
    world.tmdb.set_dates(LIBERATION, (4, '2026-11-17', ''))
    world.jw.edges['Liberation'] = [jw_node(LIBERATION, 'Liberation', 2026, [
        jw_offer('RENT', 'Amazon Video', LIBERATION_AMAZON, '$5.99', f'{TODAY}T05:00:00Z', created=TODAY)])]
    world.pages.text = FakeStorePages.AVAILABLE
    asked = len(world.jw.queries)
    world.run()
    r = world.tracking()[LIBERATION]
    assert 'Liberation' in world.jw.queries[asked:]
    assert r['status'] == 'available' and r['_put_back_on'] == TODAY, r
    assert (r['digital_date'], r['_digital_date_source']) == (TODAY, FIRST_OFFER), r
    assert not r.get('_is_preorder') and not r.get('_type4_pending'), r
    assert _on_main_wall(world.wall()[LIBERATION]), world.wall()[LIBERATION]
    with open(os.path.join(world.tmp, 'metrics', 'newly_available.json')) as f:
        queued = json.load(f)
    assert queued['movie_ids'].count(LIBERATION) == 1 and queued['count'] == len(queued['movie_ids']), queued


def test_held_film_waits_on_tmdbs_date_while_its_store_page_reads_preorder(world):
    """Critic N3 (any held film): Harlem, held because its store page read "Pre-order"
    (`_rent_preorder_held`, yesterday), gets a TMDB digital date of today. The Type-4 path put a
    held film back on TMDB's date with no store check. Now it gets the provider path's check:
    the page still reads "Pre-order" -> held, today a "not out yet" day; the next day the page
    reads normally -> back, dated the day after."""
    rec = real(HARLEM)
    rec['_rent_preorder_held'] = day(-1)
    world.seed({HARLEM: rec})
    world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, TODAY, ''))
    world.jw.use_real(Q)
    node = world.jw.node(Q, HARLEM)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(-2)}T07:00:00Z', created=day(-2))
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=0)
    r = world.tracking()[HARLEM]
    assert r['status'] == 'tracking' and r['_rent_preorder_held'] == TODAY and r['_jw_last_refuted'] == TODAY, r
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=1)
    r = world.tracking()[HARLEM]
    assert r['status'] == 'available' and r['digital_date'] == day(1), r
