#!/usr/bin/env python3
"""
Round 2e -- the pre-order / buy-only changes, proved end to end.

Covers the round-2d review findings fixed in round 2e:
  PO-3   discovery's provider path keeps a buy-only pre-order waiting while JustWatch still shows it
         for purchase only, even when TMDB lists a rental or stream (it was the nightly loop: on the
         wall, flagged back by enrichment, on again). An owner override (False) or a store page
         reading "available" still lets a genuine buy-only release through.
  PO-4   Amazon's robot check (CAPTCHA) is an unreadable page, not a "Pre-order" reading: the film
         is held that run but no "not out yet" day is recorded for a film already held; the daily
         buy-only check answers "no answer today" (None).
  TP-01  the gap fill and enrichment's catch-up treat a film as buy-only when its wall entry OR its
         tracking record says so (Wicker and The Social Reckoning disagree on main).
  TP-02  the gap fill reads the store page before graduating a pre-order on a rental: a page still
         reading "Pre-order" keeps it a pre-order (a "not out yet" day in tracking; none on a CAPTCHA).
  TP-03  the gap fill leaves a held film to discovery.
  TP-07  the gap fill's dating: a still-'tracking' pre-order and a 'coming soon' one are dated today;
         a film tracking already had out keeps its old date; a gap-fill buy-only flag is dated the
         day its rental goes live.
  e1b    the DVD-only (Barnes & Noble) shape is no longer on the main wall after discovery, and at no
         point of the day more than production.

Ported (with the fixed behaviour asserted) from the round-2d skeptics' files:
  review/tests-verify/wt/tests/test_verify_tp_preorders.py  (v01a, v01b, v01d, v02, v03, v07a-d)
  review/preorders-verify/wt/tests/test_verify_po.py         (po3 / fix_po3, po4 / fix_po4)

How the tests run: the test_step1_preorders.py harness -- the REAL daily phases (discovery,
enrichment, gap fill, each a fresh DataGenerator) in a throw-away sandbox, only the network (TMDB,
JustWatch, store pages) and the clock faked, every write into the worktree refused. Records are
REAL (git show 78303fd6 via the harness fixtures, or `git show origin/main:` below, verbatim);
JustWatch nodes and store pages are STAGED where a test says so (each says what).

Run:  cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_round2e_preorders.py -q -p no:cacheprovider
"""
import copy
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step1_preorders as tsp  # noqa: E402
from test_step1_preorders import (  # noqa: E402,F401  (fixtures: write audit, production code, e cache)
    _worktree_write_audit, head_code_root, e_root, _e_results, _MISSING,
    TODAY, WICKER, GALAXYMPHONY, TOM_AND_JERRY, LIBERATION, LIBERATION_TMDB,
    scenario, two_days, run_daily, run_daily_with_code, final, after, only, on_main_wall, in_preorder_lane,
    brief, brief_rec, fixtures, offer, jw_node, amazon_rent, amazon_rent_from, amazon_preorder_rent,
    netflix_stream, jw_titles, _wicker_buyonly_node, _lib_spec, _lib_node, pipeline_sandbox, Patcher,
)

# Store pages as the page check reads them (its own signal words). STAGED.
PREORDER_PAGE = 'Available to pre-order. Releases soon. Pre-order HD $19.99'
LIVE_PAGE = 'Rent now $19.99  Buy now $24.99'
CAPTCHA_PAGE = ('Enter the characters you see below. Sorry, we just need to make sure you are not a robot. '
                'Type the characters you see in this image: captcha')

OLMO, MARBLE_HALL, LAST_KISS = '1212934', 'tv_283319', '1318467'

# Real records: `git show origin/main:movie_tracking.json` / `:data.json` (0bc30d79, 2026-11-16),
# verbatim. Olmo: a dateless buy-only pre-order (TMDB lists an Apple TV Store rental, JustWatch a
# Fandango purchase). Marble Hall Murders: a limited series production transitions every night
# (TMDB lists a PBS Masterpiece Amazon Channel stream, the stores sell it). The Last Kiss: a buy-only
# pre-order production transitions every night through its past TMDB digital date.
MAIN = json.loads(r'''
{"1212934": {"tracking": {"_buyonly_preorder": true, "_discovery_source": "provider_availability_check", "_transitioned_at": "2026-08-09", "enriched": true, "enrichment_date": "2026-08-09", "festival": "Berlin/Berlinale", "first_seen": "2026-01-06", "has_providers": true, "intake_pass": "C", "providers": {"buy": [], "rent": ["Apple TV Store"], "streaming": []}, "status": "available", "title": "Olmo", "year": 2025}, "wall": {"_buyonly_preorder": true, "_discovered_at": "2026-08-09T08:34:51.036082", "_discovery_source": "provider_availability_check", "_enrichment_attempts": 1, "_enrichment_status": "completed", "_imdb_votes": 274, "_is_preorder": true, "_last_enrichment_attempt": "2026-08-09", "_minimal_entry": false, "_needs_review": false, "_reissue": false, "_slop_confidence": "weak", "_slop_reason": "score:1(mid_imdb)", "_tmdb_fetch_failed": false, "_trailer_source": "gemini_playwright", "_watch_links_verified": "2026-08-10T09:36:18.971801", "_wiki_language_count": 3, "bootstrap_date": false, "budget": 0, "country": "United States of America", "crew": {"cast": ["Aivan Uttapa", "Gustavo Sánchez Parra", "Diego Olmedo", "Andrea Suarez Paz", "Rosa Armendariz"], "director": "Fernando Eimbcke"}, "digital_date": "", "display_title": "Olmo", "featured": false, "filters": {"auto_categorized": true, "is_documentary": false, "is_foreign": false, "is_indie": true, "is_restoration": false, "is_series": false, "is_staff_pick": false, "is_virtual_screening": false, "manual_override": null}, "genres": ["Comedy", "Drama"], "id": "1212934", "imdb_rating": "6.2", "keywords": ["coming of age", "house party", "teenage boy", "1980s", "multiple sclerosis"], "letterboxd_score": "3.5", "links": {"cast_wiki": {"Gustavo Sánchez Parra": "https://en.wikipedia.org/wiki/Gustavo_S%C3%A1nchez_Parra"}, "director_wiki": "https://en.wikipedia.org/wiki/Fernando_Eimbcke", "imdb": "https://www.imdb.com/title/tt30441926/", "justwatch": "https://www.justwatch.com/us/movie/olmo", "letterboxd": "https://letterboxd.com/film/olmo", "metacritic": "https://www.metacritic.com/movie/olmo/", "rt": "https://www.rottentomatoes.com/m/olmo", "trailer": "https://www.youtube.com/watch?v=vIjTz_UFKxM", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1212934.mp4", "wikipedia": "https://en.wikipedia.org/wiki/Olmo_(film)"}, "manually_corrected": false, "metacritic_score": "78", "original_language": "en", "original_title": "Olmo", "poster": "https://image.tmdb.org/t/p/w500/zPVWOGE2kSU7GjGNazkdwhkq6Yn.jpg", "pre_order_links": [{"buy_price": "$14.99", "link": "https://athome.fandango.com/content/browse/details/Olmo/5004043", "price": "$14.99", "service": "Fandango At Home"}], "providers": {"buy": [], "rent": ["Apple TV Store"], "streaming": []}, "reissue_label": null, "rt_score": "95%", "runtime": 84, "status": "available", "studio": "Plan B Entertainment", "synopsis": "When Olmo gets invited to a party by his beautiful neighbor, he will do whatever he can to meet up with her, embarking on a night of laughs and chaos.", "title": "Olmo", "watch_links": {}, "year": 2026}}, "1318467": {"tracking": {"_buyonly_preorder": true, "_discovery_source": "tmdb_type4", "_transitioned_at": "2026-11-15", "enriched": true, "enrichment_date": "2026-11-15", "has_providers": true, "intake_date": "2026-09-15", "intake_pass": "A", "is_slop": true, "providers": {"buy": [], "rent": [], "streaming": []}, "status": "tracking", "title": "The Last Kiss", "year": 2026}, "wall": {"_buyonly_preorder": true, "_digital_date_source": "tmdb_type4", "_discovered_at": "2026-09-15T13:16:03.790471", "_discovery_source": "tmdb_type4", "_enrichment_attempts": 60, "_enrichment_gaps": ["watch_links", "rt_score", "metacritic_score"], "_enrichment_status": "completed", "_imdb_votes": 1399, "_is_preorder": true, "_last_enrichment_attempt": "2026-11-15", "_minimal_entry": false, "_needs_review": false, "_reissue": false, "_slop_confidence": "weak", "_slop_reason": "score:5(no_rt,no_imdb,no_rt_link)", "_tmdb_fetch_failed": false, "_trailer_source": "gemini_playwright", "_watch_links_verified": "2026-10-15T14:08:59.822398", "_wiki_language_count": 1, "bootstrap_date": false, "budget": 0, "country": "United States of America", "crew": {"cast": ["Mckenna Grace", "Arkira Chantaratananond", "Jaden Michael", "Riley Davis", "Bergman Freedman"], "director": "Yoko Okumura"}, "digital_date": "2026-09-15", "display_title": "The Last Kiss", "featured": false, "filters": {"auto_categorized": true, "is_documentary": false, "is_foreign": false, "is_indie": false, "is_restoration": false, "is_series": false, "is_staff_pick": false, "is_virtual_screening": false, "manual_override": null}, "genres": ["Horror", "Mystery"], "id": "1318467", "imdb_rating": "5.3", "is_slop": true, "keywords": ["supernatural", "kiss", "premonition", "murder", "curse", "serial killer", "slasher", "death", "traumatic experience", "supernatural horror", "teen horror"], "letterboxd_score": "2.8", "links": {"cast_wiki": {"Jaden Michael": "https://en.wikipedia.org/wiki/Jaden_Michael", "Mckenna Grace": "https://en.wikipedia.org/wiki/Mckenna_Grace"}, "director_wiki": "https://en.wikipedia.org/wiki/Yoko_Okumura", "imdb": "https://www.imdb.com/title/tt33253206/", "justwatch": "https://www.justwatch.com/us/movie/the-last-kiss-2026", "letterboxd": "https://letterboxd.com/film/the-last-kiss-2026", "rt": "https://www.rottentomatoes.com/m/the_last_kiss_2026", "trailer": "https://www.youtube.com/watch?v=lAKtuOVkAgU", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1318467.mp4", "wikipedia": "https://en.wikipedia.org/wiki/The_Last_Kiss_(2026_film)"}, "manually_corrected": false, "original_language": "en", "original_title": "The Last Kiss", "poster": "https://image.tmdb.org/t/p/w500/cLZ7iFZc25vluSIKt3XtdSTait4.jpg", "pre_order_links": [{"buy_price": "$9.99", "link": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d0d60f8f-df47-4ced-9c9a-0c404e4c6b86&tag=nrw04-20", "price": "$9.99", "service": "Amazon Video"}, {"buy_price": "$14.99", "link": "https://tv.apple.com/us/movie/the-last-kiss/umc.cmc.6bw1vbnfegm9gsk49clrthmcs?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6808888910", "price": "$14.99", "service": "Apple TV Store"}, {"buy_price": "$14.99", "link": "https://athome.fandango.com/content/browse/details/The-Last-Kiss/5090572", "price": "$14.99", "service": "Fandango At Home"}], "providers": {"buy": [], "rent": [], "streaming": []}, "reissue_label": null, "rt_score": null, "runtime": 97, "status": "available", "studio": "Man in a Tree Productions", "synopsis": "A young woman discovers she can foresee the death of anyone she kisses, and when a vision predicts her crush will die in a murder spree targeting her closest friends, she races to uncover the killer before more lives are lost.", "title": "The Last Kiss", "watch_links": {}, "year": 2026}}, "tv_283319": {"tracking": {"_buyonly_preorder": true, "_discovery_source": "provider_availability_check", "_transitioned_at": "2026-11-15", "content_type": "limited_series", "enriched": true, "enrichment_date": "2026-11-15", "episode_count": 6, "first_air_date": "2026-09-06", "genres": ["Mystery", "Crime"], "has_providers": true, "intake_date": "2026-09-06", "networks": ["BBC One"], "original_language": "en", "poster": "https://image.tmdb.org/t/p/w500/yEKMdxsXLqwcTTkGcqK4gqyW2bw.jpg", "providers": {"buy": ["Amazon Video", "Apple TV Store", "Google Play Movies", "Fandango At Home"], "rent": [], "streaming": ["PBS Masterpiece Amazon Channel"]}, "runtime": null, "status": "tracking", "synopsis": "Returning to England, Susan Ryeland is reluctantly drawn into a new Atticus Pünd mystery, this time written by a new, young writer. 'Pünd’s Last Case\" is a story set in 1955, in an exotic villa in Corfu – but the identity of a real killer is hidden in the text, and once again Susan is going to find herself in grave danger.", "title": "Marble Hall Murders", "tmdb_id": 283319}, "wall": {"_buyonly_preorder": true, "_digital_date_source": "first_air_date", "_discovered_at": "2026-09-09T12:50:40.130009", "_discovery_source": "provider_availability_check", "_enrichment_attempts": 66, "_enrichment_gaps": ["watch_links", "wikipedia", "metacritic_score", "letterboxd_score"], "_enrichment_status": "completed", "_imdb_votes": 1758, "_is_preorder": true, "_last_enrichment_attempt": "2026-11-15", "_minimal_entry": false, "_needs_review": false, "_reissue": false, "_slop_confidence": "weak", "_slop_reason": "score:1(no_wiki,good_imdb)", "_tmdb_fetch_failed": false, "_trailer_source": "gemini_playwright", "bootstrap_date": false, "budget": 0, "content_type": "limited_series", "country": "GB", "crew": {"cast": ["Lesley Manville", "Tim McMullan", "Luke Lambert", "Harry Lloyd", "Rupert Penry-Jones"], "director": "Rebecca Gatward"}, "display_title": "Marble Hall Murders", "episode_count": 6, "featured": false, "filters": {"auto_categorized": true, "is_documentary": false, "is_foreign": false, "is_indie": false, "is_restoration": false, "is_series": true, "is_staff_pick": false, "is_virtual_screening": false, "manual_override": null}, "genres": ["Mystery", "Crime"], "id": "tv_283319", "imdb_rating": "7.6", "keywords": ["based on novel or book", "miniseries"], "letterboxd_score": null, "links": {"cast_wiki": {"Lesley Manville": "https://en.wikipedia.org/wiki/Lesley_Manville", "Tim McMullan": "https://en.wikipedia.org/wiki/Tim_McMullan"}, "imdb": "https://www.imdb.com/title/tt35617054/", "justwatch": "https://www.justwatch.com/us/tv-show/marble-hall-murders", "rt": "https://www.rottentomatoes.com/tv/marble_hall_murders", "trailer": "https://www.youtube.com/watch?v=DMCyCJoxgTY", "wikipedia": null}, "manually_corrected": false, "networks": ["BBC One"], "original_language": "en", "original_title": "Marble Hall Murders", "poster": "https://image.tmdb.org/t/p/w500/3WfgRJBIaOTsiu2bQO23xWb08ro.jpg", "pre_order_links": [{"buy_price": "$14.99", "link": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d58dd31a-ca11-4434-81af-635f331a53a3&tag=nrw04-20", "price": "$14.99", "service": "Amazon Video"}, {"buy_price": "$14.99", "link": "https://tv.apple.com/us/show/marble-hall-murders/umc.cmc.6lfobc88klfqazou78ngpelmz?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv", "price": "$14.99", "service": "Apple TV Store"}, {"buy_price": "$14.99", "link": "https://athome.fandango.com/content/browse/details/Marble-Hall-Murders-Season-1/5172175", "price": "$14.99", "service": "Fandango At Home"}], "providers": {"buy": ["Amazon Video"], "rent": [], "streaming": ["PBS Masterpiece Amazon Channel"]}, "reissue_label": null, "rt_score": "75%", "runtime": null, "status": "available", "studio": "Eleventh Hour Films", "synopsis": "Returning to England, Susan Ryeland is reluctantly drawn into a new Atticus Pünd mystery, this time written by a new, young writer. 'Pünd’s Last Case\" is a story set in 1955, in an exotic villa in Corfu – but the identity of a real killer is hidden in the text, and once again Susan is going to find herself in grave danger.", "title": "Marble Hall Murders", "watch_links": {}, "year": 2026}}}
''')


def _rec(mid):
    return copy.deepcopy(MAIN[mid]['tracking'])


def _entry(mid):
    return copy.deepcopy(MAIN[mid]['wall'])


def _spec(ids, tracking, wall, tmdb, jw, phases, today, pages=(), jw_days=None, jw_outage=None):
    """A harness scenario from explicit records (the harness's own `scenario` only knows its fixtures)."""
    return {'ids': list(ids), 'tracking': tracking, 'wall': wall, 'tmdb': tmdb, 'jw': jw,
            'jw_days': copy.deepcopy(jw_days or {}), 'jw_outage': dict(jw_outage or {}), 'jw_malformed': [],
            'tmdb_fail': [], 'pages': [list(p) for p in pages], 'phases': list(phases), 'today': today,
            'phase_patches': {}}


def _transitions(res, mid):
    """Days on which discovery moved the film to 'available' (stamped `_transitioned_at` that day).
    (Not metrics/newly_available.json: discovery leaves it untouched on a day no film is waiting.)"""
    out = []
    for k, st in res['phases'].items():
        rec = st['tracking'][mid] or {}
        if (k.endswith(':discover') and rec.get('status') == 'available'
                and (rec.get('_transitioned_at') or '')[:10] == k.split(':')[1]):
            out.append(k.split(':')[1])
    return out


def _on_main_at(res, mid):
    """[(phase key, on the main wall?)] after every phase."""
    return [(k, on_main_wall(only(st['wall'][mid]))) for k, st in res['phases'].items()]


def _no_more_on_main_than(v2, head, mid):
    """At every checkpoint, v2 has the film on the main wall only where production does too."""
    worse = [(k, hk) for (k, v), (hk, h) in zip(_on_main_at(v2, mid), _on_main_at(head, mid)) if v and not h]
    return worse


# ==================================================================================================
# PO-3: discovery keeps a buy-only pre-order waiting while JustWatch shows it for purchase only
# ==================================================================================================

def _olmo_node(offers):
    return {'id': 'tm' + OLMO, 'objectId': int(OLMO), 'objectType': 'MOVIE',
            'content': {'title': 'Olmo', 'originalReleaseYear': 2025, 'fullPath': '/us/movie/olmo',
                        'externalIds': {'tmdbId': OLMO}, 'credits': [{'role': 'DIRECTOR', 'name': 'Fernando Eimbcke'}]},
            'offers': offers}


OLMO_FANDANGO = 'https://athome.fandango.com/content/browse/details/Olmo/5004043'   # its real pre_order_link


def _olmo_tmdb():
    """STAGED TMDB for Olmo: minimal details (the harness's Liberation payload renamed), no US release
    dates, and the US Apple TV Store rental its real tracking record lists."""
    details = copy.deepcopy(LIBERATION_TMDB['details'])
    details.update({'id': int(OLMO), 'title': 'Olmo', 'original_title': 'Olmo', 'release_date': '2025-02-15',
                    'credits': {'cast': [], 'crew': [{'job': 'Director', 'name': 'Fernando Eimbcke'}]}})
    return {OLMO: {'details': details, 'release_dates': {'id': int(OLMO), 'results': []},
                   'watch_providers': {'id': int(OLMO), 'results': {'US': {'rent': [
                       {'provider_id': 2, 'provider_name': 'Apple TV Store', 'display_priority': 4}]}}}}}


def _olmo_buy_node():
    """STAGED JustWatch: Olmo's real purchase link (Fandango At Home, $14.99) and nothing else."""
    return _olmo_node([offer('BUY', 'Fandango At Home', 'vudu', OLMO_FANDANGO, '$14.99', None, '2026-08-09T00:00:00Z')])


def _olmo_loop_spec(days, pages=()):
    """The R2D PO-3 shape: Olmo (real records) STAGED as an ordinary main-wall film dated 11-10 that
    the gap fill is about to flag buy-only (JustWatch: a purchase only), while TMDB lists a rental.
    Day 0 runs the gap fill alone, every later day the full daily run."""
    rec = _rec(OLMO)
    rec.pop('_buyonly_preorder', None)
    rec.update({'digital_date': '2026-11-10', '_transitioned_at': '2026-11-10'})
    entry = _entry(OLMO)
    for k in ('_is_preorder', '_buyonly_preorder', 'pre_order_links'):
        entry.pop(k, None)
    entry['digital_date'] = '2026-11-10'
    entry['watch_links'] = {'vod': [{'service': 'Fandango', 'link': OLMO_FANDANGO, 'buy_price': '$14.99'}]}
    phases = [(days[0], 'gap_fill')] + [(d, p) for d in days[1:] for p in ('discover', 'enrich', 'gap_fill')]
    return _spec([OLMO], {OLMO: rec}, [entry], _olmo_tmdb(), {OLMO: _olmo_buy_node()}, phases, days[0], pages=pages)


def test_po3_olmo_gap_fill_flag_no_longer_starts_a_nightly_loop(tmp_path, head_code_root):
    """R2D PO-3 (round 2d sent a gap-fill buy-only flag back to 'tracking'). Olmo's real shape: TMDB
    lists an Apple TV Store rental, JustWatch only a Fandango purchase. 11-14 the gap fill flags it
    a buy-only pre-order; then three full days. Round 2d moved it to 'available' on TMDB's listing
    every night (on the main wall dated that day until enrichment flagged it back: 3 transitions,
    newly 'new' every day). Fixed: JustWatch decides -- no transition on any day, never on the main
    wall at any point (no more than production), still checked on JustWatch in every discovery, and
    each day kept as a "not out yet" day (rule 3: the day it really comes out is the one it gets)."""
    days = ('2026-11-14', '2026-11-15', '2026-11-16', '2026-11-17')
    spec = _olmo_loop_spec(days)
    v2 = run_daily(spec, str(tmp_path / 'v2'))
    head = run_daily_with_code(head_code_root, spec, str(tmp_path / 'prod'))

    gf0 = after(v2, 'gap_fill', days[0])
    assert gf0['tracking'][OLMO]['status'] == 'tracking' and gf0['tracking'][OLMO].get('_buyonly_preorder'), \
        f'precondition: the gap fill flags it: {brief_rec(gf0["tracking"][OLMO])}'
    assert _transitions(v2, OLMO) == [], f'discovery transitioned it on TMDB\'s listing: {_transitions(v2, OLMO)}'
    assert not any(main for _k, main in _on_main_at(v2, OLMO)), _on_main_at(v2, OLMO)
    assert not _no_more_on_main_than(v2, head, OLMO)
    # ... and it stays a VISIBLE pre-order (as production shows it), never an invisible dateless one
    for k, st in v2['phases'].items():
        assert in_preorder_lane(only(st['wall'][OLMO])), f'{k}: {brief(only(st["wall"][OLMO]))}'
    for d in days[1:]:
        rec = after(v2, 'discover', d)['tracking'][OLMO]
        assert 'Olmo' in jw_titles(v2, 'discover', d), f'{d}: not checked on JustWatch'
        assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder') and rec.get('_is_preorder'), brief_rec(rec)
        assert rec.get('_jw_last_refuted') == d and rec.get('_jw_last_checked') == d, brief_rec(rec)
        assert not rec.get('digital_date'), f'{d}: a buy-only day became its date: {brief_rec(rec)}'
    assert 'still a buy-only pre-order' in v2['log']


def _olmo_flagged_spec(phases, pages=()):
    """Olmo exactly as main has it (a dateless buy-only pre-order), back in 'tracking' as round 2d's gap
    fill leaves such a film, so discovery checks it."""
    rec = _rec(OLMO)
    rec['status'] = 'tracking'
    return _spec([OLMO], {OLMO: rec}, [_entry(OLMO)], _olmo_tmdb(), {OLMO: _olmo_buy_node()}, phases, TODAY,
                 pages=pages)


def _set_preorder_override(mid, value):
    """A hook: the owner sets config.yaml preorder_overrides[mid] (in the sandbox's copy)."""
    def hook(day):
        import yaml
        with open('config.yaml') as f:
            cfg = yaml.safe_load(f)
        cfg.setdefault('preorder_overrides', {})[str(mid)] = value
        with open('config.yaml', 'w') as f:
            yaml.safe_dump(cfg, f)
        return True
    return hook


@pytest.mark.parametrize('how', ['store_page_reads_available', 'owner_override_false'])
def test_po3_genuine_buy_only_release_still_graduates(how, tmp_path):
    """The other side of PO-3: a buy-only film that IS out for purchase. Olmo (real records) waiting
    in tracking, TMDB lists its Apple rental, JustWatch shows only the Fandango purchase -- and either
    the Fandango page reads 'Buy now' (STAGED) or the owner set preorder_overrides[Olmo] = false (the
    escape hatch for a verified released buy-only film). The fix must not freeze it: the same check
    enrichment makes lets it through, so it goes on the main wall today and stays there after
    enrichment and the gap fill (rule 1: a wait, never a drop)."""
    if how == 'store_page_reads_available':
        spec = _olmo_flagged_spec(('discover', 'enrich', 'gap_fill'), pages=[('athome.fandango.com', 'Olmo  Buy now $14.99')])
        res = run_daily(spec, str(tmp_path / 'sbx'))
    else:
        spec = _olmo_flagged_spec(('hook:override', 'discover', 'enrich', 'gap_fill'))
        res = run_daily(spec, str(tmp_path / 'sbx'), hooks={'override': _set_preorder_override(OLMO, False)})
    disc = after(res, 'discover')
    assert disc['tracking'][OLMO]['status'] == 'available' and _transitions(res, OLMO) == [TODAY], \
        brief_rec(disc['tracking'][OLMO])
    entry = only(final(res)['wall'][OLMO])
    # Dated the day it became watchable: its first JustWatch offer record (2026-08-09 in these
    # records), not the day the check noticed (rule 3; Olmo really was out since August).
    assert on_main_wall(entry) and entry['digital_date'] == '2026-08-09', brief(entry)
    assert 'still a buy-only pre-order' not in res['log']


def test_po3_galaxymphony_real_loop_ends_over_three_days(tmp_path, head_code_root):
    """Galaxymphony (real 78303fd6 records): a buy-only pre-order TMDB lists on an Amazon-channel
    stream NRW skips, while JustWatch shows only a Barnes & Noble DVD. Production moved it to
    'available' every night 11-02..11-15 (metrics/discovery_run.json) and enrichment flagged it back;
    round 2d did the same. Three full days: no transition, never on the main wall at any point (no
    more than production), checked on JustWatch in every discovery, each day a "not out yet" day."""
    days = (TODAY, '2026-11-15', '2026-11-16')
    spec = scenario([GALAXYMPHONY], wall_ids=[GALAXYMPHONY], phases=two_days(*days))
    v2 = run_daily(spec, str(tmp_path / 'v2'))
    head = run_daily_with_code(head_code_root, spec, str(tmp_path / 'prod'))
    title = fixtures()['tracking'][GALAXYMPHONY]['title']

    assert _transitions(head, GALAXYMPHONY) == list(days), 'precondition: production loops on this shape'
    assert _transitions(v2, GALAXYMPHONY) == [], _transitions(v2, GALAXYMPHONY)
    assert not any(main for _k, main in _on_main_at(v2, GALAXYMPHONY)), _on_main_at(v2, GALAXYMPHONY)
    assert not _no_more_on_main_than(v2, head, GALAXYMPHONY)
    assert v2['log'].count('still a buy-only pre-order') >= len(days), 'PO-3 check not reached every day'
    for d in days:
        rec = after(v2, 'discover', d)['tracking'][GALAXYMPHONY]
        assert title in jw_titles(v2, 'discover', d), f'{d}: not checked on JustWatch'
        assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)
        assert rec.get('_jw_last_refuted') == d, brief_rec(rec)


def test_po3_the_last_kiss_real_loop_ends(tmp_path, head_code_root):
    """The Last Kiss (real origin/main records): a buy-only pre-order whose TMDB digital date (STAGED:
    2026-09-15, its wall date and intake day) has passed; JustWatch (STAGED from its three real
    pre_order_links) sells it on Amazon, Apple and Fandango, rents and streams it nowhere. Production
    moved it to 'available' every night on TMDB's date (the pre-order graduation bypass). Two full days:
    discovery checks it on JustWatch and keeps it waiting -- no transition, never on the main wall (no
    more than production), each day a "not out yet" day. (Round 2d's Type-4 buy-only check already
    ended this one; pinned here with the other real loopers so a change to PO-3 can't reopen it.)"""
    days = (TODAY, '2026-11-15')
    t4 = {'id': int(LAST_KISS), 'results': [{'iso_3166_1': 'US', 'release_dates': [
        {'certification': '', 'descriptors': [], 'iso_639_1': '', 'note': '', 'type': 4,
         'release_date': '2026-09-15T00:00:00.000Z'}]}]}
    tmdb = {LAST_KISS: {'details': dict(copy.deepcopy(LIBERATION_TMDB['details']), id=int(LAST_KISS),
                                        title='The Last Kiss', original_title='The Last Kiss'),
                        'release_dates': t4, 'watch_providers': {'id': int(LAST_KISS), 'results': {}}}}
    node = {'id': 'tm' + LAST_KISS, 'objectId': int(LAST_KISS), 'objectType': 'MOVIE',
            'content': {'title': 'The Last Kiss', 'originalReleaseYear': 2026, 'fullPath': '/us/movie/the-last-kiss-2026',
                        'externalIds': {'tmdbId': LAST_KISS}, 'credits': [{'role': 'DIRECTOR', 'name': 'Yoko Okumura'}]},
            'offers': [offer('BUY', p['service'], {'Amazon Video': 'amazon', 'Apple TV Store': 'itunes'}.get(p['service'], 'vudu'),
                             p['link'].replace('&tag=nrw04-20', ''), p['buy_price'], None, '2026-09-15T00:00:00Z')
                       for p in _entry(LAST_KISS)['pre_order_links']]}
    spec = _spec([LAST_KISS], {LAST_KISS: _rec(LAST_KISS)}, [_entry(LAST_KISS)], tmdb, {LAST_KISS: node},
                 two_days(*days), TODAY)
    v2 = run_daily(spec, str(tmp_path / 'v2'))
    head = run_daily_with_code(head_code_root, spec, str(tmp_path / 'prod'))

    assert _transitions(head, LAST_KISS) == list(days), 'precondition: production loops on this shape'
    # Round 2f+ (owner, Nov 2026: "buy-only is buyable"; its real Amazon page reads "Buy UHD
    # $14.99"): out on its first check, dated TMDB's 2026-09-15, and it STAYS -- the nightly loop
    # ends the other way: one transition, on the main wall every phase after.
    assert _transitions(v2, LAST_KISS) == [TODAY], _transitions(v2, LAST_KISS)
    for d in days:
        rec = after(v2, 'gap_fill', d)['tracking'][LAST_KISS]
        assert rec['status'] == 'available' and rec['digital_date'] == '2026-09-15', brief_rec(rec)
        assert on_main_wall(only(after(v2, 'gap_fill', d)['wall'][LAST_KISS])), d


class _TvNet(tsp.FakeNet):
    """The harness network plus TMDB's TV endpoints (a limited series is 'tv_<id>'). A TV id asked of
    TMDB's MOVIE release-dates endpoint gets TMDB's real answer for a wrong id: 404."""
    TV_RE = re.compile(r'^https://api\.themoviedb\.org/3/tv/(\d+)(/watch/providers)?/?$')
    MOVIE_TV_RE = re.compile(r'^https://api\.themoviedb\.org/3/movie/tv_\d+')

    def get(self, url, params=None, timeout=None, **kw):
        m = self.TV_RE.match(url or '')
        if m:
            mid, kind = 'tv_' + m.group(1), m.group(2) or ''
            self.tmdb_calls.append((self.phase, mid, kind))
            fx = (self.spec.get('tmdb') or {}).get(mid) or {}
            if kind == '/watch/providers':
                return tsp.FakeResponse(200, fx.get('watch_providers') or {'id': int(m.group(1)), 'results': {}})
            if fx.get('details'):
                return tsp.FakeResponse(200, fx['details'])
            return tsp.FakeResponse(404, {'status_code': 34, 'status_message': 'not found'})
        if self.MOVIE_TV_RE.match(url or ''):
            self.tmdb_calls.append((self.phase, url, 'movie_endpoint_tv_id'))
            return tsp.FakeResponse(404, {'status_code': 34, 'status_message': 'not found'})
        return super().get(url, params=params, timeout=timeout, **kw)


def test_po3_marble_hall_murders_real_tv_loop_ends(tmp_path, monkeypatch):
    """Marble Hall Murders (real origin/main records; a limited series, id tv_283319): a buy-only
    pre-order production moved to 'available' every night 11-01..11-15 because TMDB lists a PBS
    Masterpiece Amazon Channel stream (STAGED from its tracking providers). JustWatch (STAGED from its
    three real pre_order_links) sells it on Amazon, Apple and Fandango; the channel stream is one NRW
    skips. PO-3's check asks TMDB for a movie Type-4 date with the 'tv_' id (TMDB: 404) and reads
    Amazon's page (renders nothing readable): still a pre-order. Three discovery runs: no transition,
    never on the main wall, checked on JustWatch every day, no crash on the TV id."""
    monkeypatch.setattr(tsp, 'FakeNet', _TvNet)
    days = (TODAY, '2026-11-15', '2026-11-16')
    providers = {'id': 283319, 'results': {'US': {
        'buy': [{'provider_id': i, 'provider_name': n, 'display_priority': i}
                for i, n in enumerate(['Amazon Video', 'Apple TV Store', 'Google Play Movies', 'Fandango At Home'])],
        'flatrate': [{'provider_id': 294, 'provider_name': 'PBS Masterpiece Amazon Channel', 'display_priority': 9}]}}}
    tech = {'Amazon Video': 'amazon', 'Apple TV Store': 'itunes', 'Fandango At Home': 'vudu'}
    node = {'id': 'ts283319', 'objectId': 283319, 'objectType': 'SHOW',
            'content': {'title': 'Marble Hall Murders', 'originalReleaseYear': 2026,
                        'fullPath': '/us/tv-show/marble-hall-murders', 'externalIds': {'tmdbId': '283319'}, 'credits': []},
            'offers': [offer('BUY', p['service'], tech[p['service']], p['link'].replace('&tag=nrw04-20', ''),
                             p['buy_price'], None, '2026-09-06T00:00:00Z') for p in _entry(MARBLE_HALL)['pre_order_links']]
            + [offer('FLATRATE', 'PBS Masterpiece Amazon Channel', 'amazonpbsmasterpiece',
                     'https://watch.amazon.com/detail?gti=amzn1.dv.gti.marble-hall-staged', None,
                     '2026-09-07T04:00:00Z', '2026-09-07T04:00:00Z')]}
    spec = _spec([MARBLE_HALL], {MARBLE_HALL: _rec(MARBLE_HALL)}, [_entry(MARBLE_HALL)],
                 {MARBLE_HALL: {'watch_providers': providers}}, {MARBLE_HALL: node},
                 [(d, 'discover') for d in days], TODAY)
    res = run_daily(spec, str(tmp_path / 'sbx'))

    assert any(c[1] == MARBLE_HALL and c[2] == '/watch/providers' for c in res['tmdb_calls']), 'precondition: TMDB asked'
    # Round 2f+ (owner, Nov 2026: "buy-only is buyable"): sold on Amazon, Apple and Fandango, out
    # of theaters -- out on its first check, dated its first offer record (2026-09-06), and it
    # stays: one transition, no nightly loop, no crash on the TV id.
    assert _transitions(res, MARBLE_HALL) == [TODAY], _transitions(res, MARBLE_HALL)
    for d in days:
        rec = after(res, 'discover', d)['tracking'][MARBLE_HALL]
        assert rec['status'] == 'available' and rec['digital_date'] == '2026-09-06', brief_rec(rec)
    assert 'Unexpected error during provider checking' not in res['log']


# ==================================================================================================
# PO-4 + CAPTCHA: Amazon's robot check is no reading, never a "not out yet" day for a held film
# ==================================================================================================

def _day_by_day(days_pages, root, node, code_root=None):
    """One harness run per day (the fake store page is fixed per run), carrying tracking and the
    film's wall entry over. Liberation (real held record: pending TMDB date 11-17, held since a
    2026-09-15 'no valid offers' check). days_pages: [(day, Amazon page text)]."""
    cur = _lib_spec(phases=[], jw_over={LIBERATION: node})
    out = []
    for i, (d, page) in enumerate(days_pages):
        s = copy.deepcopy(cur)
        s['phases'] = [[d, 'discover']]
        s['today'] = d
        s['pages'] = [['amazon.com', page]]
        work = os.path.join(root, f'd{i}')
        res = run_daily_with_code(code_root, s, work) if code_root else run_daily(s, os.path.join(work, 'sbx'))
        st = final(res)
        out.append((d, st, res))
        cur['tracking'] = {k: v for k, v in st['tracking'].items() if v}
        cur['wall'] = [only(v) for v in st['wall'].values() if only(v)]
    return out


def test_po4_captcha_on_the_type4_putback_is_no_reading(tmp_path):
    """R2D PO-4. Liberation (real held record) reaches its pending TMDB date 11-17; JustWatch (STAGED)
    shows its Amazon rental live from 11-17 00:00 ET. On 11-17 Amazon answers with its robot check
    (CAPTCHA); on 11-18 the page reads. Round 2d counted the CAPTCHA as a "Pre-order" reading: held,
    11-17 stored as a proven "not out yet" day, and the film was put back on 11-18 dated 11-18 -- a
    day late, on a day nothing proved it out. Fixed: held on 11-17 (an unreadable page never puts a
    film on), but nothing recorded; back on 11-18 dated 11-17, the day JustWatch first recorded the
    live rental (rule 3)."""
    node = _lib_node(amazon_rent_from('B0LIBLIVE', '2026-11-17T05:00:00Z', created='2026-11-17T05:00:00Z'))
    out = _day_by_day([('2026-11-17', CAPTCHA_PAGE), ('2026-11-18', LIVE_PAGE)], str(tmp_path / 'v2'), node)
    d1, d2 = out[0][1]['tracking'][LIBERATION], out[1][1]['tracking'][LIBERATION]
    assert 'CAPTCHA wall hit' in out[0][2]['log'], 'precondition: the robot check was hit'
    assert d1['status'] == 'tracking', brief_rec(d1)
    assert d1.get('_jw_last_refuted') != '2026-11-17' and d1.get('_rent_preorder_held') != '2026-11-17', \
        brief_rec(d1, '_rent_preorder_held')
    assert d2['status'] == 'available' and d2['digital_date'] == '2026-11-17', brief_rec(d2)


def test_po4_captcha_on_the_provider_path_records_nothing_for_a_held_film(tmp_path):
    """The provider path's own store check for a film ALREADY held (Liberation, real held record,
    pending TMDB date 11-17 still ahead): on 11-14 JustWatch (STAGED) shows an Amazon rental live from
    11-14 and Amazon serves its robot check; on 11-15 the page reads. Held on 11-14 (never on the wall
    unread), with no "not out yet" day recorded for it (it is checked daily anyway) -- round 2d stored
    11-14 as one and dated the put-back 11-15. Fixed: back on 11-15 dated 11-14, the day JustWatch
    first recorded the live rental (rule 3)."""
    node = _lib_node(amazon_rent_from('B0LIBLIVE', '2026-11-14T05:00:00Z', created='2026-11-14T05:00:00Z'))
    out = _day_by_day([(TODAY, CAPTCHA_PAGE), ('2026-11-15', LIVE_PAGE)], str(tmp_path / 'v2'), node)
    d1, d2 = out[0][1]['tracking'][LIBERATION], out[1][1]['tracking'][LIBERATION]
    assert 'CAPTCHA wall hit' in out[0][2]['log'], 'precondition: the robot check was hit'
    assert d1['status'] == 'tracking' and d1.get('_jw_revert_count'), brief_rec(d1)
    assert d1.get('_jw_last_refuted') != TODAY and d1.get('_rent_preorder_held') != TODAY, \
        brief_rec(d1, '_rent_preorder_held')
    assert d2['status'] == 'available' and d2['digital_date'] == TODAY, brief_rec(d2)


def test_po4_captcha_on_the_provider_path_holds_a_film_not_yet_held_and_rechecks_it(tmp_path):
    """A film NOT held yet (Tom and Jerry: Forbidden Compass, real records, here an ordinary tracking
    film -- not a buy-only pre-order -- that TMDB lists on Apple): JustWatch (STAGED) shows an Amazon
    rental live from today, and Amazon serves its robot check. It must not go on the wall unread
    (rule 4), and it must be checked again the next run whatever TMDB lists (rule 1): 2e marks it
    held. The next day the page reads and it is on the main wall."""
    jw = jw_node(TOM_AND_JERRY, amazon_rent('B0TJCAPTCHA'))
    base = scenario([TOM_AND_JERRY], wall_ids=[TOM_AND_JERRY], jw_over={TOM_AND_JERRY: jw},
                    tracking_over={TOM_AND_JERRY: {'_buyonly_preorder': _MISSING}},
                    wall_over={TOM_AND_JERRY: {'_buyonly_preorder': _MISSING}})
    cur, out = base, []
    for i, (d, page) in enumerate(((TODAY, CAPTCHA_PAGE), ('2026-11-15', LIVE_PAGE))):
        s = copy.deepcopy(cur)
        s.update(phases=[[d, 'discover']], today=d, pages=[['amazon.com', page]])
        res = run_daily(s, str(tmp_path / f'd{i}' / 'sbx'))
        out.append((d, final(res), res))
        cur = dict(cur, tracking={k: v for k, v in final(res)['tracking'].items() if v},
                   wall=[only(v) for v in final(res)['wall'].values() if only(v)])
    d1, d2 = out[0][1]['tracking'][TOM_AND_JERRY], out[1][1]['tracking'][TOM_AND_JERRY]
    assert 'CAPTCHA wall hit' in out[0][2]['log'], 'precondition: the robot check was hit'
    assert d1['status'] == 'tracking' and d1.get('_rent_preorder_held'), brief_rec(d1, '_rent_preorder_held')
    assert not on_main_wall(only(out[0][1]['wall'][TOM_AND_JERRY]))
    assert 'Tom and Jerry: Forbidden Compass' in jw_titles(out[1][2], 'discover')
    assert d2['status'] == 'available' and on_main_wall(only(out[1][1]['wall'][TOM_AND_JERRY])), brief_rec(d2)


def test_po4_daily_buy_only_check_gives_no_answer_on_a_captcha(tmp_path):
    """_jw_shows_rent_or_stream (discovery's daily buy-only check) for Tom and Jerry (real buy-only
    pre-order) when JustWatch (STAGED) lists an Amazon pre-order rental (offer start Dec 4) and Amazon
    serves its robot check: None -- no answer today -- so _buyonly_still_waiting keeps it waiting and
    records NOTHING (round 2d read the CAPTCHA as not 'available' and stored today as a proven "not out
    yet" day)."""
    jw = jw_node(TOM_AND_JERRY, amazon_preorder_rent('B0TJSTAGED'))
    spec = scenario([TOM_AND_JERRY], phases=(), jw_over={TOM_AND_JERRY: jw}, pages=[('amazon.com', CAPTCHA_PAGE)])
    rec = copy.deepcopy(spec['tracking'][TOM_AND_JERRY])
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()) as log:
        with pipeline_sandbox(spec, str(tmp_path / 'sbx')) as (gen, net):
            disc = gen._discoverer
            answer = disc._jw_shows_rent_or_stream(TOM_AND_JERRY, copy.deepcopy(rec))
            disc._page_verdicts.clear()
            waits = disc._buyonly_still_waiting(TOM_AND_JERRY, rec)
            pages = list(net.pages)
    assert any('amazon.com' in u for _ph, u in pages), f'precondition: Amazon page read: {pages}'
    assert 'CAPTCHA wall hit' in log.getvalue()
    assert answer is None, answer
    assert waits is True and rec.get('_buyonly_preorder')
    assert '_jw_last_refuted' not in rec and '_jw_last_checked' not in rec, brief_rec(rec)


# ==================================================================================================
# TP-01: buy-only by the wall entry OR the tracking record (gap fill + enrichment catch-up)
# ==================================================================================================

APPLE_WICKER = 'https://tv.apple.com/us/movie/wicker/umc.cmc.verify'


def _apple_rent(start='2026-10-23T07:00:00Z', created='2026-11-14T07:00:00Z'):
    """STAGED: an Apple TV Store RENT whose offer start is Wicker's theatrical date (Apple lists rentals
    from the theater opening -- justwatch.py)."""
    return offer('RENT', 'Apple TV Store', 'itunes', APPLE_WICKER, '$19.99', start, created)


def _type4(day):
    return dict(fixtures()['tmdb'][WICKER], release_dates={'id': int(WICKER), 'results': [
        {'iso_3166_1': 'US', 'release_dates': [{'type': 4, 'release_date': f'{day}T00:00:00.000Z', 'note': ''}]}]})


@pytest.mark.parametrize('wall_flag', ['wall_unflagged_as_on_main', 'wall_flagged'])
def test_tp01_gap_fill_reads_buy_only_from_tracking_too(wall_flag, tmp_path):
    """R2D-TP-01 (port of v01a). Wicker is a buy-only pre-order in tracking, but its wall entry lacks
    the flag (as on main, with The Social Reckoning). Its date has arrived (STAGED: today) and
    JustWatch (STAGED) lists only an Apple TV Store rental (a pre-order listing). Round 2d's gap fill
    read only the wall flag and put it on the main wall, tracking 'available'. Fixed: it stays a
    pre-order, waiting in tracking -- with or without the wall flag."""
    node = _wicker_buyonly_node()
    node['offers'].append(_apple_rent())
    wall_over = {WICKER: {'digital_date': TODAY}}
    if wall_flag == 'wall_flagged':
        wall_over[WICKER]['_buyonly_preorder'] = True
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'digital_date': TODAY}}, wall_over=wall_over)
    assert spec['tracking'][WICKER]['_buyonly_preorder'] is True
    assert bool(spec['wall'][-1].get('_buyonly_preorder')) is (wall_flag == 'wall_flagged')
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert in_preorder_lane(entry) and not on_main_wall(entry), brief(entry)
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), brief_rec(rec)


@pytest.mark.parametrize('page', ['apple_page_reads_preorder', 'pages_unreadable', 'apple_page_reads_available'])
def test_tp01_full_day_never_on_the_main_wall_the_day_discovery_proved_it_not_out(page, tmp_path):
    """R2D-TP-01 (port of v01b), the real daily order. TMDB moves Wicker's digital date to today
    (STAGED); JustWatch (STAGED) lists an Apple TV Store rental beside the Fandango purchase.
    Discovery reads Apple's page: still 'Pre-order' (or unreadable) -> keeps it waiting and stores
    today as "not out yet". Round 2d's enrichment catch-up then published it on the main wall dated
    that very day. Fixed: enrichment leaves it to discovery's buy-only check -- not on the main wall at
    any point. Control: Apple's page reads 'Rent now' -> discovery graduates it, on the main wall
    today."""
    node = _wicker_buyonly_node()
    node['offers'].append(_apple_rent())
    pages = {'apple_page_reads_preorder': [('tv.apple.com', PREORDER_PAGE)], 'pages_unreadable': [],
             'apple_page_reads_available': [('tv.apple.com', LIVE_PAGE)]}[page]
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, tmdb_over={WICKER: _type4(TODAY)},
                    pages=pages)
    res = run_daily(spec, str(tmp_path / 'sbx'))
    d_rec = after(res, 'discover')['tracking'][WICKER]
    entry = only(final(res)['wall'][WICKER])
    # Round 2f+: TMDB's digital date (today) has arrived and stores list it -> out by the pre-order
    # labeler when the page can't be read too; only a page reading 'Pre-order' still holds it.
    if page in ('apple_page_reads_available', 'pages_unreadable'):
        assert d_rec['status'] == 'available' and on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
        return
    assert d_rec['status'] == 'tracking' and d_rec.get('_jw_last_refuted') == TODAY, 'precondition: discovery held it'
    assert not any(main for _k, main in _on_main_at(res, WICKER)), _on_main_at(res, WICKER)
    assert final(res)['tracking'][WICKER]['status'] == 'tracking'


def test_tp01_three_days_waiting_then_on_the_day_amazon_goes_live(tmp_path):
    """R2D-TP-01 (port of v01d) over three daily runs. 11-14 and 11-15: JustWatch (STAGED) lists only
    Apple's rental and its page reads 'Pre-order' (each a "not out yet" day in tracking). 11-16:
    Amazon's rental goes live (STAGED; its page reads 'Rent now'). Round 2d had Wicker on the main wall
    on 11-14 and 11-15 while tracking said not out. Fixed: off the main wall both days, on it from 11-16
    dated 11-16 -- the day it really came out (rule 3)."""
    node = _wicker_buyonly_node()
    node['offers'].append(_apple_rent())
    live = _wicker_buyonly_node()
    live['offers'] += [_apple_rent(), amazon_rent_from('B0WICKERVERIFY', '2026-11-16T05:00:00Z',
                                                      created='2026-11-16T05:00:00Z', price='$19.99')]
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, tmdb_over={WICKER: _type4(TODAY)},
                    pages=[('tv.apple.com', PREORDER_PAGE), ('amazon.com', LIVE_PAGE)],
                    jw_days={'2026-11-16': {WICKER: live}}, phases=two_days(TODAY, '2026-11-15', '2026-11-16'))
    res = run_daily(spec, str(tmp_path / 'sbx'))
    for k, st in res['phases'].items():
        d = k.split(':')[1]
        e, r = only(st['wall'][WICKER]), st['tracking'][WICKER]
        if d in (TODAY, '2026-11-15'):
            assert not on_main_wall(e), f'{k}: on the main wall while tracking waits: {brief(e)} {brief_rec(r)}'
    end = only(final(res)['wall'][WICKER])
    assert on_main_wall(end) and end['digital_date'] == '2026-11-16', brief(end)
    assert final(res)['tracking'][WICKER]['digital_date'] == '2026-11-16'


# ==================================================================================================
# TP-02: the gap fill reads the store page before graduating a pre-order on a rental
# ==================================================================================================

def _gf_amazon_spec(phases, page_text, start='2026-11-13T05:00:00Z'):
    """Wicker (real records: a future pending pre-order, not held, in the PRE-ORDER lane for 12-01)
    with an Amazon rental JustWatch (STAGED) recorded on its offer-start day 11-13 -- past, so
    'live' -- while Amazon's page (STAGED) reads `page_text`. The Last Blossom's real pattern: its
    Amazon offer start passed while its page still read 'Pre-order' (production held it 10-07/10-08)."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', start, created=start, price='$19.99'))
    pages = [('amazon.com', page_text)] if page_text is not None else []
    return scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=phases, pages=pages)


@pytest.mark.parametrize('phases', [('gap_fill',), ('discover', 'enrich', 'gap_fill')], ids=['gap_fill_only', 'full_day'])
def test_tp02_gap_fill_keeps_a_preorder_whose_store_page_still_reads_preorder(phases, tmp_path):
    """R2D-TP-02 (port of v02). Round 2d's gap fill graduated Wicker on the live Amazon listing alone
    (no page read: up to 10 days before release, on the main wall). Fixed: the gap fill reads Amazon's
    page first; 'Pre-order' keeps it a pre-order and stores today as a "not out yet" day in tracking."""
    res = run_daily(_gf_amazon_spec(phases, PREORDER_PAGE), str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert any(ph.endswith(':gap_fill') and 'amazon.com' in u for ph, u in res['pages']), res['pages']
    assert in_preorder_lane(entry) and not on_main_wall(entry), brief(entry)
    assert rec['status'] == 'tracking' and rec.get('_jw_last_refuted') == TODAY, brief_rec(rec)


def test_tp02_gap_fill_graduates_when_the_store_page_reads_live(tmp_path):
    """Control for TP-02: the same live Amazon rental, Amazon's page reads 'Rent now' -> the gap fill
    graduates Wicker today: on the main wall dated today, tracking 'available' with its pre-order flags
    gone."""
    res = run_daily(_gf_amazon_spec(('gap_fill',), LIVE_PAGE), str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    # A buy-only film the gap fill graduates is dated the day it became watchable: Amazon's
    # rental, recorded and live since 2026-11-13 (round 2f+), not the day the gap fill noticed.
    assert on_main_wall(entry) and entry['digital_date'] == '2026-11-13', brief(entry)
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-11-13', brief_rec(rec)
    assert not any(rec.get(k) for k in ('_is_preorder', '_buyonly_preorder', '_type4_pending')), brief_rec(rec)


def test_tp02_gap_fill_captcha_keeps_it_a_preorder_without_a_not_out_yet_day(tmp_path):
    """TP-02 on Amazon's robot check: the page can't be read, so the gap fill doesn't graduate Wicker
    today (an unread page never puts a film on), but it records NO "not out yet" day: a CAPTCHA proves
    nothing about the film (rule 4)."""
    spec = _gf_amazon_spec(('gap_fill',), CAPTCHA_PAGE)
    before = spec['tracking'][WICKER].get('_jw_last_refuted')
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert 'CAPTCHA wall hit' in res['log']
    assert in_preorder_lane(entry), brief(entry)
    assert rec.get('_jw_last_refuted') == before and rec.get('_jw_last_refuted') != TODAY, brief_rec(rec)


def test_tp02_gap_fill_graduates_on_streaming_without_a_page_read(tmp_path):
    """Streaming has no pre-orders: Wicker gets a Netflix stream today (STAGED) -> the gap fill
    graduates it today without rendering any store page (no Playwright cost)."""
    node = _wicker_buyonly_node()
    node['offers'].append(netflix_stream('wicker-staged'))
    res = run_daily(scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',)),
                    str(tmp_path / 'sbx'))
    entry = only(final(res)['wall'][WICKER])
    assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
    assert res['pages'] == [], res['pages']


# ==================================================================================================
# TP-03: the gap fill leaves a held film to discovery
# ==================================================================================================

def test_tp03_gap_fill_leaves_a_held_preorder_to_discovery(tmp_path):
    """R2D-TP-03 (port of v03). Wicker was held yesterday by its store page (`_rent_preorder_held`
    11-13, a "not out yet" day); its wall entry is still in the PRE-ORDER lane. Today JustWatch
    (STAGED) shows Amazon's rental past its offer start. The gap fill must not graduate it: discovery
    checks a held film's page and dates it."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', '2026-11-12T05:00:00Z', created='2026-11-12T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'_rent_preorder_held': '2026-11-13', '_jw_last_refuted': '2026-11-13'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert in_preorder_lane(entry) and not on_main_wall(entry), brief(entry)
    assert rec['status'] == 'tracking', brief_rec(rec)


# ==================================================================================================
# TP-07: the gap fill's dating rules
# ==================================================================================================

def test_tp07a_still_tracking_preorder_with_a_passed_wall_date_is_dated_today(tmp_path):
    """R2D-TP-07 / M08c (port of v07a). Wicker still 'tracking' (never out), its pre-order date 11-10
    passed; Amazon's rental (STAGED) live today, page unreadable. The gap fill graduates it dated
    TODAY -- never its old pre-order date (rule 3)."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', f'{TODAY}T05:00:00Z', created=f'{TODAY}T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'digital_date': '2026-11-10'}}, wall_over={WICKER: {'digital_date': '2026-11-10'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
    assert rec['status'] == 'available' and rec['digital_date'] == TODAY, brief_rec(rec)


def test_tp07b_a_film_tracking_already_had_out_keeps_its_date(tmp_path):
    """R2D-TP-07 / M08e (port of v07b). Tracking has Wicker out since 10-24 (no later "not out yet"
    day); its wall entry still carries a stale pre-order flag; Amazon's rental (STAGED) is live since
    10-24. The gap fill clears the flag and keeps 10-24 (the Carolina Caroline case: re-stamping today
    would make an old film look brand-new)."""
    node = _wicker_buyonly_node()
    node['offers'].append(amazon_rent_from('B0WICKERVERIFY', '2026-10-24T05:00:00Z', created='2026-10-24T05:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'status': 'available', 'digital_date': '2026-10-24'}},
                    wall_over={WICKER: {'digital_date': '2026-10-24'}})
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == '2026-10-24', brief(entry)
    assert rec['digital_date'] == '2026-10-24', brief_rec(rec)


def test_tp07c_buy_only_flagged_by_the_gap_fill_is_dated_the_day_its_rental_goes_live(tmp_path):
    """R2D-TP-07 / M09b (port of v07c). An ordinary wall film (Wicker, dated 11-10, tracking
    'available', no TMDB digital date) that JustWatch shows buy-only on 11-14: the gap fill flags it a
    buy-only pre-order and sends it back to tracking without its old date. 11-15 Amazon's rental goes
    live (STAGED): discovery graduates it dated 11-15, never the old 11-10 (a day it was only buyable)."""
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
    assert gf['tracking'][WICKER]['status'] == 'tracking' and not gf['tracking'][WICKER].get('digital_date'), \
        brief_rec(gf['tracking'][WICKER])
    rec = final(res)['tracking'][WICKER]
    assert rec['status'] == 'available' and rec['digital_date'] == '2026-11-15', brief_rec(rec)


def test_tp07d_coming_soon_preorder_tracking_calls_available_is_dated_the_day_it_streams(tmp_path):
    """R2D-TP-07 (port of v07d): the shape of the 35 'coming soon' pre-orders on main -- tracking
    'available', wall entry a FUTURE-dated pre-order (12-01), `_transitioned_at` in the past (10-24).
    Streaming appears today (STAGED: Netflix). It became watchable today: dated today, never its 10-24
    pre-order placement day (round 2d dated it 10-24, weeks before it came out)."""
    node = _wicker_buyonly_node()
    node['offers'].append(offer('FLATRATE', 'Netflix', 'nfx', 'https://www.netflix.com/title/8100verify', None,
                                f'{TODAY}T07:00:00Z', f'{TODAY}T07:00:00Z'))
    spec = scenario([WICKER], wall_ids=[WICKER], jw_over={WICKER: node}, phases=('gap_fill',),
                    tracking_over={WICKER: {'status': 'available', '_type4_pending': _MISSING, '_buyonly_preorder': _MISSING}})
    assert spec['tracking'][WICKER]['_transitioned_at'] == '2026-10-24' and spec['wall'][-1]['digital_date'] == '2026-12-01'
    res = run_daily(spec, str(tmp_path / 'sbx'))
    entry, rec = only(final(res)['wall'][WICKER]), final(res)['tracking'][WICKER]
    assert on_main_wall(entry) and entry['digital_date'] == TODAY, brief(entry)
    assert rec['digital_date'] == TODAY, brief_rec(rec)


# ==================================================================================================
# e1b: the DVD-only shape (Galaxymphony) -- no longer on the main wall after discovery, nor at any
# later point of the day more than production
# ==================================================================================================

@pytest.mark.parametrize('lane', ['as_recorded', 'held_silent', 'skipped', 'buyonly'])
def test_e1b_bn_dvd_only_shape_never_on_the_main_wall_more_than_production(lane, e_root, head_code_root):
    """The regression guard's BN shape (Galaxymphony: a Barnes & Noble DVD only on JustWatch, plus an
    Amazon-channel stream NRW skips) in each lane Step 1 changed. Round 2d had it on the main wall
    after discovery in three lanes (strict-xfail 'known exposures': graduated on TMDB's listing,
    entry synced, waiting for enrichment to pull it). Round 2e's PO-3 check removed those exposures:
    after EVERY phase of the day (discovery, enrichment, gap fill) v2 has it on the main wall no more
    than production does."""
    mid, head, v2, _ = _e_results('BN', lane, e_root, head_code_root)
    assert list(v2['phases']) == list(head['phases'])
    worse = _no_more_on_main_than(v2, head, mid)
    assert not worse, (f'BN/{lane}: v2 on the main wall where production is not, at {worse}\n'
                       f'  v2: {tsp._summary(v2, mid)}\n  production: {tsp._summary(head, mid)}')
