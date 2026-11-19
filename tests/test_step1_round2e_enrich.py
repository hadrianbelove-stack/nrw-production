"""
Round 2e verification -- the ENRICH group: EO-5 (trailer hosting after enrichment's saves),
TP-01 (enrichment's catch-up of a pre-order whose TRACKING record is buy-only though its wall
entry is not), and the morning report's wording for a reverted reissue.

Tests to keep. Each asserts the FIXED behaviour the owner's rules require and passes on the 2e
code; each docstring says the scenario, the finding it covers and what went wrong without the fix.

Owner's rules these hold the code to:
  1. A film held as "not out yet" is a WAIT, never a drop; every held film is re-checked every run.
  2. JustWatch decides availability, never TMDB.
  3. A film is dated the day it actually became available, never on a day a check proved it
     unavailable.
  4. JustWatch errors never count against a film nor publish an unconfirmed one.
  5. Remove and Revert are opposites (removed = never back; reverted = back on its own when out).

Harnesses (imported from the Step 1 test files, not copied):
  * `nrw` (tests/test_step1_enrichment.py): the real enrichment phase in a tmp checkout, verbatim
    78303fd6 records, TMDB / JustWatch / every other network call faked, a write guard on the NRW
    checkouts. The trailer host (`host_trailer_for_movie`) is a recorder here: nothing downloads.
  * `scenario` / `run_daily` (tests/test_step1_preorders.py): the real daily phases on the real
    Wicker records (78303fd6), clock frozen at 09:00 on 2026-11-14, store pages faked; the
    worktree write audit (`_worktree_write_audit`, imported below) is on for every test here.
  * The morning report runs over the REAL origin/main files of commit 0bc30d79 (2026-11-16 00:25,
    "Local RT stamp"), read with `git show` through this checkout's object store.

Ported from the round-2d reviewers' tests (assertions turned to the fixed behaviour):
  * review/enrich-ops-verify/tests/test_eo5_verify.py -> test_eo5_no_hosting_once_the_phase_time_is_used_up
  * review/tests-verify/wt/tests/test_verify_tp_preorders.py, enrichment side of v01a / v01b ->
    test_tp01_enrichment_alone_leaves_a_tracking_buyonly_preorder_to_discovery,
    test_tp01_full_day_discovery_holds_it_and_enrichment_keeps_it_off_the_main_wall;
    its print-only production run (v01c) -> test_tp01_v2_puts_it_on_the_main_wall_no_more_than_production
    (now asserting v2 <= production).

Run: cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_round2e_enrich.py -q -p no:cacheprovider
"""
import copy
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_step1_enrichment import (  # noqa: E402,F401  (nrw is a fixture)
    nrw, _Clock, _two_arrivals_and_a_putback, SUKMA, LEMONADE, PREY, WT, today,
)
from test_step1_preorders import (  # noqa: E402,F401  (_worktree_write_audit: autouse fixture;
    _worktree_write_audit, head_code_root,  # head_code_root: production's pipeline/ at 78303fd6)
    WICKER, TODAY, scenario, run_daily, run_daily_with_code, final, after, only, on_main_wall,
    brief, brief_rec, fixtures, offer, amazon_rent_from, _wicker_buyonly_node, jw_titles,
)


# =============================================================================================
# EO-5: trailer hosting after enrichment's saves
# =============================================================================================

def _yt(mid):
    return f'https://www.youtube.com/watch?v=TEST{int(mid):07d}'


def _give_trailers(nrw, *mids):
    """Each film's wall entry gets a YouTube trailer and no hosted copy (what hosting looks for)."""
    for mid in mids:
        links = dict(nrw.wall()[mid].get('links') or {})
        links['trailer'] = _yt(mid)
        links.pop('trailer_hosted', None)
        nrw.edit_wall_entry(mid, links=links)


class _Phase:
    """One enrichment phase (generate_data.py --enrich) with a controllable clock inside
    pipeline/enricher.py and a recording trailer host. `hosting_minutes`: how long each hosting
    call takes on that clock (a yt-dlp download + B2 upload)."""

    def __init__(self, nrw, monkeypatch, hosting_minutes=0.0):
        import pipeline.enricher as enricher_mod
        self.nrw = nrw
        self.clock = _Clock(enricher_mod.time)
        monkeypatch.setattr(enricher_mod, 'time', self.clock)
        self.hosting_minutes = hosting_minutes
        self.hosted = []                 # (title, clock minutes when the call started)
        self.purge_at = []               # clock minutes at each disk purge (no-argument call)
        self.on_details = {}             # film id -> clock minutes to jump to at its TMDB fetch
        self.at_enrichment_save = None   # clock minutes to jump to at the data.json save
        self.gen = None

    def minutes(self):
        return self.clock.offset / 60.0

    def run(self):
        g = self.nrw.new_generator()
        self.gen = g
        phase = self
        real_details, real_save, real_purge = g.get_movie_details, g._safe_save_data_json, g.purge_removed_movies

        def details(movie_id):
            if str(movie_id) in phase.on_details:
                phase.clock.offset = phase.on_details[str(movie_id)] * 60.0
            return real_details(movie_id)

        def save(display_data, movies, label=None, **kw):
            if label == 'enrichment' and phase.at_enrichment_save is not None:
                phase.clock.offset = phase.at_enrichment_save * 60.0
            return real_save(display_data, movies, label=label, **kw)

        def purge(movies_list=None):
            if movies_list is None:
                phase.purge_at.append(phase.minutes())
            return real_purge(movies_list)

        def host(movie_id, title, year, url):
            phase.hosted.append((title, round(phase.minutes(), 2)))
            phase.clock.offset += phase.hosting_minutes * 60.0
            return None                          # nothing hosted (a failed download)

        def trailer(details_):
            mid = str((details_ or {}).get('id', ''))
            return (_yt(mid), 'test') if mid else None

        g.get_movie_details = details
        g._safe_save_data_json = save
        g.purge_removed_movies = purge
        g.host_trailer_for_movie = host
        g.find_trailer_url = trailer             # enrichment finds each film's YouTube trailer
        return g.enrich_newly_available_movies()

    def hosted_titles(self):
        return [t for t, _ in self.hosted]


def _metrics(nrw):
    with open(nrw.root / 'metrics' / 'enrichment_run.json') as f:
        return json.load(f)


def test_eo5_no_hosting_once_the_phase_time_is_used_up(nrw, monkeypatch, capsys):
    """EO-5 (ported from review/enrich-ops-verify/tests/test_eo5_verify.py). Three films queued
    (Sukma and Lemonade Blessing new today, Prey of Wrath put back today), each with a YouTube
    trailer and no hosted copy. The loop's clock jumps 3 hours past its start during the first
    film, so the loop stops at its 50-minute limit with two films unreached. The orchestrator
    kills --enrich at 60 minutes: hosting must not start (it has no clock of its own in 2d), so
    the disk purge and metrics/enrichment_run.json that follow it still get written.
    Without the fix (2d): hosting ran for all three films -- two of them never enriched -- each a
    yt-dlp download + B2 upload with no time check, past the kill."""
    _two_arrivals_and_a_putback(nrw)
    _give_trailers(nrw, SUKMA, LEMONADE, PREY)
    p = _Phase(nrw, monkeypatch)
    p.on_details[SUKMA] = 180              # 3 hours: the 50-minute stop fires at the next film
    capsys.readouterr()

    p.run()

    out = capsys.readouterr().out
    assert 'Enrichment phase passed 50 min' in out, 'setup: the loop time stop did not fire'
    assert p.hosted == [], f'trailer hosting ran after the phase time was used up: {p.hosted}'
    assert "Trailer hosting: the phase's time is used up" in out
    assert p.purge_at, 'the disk purge did not run'
    m = _metrics(nrw)
    assert any(d.get('reason') == 'loop_timeout' for d in m['deferred_details'])
    assert nrw.lane(PREY) == 'HIDDEN', 'setup: the unreached put-back should wait hidden'


def test_eo5_hosting_only_for_films_the_loop_processed(nrw, monkeypatch, capsys):
    """EO-5. The same three films; the loop's clock reads 51 minutes once Sukma is fetched, so
    the loop stops after Sukma (Lemonade Blessing and the put-back Prey of Wrath are left for the
    next run; Prey waits hidden for its JustWatch check). Hosting still has time (51 < 55): it
    may host only what this run enriched -- Sukma.
    Without the fix (2d): hosting looped over the whole queue, so it downloaded trailers for the
    two films the loop never reached (one of them a put-back hidden as unconfirmed)."""
    _two_arrivals_and_a_putback(nrw)
    _give_trailers(nrw, SUKMA, LEMONADE, PREY)
    p = _Phase(nrw, monkeypatch)
    p.on_details[SUKMA] = 51
    capsys.readouterr()

    p.run()

    out = capsys.readouterr().out
    assert 'Enrichment phase passed 50 min' in out and '2 remaining movies' in out, 'setup'
    assert p.hosted_titles() == ['Sukma'], f'hosted: {p.hosted}'
    assert nrw.lane(PREY) == 'HIDDEN' and nrw.wall()[PREY]['_jw_unconfirmed'] == today()


def test_eo5_removed_and_reverted_films_in_a_stale_queue_get_no_hosting(nrw, monkeypatch, capsys):
    """EO-5 / owner rule 5. A stale metrics/newly_available.json (discovery did not rewrite it)
    still lists Sukma, Lemonade Blessing and Prey of Wrath. Since then the owner REMOVED Lemonade
    Blessing (tracking 'removed', the admin Remove's fields; its wall entry outlived the Remove --
    a stale write put it back) and REVERTED Prey of Wrath (putback.owner_revert +
    revert_wall_entry: hidden, waiting to come out). Enrichment skips both, the end-of-run purge
    drops both entries, and no trailer is hosted for either.
    Without the fix (2d): the hosting loop took every queued film still in data.json, so it
    hosted trailers for the removed title and the reverted one (time and B2 space for films the
    same run then purged)."""
    from pipeline import putback
    _two_arrivals_and_a_putback(nrw)
    _give_trailers(nrw, SUKMA, LEMONADE, PREY)
    lem = nrw.track(LEMONADE)
    lem.update({'status': 'removed', 'removed_from_wall': True, 'removed_at': f'{today()}T08:00:00',
                'removed_date': today(), 'removed_reason': 'manual_removal'})   # admin/routes/movies.py remove_movie
    nrw.put_track(LEMONADE, lem)
    prey = nrw.track(PREY)
    assert putback.owner_revert(prey) is True
    nrw.put_track(PREY, prey)
    data = json.load(open(nrw.root / 'data.json'))
    assert putback.revert_wall_entry(data, PREY)
    with open(nrw.root / 'data.json', 'w') as f:
        json.dump(data, f)
    queue = json.load(open(nrw.root / 'metrics' / 'newly_available.json'))['movie_ids']
    assert queue == [SUKMA, LEMONADE, PREY], 'setup: the stale queue'
    p = _Phase(nrw, monkeypatch)
    capsys.readouterr()

    p.run()

    out = capsys.readouterr().out
    assert 'removed by the owner, skipping' in out and 'sent back by the owner' in out, 'setup'
    assert p.hosted_titles() == ['Sukma'], f'hosted: {p.hosted}'
    assert LEMONADE not in nrw.wall() and PREY not in nrw.wall(), 'the purge did not drop them'
    assert nrw.track(LEMONADE)['status'] == 'removed'
    assert nrw.track(PREY)['status'] == 'tracking' and nrw.track(PREY).get('_reverted_by_owner')


def test_eo5_hosting_starts_nothing_past_55_minutes_so_purge_and_metrics_beat_the_kill(nrw, monkeypatch, capsys):
    """EO-5. A heavy day: the loop enriches all three films and the data.json save lands at
    50 minutes into the phase. Each trailer download + upload takes 4 minutes. Hosting may not
    START a film after 55 minutes (constants.ENRICHMENT_LOOP_TIMEOUT_MINUTES + 5): it hosts at
    50 and 54, then stops, so the disk purge and metrics/enrichment_run.json land at 58 minutes,
    before the orchestrator's 60-minute kill (daily_orchestrator.py, timeout=3600).
    Without the fix (2d): hosting had no clock -- the third download started at 58 and the purge
    and metrics would have run at 62 minutes, after the kill (lost)."""
    _two_arrivals_and_a_putback(nrw)
    p = _Phase(nrw, monkeypatch, hosting_minutes=4)
    p.at_enrichment_save = 50
    capsys.readouterr()

    p.run()

    out = capsys.readouterr().out
    assert [t for t, _ in p.hosted] == ['Sukma', 'Lemonade Blessing'], f'hosted: {p.hosted}'
    assert all(started <= 55 for _, started in p.hosted), p.hosted
    assert "Trailer hosting: the phase's time is used up" in out
    assert p.purge_at and p.purge_at[0] < 60, f'disk purge at {p.purge_at} minutes'
    assert _metrics(nrw)['enrichment_duration_seconds'] < 3600


# =============================================================================================
# TP-01: enrichment's catch-up and a pre-order that is buy-only by its TRACKING record
# =============================================================================================
# Wicker (1195803, real 78303fd6 records): tracking says buy-only pre-order (_buyonly_preorder,
# _type4_pending, status 'tracking'); its wall entry is a PRE-ORDER entry WITHOUT the buy-only flag
# (the same mismatch on origin/main for Wicker and The Social Reckoning). It has an Amazon
# pre-order link in watch_links.vod.

APPLE_WICKER = 'https://tv.apple.com/us/movie/wicker/umc.cmc.verify'
PREORDER_PAGE = 'Wicker  Available to pre-order. Releases soon. Pre-order HD $19.99'
LIVE_PAGE = 'Wicker  Rent now $19.99  Buy now $24.99'


def _apple_rent(start='2026-10-23T07:00:00Z', created='2026-11-14T07:00:00Z'):
    """SYNTHETIC (as in the reviewer's v01 tests): an Apple TV Store RENT whose offer start is
    Wicker's theatrical date -- Apple's store lists rentals from the theater opening
    (pipeline/justwatch.py), so it proves nothing about today."""
    return offer('RENT', 'Apple TV Store', 'itunes', APPLE_WICKER, '$19.99', start, created)


def _type4(day):
    """TMDB moves Wicker's US digital date to `day` (it really moved 12-01 -> 11-24 on main)."""
    return dict(fixtures()['tmdb'][WICKER], release_dates={'id': int(WICKER), 'results': [
        {'iso_3166_1': 'US', 'release_dates': [{'type': 4, 'release_date': f'{day}T00:00:00.000Z', 'note': ''}]}]})


def _wicker_with(*extra):
    node = _wicker_buyonly_node()
    node['offers'].extend(extra)
    return node


def test_tp01_enrichment_alone_leaves_a_tracking_buyonly_preorder_to_discovery(tmp_path):
    """TP-01, enrichment side of the reviewer's v01a. Wicker's date (wall and tracking) is today;
    JustWatch lists its Fandango purchase and an Apple TV Store rental whose offer start is the
    theatrical date. Only enrichment runs. Its catch-up must leave Wicker to discovery's daily
    buy-only check (tracking says buy-only), so it stays a PRE-ORDER, still waiting in tracking.
    Without the fix (2d): catch-up read only the wall entry's flag, queued Wicker as an ordinary
    past-date pre-order, its JustWatch pre-check saw a rental, cleared the pre-order flag and put
    it on the MAIN wall dated today -- on a store's pre-order listing (rules 2 and 3)."""
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_with(_apple_rent())},
                    phases=('enrich',), tracking_over={WICKER: {'digital_date': TODAY}},
                    wall_over={WICKER: {'digital_date': TODAY}})
    assert spec['tracking'][WICKER]['_buyonly_preorder'] is True
    assert not [w for w in spec['wall'] if str(w.get('id')) == WICKER][0].get('_buyonly_preorder')
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert not on_main_wall(entry) and entry.get('_is_preorder'), (brief(entry), brief_rec(rec))
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)
    assert 'Wicker' not in jw_titles(res, 'enrich'), 'enrichment checked it instead of leaving it to discovery'


@pytest.mark.parametrize('page', ['apple_page_reads_preorder', 'pages_unreadable', 'apple_page_reads_available'])
def test_tp01_full_day_discovery_holds_it_and_enrichment_keeps_it_off_the_main_wall(page, tmp_path):
    """TP-01, enrichment side of the reviewer's v01b. TMDB moves Wicker's digital date to today;
    JustWatch lists its Fandango purchase and an Apple TV Store rental (offer start = theatrical
    date). Discovery runs its buy-only check: the Apple page reads "Pre-order" (or can't be read),
    so it keeps Wicker waiting and records today as a "not out yet" day. Enrichment, the same
    morning, must not put it on the main wall (rule 3: never dated on a day a check proved it
    unavailable). Control: when the Apple page reads "available", discovery graduates it and
    enrichment keeps it on the main wall, dated today.
    Without the fix (2d): enrichment's catch-up graduated it anyway -- on the main wall dated the
    very day discovery had just proven it not out ('pre-order flag cleared (date passed, no longer
    buy-only)')."""
    pages = {'apple_page_reads_preorder': [('tv.apple.com', PREORDER_PAGE)],
             'pages_unreadable': [],
             'apple_page_reads_available': [('tv.apple.com', LIVE_PAGE)]}[page]
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_with(_apple_rent())},
                    tmdb_over={WICKER: _type4(TODAY)}, pages=pages, phases=('discover', 'enrich'))
    res = run_daily(spec, str(tmp_path / 'sbx'))
    d_rec = after(res, 'discover')['tracking'][WICKER]
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    # Round 2f+: TMDB's digital date (today) has arrived and stores list it -> out by the pre-order
    # labeler when the page can't be read too; only a page reading 'Pre-order' still holds it.
    if page in ('apple_page_reads_available', 'pages_unreadable'):
        assert d_rec['status'] == 'available', brief_rec(d_rec)
        assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
        return
    assert d_rec['status'] == 'tracking' and d_rec.get('_jw_last_refuted') == TODAY, \
        f'setup: discovery should hold it: {brief_rec(d_rec)}'
    assert not on_main_wall(entry), f'on the main wall the day discovery held it: {brief(entry)} {brief_rec(rec)}'
    assert entry.get('_is_preorder') and rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), \
        (brief(entry), brief_rec(rec))


def test_tp01_the_skip_does_not_starve_a_genuine_release(tmp_path):
    """TP-01 fix risk: the catch-up now leaves such a film to discovery -- it must not be
    starved. Day 1 (11-14, TMDB's date): JustWatch lists Apple's rental only and its page reads
    "Pre-order": discovery holds Wicker, enrichment leaves it a pre-order. Day 2 (11-15): Amazon's
    rental goes live (offer start 11-15): discovery graduates it, enrichment confirms it -- on the
    main wall, dated 11-15, the day it came out (rules 1 and 3).
    Without the fix (2d): day 1 already fails -- enrichment put it on the main wall dated 11-14,
    the day discovery proved it not out. The day-2 half guards the fix's trade-off (the genuine
    release is not starved)."""
    live = _wicker_with(_apple_rent(), amazon_rent_from('B0WICKERVERIFY', '2026-11-15T05:00:00Z',
                                                       created='2026-11-15T05:00:00Z', price='$19.99'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_with(_apple_rent())},
                    tmdb_over={WICKER: _type4(TODAY)},
                    pages=[('tv.apple.com', PREORDER_PAGE), ('amazon.com', LIVE_PAGE)],
                    jw_days={'2026-11-15': {WICKER: live}},
                    phases=[(TODAY, 'discover'), (TODAY, 'enrich'),
                            ('2026-11-15', 'discover'), ('2026-11-15', 'enrich')])
    res = run_daily(spec, str(tmp_path / 'sbx'))
    day1 = after(res, 'enrich', TODAY)
    assert not on_main_wall(only(day1['wall'][WICKER])), brief(only(day1['wall'][WICKER]))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-11-15', brief_rec(rec)
    assert on_main_wall(entry) and entry['digital_date'] == '2026-11-15', brief(entry)


def test_tp01_v2_puts_it_on_the_main_wall_no_more_than_production(head_code_root, tmp_path):
    """Regression bar (v2 must not put more not-yet-out films on the main wall than production):
    the reviewer's v01b day (Apple page reads "Pre-order"), the full daily order discover ->
    enrich -> gap fill, run under production's pipeline (78303fd6, in a subprocess) and under
    this tree. Wherever v2 shows Wicker on the main wall, production must too. (Production puts
    it there through the gap fill, dated 10-24 -- the round-2d skeptic's v01c; v2 keeps it a
    pre-order through all three phases.)"""
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: _wicker_with(_apple_rent())},
                    tmdb_over={WICKER: _type4(TODAY)}, pages=[('tv.apple.com', PREORDER_PAGE)],
                    phases=('discover', 'enrich', 'gap_fill'))
    v2 = only(final(run_daily(copy.deepcopy(spec), str(tmp_path / 'v2')))['wall'][WICKER])
    prod = only(final(run_daily_with_code(head_code_root, spec, str(tmp_path / 'prod')))['wall'][WICKER])
    assert not on_main_wall(v2), brief(v2)
    assert on_main_wall(v2) <= on_main_wall(prod), (brief(v2), brief(prod))


# =============================================================================================
# The morning report: a reverted reissue in the "sent back by you, still waiting" list
# =============================================================================================

ORIGIN_MAIN = '0bc30d79'      # origin/main on 2026-11-16 00:25 (-0800)
TEKKONKINKREET = '13754'      # real reissue on the wall ('20th Anniversary', _reissue True)


def _git_show(path):
    return subprocess.check_output(['git', '-C', WT, 'show', f'{ORIGIN_MAIN}:{path}'])


@pytest.fixture
def real_checkout(tmp_path, monkeypatch):
    """A tmp copy of origin/main's data.json, movie_tracking.json and the metrics the morning
    report reads (CI's 2026-11-15 run), with the cwd there."""
    root = tmp_path / 'real'
    (root / 'metrics').mkdir(parents=True)
    for rel in ('data.json', 'movie_tracking.json', 'metrics/discovery_run.json',
                'metrics/enrichment_run.json'):
        (root / rel).write_bytes(_git_show(rel))
    monkeypatch.chdir(root)
    return root


def _morning_report_module():
    import importlib
    import signal
    scripts = os.path.join(WT, 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    old = signal.getsignal(signal.SIGPIPE)
    try:
        mod = importlib.import_module('morning_report')
    finally:
        signal.signal(signal.SIGPIPE, old)
    assert os.path.realpath(mod.__file__).startswith(os.path.realpath(WT)), mod.__file__
    return mod


def _revert_in_real_tracking(root, mid, on_day, **edits):
    """The owner reverts a real film on `on_day` (putback.owner_revert, the code path of the admin
    button and scripts/revert_movie.py); `edits` stand for later runs' changes."""
    from pipeline import putback
    path = root / 'movie_tracking.json'
    trk = json.loads(path.read_text())
    rec = trk['movies'][mid]
    assert putback.owner_revert(rec, today=on_day) is True
    rec.update(edits)
    path.write_text(json.dumps(trk))
    return rec


def test_morning_report_names_a_reverted_reissue_as_a_reissue_on_real_data(real_checkout):
    """REV-1's report wording, on origin/main's real files (CI's 2026-11-15 run). The owner sent
    back two real wall films on 11-08: Tekkonkinkreet, a reissue ('20th Anniversary'), and Rose of
    Nevada, an ordinary release. A week later neither has come back. The report must tell the
    owner the reissue will NOT come back by itself (JustWatch lists the original film; re-add it
    when the restoration is out), and keep the ordinary wording for the other film.
    Without the fix (2d): the reissue read "waiting 7 days, nothing new on JustWatch" -- as if
    JustWatch were still checking it, when discovery no longer even looks it up."""
    ROSE = '1399525'
    _revert_in_real_tracking(real_checkout, TEKKONKINKREET, '2026-11-08')
    _revert_in_real_tracking(real_checkout, ROSE, '2026-11-08')
    mr = _morning_report_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mr.overnight()
    out = buf.getvalue()
    lines = {mid: [ln for ln in out.splitlines() if ln.strip().startswith('•') and title in ln]
             for mid, title in ((TEKKONKINKREET, 'Tekkonkinkreet'), (ROSE, 'Rose of Nevada'))}
    # Owner, Nov 2026: a reverted reissue is checked daily like any reverted film -- both read
    # the same, information only (nothing to re-add).
    assert 'Sent back by you, still waiting: 2' in out, out[-2500:]
    tek, rose = lines[TEKKONKINKREET], lines[ROSE]
    assert len(tek) == 1 and 'sent back 2026-11-08' in tek[0] and 'nothing new on JustWatch' in tek[0], tek
    assert len(rose) == 1 and 'waiting 7 days, nothing new on JustWatch' in rose[0], rose
    assert 're-add' not in out, out[-2500:]
