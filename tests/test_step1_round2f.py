"""Round 2f: the store page's turn after a Revert, read in Amazon's REAL wording.

RV-F3 (round-2e verification): the revert gate's page path ("Pre-order" read after the revert, then
"available") never fired on a real Amazon page -- a released Amazon film reads "Rent HD $9.99 Buy HD
$19.99" and never says "buy now", so every earlier test of it used a synthetic "Rent now Buy now"
page. Live check, Nov 13 2026 (memory: preorder-detection-biased-to-preorder): a released Amazon
film reads "Rent HD $9.99 Buy HD $19.99"; an Amazon pre-order reads "Pre-order UHD $24.99 ·
Pre-order Price Guarantee" in visible text, with `preorder` only in hidden script text.

Round 2f: _read_preorder_page returns 'released' for an Amazon page that shows its own rent/buy
price buttons and no pre-order wording anywhere ('pre-order' or 'preorder'). Only the revert gate
acts on it, and only as the turn after a post-revert "Pre-order" reading. Every other caller treats
it as it treated None (no hold; no proof for a buy-only film): what counts as a pre-release did not
change in Step 1.
"""
import logging
import os
import sys

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_step1_holds_and_dates as h  # noqa: E402
from test_step1_holds_and_dates import (  # noqa: E402,F401  (world: the fixture)
    world, day, HARLEM, CONFIRMED, FakeStorePages,
)
from test_step1_revert import _on_main_wall  # noqa: E402
from test_step1_round2e_revert import _harlem_reverted_amazon_live_before, _back_on  # noqa: E402

AMAZON_RELEASED = 'Once Upon a Time in Harlem  Rent HD $9.99  Buy HD $19.99  Watch with a free trial'
AMAZON_PREORDER_VISIBLE = 'Once Upon a Time in Harlem  Pre-order UHD $24.99 · Pre-order Price Guarantee'
AMAZON_PREORDER = AMAZON_PREORDER_VISIBLE + '  {"offerType":"preorder"}'   # + the hidden script text
AMAZON_URL = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-harlem000001'
APPLE_URL = 'https://tv.apple.com/us/movie/once-upon-a-time-in-harlem/umc.cmc.harlem'


@pytest.mark.parametrize('text,url,verdict', [
    (AMAZON_RELEASED, AMAZON_URL, 'released'),
    ('Once Upon a Time in Harlem  RentHD$9.99BuyHD$19.99', AMAZON_URL, 'released'),   # run-together text
    ('Once Upon a Time in Harlem  Buy UHD $24.99', AMAZON_URL, 'released'),           # for sale only
    (AMAZON_PREORDER, AMAZON_URL, 'pre-order'),
    (AMAZON_PREORDER_VISIBLE, AMAZON_URL, None),    # script text missing: unreadable, never 'released'
    (AMAZON_RELEASED + '  Pre-order Price Guarantee', AMAZON_URL, None),   # any pre-order wording
    (AMAZON_RELEASED, APPLE_URL, None),             # only Amazon's own price buttons count
    ('Once Upon a Time in Harlem  Watch with Prime', AMAZON_URL, None),
    (FakeStorePages.AVAILABLE, AMAZON_URL, 'available'),
])
def test_read_preorder_page_verdicts(world, text, url, verdict):
    d = h.discoverer_mod.ProviderDiscoverer.__new__(h.discoverer_mod.ProviderDiscoverer)
    d.logger = logging.getLogger('test_step1_round2f')
    world.pages.text = text
    assert d._read_preorder_page(url, 'Once Upon a Time in Harlem') == verdict


def test_reverted_film_comes_back_when_amazons_real_page_turns_from_preorder_to_rent(world):
    """Harlem reverted on day 0 although JustWatch already showed Amazon's rental as live (its offer
    start day -5: an offer start doesn't always mark the go-live -- The Last Blossom). Day 1 Amazon's
    page still reads "Pre-order" (real wording); day 2 it shows "Rent HD $9.99 Buy HD $19.99": back
    on day 2, dated day 2 (TMDB has no digital date), on the main wall."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = AMAZON_PREORDER
    world.run(on_day=1)
    r1 = world.tracking()[HARLEM]
    assert r1['status'] == 'tracking' and r1['_revert_page_preorder'] == day(1) == r1['_jw_last_refuted'], r1
    world.pages.text = AMAZON_RELEASED
    world.run(on_day=2)
    r2 = world.tracking()[HARLEM]
    assert (r2['status'], r2['digital_date'], r2['_digital_date_source']) == ('available', day(2), CONFIRMED), r2
    assert _on_main_wall(world.wall().get(HARLEM))


def test_amazons_real_released_page_all_along_never_brings_a_reverted_film_back(world):
    """Control: the same reverted film, Amazon's page showing it for rent every day (it was out when
    the owner reverted it, and the page never read "Pre-order" after): the owner's revert stands."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = AMAZON_RELEASED
    assert _back_on(world, HARLEM, range(1, 6)) is None


def test_a_page_with_only_the_visible_preorder_wording_is_no_turn(world):
    """Day 1 "Pre-order"; days 2-4 the page renders without its script text, so only the visible
    "Pre-order UHD $24.99" is left: unreadable (None), not a turn -- it keeps waiting."""
    _harlem_reverted_amazon_live_before(world)
    world.pages.text = AMAZON_PREORDER
    world.run(on_day=1)
    world.pages.text = AMAZON_PREORDER_VISIBLE
    assert _back_on(world, HARLEM, range(2, 5)) is None
