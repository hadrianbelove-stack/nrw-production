"""Step 1 v2, round 2e: the owner's Revert -- the fixes for the round-2d review findings.

Owner's rules (Nov 15): Revert = a film wrongly marked new (usually the pre-order problem): off
the wall now, back ON ITS OWN the day it's really out; the opposite of Remove. JustWatch decides
availability, never TMDB. A film is dated the day it actually became available, never on a day a
check proved it unavailable. A JustWatch error never counts against a film.

Findings covered (round-2d review, scratchpad/tasks/wge3egvb7.output):
  * R2D-REV-1  a reverted REISSUE came back on the ORIGINAL film's catalog churn;
  * CRIT-1     a release later on the revert's own day never brought the film back;
  * R2D-REV-2  an Amazon CAPTCHA counted as a "Pre-order" reading in the revert gate;
  * R2D-REV-4  the revert gate read only the FIRST store's page, not Amazon's;
  * CRIT-2     a reverted pre-order whose store page turned "available" waited for TMDB's date,
               and that day was stored as "not out yet";
  * CRIT-3     the per-day page cache missed between a tagged and an untagged Amazon URL;
  * the round-2d tests-lens checks (R2D-TP-04/05/06/08/09/11) and the revert lens's clean checks,
    ported so they keep running.

Ported from the round-2d reviewers' files (assertions turned to the FIXED behaviour):
  review/tests-verify/wt/tests/test_verify_tp_holds.py   (v04, v05, v06, v08, v09a-e, v11)
  review/critic/wt/tests/test_critic_2d.py               (c1, c2, c3, c3b)
  review/revert-verify/wt/tests/test_skeptic_revert_2d.py (rev1*, rev2*, rev4*)
  review/revert/wt/tests/test_review_revert_2d.py        (the revert-gate ones)

Harness: tests/test_step1_holds_and_dates.py's World -- the real v2 pipeline in a pytest tmp dir,
only the network and the clock faked (day N = 2026-11-14 + N, 12:00 UTC), a write guard on every
NRW checkout. Records are verbatim 78303fd6 (Harlem, Liberation, Mistletoe, The Killer); JustWatch
offers a test adds are SYNTHETIC and say what real pattern they copy.

Run: cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_round2e_revert.py -q -p no:cacheprovider
"""
import os
import sys
import time

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_step1_holds_and_dates as h  # noqa: E402
from test_step1_holds_and_dates import (  # noqa: E402,F401  (world: the fixture)
    world, real, day, TODAY, HARLEM, HARLEM_AMAZON, LIBERATION, MISTLETOE, putback, jw_offer, jw_node,
    harlem_store_offers, tmdb_details, FakeStorePages, JustWatchClient, OWNER_REVERT, FIRST_OFFER,
    EVIDENCE, CONFIRMED, WORKTREE, _harlem_on_the_wall_by_mistake,
)
from test_step1_revert import (  # noqa: E402
    KILLER, Q, INCONCLUSIVE, HARLEM_APPLE, _killer_on_the_wall_by_mistake, _cinema, _on_main_wall,
    _owner_reverts,
)

OFFER_START = putback.OFFER_START
AFTER_HOLD = putback.AFTER_HOLD
# Amazon's robot check, as the headless browser reads it (two wordings _read_preorder_page knows).
CAPTCHA_PAGES = {
    'captcha': ('Enter the characters you see below. Sorry, we just need to make sure you are not a robot. '
                'Type the characters you see in this image: captcha'),
    'not_a_robot': 'Enter the characters you see below. Sorry, we just need to make sure you are not a robot.',
}
LIB_FAH = 'https://athome.fandango.com/content/browse/details/Liberation/1129188'
LIB_APPLE = 'https://tv.apple.com/us/movie/liberation/umc.cmc.liberation'
LIB_AMZ = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-liberation01'


def _amazon_goes_live_at(node, instant):
    """Harlem's store listings as JustWatch lists them (recorded day -1), Amazon's offer start
    `instant` (SYNTHETIC; real 2026 indie starts include 16:00, 19:35, 20:24, 22:26 UTC)."""
    node['offers'] = _cinema(node) + harlem_store_offers(instant, created=day(-1))


def _harlem_reverted_amazon_live_before(world):
    """Harlem reverted on day 0 while JustWatch already showed Amazon's rental as live (offer start
    day -5: an offer start doesn't always mark the go-live -- The Last Blossom)."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(-5)}T07:00:00Z', created=day(-5))
    return node


def _back_on(world, mid, days, enrich=False):
    """Run discovery (and enrichment) on each day; the first (day, digital_date, source) it is back."""
    for n in days:
        world.run(on_day=n)
        if enrich:
            world.enrich(on_day=n)
        rec = world.tracking()[mid]
        if rec['status'] == 'available':
            return day(n), rec.get('digital_date'), rec.get('_digital_date_source')
    return None


# ===========================================================================
# R2D-REV-1: a reverted REISSUE never comes back by itself
# ===========================================================================

def _killer_reverted(world):
    node, script_out = _killer_on_the_wall_by_mistake(world)   # real record; scripts/revert_movie.py
    world.run(on_day=1)
    world.enrich(on_day=1)
    rec = world.tracking()[KILLER]
    assert rec['status'] == 'tracking' and rec['_reverted_by_owner'] == TODAY, rec
    assert KILLER not in world.wall()
    return node, script_out


@pytest.mark.parametrize('how', ['new_amazon_record', 'same_amazon_record_new_start'])
def test_rev1_reverted_reissue_comes_back_on_an_amazon_relisting_of_the_original(world, how):
    """The Killer (real record: a '4K Restoration' reissue, added by hand) is reverted while the
    restoration is theatrical-only. Day 5 Amazon re-lists the 1990 ORIGINAL -- as a new record, or
    the old 2019 record with a new offer start (SYNTHETIC; real pattern: 6 of 73 old films with an
    Amazon rental had a new offer start in 60 days -- Kill Bill: Vol. 2, Child's Play, The Piano).
    R2D-REV-1: round 2d put it back on the main wall dated day 5 (jw_offer_start), restoration
    still not out. Owner, Nov 2026 (no "re-add it yourself"): checked daily like any reverted
    film, it comes back on the first new way to watch it after the revert -- here the original's
    Amazon re-listing, dated day 5 (the revert's note warns the original's listing can do this)."""
    node, script_out = _killer_reverted(world)
    assert 'A reissue' in script_out and 'original film' in script_out, script_out
    amazon = 'https://www.amazon.com/gp/video/detail/B0KILLERORIG'
    if how == 'same_amazon_record_new_start':
        node['offers'].append(jw_offer('RENT', 'Amazon Video', amazon, '$3.99', '2019-03-01T08:00:00Z',
                                       created='2019-03-01'))
    asked = len(world.jw.queries)
    for n in (2, 3, 4):
        world.run(on_day=n)
    if how == 'same_amazon_record_new_start':
        node['offers'][-1]['availableFromTime'] = f'{day(5)}T08:00:00Z'
    else:
        node['offers'].append(jw_offer('RENT', 'Amazon Video', amazon, '$3.99', f'{day(5)}T08:00:00Z',
                                       created=day(5)))
    world.run(on_day=5)
    world.enrich(on_day=5)
    rec = world.tracking()[KILLER]
    assert (rec['status'], rec['digital_date']) == ('available', day(5)), (how, rec.get('_digital_date_source'))
    assert 'The Killer' in world.jw.queries[asked:], world.jw.queries[asked:]   # checked daily


def test_rev1_reverted_reissue_comes_back_on_a_streaming_rotation_of_the_original(world):
    """The same reverted reissue; day 5 the 1990 original rotates onto Tubi (a FREE offer recorded
    day 5 -- SYNTHETIC; real pattern: 20 of 75 old films with a streaming offer got a new one in
    60 days -- Child's Play on Tubi, Dune (1984) on HBO Max, Rocky I-V on Prime Video).
    R2D-REV-1: round 2d put it back dated day 5 (jw_first_offer), indistinguishable from the
    restoration landing on streaming. Owner, Nov 2026: checked daily, it comes back on it, dated
    day 5 -- information beats a manual re-add."""
    node, _ = _killer_reverted(world)
    for n in (2, 3, 4):
        world.run(on_day=n)
    node['offers'].append(jw_offer('FREE', 'Tubi TV', 'https://tubitv.com/movies/100001/the-killer',
                                   created=day(5)))
    asked = len(world.jw.queries)
    world.run(on_day=5)
    world.enrich(on_day=5)
    rec = world.tracking()[KILLER]
    assert (rec['status'], rec.get('digital_date')) == ('available', day(5)), rec
    assert 'The Killer' in world.jw.queries[asked:]


def test_rev1_morning_report_names_a_reverted_reissue_as_one_to_re_add(world):
    """Control + report wording (R2D-REV-1): with no churn at all, the reverted reissue waits every
    day (days 2-8). The morning report names it under "Sent back by you, still waiting" and says WHY
    in the reissue's terms: JustWatch can't tell the restoration from the original, re-add it when
    the restoration is out. Before the fix the report said "waiting 8 days, nothing new on
    JustWatch" -- as if JustWatch might still bring it back. Round 2f (ENR-4): named from the day it
    is reverted (it waits for the owner, so a week's wait tells nothing), and not counted as
    "checked daily" (it is never looked up)."""
    _killer_reverted(world)
    for n in range(2, 9):
        world.run(on_day=n)
        assert world.tracking()[KILLER]['status'] == 'tracking', n
    # Owner, Nov 2026: a reverted reissue is checked daily like any reverted film, so the report
    # counts it as such and names it only once it is taking long -- information, nothing to do.
    early, late = world.morning_report(day(1)), world.morning_report(day(8))
    assert 'Held, checked daily until they come out: 1' in early and 'The Killer' not in early, early
    line = [ln for ln in late.splitlines() if 'The Killer' in ln]
    assert line and 'nothing new on JustWatch' in line[0] and 're-add' not in late, late


# ===========================================================================
# CRIT-1: a release later on the revert's own day brings it back (the day after)
# ===========================================================================

@pytest.mark.parametrize('amazon_live, expect', [
    pytest.param(f'{day(0)}T20:00:00Z', (day(1), day(1), AFTER_HOLD), id='afternoon-of-the-revert-day'),
    pytest.param(f'{day(1)}T04:00:00Z', (day(1), day(1), OFFER_START), id='next-day-midnight-eastern'),
    pytest.param(f'{day(0)}T09:00:00Z', None, id='live-before-the-revert'),
])
def test_crit1_amazon_going_live_after_the_revert_moment_brings_it_back(world, amazon_live, expect):
    """Port of critic c1. Day 0 at 12:00 UTC (a California morning) the owner reverts Harlem --
    Amazon's page still read "Pre-order". Amazon's rental goes live at `amazon_live`; from day 1 on
    JustWatch lists it live and the page reads "available". CRIT-1: round 2d compared DAYS, so a
    rental going live that same afternoon (after the revert) never counted, and no run read
    "Pre-order" after the revert -- it waited forever. Fixed: the revert's moment
    (_reverted_by_owner_at) is compared with Amazon's full offer start; it is back on day 1, dated
    the day after the revert (never on it), not flagged for review, on the main wall. A rental
    live BEFORE the revert is no news: the owner's revert stands."""
    node = _harlem_on_the_wall_by_mistake(world)       # reverted day 0 at 12:00 UTC (the clock)
    _amazon_goes_live_at(node, amazon_live)
    world.pages.text = FakeStorePages.AVAILABLE
    back = _back_on(world, HARLEM, range(1, 11), enrich=True)
    assert back == expect, (back, world.tracking()[HARLEM])
    rec = world.tracking()[HARLEM]
    if expect:
        assert not rec.get('_date_needs_review') and '_reverted_by_owner_at' not in rec, rec
        e = world.wall()[HARLEM]
        assert _on_main_wall(e) and e['digital_date'] == day(1), e
    else:
        assert rec['status'] == 'tracking' and HARLEM not in world.wall()


@pytest.fixture
def set_tz():
    """Switch the process time zone (datetime.now() / today_str() follow it); restored after."""
    old = os.environ.get('TZ')

    def _set(name):
        os.environ['TZ'] = name
        time.tzset()
    yield _set
    if old is None:
        os.environ.pop('TZ', None)
    else:
        os.environ['TZ'] = old
    time.tzset()


def _revert_harlem_at_pacific_evening(world, set_tz, hours_after_noon_utc):
    """Harlem on the wall by mistake; the owner reverts it from the admin on the Mac (Pacific),
    `hours_after_noon_utc` after day 0 12:00 UTC (no `today`: the button's own clock)."""
    node = _harlem_on_the_wall_by_mistake(world)
    movies = world.tracking()
    movies[HARLEM].update({'status': 'available', 'digital_date': day(-1)})   # undo the helper's revert
    for k in ('_reverted_by_owner', '_reverted_by_owner_at'):
        movies[HARLEM].pop(k, None)
    world.save_tracking(movies)
    set_tz('America/Los_Angeles')
    world.clock.days = hours_after_noon_utc / 24
    movies = world.tracking()
    assert putback.owner_revert(movies[HARLEM])
    world.save_tracking(movies)
    set_tz('UTC')                              # CI runs in UTC
    return node, world.tracking()[HARLEM]


def test_crit1_the_revert_keeps_the_macs_day_and_stamps_its_moment_in_utc(world, set_tz):
    """CRIT-1, the stamp. The owner reverts at 19:00 Pacific on day 0 = 03:00 UTC on day 1. The
    revert's DAY stays the Mac's date (day 0: never dated on or before it) and its MOMENT is
    stamped in UTC, as JustWatch's offer starts are (2026-11-15T03:00Z). Without the moment the
    gate can only compare days, and a release later on the revert's own day never counts."""
    _, rec = _revert_harlem_at_pacific_evening(world, set_tz, 15)
    assert rec['_reverted_by_owner'] == TODAY and rec['_jw_last_refuted'] == TODAY, rec
    assert rec.get('_reverted_by_owner_at', '').startswith(f'{day(1)}T03:0'), rec


def test_crit1_late_evening_pacific_revert_before_a_midnight_eastern_release(world, set_tz):
    """Timezone edge (CRIT-1). The owner reverts Harlem at 19:00 Pacific on day 0 (03:00 UTC on
    day 1). Amazon's rental goes live at midnight Eastern (day 1 04:00Z, after the revert). CI
    (UTC) runs on day 1: it is back that run, dated day 1 by Amazon's offer start. If the revert's
    day were taken in UTC, CI would see "reverted today" and wait a day (dated a day late); if the
    revert's moment were compared as a local time, the evening revert would look later than the
    release and it would never come back by itself."""
    node, _ = _revert_harlem_at_pacific_evening(world, set_tz, 15)
    _amazon_goes_live_at(node, f'{day(1)}T04:00:00Z')
    world.pages.text = FakeStorePages.AVAILABLE
    assert _back_on(world, HARLEM, [1]) == (day(1), day(1), OFFER_START)


def test_crit1_a_second_revert_is_judged_from_its_own_moment(world):
    """CRIT-1 with a second revert. Reverted on day 0; Amazon's rental goes live day 2 (07:00 UTC)
    -> back on day 2. The owner reverts it AGAIN on day 3 (12:00 UTC): the day-2 start is from
    before that revert and doesn't bring it back (day 4 waits). Then JustWatch shows a new Amazon
    4K tier that went live on day 3 at 20:00 UTC -- after the second revert, the same day: back on
    day 5, dated day 4 (the day after the revert, never on it). Round 2d compared days and never
    counted that same-day tier."""
    node = _harlem_on_the_wall_by_mistake(world)
    _amazon_goes_live_at(node, f'{day(2)}T07:00:00Z')
    world.pages.text = INCONCLUSIVE
    assert _back_on(world, HARLEM, [1, 2]) == (day(2), day(2), OFFER_START)
    world.enrich(on_day=2)
    world.clock.days = 3
    assert _owner_reverts(world, HARLEM, 3)
    rec = world.tracking()[HARLEM]
    assert rec['_reverted_by_owner'] == day(3) and rec['_jw_last_refuted'] == day(3), rec
    assert _back_on(world, HARLEM, [4]) is None
    node['offers'].append(jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$7.99', f'{day(3)}T20:00:00Z',
                                   ptype='4K', created=day(4)))
    assert _back_on(world, HARLEM, [5]) == (day(5), day(4), AFTER_HOLD)


def test_crit1_moment_boundaries_and_time_formats():
    """CRIT-1, the comparison itself (owner reverted 2026-11-10 at 16:00 UTC). An Amazon start at
    the revert's very second is not after it; one second later is. JustWatch-style times with
    fractional seconds, '+00:00' or another offset are read as moments (a 12:00 -08:00 start is
    20:00 UTC: after the revert). A streaming record with a full time counts the same way. A record
    reverted before round 2e (no _reverted_by_owner_at) still compares days, as before. Without
    the fix every same-day start was ignored."""
    rec = {'status': 'available', 'title': 'X', 'year': 2026}
    putback.owner_revert(rec, today='2026-11-10')
    rec['_reverted_by_owner_at'] = '2026-11-10T16:00:00Z'

    def back(streams=(), starts=()):
        return putback.owner_revert_putback(rec, list(streams), list(starts), False, None, '2026-11-14')
    assert back(starts=['2026-11-10T16:00:00Z']) is None
    for start in ('2026-11-10T16:00:01Z', '2026-11-10T20:00:00.000Z', '2026-11-10T20:00:00+00:00',
                  '2026-11-10T12:00:00-08:00'):
        assert back(starts=[start]) == ('2026-11-11', AFTER_HOLD), start
    assert back(streams=['2026-11-10T18:00:00Z']) == ('2026-11-11', AFTER_HOLD)
    assert back(streams=['2026-11-10T15:00:00Z']) is None
    old = dict(rec)
    old.pop('_reverted_by_owner_at')
    assert putback.owner_revert_putback(old, [], ['2026-11-10T20:00:00Z'], False, None, '2026-11-14') is None
    assert putback.owner_revert_putback(old, [], ['2026-11-11T04:00:00Z'], False, None,
                                        '2026-11-14') == ('2026-11-11', OFFER_START)


def test_crit1_justwatch_returns_full_offer_start_and_record_times(world):
    """CRIT-1, the data: JustWatch's reply for Harlem (SYNTHETIC offers: an Amazon rental live since
    yesterday 20:00 UTC, a Peacock stream recorded with a full time yesterday, a Hulu stream with a
    day-only record). verify_availability keeps the days it always returned AND the full times the
    revert gate compares (live_rent_start_times, stream_offer_times). Without them the gate could
    only compare days."""
    world.jw.edges[Q] = [jw_node(HARLEM, Q, 2026, [
        jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$5.99', f'{day(-1)}T20:00:00Z', created=day(-1)),
        jw_offer('FLATRATE', 'Peacock', 'https://www.peacocktv.com/watch/harlem', created=f'{day(-1)}T18:30:00Z'),
        jw_offer('FLATRATE', 'Hulu', 'https://www.hulu.com/movie/harlem', created=day(-2))])]
    r = JustWatchClient().verify_availability(Q, 2026, tmdb_id=HARLEM)
    assert r['has_live_rent'] is True
    assert r['live_rent_starts'] == [day(-1)] and r.get('live_rent_start_times') == [f'{day(-1)}T20:00:00Z'], r
    assert r['stream_offer_dates'] == [day(-2), day(-1)]
    assert r.get('stream_offer_times') == [day(-2), f'{day(-1)}T18:30:00Z'], r


# ===========================================================================
# R2D-REV-2: an Amazon CAPTCHA in the revert gate records nothing
# ===========================================================================

@pytest.mark.parametrize('robot', sorted(CAPTCHA_PAGES))
def test_rev2_a_captcha_day_records_nothing_and_the_revert_stands(world, robot):
    """Harlem reverted while JustWatch already showed Amazon's rental live (start day -5); Amazon's
    page reads "available" every day -- by the rule, a page that read "available" all along is no
    news: the owner's revert stands. Day 2 Amazon answers with its robot check. R2D-REV-2: round 2d
    read the CAPTCHA as "Pre-order", stored day 2 as a "not out yet" day and as the page's
    "Pre-order" reading, so day 3's "available" put it back on the main wall against the revert.
    Fixed: the CAPTCHA is logged for the owner (morning report's CAPTCHA list) but records nothing,
    and the film keeps waiting on day 3 and after enrichment."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=1)
    assert '_revert_page_preorder' not in world.tracking()[HARLEM]
    world.pages.text = CAPTCHA_PAGES[robot]
    world.run(on_day=2)
    r2 = world.tracking()[HARLEM]
    assert r2['status'] == 'tracking' and '_revert_page_preorder' not in r2, r2
    assert r2['_jw_last_refuted'] == TODAY, 'a robot check is not a "not out yet" day'
    assert 'CAPTCHA' in world.last_output and Q in world.metrics()['captcha_block_titles']
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=3)
    world.enrich(on_day=3)
    r3 = world.tracking()[HARLEM]
    assert r3['status'] == 'tracking' and r3['_jw_revert_reason'] == OWNER_REVERT, r3
    assert not _on_main_wall(world.wall().get(HARLEM))


def test_rev2_a_captcha_day_never_pushes_a_release_a_day_later(world):
    """Second effect of R2D-REV-2 (skeptic rev2). Day 1 Amazon's page reads "Pre-order" (a real
    "not out yet" day); TMDB dates the release day 2, and on day 2 Amazon shows its robot check;
    day 3 the page reads "available". Round 2d stored the CAPTCHA day as "not out yet", so TMDB's
    day-2 date was refused and the film was dated day 3. Fixed: dated day 2 (TMDB's date, after the
    last real "not out yet" day) -- never on a day only an unreadable page spoke for."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    assert world.tracking()[HARLEM]['_revert_page_preorder'] == day(1)
    world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, day(2), ''))
    world.pages.text = CAPTCHA_PAGES['not_a_robot']
    world.run(on_day=2)
    assert world.tracking()[HARLEM]['_jw_last_refuted'] == day(1)
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=3)
    r3 = world.tracking()[HARLEM]
    assert (r3['status'], r3['digital_date'], r3['_digital_date_source']) == ('available', day(2), EVIDENCE), r3


def test_rev2_control_a_page_that_read_available_all_along_never_brings_it_back(world):
    """Control for R2D-REV-2 (review + skeptic controls): the same reverted film, Amazon's page
    "available" every day for ten days, no CAPTCHA: the owner's revert stands throughout."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = FakeStorePages.AVAILABLE
    assert _back_on(world, HARLEM, range(1, 11)) is None
    assert world.tracking()[HARLEM]['_jw_last_refuted'] == TODAY


# ===========================================================================
# R2D-REV-4: the revert gate reads Amazon's page when JustWatch lists Amazon
# ===========================================================================

@pytest.mark.parametrize('first', ['apple_first', 'amazon_first'])
def test_rev4_the_revert_gate_reads_amazons_page_whatever_the_store_order(world, monkeypatch, first):
    """The Last Blossom pattern for a reverted film (real: production held it 2026-10-07/08 on an
    Amazon page reading "Pre-order" though Amazon's offer start had passed; out 10-09): Amazon's
    start passed before the revert, its page reads "Pre-order" days 1-3 and "available" from day 4.
    JustWatch lists Apple's rental before Amazon's or after (SYNTHETIC order; 71 of 500 wall films
    with an Amazon link list another store first). Apple's page can't be read. R2D-REV-4: round 2d
    read only the first store's page -- with Apple first it never saw Amazon's page turn and the
    film waited for good. Fixed: Amazon's page is read either way; back on day 4, dated day 4."""
    node = _harlem_on_the_wall_by_mistake(world)
    apple = [jw_offer('RENT', 'Apple TV Store', HARLEM_APPLE, '$5.99', '2026-10-16T07:00:00Z', created=day(-5))]
    amazon = [jw_offer('RENT', 'Amazon Video', HARLEM_AMAZON, '$5.99', f'{day(-5)}T07:00:00Z', created=day(-5)),
              jw_offer('BUY', 'Amazon Video', HARLEM_AMAZON, '$14.99', f'{day(-5)}T07:00:00Z', created=day(-5))]
    node['offers'] = _cinema(node) + (apple + amazon if first == 'apple_first' else amazon + apple)
    state = {'amazon': 'pre-order'}
    read = []

    def fake_read(self, url, title):
        read.append(url)
        return state['amazon'] if 'amazon.com' in url else None
    monkeypatch.setattr(h.discoverer_mod.ProviderDiscoverer, '_read_preorder_page', fake_read)
    assert _back_on(world, HARLEM, [1, 2, 3]) is None
    rec = world.tracking()[HARLEM]
    assert (rec.get('_revert_page_preorder'), rec.get('_jw_last_refuted')) == (day(3), day(3)), rec
    assert any('amazon.com' in u for u in read), read
    state['amazon'] = 'available'
    assert _back_on(world, HARLEM, [4]) == (day(4), day(4), CONFIRMED)


# ===========================================================================
# CRIT-2: a reverted pre-order is back on its store page's word, before TMDB's date
# ===========================================================================

def test_crit2_reverted_preorder_back_on_its_store_pages_word_before_tmdbs_date(world):
    """Port of critic c2. Liberation (real hold: pending TMDB date 2026-11-17 = day 3) is reverted on
    day 0. JustWatch lists store rentals only (SYNTHETIC: Fandango At Home first, Apple -- never
    "live" by the rules), so the gate reads the first store's page. Day 1 it reads "Pre-order"; day
    2 "available". CRIT-2: round 2d's own gate said "back today", but the provider path's
    future-TMDB-date guard held it, stored day 2 (a day the page read "available") as "not out
    yet" and brought it back only on TMDB's date. Fixed: back on day 2, dated day 2, its last "not
    out yet" day still day 1; on the main wall (not a pre-order) after enrichment, and TMDB's date
    arriving on day 3 doesn't move it."""
    rec = real(LIBERATION)
    assert rec['_type4_pending'] and rec['digital_date'] == '2026-11-17'
    world.seed({LIBERATION: rec})
    world.tmdb.set_dates(LIBERATION, (4, '2026-11-17', ''))
    world.jw.edges['Liberation'] = [jw_node(LIBERATION, 'Liberation', 2026, [
        jw_offer('RENT', 'Fandango At Home', LIB_FAH, '$5.99', None, created=day(-5)),
        jw_offer('RENT', 'Apple TV Store', LIB_APPLE, '$5.99', '2026-09-15T07:00:00Z', created=day(-5))])]
    movies = world.tracking()
    assert putback.owner_revert(movies[LIBERATION], today=day(0))
    world.save_tracking(movies)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    r1 = world.tracking()[LIBERATION]
    assert r1['status'] == 'tracking' and r1['_revert_page_preorder'] == day(1) and r1['_jw_last_refuted'] == day(1)
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=2)
    r2 = world.tracking()[LIBERATION]
    assert (r2['status'], r2.get('digital_date'), r2.get('_digital_date_source')) == ('available', day(2), CONFIRMED), r2
    assert r2['_jw_last_refuted'] == day(1), 'a day the store page read "available" stored as "not out yet"'
    assert not r2.get('_is_preorder') and not r2.get('_type4_pending'), r2
    world.enrich(on_day=2)
    e = world.wall()[LIBERATION]
    assert _on_main_wall(e) and e['digital_date'] == day(2), e
    world.run(on_day=3)
    world.enrich(on_day=3)
    assert world.tracking()[LIBERATION]['digital_date'] == day(2)
    assert world.wall()[LIBERATION]['digital_date'] == day(2)


# ===========================================================================
# CRIT-3: one read of a store page a day, tagged URL or not
# ===========================================================================

def _liberation_buyonly_with_a_future_amazon_rental(world):
    """Liberation's real record made a buy-only pre-order (no TMDB date); JustWatch now lists an
    Amazon rental whose offer start is day 5 (SYNTHETIC: not live yet), and Amazon's page reads
    "available". Discovery's buy-only daily check asks JustWatch WITHOUT the affiliate tag, the
    provider path WITH it: the same page under two URLs."""
    rec = real(LIBERATION)
    for k in ('_type4_pending', 'digital_date', '_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at',
              '_jw_last_checked', '_is_preorder'):
        rec.pop(k, None)
    rec.update({'status': 'tracking', '_buyonly_preorder': True})
    world.seed({LIBERATION: rec})
    world.tmdb.set_dates(LIBERATION)
    world.jw.edges['Liberation'] = [jw_node(LIBERATION, 'Liberation', 2026, [
        jw_offer('RENT', 'Amazon Video', LIB_AMZ, '$5.99', f'{day(5)}T05:00:00Z', created=day(-2)),
        jw_offer('BUY', 'Amazon Video', LIB_AMZ, '$14.99', f'{day(5)}T05:00:00Z', created=day(-2))])]
    world.pages.text = FakeStorePages.AVAILABLE


def test_crit3_a_store_page_is_rendered_once_a_run_tagged_or_untagged(world):
    """Port of critic c3. CRIT-3: round 2d keyed its one-read-a-day page cache by the full URL, so
    the buy-only check (untagged Amazon URL) and the store check (with `tag=`) rendered Amazon's page
    twice -- two reads that could disagree. Fixed: the key drops the affiliate tag; one render a
    run, whichever check asks first."""
    _liberation_buyonly_with_a_future_amazon_rental(world)
    world.pages.visited.clear()
    world.run(on_day=0)
    visits = [u for u in world.pages.visited if 'liberation01' in u]
    assert len(visits) == 1, visits


def test_crit3_no_second_disagreeing_read_can_turn_a_graduation_into_a_hold(world):
    """Port of critic c3b. Same film; Amazon's page would show its robot check on a SECOND render.
    Round 2d rendered it twice: the first read ("available") graduated the buy-only pre-order, the
    second (a CAPTCHA, read as "Pre-order") then held it as a rent pre-order -- today stored as "not
    out yet" though the page read "available" minutes earlier, and the buy-only flag gone. Fixed:
    there is no second render: no store-page hold and no "not out yet" day on the strength of a
    read that never happened, and the film is never left held without its buy-only flag."""
    _liberation_buyonly_with_a_future_amazon_rental(world)
    pages = world.pages

    class _Switch(list):
        def append(self, x):
            super().append(x)
            if len(self) == 2:
                pages.text = CAPTCHA_PAGES['not_a_robot']
    pages.visited = _Switch()
    world.run(on_day=0)
    r = world.tracking()[LIBERATION]
    assert len(pages.visited) == 1, list(pages.visited)
    assert not r.get('_rent_preorder_held') and r.get('_jw_last_refuted') != day(0), r
    assert r['status'] == 'available' or r.get('_buyonly_preorder'), r


def test_crit3_page_key_drops_only_the_affiliate_tag():
    """CRIT-3, the key itself: Amazon's page with or without `tag=` (anywhere in the query) is one
    page; a different title (gti) is another page; other query parameters (Apple's playableId) are
    kept. Without it the tagged and untagged reads of one page missed each other."""
    k = h.discoverer_mod._page_key
    a = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.5c1e7f2a-0b6d-4e1f-9a1c-harlem2026'
    assert k(a) == k(a + '&tag=nrw04-20') == k(
        'https://watch.amazon.com/detail?tag=nrw04-20&gti=amzn1.dv.gti.5c1e7f2a-0b6d-4e1f-9a1c-harlem2026')
    assert k(a) != k('https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-liberation01')
    apple = ('https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2'
             '&ct=app_tv&playableId=tvs.sbd.9001%3A6812862855')
    assert 'playableId=tvs.sbd.9001%3A6812862855' in k(apple) and 'at=1000l3V2' in k(apple)


# ===========================================================================
# Round-2d tests lens (R2D-TP-04/05/06/08/09/11), ported: still hold on 2e
# ===========================================================================

def _hold(rec):
    return {k: rec.get(k) for k in ('status', '_jw_revert_reason', '_jw_revert_count', '_jw_reverted_at',
                                    '_reverted_by_owner', 'enriched', '_jw_last_refuted')}


@pytest.mark.parametrize('page', ['unreadable', 'available'])
def test_v04_enrich_id_keeps_a_reverted_films_hold_and_it_keeps_waiting(world, page):
    """R2D-TP-04 (v04): `--enrich-id` on a reverted film must not rewrite its hold (round 2c's
    enrichment re-checked it and undid the revert). Then TMDB lists a rental on day 3 with nothing
    new on JustWatch (store listings recorded day -1, Amazon's start day 10): it keeps waiting."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = INCONCLUSIVE if page == 'unreadable' else FakeStorePages.AVAILABLE
    before = _hold(world.tracking()[HARLEM])
    world._phase(lambda: world.enrichment_generator().enrich_newly_available_movies(target_id=HARLEM),
                 'enrichment', 1)
    assert _hold(world.tracking()[HARLEM]) == before
    world.tmdb.set_providers(HARLEM, rent=['Apple TV Store'])
    world.run(on_day=3)
    assert world.tracking()[HARLEM]['status'] == 'tracking'


def test_v05_stale_reverted_entry_never_takes_the_genuine_films_catch_up_slot(world):
    """R2D-TP-05 (v05): a stale pre-revert entry of the reverted Harlem sits FIRST in data.json,
    hidden and waiting for its check; Mistletoe (real record, here out and waiting hidden) is a
    genuine film. With a catch-up batch of 1, the reverted film must never take the slot: Harlem is
    purged and Mistletoe is shown."""
    import pipeline.enricher as enricher_mod
    _harlem_on_the_wall_by_mistake(world)
    movies = world.tracking()
    gen = real(MISTLETOE)
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        gen.pop(k, None)
    gen.update({'status': 'available', 'digital_date': day(-1), 'enriched': False})
    movies[MISTLETOE] = gen
    world.save_tracking(movies)
    world.tmdb.details[MISTLETOE] = tmdb_details(MISTLETOE, gen)
    title = gen['title']
    world.jw.edges[title] = [jw_node(MISTLETOE, title, gen.get('year') or 2026, [
        jw_offer('FLATRATE', 'Hallmark+', 'https://www.hallmarkplus.com/verify', created=day(-1))])]
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
    assert HARLEM not in wall
    assert not wall[MISTLETOE].get('hidden'), wall[MISTLETOE]


@pytest.mark.parametrize('variant', ['pending', 'fresh'])
def test_v06_tmdbs_date_alone_never_brings_it_back_when_the_page_cannot_be_read(world, variant):
    """R2D-TP-06 (v06): TMDB dates the release day 3 (first listed day 1 or day 3) while JustWatch
    still shows Amazon's rental starting day 10 and the page can't be read: it waits through day 9
    (JustWatch decides, never TMDB) and is back on day 10, dated day 10."""
    node = _harlem_on_the_wall_by_mistake(world)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(10)}T07:00:00Z', created=day(-1))
    world.pages.text = INCONCLUSIVE
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


def test_v08_held_pending_preorder_waits_on_its_arrived_date_while_the_page_reads_preorder(world):
    """R2D-TP-08 (v08): a held film whose stored pending TMDB date arrives today, store page still
    "Pre-order": held (today a "not out yet" day); the next day the page reads normally -> back,
    dated that day (never on TMDB's date alone)."""
    rec = real(HARLEM)
    rec.update({'_type4_pending': True, 'digital_date': TODAY, '_discovery_source': 'tmdb_type4'})
    world.seed({HARLEM: rec})
    world.tmdb.set_dates(HARLEM, (3, '2026-10-16', ''), (4, TODAY, ''))
    world.jw.use_real(Q)
    node = world.jw.node(Q, HARLEM)
    node['offers'] = _cinema(node) + harlem_store_offers(f'{day(-1)}T07:00:00Z', created=day(-1))
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=0)
    r = world.tracking()[HARLEM]
    assert r['status'] == 'tracking' and r.get('_jw_last_refuted') == TODAY, r
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=1)
    r = world.tracking()[HARLEM]
    assert r['status'] == 'available' and r['digital_date'] == day(1), r


def test_v09a_the_store_page_is_rendered_once_on_a_put_back_day(world):
    """R2D-TP-09 (v09a): on the day a reverted film comes back on its store page's word, the
    revert gate and the pre-order guard right after it read the page ONCE (a second read could
    disagree with the first)."""
    _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    world.pages.text = FakeStorePages.AVAILABLE
    seen = len(world.pages.visited)
    world.run(on_day=2)
    assert world.tracking()[HARLEM]['status'] == 'available'
    assert len(world.pages.visited) - seen == 1, world.pages.visited[seen:]


def _add_movie(world, on_day):
    world._mp.syspath_prepend(os.path.join(WORKTREE, 'scripts'))
    import add_movie
    assert os.path.realpath(add_movie.__file__).startswith(WORKTREE)
    world._mp.setattr(sys, 'argv', ['add_movie.py', HARLEM, '--date', day(on_day)])
    world._phase(add_movie.main, 'add movie', on_day)


def test_v09b_a_hand_readd_ends_the_owners_revert(world):
    """R2D-TP-09 (v09b): /add-movie on a reverted film ends the owner's revert; a later automatic
    pull back to tracking (e.g. enrichment's PVOD gate) must not count as the owner's revert."""
    _harlem_on_the_wall_by_mistake(world)
    _add_movie(world, 1)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'available' and '_reverted_by_owner' not in rec, rec
    assert '_reverted_by_owner_at' not in rec, rec
    rec.update({'status': 'tracking', '_jw_revert_count': 1, '_jw_revert_reason': 'justwatch_theatrical_pvod'})
    assert not putback.is_owner_reverted(rec)


def test_v09c_owner_revert_drops_an_old_page_reading():
    """R2D-TP-09 (v09c): a new revert forgets an old "Pre-order" page reading, so it can't count
    as the "turn" that brings the film back."""
    rec = real(HARLEM)
    rec.update({'status': 'available', '_revert_page_preorder': day(-3)})
    assert putback.owner_revert(rec, today=TODAY)
    assert '_revert_page_preorder' not in rec, rec


def test_v09d_second_revert_waits_on_a_page_that_read_available_at_that_revert(world):
    """R2D-TP-09 (v09d): reverted on day 0, page "Pre-order" on day 1; re-added by hand on day 2;
    reverted AGAIN on day 3 (the clock set to day 3, as the admin would stamp it -- the reviewer's
    original passed today=day 3 with the clock on day 2, an inconsistent revert moment). Amazon's
    rental went live on day 3 at 07:00 UTC, before that second revert. On day 4 the page reads
    "available": the old day-1 reading must not count, nothing is new since the second revert --
    it keeps waiting."""
    _harlem_on_the_wall_by_mistake(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    assert world.tracking()[HARLEM]['_revert_page_preorder'] == day(1)
    _add_movie(world, 2)
    world.clock.days = 3
    movies = world.tracking()
    assert putback.owner_revert(movies[HARLEM], today=day(3))
    world.save_tracking(movies)
    site = {'movies': list(world.wall().values())}
    putback.revert_wall_entry(site, HARLEM)
    world.save_wall(site['movies'])
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=4)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'tracking', rec


def test_v09e_link_finder_spends_at_most_its_budget_soonest_release_first(world):
    """R2D-TP-09 (v09e): the pre-order link finder before enrichment's loop spends at most its
    15-minute budget, soonest release first (four PRE-ORDER entries, each Amazon lookup 6 minutes:
    three are asked, the latest waits for the next run)."""
    import types
    import pipeline.enricher as enricher_mod
    from test_step1_holds_and_dates import FakeVodScraper
    films = [('9200004', 'Fourth', 12), ('9200003', 'Third', 9), ('9200002', 'Second', 6), ('9200001', 'First', 3)]
    world.seed({}, wall=[{'id': mid, 'title': t, 'year': 2026, 'digital_date': day(n), '_is_preorder': True,
                          '_enrichment_status': 'completed'} for mid, t, n in films])
    clock = {'t': 1_900_000_000.0}
    fake_time = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith('_')})
    fake_time.time = lambda: clock['t']
    world._mp.setattr(enricher_mod, 'time', fake_time)
    asked = []

    def find_amazon_link(self, title, year, director=None):
        asked.append(title)
        clock['t'] += 6 * 60
        return None
    world._mp.setattr(FakeVodScraper, 'find_amazon_link', find_amazon_link)
    world.enrich(on_day=0)
    assert asked == ['First', 'Second', 'Third'], asked
    assert '15-min budget used; 1 film(s) wait for the next run' in world.last_output, world.last_output[-600:]


def test_v11_gap_fill_leaves_a_reverted_films_tracking_record_alone(world):
    """R2D-TP-11 (v11): Harlem reverted while TMDB dates it day 10; a stale write left its old
    main-wall entry; JustWatch shows it buy-only (SYNTHETIC: an Amazon purchase). The gap fill must
    not touch the reverted film's tracking record (discovery decides for it)."""
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
    assert not changed, f"the gap fill rewrote a reverted film's tracking record: {changed}"


# ===========================================================================
# Round-2d revert lens: the clean revert-gate checks, ported
# ===========================================================================

def test_revert_of_a_pending_preorder_waits_off_the_wall_and_is_back_on_amazons_start(world):
    """Revert lens (clean check): Liberation (real record, in the pre-order lane, TMDB 11-17) is
    reverted from the PRE-ORDER lane. Days 1-2 no pre-order entry is re-created and JustWatch is
    asked each run; day 3 (11-17) Amazon's pre-order rental goes live (SYNTHETIC: start 11-17,
    listed day -4) -> back on the main wall dated 11-17 by Amazon's offer start."""
    rec = real(LIBERATION)
    entry = {'id': LIBERATION, 'title': 'Liberation', 'year': 2026, 'digital_date': '2026-11-17',
             '_is_preorder': True, '_enrichment_status': 'completed'}
    world.seed({LIBERATION: rec}, wall=[entry])
    world.tmdb.set_dates(LIBERATION, (4, '2026-11-17', ''))
    world.jw.edges['Liberation'] = [jw_node(LIBERATION, 'Liberation', 2026, [
        jw_offer('RENT', 'Amazon Video', h.LIBERATION_AMAZON, '$5.99', '2026-11-17T08:00:00Z', created=day(-4)),
        jw_offer('BUY', 'Amazon Video', h.LIBERATION_AMAZON, '$14.99', '2026-11-17T08:00:00Z', created=day(-4))])]
    world.pages.text = INCONCLUSIVE
    assert _owner_reverts(world, LIBERATION, 0)
    r = world.tracking()[LIBERATION]
    assert r['digital_date'] == '2026-11-17' and r['_type4_pending'], r
    for n in (1, 2):
        asked = len(world.jw.queries)
        world.run(on_day=n)
        world.enrich(on_day=n)
        r = world.tracking()[LIBERATION]
        assert r['status'] == 'tracking' and 'Liberation' in world.jw.queries[asked:], r
        assert LIBERATION not in world.wall(), world.wall().get(LIBERATION)
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=3)
    r = world.tracking()[LIBERATION]
    assert (r['status'], r['digital_date'], r['_digital_date_source']) == ('available', '2026-11-17', OFFER_START), r
    world.enrich(on_day=3)
    assert _on_main_wall(world.wall()[LIBERATION]), world.wall()[LIBERATION]


def test_rerevert_resets_the_page_memory_and_the_floor(world):
    """Revert lens (clean check): a film back on its store page's word ("Pre-order" day 1,
    "available" day 2) is reverted AGAIN on day 3 (clock on day 3): the second revert forgets the
    old page reading and dates from itself, so the page that keeps reading "available" can't bring
    it straight back (days 4-5 wait)."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = FakeStorePages.AMAZON_PREORDER
    world.run(on_day=1)
    world.pages.text = FakeStorePages.AVAILABLE
    world.run(on_day=2)
    world.enrich(on_day=2)
    r = world.tracking()[HARLEM]
    assert r['status'] == 'available' and r['digital_date'] == day(2), r
    world.clock.days = 3
    _owner_reverts(world, HARLEM, 3)
    r = world.tracking()[HARLEM]
    assert '_revert_page_preorder' not in r and r['_reverted_by_owner'] == day(3) and r['_jw_last_refuted'] == day(3), r
    assert _back_on(world, HARLEM, [4, 5]) is None
