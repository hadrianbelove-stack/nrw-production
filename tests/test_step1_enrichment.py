"""
Step 1 v2 (branch step1-putback-v2, round-2b working tree) -- end-to-end tests, ENRICHMENT side.

Ported from the v1 file (nrw-step1-wt/tests/test_step1_enrichment.py, written against
a5da4f76) and extended for every round-2 / round-2b enrichment change (scratchpad
round2_changes.md, incl. its "Round 2b" section).

Owner's rules under test
  1. A film held as "not out yet" is a WAIT, never a drop.
  2. Every held film is re-checked every daily run.
  3. JustWatch decides availability (TMDB never).
  4. Dated the day it actually became available, never on a day a check proved it
     unavailable.
  5. A JustWatch error/outage never counts against a film and never puts an
     unconfirmed film on the wall.
  6. (Nov 15) Remove and Revert are opposites. Remove = never on the wall again (status
     'removed', set only by the owner's /remove or admin Remove); Revert = back to
     waiting, back on the wall the day it's really out. Nothing automatic sets 'removed';
     nothing brings a removed title back.

What runs
---------
The real daily pipeline phases, inside a throwaway directory (pytest tmp_path):
  screenings  DataGenerator.check_virtual_screening_expirations()
  phase 2     DataGenerator.check_tracking_movies()          discovery -- puts held films back
  phase 3     DataGenerator.enrich_newly_available_movies()  enrichment -- JustWatch Step 0,
                                                              dating, zero-links check, purge
  archive     DataGenerator.archive_old_movies()
  report      scripts/morning_report.py overnight() / backlog()
  curation    scripts/curate_list.py (_in_window, review_rows, capsule_queue)
  owner       admin Remove (the real /remove-movie Flask route), putback.owner_revert /
              revert_wall_entry (the Revert action), --enrich-id (single-film enrichment)
Every phase gets a fresh DataGenerator (separate processes in daily_orchestrator.py).
Every pipeline module is the real one from the v2 worktree.

Only the network is faked:
  * TMDB REST: copies of the real responses for these films (fetched read-only on
    2026-11-14), trimmed to the fields the pipeline reads. Films added in v2 tests get
    trimmed details; their release dates are real where captured (Sense and Sensibility:
    scratchpad/live/tmdb1.json) and SYNTHETIC where a scenario needs a date.
  * JustWatch GraphQL: copies of the real search results (fetched read-only on
    2026-11-14; Sense and Sensibility from scratchpad/live/jw1.json). Those captures
    predate the `dateCreated` query field, so their real record dates are unknown: every
    captured offer carries "dateCreated": null (no record date -> no JustWatch dating
    evidence). Offers and record dates a scenario needs are marked SYNTHETIC.
  * Playwright store/streaming scrapers and page checks (inconclusive), Eventive page
    fetches, Wikipedia / YouTube / RT / Letterboxd / Metacritic / OMDb / IMDb / B2.
  * A socket guard: any other network attempt is recorded and fails the test.
  * A write guard: any write under the three NRW checkouts fails the test.

Tracking rows and wall entries are verbatim copies from production:
`git show 78303fd6:movie_tracking.json` and `git show 78303fd6:data.json`. Where a
scenario changes one, the change is spelled out next to it.

Nothing in any checkout is written: data.json, movie_tracking.json/.db,
data_archive.json, metrics/, cache/, backups/ and logs/ all live in tmp_path, and the
tracking-DB singleton is pointed at a tmp copy.

Known CODE failures (strict xfail -- remove the mark once fixed):
  * a returned festival screening whose only usable JustWatch offer has no usable link
    gets its own expired Eventive page back from the watch-link step (that JustWatch call
    has no festival exclusion): kept, re-flagged a virtual screening, then hidden under
    its old screening date while tracking says 'available' -- never checked again
    (RETURNED_SCREENING_LINK_DEFECT, 3 tests);
  * enrichment never checks status 'removed': a removed title whose wall entry outlives
    the Remove is re-queued, and a "no offer" answer sets it back to 'tracking' --
    discovery then puts it back on the wall (REMOVED_REVIVED_DEFECT, 2 tests).
Fixed in round 2b (were strict xfail in round 2; now plain tests): the loop timeout's
unreached films judged by the zero-links check; the Coming Soon un-hide undoing a
JustWatch-error hide; has_live_rent blind to 'Apple TV Store'.
"""

import copy
import importlib
import io
import json
import logging
import os
import re
import signal
import socket
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta

import pytest
import requests
import yaml

sys.dont_write_bytecode = True      # no __pycache__ writes for the modules imported below

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repo these tests are in
if WT not in sys.path:
    sys.path.insert(0, WT)

_REAL_DATETIME = datetime
_PROTECTED_CHECKOUTS = (WT, '/Users/hadrianbelove/Downloads/nrw-step1-v2',
                        '/Users/hadrianbelove/Downloads/nrw-step1-wt',
                        '/Users/hadrianbelove/Downloads/nrw-production')

# Pipeline modules are imported lazily, after the test has chdir'ed into tmp_path, so no
# import-time side effect can ever land in the worktree.


# ---------------------------------------------------------------------------
# Real records: `git show 78303fd6:movie_tracking.json` (verbatim rows)
# ---------------------------------------------------------------------------

TRACKING_78303FD6 = json.loads(r'''
{
 "1025835": {"title": "Prey of Wrath", "year": 2026, "status": "tracking", "first_seen": "2026-05-02", "digital_date": "2026-05-01", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "A", "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_jw_revert_count": 10, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-05-10", "_skip_provider_discovery": true},
 "1396875": {"title": "Wildcards", "year": 2026, "status": "tracking", "intake_date": "2026-08-27", "digital_date": "2026-11-09", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "_discovery_source": "tmdb_type4", "_is_preorder": true, "_jw_revert_count": 5, "has_providers": true, "enriched": false, "enrichment_date": null, "_transitioned_at": "2026-11-13", "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-13"},
 "1814862": {"title": "Apple Music Live: Troye Sivan", "year": 2026, "status": "tracking", "intake_date": "2026-11-02", "digital_date": "2026-10-13", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "AML", "_apple_music_live": true, "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_transitioned_at": "2026-11-13", "_jw_revert_count": 10, "_jw_revert_reason": "justwatch_no_match", "_jw_reverted_at": "2026-11-13"},
 "1421634": {"title": "Sukma", "premiere_date": "2025-09-11", "digital_date": "2026-11-12", "has_providers": true, "status": "tracking", "added": "2025-09-13T22:15:43.773343", "year": 2025, "_discovery_source": "provider_availability_check", "providers": {"rent": [], "buy": [], "streaming": ["Screambox Amazon Channel"]}, "_jw_revert_count": 2, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-11-12"},
 "1405007": {"title": "Lemonade Blessing", "status": "tracking", "first_seen": "2026-01-04", "digital_date": "2026-04-29", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "backfill", "has_providers": true, "year": 2025, "premiere_date": "2025-06-05", "_discovery_source": "tmdb_type4", "enriched": false, "enrichment_date": null, "_jw_revert_count": 10, "_jw_revert_reason": "justwatch_no_valid_offers", "_jw_reverted_at": "2026-05-10", "_skip_provider_discovery": true},
 "1503762": {"title": "Sense and Sensibility", "year": 2026, "status": "tracking", "intake_date": "2026-09-22", "digital_date": "2026-11-03", "providers": {"rent": [], "buy": [], "streaming": []}, "intake_pass": "B", "has_providers": true, "enriched": false, "enrichment_date": null, "_discovery_source": "tmdb_type4", "_transitioned_at": "2026-11-13", "_jw_revert_reason": "justwatch_theatrical_pvod", "_jw_reverted_at": "2026-11-13", "_jw_revert_count": 1},
 "1333144": {"title": "After This Death", "year": 2025, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-11-20", "providers": {}, "intake_pass": "C", "festival": "Berlin/Berlinale", "has_providers": false, "_discovery_source": "tmdb_type4", "_type4_pending": true, "_is_preorder": true, "enriched": true, "enrichment_date": "2026-11-06"},
 "1500908": {"title": "The Vile", "year": 2025, "status": "tracking", "first_seen": "2026-01-06", "digital_date": "2026-11-20", "providers": {}, "intake_pass": "C", "festival": "Fantastic Fest", "has_providers": false, "_discovery_source": "tmdb_type4", "_type4_pending": true, "_is_preorder": true, "enriched": true, "enrichment_date": "2026-11-09"},
 "1376929": {"title": "Disposable Humanity", "year": 2025, "status": "available", "first_seen": "2026-01-06", "providers": {"rent": ["Eventive"], "buy": [], "streaming": []}, "intake_pass": "C", "festival": "NYFF", "has_providers": true, "enriched": true, "enrichment_date": "2026-09-11", "imdb_id": "tt7336082", "_discovery_source": "provider_availability_check", "digital_date": "2026-09-11", "_transitioned_at": "2026-09-11"},
 "1021848": {"title": "Queen at Sea", "year": 2026, "status": "tracking", "first_seen": "2026-02-09", "providers": {"rent": [], "buy": ["Fandango At Home"], "streaming": []}, "intake_pass": "C", "festival": "Berlin/Berlinale", "has_providers": false, "_discovery_source": "provider_availability_check", "enriched": true, "enrichment_date": "2026-10-31", "_transitioned_at": "2026-10-31", "_buyonly_preorder": true}
}
''')

PREY, WILDCARDS, TROYE, SUKMA, LEMONADE = '1025835', '1396875', '1814862', '1421634', '1405007'
SENSE, AFTER_DEATH, VILE, DISPOSABLE, QUEEN = '1503762', '1333144', '1500908', '1376929', '1021848'
BEWARE = '1244523'

# Real wall entries: `git show 78303fd6:data.json` (verbatim)
WALL_78303FD6 = json.loads(r'''
{
 "1333144": {"id": "1333144", "title": "After This Death", "digital_date": "2026-11-20", "bootstrap_date": false, "manually_corrected": false, "synopsis": "A woman's affair with an enigmatic underground musician throws her life into chaos when he disappears. Forced to fend off his obsessive fans, she also has to confront her fractured marriage, and reclaim her identity and her future.", "genres": ["Drama", "Mystery", "Music", "Comedy"], "runtime": 96, "year": 2025, "rt_score": "45%", "providers": {}, "links": {"wikipedia": "https://en.wikipedia.org/wiki/After_This_Death", "trailer": "https://www.youtube.com/watch?v=VuR2WnooI8Q", "rt": "https://www.rottentomatoes.com/m/after_this_death", "cast_wiki": {"Mía Maestro": "https://en.wikipedia.org/wiki/M%C3%ADa_Maestro", "Lee Pace": "https://en.wikipedia.org/wiki/Lee_Pace", "Rupert Friend": "https://en.wikipedia.org/wiki/Rupert_Friend"}, "imdb": "https://www.imdb.com/title/tt35108047/", "letterboxd": "https://letterboxd.com/film/after-this-death", "director_wiki": "https://en.wikipedia.org/wiki/Lucio_Castro", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1333144.mp4"}, "watch_links": {}, "pre_order_links": [], "_enrichment_status": "completed", "_discovered_at": "2026-11-06T15:46:30.173013", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/zLMJ5Y3pIBW7CL6I502i9URzHkA.jpg", "studio": "2AM", "budget": 0, "country": "United States of America", "original_language": "en", "original_title": "After This Death", "display_title": "After This Death", "crew": {"director": "Lucio Castro", "cast": ["Mía Maestro", "Lee Pace", "Rupert Friend", "Philip Ettinger", "Gwendoline Christie"]}, "_discovery_source": "tmdb_type4", "_is_preorder": true, "_enrichment_attempts": 1, "_last_enrichment_attempt": "2026-11-06", "imdb_rating": "5.8", "letterboxd_score": "3.0", "keywords": [], "_wiki_language_count": 3, "_trailer_source": "gemini_playwright", "_imdb_votes": 124, "_digital_date_source": "tmdb_type4", "_needs_review": false, "_slop_reason": "score:2(low_imdb)", "_slop_confidence": "weak", "status": "available", "_enrichment_gaps": ["watch_links", "metacritic_score"], "reissue_label": null, "_reissue": false, "filters": {"is_indie": false, "is_foreign": false, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": false, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "featured": false},
 "1500908": {"id": "1500908", "title": "The Vile", "digital_date": "2026-11-20", "bootstrap_date": false, "manually_corrected": false, "synopsis": "Devoted wife and mother Amani, whose life begins to unravel when her husband returns home with a second wife and an unseen darkness infiltrates her life.", "genres": ["Horror", "Thriller"], "runtime": 97, "year": 2025, "rt_score": null, "providers": {}, "links": {"wikipedia": null, "trailer": "https://www.youtube.com/watch?v=uhHajuhmMXQ", "rt": null, "imdb": "https://www.imdb.com/title/tt37371373/", "letterboxd": "https://letterboxd.com/film/the-vile", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1500908.mp4", "trailer_hosted_subs": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1500908.en.vtt"}, "watch_links": {"vod": [{"service": "Amazon", "link": "https://www.amazon.com/gp/video/detail/B0GW46V6TZ?tag=nrw04-20"}]}, "pre_order_links": [{"service": "Amazon", "link": "https://www.amazon.com/gp/video/detail/B0GW46V6TZ?tag=nrw04-20"}], "_enrichment_status": "completed", "_discovered_at": "2026-11-09T18:15:15.750494", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/yzvKrIFvHQwUuibOoHX9xSx0JQ3.jpg", "studio": "Spooky Pictures", "budget": 0, "country": "United Arab Emirates", "original_language": "ar", "original_title": "حوبة", "display_title": "The Vile (حوبة)", "crew": {"director": "Majid al-Ansari", "cast": ["Bdoor Mohammad", "Sarah Taibah", "Jasem Alkharraz", "Samira Al-Wahaibi", "Iman Tarik"]}, "_discovery_source": "tmdb_type4", "_is_preorder": true, "_enrichment_attempts": 1, "_last_enrichment_attempt": "2026-11-09", "imdb_rating": "6.5", "letterboxd_score": "3.2", "keywords": ["wife", "supernatural", "supernatural horror", "psychological", "pregnant", "psychological horror", "horror"], "_trailer_source": "gemini_playwright", "_imdb_votes": 158, "_digital_date_source": "tmdb_type4", "_needs_review": false, "is_slop": true, "_slop_reason": "score:6(no_wiki,no_rt,mid_imdb,no_rt_link)", "_slop_confidence": "weak", "status": "available", "_enrichment_gaps": ["rt_score", "wikipedia", "metacritic_score"], "reissue_label": null, "_reissue": false, "filters": {"is_indie": false, "is_foreign": true, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": false, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "featured": false},
 "1376929": {"id": "1376929", "title": "Disposable Humanity", "digital_date": "2026-09-04", "bootstrap_date": false, "manually_corrected": false, "synopsis": "The Mitchell family investigates the Nazi Aktion T4 program which targeted disabled people and catalyzed the Holocaust.", "genres": ["Documentary"], "runtime": 95, "year": 2025, "rt_score": "100%", "providers": {"rent": ["Eventive"], "buy": [], "streaming": []}, "links": {"wikipedia": null, "trailer": "https://www.youtube.com/watch?v=1FTQ6XpDhJg", "rt": "https://www.rottentomatoes.com/m/disposable_humanity", "justwatch": "https://www.justwatch.com/us/movie/disposable-humanity", "metacritic": "https://www.metacritic.com/movie/disposable-humanity/", "imdb": "https://www.imdb.com/title/tt7336082/", "letterboxd": "https://letterboxd.com/film/disposable-humanity", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1376929.mp4"}, "watch_links": {"vod": [{"service": "Eventive", "link": "https://watch.eventive.org/disposablehumanity/play/6a7868d1bdb10f0bb45affc6", "rent_price": "$19.39", "price": "$19.39"}]}, "pre_order_links": [], "_enrichment_status": "completed", "_discovered_at": "2026-09-11T12:45:48.816715", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/o5LyN68dyvXzhXGWlcfUrIN7bHJ.jpg", "studio": "CSM Productions", "budget": 350000, "country": "Unknown", "original_language": "en", "original_title": "Disposable Humanity", "display_title": "Disposable Humanity", "crew": {"director": "Cameron S. Mitchell", "cast": ["Cameron S. Mitchell", "David T. Mitchell", "Sharon L. Snyder", "Susanne Knittel", "Emma Mitchell"]}, "_discovery_source": "provider_availability_check", "_enrichment_attempts": 1, "_last_enrichment_attempt": "2026-09-11", "imdb_rating": "7.5", "letterboxd_score": null, "keywords": [], "_trailer_source": "gemini_playwright", "metacritic_score": "0", "_imdb_votes": 35, "_digital_date_source": "detection", "_needs_review": false, "_slop_reason": "score:1(no_wiki,good_imdb)", "_slop_confidence": "weak", "status": "available", "_enrichment_gaps": ["wikipedia", "letterboxd_score"], "reissue_label": null, "_reissue": false, "virtual_screening_info": {"platform": "Eventive", "screening_slug": "disposablehumanity", "screening_name": "Disposable Humanity", "available_start": "2026-09-04", "available_end": "2026-11-01", "discovered": "2026-09-11", "last_checked": "2026-10-06", "status": "expired"}, "filters": {"is_indie": false, "is_foreign": false, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": true, "is_series": false, "is_documentary": true, "auto_categorized": true, "manual_override": null}, "featured": false, "hidden": true},
 "1021848": {"id": "1021848", "title": "Queen at Sea", "bootstrap_date": false, "manually_corrected": false, "synopsis": "As advanced dementia erodes an older woman's ability to communicate her inner life, her husband and daughter struggle to act in her best interests, navigating love and the fragile boundaries between care, protection and autonomy.", "genres": ["Drama"], "runtime": 121, "year": 2026, "rt_score": "91%", "providers": {"rent": [], "buy": ["Fandango At Home"], "streaming": []}, "links": {"wikipedia": "https://en.wikipedia.org/wiki/Queen_at_Sea", "trailer": "https://www.youtube.com/watch?v=zOd6fouRRcc", "rt": "https://www.rottentomatoes.com/m/queen_at_sea", "justwatch": "https://www.justwatch.com/us/movie/queen-at-sea", "cast_wiki": {"Juliette Binoche": "https://en.wikipedia.org/wiki/Juliette_Binoche", "Tom Courtenay": "https://en.wikipedia.org/wiki/Tom_Courtenay", "Anna Calder-Marshall": "https://en.wikipedia.org/wiki/Anna_Calder-Marshall"}, "metacritic": "https://www.metacritic.com/movie/queen-at-sea/", "imdb": "https://www.imdb.com/title/tt27541205/", "letterboxd": "https://letterboxd.com/film/queen-at-sea"}, "watch_links": {}, "pre_order_links": [{"service": "Fandango At Home", "link": "https://athome.fandango.com/content/browse/details/Queen-at-Sea/5287829", "buy_price": "$14.99", "price": "$14.99"}], "_enrichment_status": "completed", "_discovered_at": "2026-10-31T14:16:33.364329", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/ueYawr1nldKchzyP8Q9KJpn31SK.jpg", "studio": "The Bureau", "budget": 0, "country": "United Kingdom", "original_language": "en", "original_title": "Queen at Sea", "display_title": "Queen at Sea", "crew": {"director": "Lance Hammer", "cast": ["Juliette Binoche", "Tom Courtenay", "Anna Calder-Marshall", "Florence Hunt", "Steven Cree"]}, "_discovery_source": "provider_availability_check", "_enrichment_attempts": 1, "_last_enrichment_attempt": "2026-10-31", "_is_preorder": true, "_buyonly_preorder": true, "imdb_rating": "7.6", "letterboxd_score": "3.8", "keywords": ["dementia", "autonomy", "consent"], "_wiki_language_count": 6, "_trailer_source": "gemini_playwright", "metacritic_score": "85", "_imdb_votes": 824, "_digital_date_source": "detection", "_needs_review": false, "_slop_reason": "score:-1(good_imdb)", "_slop_confidence": "weak", "status": "available", "_enrichment_gaps": ["watch_links"], "reissue_label": null, "_reissue": false, "filters": {"is_indie": true, "is_foreign": false, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": false, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "featured": false}
}
''')

# Beware Boiúna: a buy-only pre-order on the wall with real buy links and a passed TMDB date
# (2026-11-03). Verbatim: `git show 78303fd6:movie_tracking.json` / `git show 78303fd6:data.json`.
TRACKING_78303FD6[BEWARE] = json.loads(r'''{"title": "Beware Boiúna", "year": 2026, "status": "tracking", "intake_date": "2026-09-15", "providers": {"rent": [], "buy": ["Fandango At Home"], "streaming": []}, "intake_pass": "C", "festival": "Fantastic Fest", "has_providers": true, "_discovery_source": "tmdb_type4", "enriched": true, "enrichment_date": "2026-11-13", "_transitioned_at": "2026-11-13", "_buyonly_preorder": true, "_is_preorder": true, "is_slop": true}''')
WALL_78303FD6[BEWARE] = json.loads(r'''{"id": "1244523", "title": "Beware Boiúna", "bootstrap_date": false, "manually_corrected": false, "synopsis": "A medical mission deep in the Amazon becomes a desperate fight for survival when a colossal ancient predator awakens, turning the jungle into a deadly battleground where nature decides who lives and dies.", "genres": ["Horror", "Thriller", "Action"], "runtime": 104, "year": 2026, "rt_score": null, "providers": {"rent": [], "buy": ["Fandango At Home"], "streaming": []}, "links": {"wikipedia": "https://en.wikipedia.org/wiki/Beware_Boi%C3%BAna", "trailer": "https://www.youtube.com/watch?v=4fn4UcgzRhg", "rt": null, "justwatch": "https://www.justwatch.com/us/movie/titan-2024", "cast_wiki": {"Kiana Madeira": "https://en.wikipedia.org/wiki/Kiana_Madeira", "Jessica Rothe": "https://en.wikipedia.org/wiki/Jessica_Rothe"}, "metacritic": "https://www.metacritic.com/movie/beware-boiuna/", "imdb": "https://www.imdb.com/title/tt10377864/", "letterboxd": "https://letterboxd.com/film/beware-boiuna", "director_wiki": "https://en.wikipedia.org/wiki/Mike_P._Nelson", "trailer_hosted": "https://f004.backblazeb2.com/file/NRW-TRAILERS/1244523.mp4"}, "watch_links": {"vod": [{"service": "Amazon", "link": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb&tag=nrw04-20", "buy_price": "$14.99", "price": "$14.99"}, {"service": "Apple TV", "link": "https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6812862855", "buy_price": "$14.99", "price": "$14.99"}, {"service": "Fandango", "link": "https://athome.fandango.com/content/browse/details/Beware-Boi-na/5214925", "buy_price": "$14.99", "price": "$14.99"}]}, "pre_order_links": [{"service": "Amazon Video", "link": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb&tag=nrw04-20", "buy_price": "$14.99", "price": "$14.99"}, {"service": "Apple TV Store", "link": "https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6812862855", "buy_price": "$14.99", "price": "$14.99"}, {"service": "Fandango At Home", "link": "https://athome.fandango.com/content/browse/details/Beware-Boi-na/5214925", "buy_price": "$14.99", "price": "$14.99"}], "_enrichment_status": "completed", "_discovered_at": "2026-11-05T16:14:02.415462", "_tmdb_fetch_failed": false, "_minimal_entry": false, "poster": "https://image.tmdb.org/t/p/w500/uW5YMPxJUzT9bkafrCKHXjPTCoQ.jpg", "studio": "Constantin Film", "budget": 0, "country": "United States of America", "original_language": "en", "original_title": "Beware Boiúna", "display_title": "Beware Boiúna", "crew": {"director": "Mike P. Nelson", "cast": ["Kiana Madeira", "Jessica Rothe", "Will Close", "Juan Pablo Shuk", "Logan Marshall-Green"]}, "_discovery_source": "tmdb_type4", "_is_preorder": true, "_enrichment_attempts": 8, "_last_enrichment_attempt": "2026-11-13", "_buyonly_preorder": true, "imdb_rating": "5.7", "letterboxd_score": "2.8", "keywords": ["animal attack", "giant snake", "amazon rainforest", "survival", "creature", "survival horror", "creature feature", "rainforest", "animal horror", "humanitarian work", "brazil", "brazilian folklore"], "_wiki_language_count": 5, "_trailer_source": "gemini_playwright", "metacritic_score": "49", "_imdb_votes": 3048, "_needs_review": false, "is_slop": true, "_slop_reason": "score:5(no_rt,low_imdb,no_rt_link)", "_slop_confidence": "weak", "status": "available", "_enrichment_gaps": ["watch_links", "rt_score"], "reissue_label": null, "_reissue": false, "filters": {"is_indie": false, "is_foreign": false, "is_staff_pick": false, "is_restoration": false, "is_virtual_screening": false, "is_series": false, "is_documentary": false, "auto_categorized": true, "manual_override": null}, "featured": false, "_watch_links_verified": "2026-11-13T16:43:29.139704", "_rt_retry_count": 3, "_rt_last_retry": "2026-11-06T07:00:44.098058", "digital_date": "2026-11-03", "_digital_date_source": "tmdb_type4"}''')


def today():
    return datetime.now().strftime('%Y-%m-%d')


def day(offset):
    return (datetime.now() + timedelta(days=offset)).strftime('%Y-%m-%d')


def stamp(offset, hour=5):
    """A JustWatch timestamp `offset` days from today (offset <= -1 is always in the past)."""
    return f'{day(offset)}T{hour:02d}:00:00Z'


# ---------------------------------------------------------------------------
# TMDB responses (GET /movie/{id}, /release_dates, /watch/providers)
# ---------------------------------------------------------------------------

TMDB = json.loads(r'''
{
 "1025835": {"details": {"id": 1025835, "title": "Prey of Wrath", "original_title": "Prey of Wrath", "original_language": "en", "release_date": "2026-05-01", "runtime": 79, "overview": "An elite special forces operative is sent by Russian Intelligence to hunt down former teammates who have hijacked nuclear warheads.", "poster_path": "/jeMmzpYBe2V0GYGpLfESlb2ZaVF.jpg", "budget": 0, "origin_country": ["US"], "genres": [{"id": 28, "name": "Action"}], "production_companies": [], "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}], "credits": {"cast": [{"name": "Tatiana Neva"}, {"name": "Cynthia Rothrock"}, {"name": "Gray Michael Sallies"}, {"name": "Louis DeStefano"}, {"name": "Leonard Zhang"}], "crew": [{"name": "Benny Tjandra", "job": "Director"}, {"name": "Doug Tochioka", "job": "Director"}]}, "external_ids": {"imdb_id": "tt13650572"}, "keywords": {"keywords": []}, "alternative_titles": {"results": []}, "videos": {"results": []}},
             "release_dates": {"id": 1025835, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 4, "release_date": "2026-05-01T00:00:00.000Z", "note": "Xumo Original"}]}]}},
 "1396875": {"details": {"id": 1396875, "title": "Wildcards", "original_title": "Wildcards", "original_language": "en", "release_date": "2026-08-27", "runtime": 110, "overview": "A jury deliberating the case of Theodore Sterling, a privileged young man accused of sexual assault of a 20-something African-American woman.", "poster_path": "/r7E2txDoZf7dxXR6BaZurvehTtx.jpg", "budget": 0, "origin_country": ["US"], "genres": [{"id": 53, "name": "Thriller"}], "production_companies": [{"id": 134677, "name": "Dark Star Pictures"}, {"id": 154444, "name": "Blacklight Pictures"}], "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}], "credits": {"cast": [{"name": "Leon"}, {"name": "Crew Morrow"}, {"name": "Elise Neal"}, {"name": "Aries Spears"}, {"name": "Stakiah Lynn Washington"}], "crew": [{"name": "Wes Miller", "job": "Director"}]}, "external_ids": {"imdb_id": "tt34375923"}, "keywords": {"keywords": [{"id": 214780, "name": "courtroom drama"}]}, "alternative_titles": {"results": []}, "videos": {"results": []}},
             "release_dates": {"id": 1396875, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 2, "release_date": "2026-08-27T00:00:00.000Z", "note": ""}, {"type": 4, "release_date": "2026-11-09T00:00:00.000Z", "note": ""}]}]}},
 "1814862": {"details": {"id": 1814862, "title": "Apple Music Live: Troye Sivan", "original_title": "Apple Music Live: Troye Sivan", "original_language": "en", "release_date": "2026-10-13", "runtime": 60, "overview": "Australian pop star Troye Sivan performs an exclusive, intimate live performance at Apple Music Hall in London's Battersea Power Station on October 13, 2026.", "poster_path": "/smt1q3xEtjubVj0hPLHJ48xUFt7.jpg", "budget": 0, "origin_country": ["US"], "genres": [{"id": 10402, "name": "Music"}], "production_companies": [], "production_countries": [], "credits": {"cast": [{"name": "Troye Sivan"}], "crew": []}, "external_ids": {"imdb_id": null}, "keywords": {"keywords": []}, "alternative_titles": {"results": []}, "videos": {"results": []}},
             "release_dates": {"id": 1814862, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 4, "release_date": "2026-10-13T00:00:00.000Z", "note": ""}]}]}},
 "1421634": {"details": {"id": 1421634, "title": "Sukma", "original_title": "Sukma", "original_language": "id", "release_date": "2025-09-11", "runtime": 108, "overview": "Arini and her family went to a small town to start a new life, but it turns into a disaster after they find an ancient mirror in a secret warehouse.", "poster_path": "/qL2mNWO116SSL9x40szobFsXlsS.jpg", "budget": 0, "origin_country": ["ID"], "genres": [{"id": 27, "name": "Horror"}, {"id": 53, "name": "Thriller"}], "production_companies": [{"id": 191451, "name": "Tiger Wong Entertainment"}, {"id": 46840, "name": "Legacy Pictures"}], "production_countries": [{"iso_3166_1": "ID", "name": "Indonesia"}], "credits": {"cast": [{"name": "Luna Maya"}, {"name": "Christine Hakim"}, {"name": "Fedi Nuril"}, {"name": "Oka Antara"}, {"name": "Anna Jobling"}], "crew": [{"name": "Baim Wong", "job": "Director"}]}, "external_ids": {"imdb_id": "tt35514142"}, "keywords": {"keywords": [{"id": 6152, "name": "supernatural"}, {"id": 162846, "name": "ghost"}]}, "alternative_titles": {"results": []}, "videos": {"results": []}},
             "release_dates": {"id": 1421634, "results": []}},
 "1405007": {"details": {"id": 1405007, "title": "Lemonade Blessing", "original_title": "Lemonade Blessing", "original_language": "en", "release_date": "2025-06-05", "runtime": 100, "overview": "Freshly tossed into private Catholic high school by his recently divorced mother, John must go from good boy to heinous sinner when he falls for a girl who requires him to commit sacrilegious acts in order to further their relationship.", "poster_path": "/37JG9YGKOQGOlBURGAhdYOzL5rQ.jpg", "budget": 0, "origin_country": ["US"], "genres": [{"id": 18, "name": "Drama"}, {"id": 35, "name": "Comedy"}], "production_companies": [], "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}], "credits": {"cast": [{"name": "Jake Ryan"}, {"name": "Jeanine Serralles"}, {"name": "Skye Alyssa Friedman"}, {"name": "Miles J. Harvey"}, {"name": "Michael Oloyede"}], "crew": [{"name": "Chris Merola", "job": "Director"}]}, "external_ids": {"imdb_id": "tt32432676"}, "keywords": {"keywords": []}, "alternative_titles": {"results": []}, "videos": {"results": []}},
             "release_dates": {"id": 1405007, "results": [{"iso_3166_1": "US", "release_dates": [{"type": 1, "release_date": "2025-06-05T00:00:00.000Z", "note": "Tribeca Festival"}, {"type": 4, "release_date": "2026-04-29T00:00:00.000Z", "note": "Letterboxd Video Store - Unreleased Gems (30 days)"}]}]}}
}
''')


def _details(mid, title, release, runtime, director, language='en', original_title=None):
    """Trimmed TMDB details for a film whose full response was not captured."""
    return {'id': int(mid), 'title': title, 'original_title': original_title or title,
            'original_language': language, 'release_date': release, 'runtime': runtime,
            'overview': f'{title}.', 'poster_path': f'/{mid}.jpg', 'budget': 0,
            'origin_country': ['US'], 'genres': [{'id': 18, 'name': 'Drama'}],
            'production_companies': [], 'production_countries': [],
            'credits': {'cast': [{'name': 'Cast Member'}], 'crew': [{'name': director, 'job': 'Director'}]},
            'external_ids': {'imdb_id': None}, 'keywords': {'keywords': []},
            'alternative_titles': {'results': []}, 'videos': {'results': []}}


def _us_dates(mid, *pairs):
    """TMDB /release_dates with these US (type, YYYY-MM-DD) entries."""
    rel = [{'type': t, 'release_date': f'{d}T00:00:00.000Z', 'note': ''} for t, d in pairs]
    return {'id': int(mid), 'results': [{'iso_3166_1': 'US', 'release_dates': rel}] if rel else []}


TMDB[SENSE] = {'details': _details(SENSE, 'Sense and Sensibility', '2026-10-16', 115, 'Georgia Oakley'),
               # real US release dates (scratchpad/live/tmdb1.json, fetched 2026-11-14)
               'release_dates': _us_dates(SENSE, (1, '2026-10-10'), (1, '2026-10-07'), (1, '2026-10-29'),
                                          (3, '2026-10-16'), (4, '2026-11-03'), (5, '2026-12-15'))}
TMDB[AFTER_DEATH] = {'details': _details(AFTER_DEATH, 'After This Death', '2025-02-15', 96, 'Lucio Castro'),
                     # SYNTHETIC: TMDB moves its digital date from 2026-11-20 to the day the test runs
                     'release_dates': _us_dates(AFTER_DEATH, (4, day(0)))}
TMDB[VILE] = {'details': _details(VILE, 'The Vile', '2025-09-20', 97, 'Majid al-Ansari', 'ar', 'حوبة'),
              # SYNTHETIC: same date move as After This Death
              'release_dates': _us_dates(VILE, (4, day(0)))}
TMDB[DISPOSABLE] = {'details': _details(DISPOSABLE, 'Disposable Humanity', '2025-09-04', 95, 'Cameron S. Mitchell'),
                    'release_dates': _us_dates(DISPOSABLE)}
TMDB[QUEEN] = {'details': _details(QUEEN, 'Queen at Sea', '2026-02-15', 121, 'Lance Hammer'),
               'release_dates': _us_dates(QUEEN)}


def _tmdb_providers(mid, **kinds):
    """TMDB /watch/providers with US {kind: [provider names]} (kind: flatrate/rent/buy)."""
    us = {'link': f'https://www.themoviedb.org/movie/{mid}/watch?locale=US'}
    for kind, names in kinds.items():
        us[kind] = [{'provider_id': i + 1, 'provider_name': n, 'display_priority': i + 1}
                    for i, n in enumerate(names)]
    return {'id': int(mid), 'results': {'US': us}}


TMDB_PROVIDERS = {
    SUKMA: _tmdb_providers(SUKMA, flatrate=['Screambox Amazon Channel']),   # the provider its row lists
    DISPOSABLE: _tmdb_providers(DISPOSABLE, rent=['Eventive']),             # the provider its row lists
    QUEEN: _tmdb_providers(QUEEN, buy=['Fandango At Home']),                # the provider its row lists
    BEWARE: _tmdb_providers(BEWARE, buy=['Fandango At Home']),              # the provider its row lists
}
# Beware Boiúna: trimmed details from its wall entry (release_date SYNTHETIC); its Type 4 date is
# the wall entry's tmdb_type4 digital_date.
TMDB[BEWARE] = {'details': _details(BEWARE, 'Beware Boiúna', '2026-09-18', 104, 'Mike P. Nelson'),
                'release_dates': _us_dates(BEWARE, (4, '2026-11-03'))}

# ---------------------------------------------------------------------------
# JustWatch search results (popularTitles nodes), keyed by search query
# ---------------------------------------------------------------------------

JW_NODES = json.loads(r'''
{
 "Prey of Wrath": [{"id": "tm1021106", "objectId": 1021106, "objectType": "MOVIE", "content": {"title": "Prey of Wrath", "originalReleaseYear": 2026, "fullPath": "/us/movie/prey-of-wrath", "externalIds": {"tmdbId": "1025835"}, "credits": [{"role": "DIRECTOR", "name": "Doug Tochioka"}, {"role": "DIRECTOR", "name": "Benny Tjandra"}]}, "offers": [
   {"monetizationType": "ADS", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://play.xumo.com/free-movies/prey-of-wrath/XM0O3DBA74F505", "availableFromTime": null, "package": {"clearName": "Xumo Play", "technicalName": "xumoplay"}},
   {"monetizationType": "ADS", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://play.xumo.com/free-movies/prey-of-wrath/XM0O3DBA74F505", "availableFromTime": null, "package": {"clearName": "Xumo Play", "technicalName": "xumoplay"}},
   {"monetizationType": "RENT", "presentationType": "SD", "retailPrice": "$4.99", "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.ed1ac374-8a37-4a08-95d3-8be3e6409461", "availableFromTime": "2026-07-08T13:13:43Z", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}},
   {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$5.99", "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.ed1ac374-8a37-4a08-95d3-8be3e6409461", "availableFromTime": "2026-07-08T13:13:43Z", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}},
   {"monetizationType": "BUY", "presentationType": "SD", "retailPrice": "$8.99", "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.ed1ac374-8a37-4a08-95d3-8be3e6409461", "availableFromTime": "2026-07-08T13:13:43Z", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}},
   {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$9.99", "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.ed1ac374-8a37-4a08-95d3-8be3e6409461", "availableFromTime": "2026-07-08T13:13:43Z", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}}]}],
 "Wildcards": [{"id": "tm2949112", "objectId": 2949112, "objectType": "MOVIE", "content": {"title": "Wildcards", "originalReleaseYear": 2026, "fullPath": "/us/movie/wildcards", "externalIds": {"tmdbId": "1396875"}, "credits": [{"role": "DIRECTOR", "name": "Wes Miller"}]}, "offers": []}],
 "Wildcards (other films only)": [
   {"id": "tm1679179", "objectId": 1679179, "objectType": "MOVIE", "content": {"title": "Tilda Swinton: The Wildcards", "originalReleaseYear": 2025, "fullPath": "/us/movie/tilda-swinton-the-wildcards", "externalIds": {"tmdbId": null}, "credits": []}, "offers": [{"monetizationType": "FREE", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://fawesome.tv/movies/10760375/tilda-swinton-the-wildcards?utm_source=justwatch&utm_medium=feed", "availableFromTime": "2026-02-11T05:00:00Z", "package": {"clearName": "Fawesome", "technicalName": "fawesometv"}}]},
   {"id": "tm1868659", "objectId": 1868659, "objectType": "MOVIE", "content": {"title": "Jack Nicholson: The Wildcards", "originalReleaseYear": 2025, "fullPath": "/us/movie/jack-nicholson-the-wildcards", "externalIds": {"tmdbId": null}, "credits": []}, "offers": [{"monetizationType": "FLATRATE", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.fubo.tv/welcome/program/SH060923190000", "availableFromTime": "2025-12-01T00:00:00Z", "package": {"clearName": "fuboTV", "technicalName": "fubotv"}}]}],
 "Sukma": [{"id": "tm1657865", "objectId": 1657865, "objectType": "MOVIE", "content": {"title": "Sukma", "originalReleaseYear": 2025, "fullPath": "/us/movie/sukma", "externalIds": {"tmdbId": "1421634"}, "credits": [{"role": "DIRECTOR", "name": "Baim Wong"}]}, "offers": [
   {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.7807a066-4a24-45b9-bfa4-14914ebac370", "availableFromTime": "2026-11-10T05:00:00Z", "package": {"clearName": "Screambox Amazon Channel", "technicalName": "amazonscreambox"}},
   {"monetizationType": "FLATRATE", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.7807a066-4a24-45b9-bfa4-14914ebac370", "availableFromTime": "2026-11-10T05:00:00Z", "package": {"clearName": "Screambox Amazon Channel", "technicalName": "amazonscreambox"}}]}],
 "Lemonade Blessing": [{"id": "tm1624555", "objectId": 1624555, "objectType": "MOVIE", "content": {"title": "Lemonade Blessing", "originalReleaseYear": 2025, "fullPath": "/us/movie/lemonade-blessing", "externalIds": {"tmdbId": "1405007"}, "credits": []}, "offers": [
   {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.fandango.com/lemonade-blessing-242868/movie-overview", "availableFromTime": null, "package": {"clearName": "Fandango", "technicalName": "fandango"}}]}],
 "Apple Music Live: Troye Sivan": [
   {"id": "tm1898699", "objectId": 1898699, "objectType": "MOVIE", "content": {"title": "Apple Music Live: Gracie Abrams", "originalReleaseYear": 2025, "fullPath": "/us/movie/apple-music-live-gracie-abrams", "externalIds": {"tmdbId": "1565821"}, "credits": []}, "offers": []},
   {"id": "tm1419695", "objectId": 1419695, "objectType": "MOVIE", "content": {"title": "Apple Music Live: Peso Pluma", "originalReleaseYear": 2023, "fullPath": "/us/movie/apple-music-live-peso-pluma", "externalIds": {"tmdbId": "1214702"}, "credits": []}, "offers": []},
   {"id": "tm1932018", "objectId": 1932018, "objectType": "MOVIE", "content": {"title": "Apple Music Live: Fred Again..", "originalReleaseYear": 2025, "fullPath": "/us/movie/apple-music-live-fred-again", "externalIds": {"tmdbId": "1600578"}, "credits": []}, "offers": []}],
 "Oppenheimer": [{"id": "tm1111989", "objectId": 1111989, "objectType": "MOVIE", "content": {"title": "Oppenheimer", "originalReleaseYear": 2023, "fullPath": "/us/movie/oppenheimer", "externalIds": {"tmdbId": "872585"}, "credits": [{"role": "DIRECTOR", "name": "Christopher Nolan"}]}, "offers": [
   {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.peacocktv.com/watch/asset/movies/oppenheimer/602fd345-3ad6-33fd-a70d-a0e059b8d38a", "availableFromTime": "2026-08-16T10:00:00Z", "package": {"clearName": "Peacock Premium", "technicalName": "peacocktv"}}]}],
 "Barbie": [{"id": "tm244331", "objectId": 244331, "objectType": "MOVIE", "content": {"title": "Barbie", "originalReleaseYear": 2023, "fullPath": "/us/movie/barbie-2023", "externalIds": {"tmdbId": "346698"}, "credits": [{"role": "DIRECTOR", "name": "Greta Gerwig"}]}, "offers": [
   {"monetizationType": "FLATRATE", "presentationType": "SD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.5750ee96-eb59-40c3-bda6-96904811a3a2", "availableFromTime": "2026-08-29T23:00:00Z", "package": {"clearName": "HBO Max Amazon Channel", "technicalName": "amazonhbomax"}}]}],
 "Dune: Part Two": [{"id": "tm1133934", "objectId": 1133934, "objectType": "MOVIE", "content": {"title": "Dune: Part Two", "originalReleaseYear": 2024, "fullPath": "/us/movie/dune-part-two-2023", "externalIds": {"tmdbId": "693134"}, "credits": [{"role": "DIRECTOR", "name": "Denis Villeneuve"}]}, "offers": [
   {"monetizationType": "FLATRATE", "presentationType": "HD", "retailPrice": null, "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.9392c069-96f9-421b-ac7a-275308e1327a", "availableFromTime": "2024-05-21T07:01:00Z", "package": {"clearName": "HBO Max Amazon Channel", "technicalName": "amazonhbomax"}}]}],
 "Sense and Sensibility": [{"id": "tm1918108", "objectId": 1918108, "objectType": "MOVIE", "content": {"title": "Sense and Sensibility", "originalReleaseYear": 2026, "fullPath": "/us/movie/sense-and-sensibility-2026", "externalIds": {"tmdbId": "1503762"}, "credits": [{"role": "DIRECTOR", "name": "Georgia Oakley"}]}, "offers": [
   {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.atomtickets.com/movies/sense-and-sensibility-2026/395156", "availableFromTime": null, "package": {"clearName": "Atom Tickets", "technicalName": "atomtickets"}},
   {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "currency": "USD", "standardWebURL": "http://www.cinemark.com/movies/sense-and-sensibility", "availableFromTime": null, "package": {"clearName": "Cinemark", "technicalName": "cinemark"}},
   {"monetizationType": "CINEMA", "presentationType": "CANVAS", "retailPrice": null, "currency": "USD", "standardWebURL": "https://www.regmovies.com/movies/sense-and-sensibility-ho00021990", "availableFromTime": null, "package": {"clearName": "Regal Cinemas", "technicalName": "regalcinemas"}},
   {"monetizationType": "BUY", "presentationType": "DVD", "retailPrice": "$17.95", "currency": "USD", "standardWebURL": "https://www.amazon.com/dp/B0HKMFS3VK?tag=justwatch09-20&linkCode=osi&th=1&psc=1", "availableFromTime": null, "package": {"clearName": "Amazon DVD / Blu-ray", "technicalName": "amazondvdbr"}},
   {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}},
   {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "currency": "USD", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1", "availableFromTime": "2026-10-16T07:00:00Z", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}},
   {"monetizationType": "RENT", "presentationType": "HD", "retailPrice": "$19.99", "currency": "USD", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}},
   {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "currency": "USD", "standardWebURL": "https://watch.amazon.com/detail?gti=amzn1.dv.gti.d728f8e3-ed57-40f8-80e2-3748f395ddb3", "availableFromTime": "2026-11-03T05:00:00Z", "package": {"clearName": "Amazon Video", "technicalName": "amazon"}},
   {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "currency": "USD", "standardWebURL": "https://tv.apple.com/us/movie/sense-and-sensibility/umc.cmc.2im3cnmcte1hgfna1hkt7wnzw?at=1", "availableFromTime": "2026-10-16T07:00:00Z", "package": {"clearName": "Apple TV Store", "technicalName": "itunes"}},
   {"monetizationType": "BUY", "presentationType": "HD", "retailPrice": "$24.99", "currency": "USD", "standardWebURL": "https://athome.fandango.com/content/browse/details/Sense-and-Sensibility/5276236", "availableFromTime": null, "package": {"clearName": "Fandango At Home", "technicalName": "vudu"}}]}]
}
''')
# The 2026-11-14 captures predate the dateCreated query field: real record dates unknown.
for _nodes in JW_NODES.values():
    for _node in _nodes:
        for _o in _node['offers']:
            _o.setdefault('dateCreated', None)

CANARY_QUERIES = ('Oppenheimer', 'Barbie', 'Dune: Part Two')  # ProviderDiscoverer._JW_CANARY_TITLES
ALL_CLOCKS = ('discoverer', 'putback', 'generator', 'enricher', 'justwatch', 'archive')
JW_PLACEHOLDER_DATE = '2000-07-14T00:00:00Z'  # JustWatch's no-record placeholder (pipeline/justwatch.py)


def _offer(mtype, service, technical, url, price=None, ptype='HD', available_from=None, created=None):
    """One JustWatch offer, in the exact shape the GraphQL API returns (v2 also reads
    dateCreated: the day JustWatch first recorded the offer)."""
    return {'monetizationType': mtype, 'presentationType': ptype, 'retailPrice': price,
            'currency': 'USD', 'standardWebURL': url, 'availableFromTime': available_from,
            'dateCreated': created, 'package': {'clearName': service, 'technicalName': technical}}


def jw_node(query, extra_offers=(), drop_cinema=False, created=None):
    """The real JustWatch node for `query` (first result), optionally with SYNTHETIC
    offers appended ("the day JustWatch lists it") or SYNTHETIC record dates stamped on
    its captured offers (`created`: {technicalName: dateCreated})."""
    node = copy.deepcopy(JW_NODES[query][0])
    if drop_cinema:
        node['offers'] = [o for o in node['offers'] if o['monetizationType'] != 'CINEMA']
    for o in node['offers']:
        tech = o['package']['technicalName']
        if created and tech in created:
            o['dateCreated'] = created[tech]
    node['offers'].extend(copy.deepcopy(list(extra_offers)))
    return node


def synthetic_node(mid, title, year, slug, offers=(), director=None):
    """A SYNTHETIC JustWatch node for a film whose search result was not captured."""
    return {'id': f'tm9{mid}', 'objectId': int(f'9{mid}'), 'objectType': 'MOVIE',
            'content': {'title': title, 'originalReleaseYear': year, 'fullPath': f'/us/movie/{slug}',
                        'externalIds': {'tmdbId': str(mid)},
                        'credits': [{'role': 'DIRECTOR', 'name': director}] if director else []},
            'offers': copy.deepcopy(list(offers))}


def amazon_rental(mid, price='$5.99', available_from=None, created=None, buy=None):
    """SYNTHETIC Amazon Video rental (and optional purchase) for film `mid`."""
    url = f'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-{int(mid):012d}'
    offers = [_offer('RENT', 'Amazon Video', 'amazon', url, price=price,
                     available_from=available_from, created=created)]
    if buy:
        offers.append(_offer('BUY', 'Amazon Video', 'amazon', url, price=buy,
                             available_from=available_from, created=created))
    return offers


def amazon_placeholder(created=None):
    """SYNTHETIC Amazon rent/buy offers whose link is Amazon's placeholder page
    (constants.PLACEHOLDER_ASINS): verified by JustWatch, but no usable watch link."""
    from constants import PLACEHOLDER_ASINS
    url = f'https://www.amazon.com/gp/video/detail/{PLACEHOLDER_ASINS[0]}'
    return [_offer('RENT', 'Amazon Video', 'amazon', url, price='$4.99', created=created),
            _offer('BUY', 'Amazon Video', 'amazon', url, price='$9.99', created=created)]


EVENTIVE_LINK = WALL_78303FD6[DISPOSABLE]['watch_links']['vod'][0]['link']


def eventive_rental(created='2026-09-04T05:00:00Z'):
    """Disposable Humanity's own (expired) Eventive screening page, which JustWatch
    lists as a "rental" (Nov 2026, pipeline/discoverer.py FESTIVAL_PLATFORMS)."""
    return _offer('RENT', 'Eventive', 'eventive', EVENTIVE_LINK, price='$19.39', created=created)


# What verify_availability returns for a title mismatch (pipeline/justwatch.py, the
# 'first_result' branch). The real search only returns title / TMDB-id matches, so the
# client-level fake below feeds this documented shape directly.
TITLE_MISMATCH = {'verified': False, 'match_confidence': 'first_result',
                  'jw_title': 'Tilda Swinton: The Wildcards', 'jw_year': 2025,
                  'has_streaming': False, 'has_rent': False, 'has_buy': False,
                  'provider_names': {'streaming': [], 'rent': [], 'buy': []}, 'watch_links': {}}


# ---------------------------------------------------------------------------
# Network fakes
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ''
        self.content = self.text.encode()
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError('no JSON body')
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f'{self.status_code} error', response=self)


class FakeTMDB:
    """api.themoviedb.org for the films under test."""

    _URL = re.compile(r'^https://api\.themoviedb\.org/3/movie/(\d+)(/release_dates|/watch/providers)?/?$')

    def __init__(self):
        self.details, self.release_dates, self.providers = {}, {}, {}
        self.down = set()          # endpoints answering 503: {'details', 'release_dates', 'providers'}
        self.calls = []
        for mid, fx in TMDB.items():
            self.details[mid] = copy.deepcopy(fx['details'])
            self.release_dates[mid] = copy.deepcopy(fx['release_dates'])
        self.providers = copy.deepcopy(TMDB_PROVIDERS)

    def handles(self, url):
        return bool(self._URL.match(url))

    def get(self, url):
        mid, sub = self._URL.match(url).groups()
        endpoint = {'/release_dates': 'release_dates', '/watch/providers': 'providers'}.get(sub, 'details')
        self.calls.append((mid, endpoint))
        if endpoint in self.down:
            return FakeResponse(503, {'status_message': 'Service Unavailable'})
        if endpoint == 'release_dates':
            return FakeResponse(200, self.release_dates.get(mid, {'id': int(mid), 'results': []}))
        if endpoint == 'providers':
            return FakeResponse(200, self.providers.get(mid, {'id': int(mid), 'results': {}}))
        if mid in self.details:
            return FakeResponse(200, self.details[mid])
        return FakeResponse(404, {'status_message': 'The resource you requested could not be found.'})


class FakeJustWatch:
    """apis.justwatch.com/graphql. `mode` models JustWatch's state:
      up               -- answers from `catalog` (search query -> nodes)
      connection_error -- the request fails (network/DNS/timeout)
      graphql_errors   -- HTTP 200 with a GraphQL `errors` body (throttling)
      malformed        -- HTTP 200, but the matched node's offers come back null
      blocked          -- HTTP 200 with zero results for EVERY query (datacenter-IP block)
      empty_offers     -- HTTP 200, every title found but with NO offers (an offers-only
                          outage: canary titles included)
    `failing`: search queries whose requests fail (connection error) whatever the mode --
    a lookup that errors for one film while JustWatch answers for the others.
    """

    URL = 'https://apis.justwatch.com/graphql'

    def __init__(self):
        self.catalog = {q: copy.deepcopy(nodes) for q, nodes in JW_NODES.items()
                        if q in CANARY_QUERIES}
        self.mode = 'up'
        self.failing = set()
        self.queries = []           # (mode, search query) in call order

    def post(self, body):
        q = ((body or {}).get('variables') or {}).get('searchQuery')
        self.queries.append(('connection_error' if q in self.failing else self.mode, q))
        if self.mode == 'connection_error' or q in self.failing:
            raise requests.exceptions.ConnectionError(
                "HTTPSConnectionPool(host='apis.justwatch.com', port=443): Max retries exceeded")
        if self.mode == 'graphql_errors':
            return FakeResponse(200, {'errors': [{'message': 'Too many requests'}], 'data': None})
        if self.mode == 'blocked':
            return FakeResponse(200, {'data': {'popularTitles': {'edges': []}}})
        nodes = copy.deepcopy(self.catalog.get(q, []))
        if self.mode == 'malformed':
            for n in nodes:
                n['offers'] = None
        if self.mode == 'empty_offers':
            for n in nodes:
                n['offers'] = []
        return FakeResponse(200, {'data': {'popularTitles': {'edges': [{'node': n} for n in nodes]}}})

    def queried(self, query, mode=None):
        return any(q == query and (mode is None or m == mode) for m, q in self.queries)

    def count(self, query):
        return sum(1 for _, q in self.queries if q == query)


class FakeVodScraper:
    """Stands in for streaming_platform_scraper.StreamingPlatformScraper (Playwright)."""
    timeout_seconds = 10
    rate_limit_seconds = 0

    def __init__(self):
        self.links = {}             # (title, provider) -> deep link the store page shows
        self.calls = []

    def get_platform_deep_link(self, title, year, provider):
        self.calls.append((title, provider))
        return self.links.get((title, provider))

    def find_amazon_link(self, title, year, director=None):
        self.calls.append((title, 'amazon pre-order'))
        return None

    def find_fandango_link(self, title, year, director=None):
        self.calls.append((title, 'fandango pre-order'))
        return None


class FakeAgentScraper:
    """Stands in for agent_link_scraper.AgentLinkScraper (Playwright)."""

    def __init__(self):
        self.calls = []

    def find_watch_link(self, movie_id, title, year, service):
        self.calls.append((title, service))
        return {'link': None}


# Host methods that are pure network fetchers (Wikipedia, YouTube/Claude trailer search,
# RT/Letterboxd/Metacritic Playwright scrapers, OMDb, IMDb dataset, B2 upload). Faked as
# "nothing found", which is a normal enrichment outcome.
HOST_NETWORK_FETCHERS = (
    'find_wikipedia_url', 'find_director_wikipedia_url', 'find_cast_wikipedia_url',
    'find_trailer_url', 'find_rt_url', 'find_metacritic_score', 'find_letterboxd_score',
    'get_omdb_data', 'get_imdb_from_omdb', 'get_imdb_rating', 'get_imdb_votes',
    'host_trailer_for_movie',
)


def _sanitized_config():
    """The worktree's real config.yaml with API secrets replaced (read-only access)."""
    with open(f'{WT}/config.yaml') as f:
        cfg = yaml.safe_load(f)
    for k in list((cfg.get('api') or {})):
        if k.endswith('_key'):
            cfg['api'][k] = f'test-{k}-not-real'
    return cfg


# ---------------------------------------------------------------------------
# Write guard: no write may land in any NRW checkout
# ---------------------------------------------------------------------------

def _install_write_guard(mp, hits):
    import builtins
    import os
    import shutil
    import sqlite3
    protected = tuple(os.path.realpath(p) for p in _PROTECTED_CHECKOUTS)

    def is_protected(path):
        try:
            raw = path.decode() if isinstance(path, bytes) else os.fspath(path)
        except TypeError:
            return False
        return os.path.realpath(raw).startswith(protected)

    real_open = builtins.open

    def guarded_open(file, mode='r', *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)) and any(c in mode for c in 'wax+') \
                and is_protected(file):
            hits.append(('open', str(file), mode))
            raise PermissionError(f'write blocked by test guard: {file}')
        return real_open(file, mode, *a, **k)
    mp.setattr(builtins, 'open', guarded_open)
    mp.setattr(io, 'open', guarded_open)

    def wrap(module, name):
        real = getattr(module, name)

        def guarded(*a, **k):
            if any(is_protected(x) for x in a[:2] if isinstance(x, (str, bytes, os.PathLike))):
                hits.append((name, str(a[:2])))
                raise PermissionError(f'{name} blocked by test guard: {a[:2]}')
            return real(*a, **k)
        mp.setattr(module, name, guarded)

    for name in ('replace', 'rename', 'remove', 'unlink', 'rmdir', 'makedirs', 'mkdir'):
        wrap(os, name)
    for name in ('move', 'copy', 'copy2', 'copyfile', 'rmtree', 'copytree'):
        wrap(shutil, name)
    real_connect = sqlite3.connect

    def guarded_connect(db, *a, **k):
        if isinstance(db, (str, bytes, os.PathLike)) and is_protected(db):
            hits.append(('sqlite3.connect', str(db)))
            raise PermissionError(f'sqlite connect blocked by test guard: {db}')
        return real_connect(db, *a, **k)
    mp.setattr(sqlite3, 'connect', guarded_connect)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class _Clock:
    """Stands in for the `time` module inside pipeline/enricher.py: time() can jump."""

    def __init__(self, real):
        self._real = real
        self.offset = 0.0

    def time(self):
        return self._real.time() + self.offset

    def __getattr__(self, name):
        return getattr(self._real, name)


class Pipeline:
    """A throwaway NRW checkout: real pipeline code, tmp data files, faked network."""

    def __init__(self, root, monkeypatch):
        self.root = root
        self.mp = monkeypatch
        self.tmdb = FakeTMDB()
        self.jw = FakeJustWatch()
        self.vod = FakeVodScraper()
        self.escaped = []           # network attempts nobody faked -- must stay empty
        self.guard_hits = []        # writes into a real checkout -- must stay empty
        self.fetches = []           # host network-fetcher calls (name)
        self.page_checks = []       # Playwright store-page pre-order checks
        self.page_verdict = None    # what every store page reads (None: inconclusive)
        self.jw_calls = []          # (title, excluded services) per verify_availability call
        self.jw_answers = {}        # title -> canned verify_availability result

        (root / 'metrics').mkdir()
        with open(root / 'config.yaml', 'w') as f:
            yaml.safe_dump(_sanitized_config(), f)
        self._write('data.json', {'generated_at': datetime.now().isoformat(), 'count': 0,
                                  'movies': [], 'staff_picks': [], 'featured': []})
        self._write('movie_tracking.json', {'movies': {}})

        _install_write_guard(monkeypatch, self.guard_hits)
        monkeypatch.chdir(root)
        monkeypatch.setenv('TMDB_API_KEY', 'test-tmdb-key-not-real')
        self._install_network_fakes()

        import pipeline.tracking_db as tracking_db
        self.tdb = tracking_db.TrackingDB(db_path=str(root / 'movie_tracking.db'),
                                          json_path=str(root / 'movie_tracking.json'))
        monkeypatch.setattr(tracking_db, '_shared_instance', self.tdb)

        # setup_logger() only adds its logs/admin.log file handler to a logger with no
        # handlers. Give it a null one for this test, so the pipeline logger writes nowhere.
        monkeypatch.setattr(logging.getLogger('data_generator'), 'handlers', [logging.NullHandler()])

        # Network side effects inside otherwise-local steps: the distributor-lookup refresh
        # (Wikipedia + TMDB, and it writes the WORKTREE's cache/), the Wikipedia
        # interlanguage count, and the Eventive page fetches of the screening check.
        import scripts.build_distributor_lookup as bdl
        import pipeline.notability as notability
        import pipeline.generator as generator_mod
        monkeypatch.setattr(bdl, 'build_lookup', lambda *a, **k: {})
        monkeypatch.setattr(notability, 'wikipedia_language_count', lambda *a, **k: None)
        monkeypatch.setattr(generator_mod.DataGenerator, '_fetch_eventive_screening_info',
                            lambda self, slug: {}, raising=False)
        monkeypatch.setattr(generator_mod.DataGenerator, '_fetch_eventive_play_info',
                            lambda self, link: {}, raising=False)
        self._install_jw_spy()

    # -- setup ------------------------------------------------------------
    def _write(self, rel, obj):
        with open(self.root / rel, 'w') as f:
            json.dump(obj, f, indent=2)

    def _block(self, what, target):
        self.escaped.append((what, str(target)[:120]))
        raise OSError(f'network disabled in tests: {what} {target}')

    def _install_network_fakes(self):
        mp = self.mp
        tmdb, jw = self.tmdb, self.jw

        def fake_get(url, params=None, **kw):
            if tmdb.handles(url):
                return tmdb.get(url)
            if url.startswith('https://datasets.imdbws.com/'):
                return FakeResponse(404, None)        # IMDb bulk dataset unavailable
            self.escaped.append(('requests.get', url))
            raise requests.exceptions.ConnectionError(f'network disabled in tests: {url}')

        def fake_other(url, *a, **kw):
            self.escaped.append(('requests', url))
            raise requests.exceptions.ConnectionError(f'network disabled in tests: {url}')

        def fake_session_post(session, url, data=None, json=None, **kw):
            if url == jw.URL:
                return jw.post(json)
            self.escaped.append(('Session.post', url))
            raise requests.exceptions.ConnectionError(f'network disabled in tests: {url}')

        def fake_session_request(session, method, url, *a, **kw):
            self.escaped.append((f'Session.{method}', url))
            raise requests.exceptions.ConnectionError(f'network disabled in tests: {url}')

        mp.setattr(requests, 'get', fake_get)
        mp.setattr(requests, 'head', fake_other)
        mp.setattr(requests, 'post', fake_other)
        mp.setattr(requests.sessions.Session, 'post', fake_session_post)
        mp.setattr(requests.sessions.Session, 'request', fake_session_request)
        mp.setattr(socket.socket, 'connect', lambda s, addr: self._block('socket.connect', addr))
        mp.setattr(socket.socket, 'connect_ex', lambda s, addr: self._block('socket.connect_ex', addr))
        mp.setattr(socket, 'create_connection', lambda addr, *a, **k: self._block('socket.create_connection', addr))
        mp.setattr(socket, 'getaddrinfo', lambda host, *a, **k: self._block('dns', host))

    def _install_jw_spy(self):
        """Record every JustWatch verification (title + excluded services); answer from
        `jw_answers` when a test feeds a canned client result."""
        from pipeline.justwatch import JustWatchClient
        real = JustWatchClient.verify_availability
        env = self

        def spy(client, title, year=None, excluded_services=None, *args, **kwargs):
            env.jw_calls.append((title, tuple(excluded_services or ())))
            if title in env.jw_answers:
                return copy.deepcopy(env.jw_answers[title])
            return real(client, title, year, excluded_services, *args, **kwargs)
        self.mp.setattr(JustWatchClient, 'verify_availability', spy)

    def seed(self, *ids, **edits):
        """Put verbatim 78303fd6 tracking rows into the tmp tracking DB. `edits`:
        {id: {field: value or None (= drop the field)}} for a scenario's stated changes."""
        movies = {mid: copy.deepcopy(TRACKING_78303FD6[mid]) for mid in ids}
        for mid, change in edits.items():
            for k, v in change.items():
                if v is None:
                    movies[mid].pop(k, None)
                else:
                    movies[mid][k] = v
        existing = self.tdb.load_all().get('movies', {})
        existing.update(movies)
        self.tdb.save_all({'movies': existing}, export_json=True)

    def put_on_wall(self, *entries):
        data = json.load(open(self.root / 'data.json'))
        data['movies'] = [copy.deepcopy(e) for e in entries] + data['movies']
        self._write('data.json', data)

    def set_config(self, **sections):
        with open(self.root / 'config.yaml') as f:
            cfg = yaml.safe_load(f)
        cfg.update(sections)
        with open(self.root / 'config.yaml', 'w') as f:
            yaml.safe_dump(cfg, f)

    def new_generator(self):
        """A fresh DataGenerator, as each `generate_data.py --phase` process builds one."""
        from pipeline.generator import DataGenerator
        g = DataGenerator()
        agent = FakeAgentScraper()
        g.streaming_scraper = g.enrichment.streaming_scraper = agent
        g.vod_scraper = g.enrichment.vod_scraper = self.vod
        for name in HOST_NETWORK_FETCHERS:
            setattr(g, name, self._fetcher(name))

        def page_check(jw_result, title):
            self.page_checks.append(title)
            return self.page_verdict                     # default None: page inconclusive
        g._discoverer._check_preorder_page = page_check
        g._save_to_imdb_cache = lambda *a, **k: None
        g._imdb_rating_cache = {}
        return g

    def _fetcher(self, name):
        def fetch(*a, **k):
            self.fetches.append(name)
            return None
        return fetch

    def shift_clock(self, days, *modules):
        """Run the named pipeline modules (default: enrichment only) as if `days` days
        had passed."""
        real = _REAL_DATETIME

        class Shifted(real):
            @classmethod
            def now(cls, tz=None):
                return real.now(tz) + timedelta(days=days)
        for name in (modules or ('enricher',)):
            self.mp.setattr(importlib.import_module(f'pipeline.{name}'), 'datetime', Shifted)

    def next_day(self, days):
        """Every pipeline phase runs `days` days later (discovery included)."""
        self.shift_clock(days, *ALL_CLOCKS)

    def mark(self):
        """A bookmark into the JustWatch query log (see queried_since)."""
        return len(self.jw.queries)

    def queried_since(self, mark):
        return [q for _, q in self.jw.queries[mark:]]

    def move_to_end(self, mid):
        """Move a film's entry to the end of data.json (file order = catch-up scan order)."""
        data = json.load(open(self.root / 'data.json'))
        entry = next(m for m in data['movies'] if str(m.get('id')) == mid)
        data['movies'] = [m for m in data['movies'] if m is not entry] + [entry]
        self._write('data.json', data)

    # -- phases -----------------------------------------------------------
    def check_screenings(self):
        return self.new_generator().check_virtual_screening_expirations()

    def discover(self):
        return self.new_generator().check_tracking_movies()

    def enrich(self, timeout_after=None):
        """Enrichment. `timeout_after=n`: its loop timeout fires after n films (0 = at once),
        this run only."""
        g = self.new_generator()
        if timeout_after is None:
            return g.enrich_newly_available_movies()
        import pipeline.enricher as enricher_mod
        saved_limit, saved_time = enricher_mod.ENRICHMENT_LOOP_TIMEOUT_MINUTES, enricher_mod.time
        try:
            if timeout_after == 0:
                self.mp.setattr(enricher_mod, 'ENRICHMENT_LOOP_TIMEOUT_MINUTES', -1)
            else:
                clock = _Clock(saved_time)
                self.mp.setattr(enricher_mod, 'time', clock)
                real_details, seen = g.get_movie_details, []

                def details(movie_id):
                    seen.append(str(movie_id))
                    if len(seen) >= timeout_after:
                        clock.offset = 3 * 3600.0        # past ENRICHMENT_LOOP_TIMEOUT_MINUTES
                    return real_details(movie_id)
                g.get_movie_details = details
            return g.enrich_newly_available_movies()
        finally:
            self.mp.setattr(enricher_mod, 'ENRICHMENT_LOOP_TIMEOUT_MINUTES', saved_limit)
            self.mp.setattr(enricher_mod, 'time', saved_time)

    def archive_old(self):
        return self.new_generator().archive_old_movies()

    def nothing_new_today(self, date):
        """metrics/newly_available.json as discovery writes it on a day with no transitions."""
        self._write('metrics/newly_available.json', {'date': date, 'movie_ids': [], 'count': 0})

    def edit_wall_entry(self, mid, **fields):
        data = json.load(open(self.root / 'data.json'))
        for m in data['movies']:
            if str(m.get('id')) == mid:
                m.update(fields)
        self._write('data.json', data)

    def script(self, name):
        """A module from the worktree's scripts/ (read in the tmp checkout: cwd-relative files)."""
        scripts = f'{WT}/scripts'
        if scripts not in sys.path:
            self.mp.syspath_prepend(scripts)
        old = signal.getsignal(signal.SIGPIPE)
        try:
            mod = importlib.import_module(name)   # morning_report sets SIGPIPE to SIG_DFL on import
        finally:
            signal.signal(signal.SIGPIPE, old)
        assert mod.__file__.startswith(WT), mod.__file__
        return mod

    @staticmethod
    def printed(fn, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(*args)
        return buf.getvalue()

    def morning_report(self, section='overnight'):
        """scripts/morning_report.py --section <section>, run in the tmp checkout; its text."""
        return self.printed(getattr(self.script('morning_report'), section))

    def put_track(self, mid, rec):
        """Save one tracking record as a pipeline step would (tmp tracking DB + JSON export)."""
        movies = self.tdb.load_all().get('movies', {})
        movies[mid] = rec
        self.tdb.save_all({'movies': movies}, export_json=True)

    # -- what the owner sees --------------------------------------------
    def wall(self):
        data = json.load(open(self.root / 'data.json'))
        return {str(m.get('id')): m for m in data['movies']}

    def lane(self, mid):
        """Where the film shows: None (not in data.json), HIDDEN, PRE-ORDER or MAIN WALL."""
        e = self.wall().get(mid)
        if e is None:
            return None
        if e.get('hidden'):
            return 'HIDDEN'
        return 'PRE-ORDER' if e.get('_is_preorder') else 'MAIN WALL'

    def track(self, mid):
        return self.tdb.get(mid)

    def archived_ids(self):
        try:
            return {str(m.get('id')) for m in json.load(open(self.root / 'data_archive.json'))['movies']}
        except FileNotFoundError:
            return set()

    def deferred_reasons(self, title):
        run = json.load(open(self.root / 'metrics' / 'enrichment_run.json'))
        return [d['reason'] for d in run['deferred_details'] if d.get('title') == title]

    def excluded_for(self, title):
        """The excluded-services lists JustWatch was asked with for `title`, in call order."""
        return [excl for t, excl in self.jw_calls if t == title]


@pytest.fixture
def nrw(tmp_path, monkeypatch):
    env = Pipeline(tmp_path, monkeypatch)
    yield env
    assert env.escaped == [], f'pipeline tried to reach the real network: {env.escaped}'
    assert env.guard_hits == [], f'pipeline tried to write into a real checkout: {env.guard_hits}'


def _put_back_today(nrw, mid, query, node, **edits):
    """Discovery confirms a held film on JustWatch and puts it back on the wall. `edits`: as
    for nrw.seed."""
    nrw.seed(mid, **edits)
    nrw.jw.catalog[query] = [node]
    nrw.discover()
    rec = nrw.track(mid)
    assert rec['status'] == 'available' and mid in nrw.wall(), 'setup: discovery did not put it back'
    assert rec.get('_put_back_on') == today(), 'setup: not a put-back'
    return rec


def _graduating_preorder(nrw, mid, query, offers=()):
    """A non-held pending pre-order on the wall whose TMDB date moved to today: discovery
    lets it through without JustWatch ('preorder_graduation'), so enrichment's Step 0 is
    its only JustWatch check."""
    nrw.seed(mid)
    nrw.put_on_wall(WALL_78303FD6[mid])
    title = TRACKING_78303FD6[mid]['title']
    nrw.jw.catalog[query] = [synthetic_node(mid, title, TRACKING_78303FD6[mid]['year'],
                                            title.lower().replace(' ', '-'), offers)]
    nrw.discover()
    rec = nrw.track(mid)
    assert rec['status'] == 'available', 'setup: the pre-order did not graduate'
    assert not nrw.jw.queried(query), 'setup: expected the pre-order bypass to skip JustWatch'
    assert nrw.wall()[mid]['digital_date'] == today()
    return rec


# ---------------------------------------------------------------------------
# (0) The harness drives the v2 worktree
# ---------------------------------------------------------------------------

def test_harness_runs_the_v2_round2b_code(nrw):
    import pipeline.enricher as enricher_mod
    import pipeline.discoverer as discoverer_mod
    import pipeline.putback as putback_mod
    import pipeline.archive as archive_mod
    for mod in (enricher_mod, discoverer_mod, putback_mod, archive_mod):
        assert mod.__file__.startswith(WT + '/'), mod.__file__
    assert hasattr(enricher_mod.MovieEnricher, '_hide_unchecked_putbacks')
    assert hasattr(putback_mod, 'note_refuted') and putback_mod.OWNER_REVERT == 'owner_revert'
    assert discoverer_mod.FESTIVAL_PLATFORMS == ['Eventive', 'Shift72']
    assert nrw.script('curate_list').__file__.startswith(WT + '/')


# ---------------------------------------------------------------------------
# (a) A JustWatch error during enrichment is not an answer about the film
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('failure', ['connection_error', 'graphql_errors', 'malformed'])
def test_jw_error_on_a_this_run_arrival_hides_it_with_no_strike(nrw, failure):
    """Prey of Wrath (held since May, JustWatch now lists Xumo + Amazon) is put back by
    discovery; JustWatch then fails while enrichment re-checks it. It arrived this run,
    so it must wait HIDDEN (_jw_unconfirmed = today) -- never on the wall unconfirmed --
    with its tracking record untouched (no strike, no 'checked' stamp, not 'enriched')
    and its enrichment-attempt budget intact."""
    before = _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    entry0 = nrw.wall()[PREY]
    assert not entry0.get('hidden'), 'setup: discovery writes the put-back visible'

    nrw.jw.mode = failure
    nrw.enrich()

    assert nrw.jw.queried('Prey of Wrath', mode=failure), 'enrichment never asked JustWatch'
    entry = nrw.wall().get(PREY)
    assert entry is not None, 'film was pulled from the wall on a JustWatch error'
    assert entry.get('hidden') is True, 'unconfirmed film left visible on the wall'
    assert entry.get('_jw_unconfirmed') == today()
    assert entry.get('_enrichment_status') != 'reverted' and not entry.get('_jw_reverted')
    assert entry.get('_enrichment_attempts', 0) == entry0.get('_enrichment_attempts', 0), \
        'error used up an enrichment attempt'
    assert entry.get('_last_enrichment_attempt') == entry0.get('_last_enrichment_attempt'), \
        'error stamped an attempt (catch-up backoff would skip it)'
    assert nrw.track(PREY) == before, 'tracking record changed on a JustWatch error'
    assert nrw.deferred_reasons('Prey of Wrath') == ['jw_error_retry']
    assert PREY not in nrw.archived_ids()


def test_jw_error_on_a_published_catchup_retry_keeps_it_as_it_was(nrw):
    """A film already on the wall from an earlier run whose enrichment failed twice before
    (TMDB down) is retried by catch-up on a day JustWatch is down: still 2 attempts, the
    backoff stamp given back, no strike -- and, not being a this-run arrival or a pending
    entry, it is left as it was (round-2 design: only unchecked arrivals are hidden)."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.edit_wall_entry(PREY, _enrichment_status='failed', _enrichment_attempts=2,
                        _last_enrichment_attempt=day(-3))          # RETRY_BACKOFF_DAYS[1] = 3: due today
    nrw.nothing_new_today(today())
    before = nrw.track(PREY)

    nrw.jw.mode = 'connection_error'
    nrw.enrich()

    assert nrw.jw.queried('Prey of Wrath', mode='connection_error'), 'catch-up did not retry the film'
    entry = nrw.wall()[PREY]
    assert entry['_enrichment_attempts'] == 2
    assert entry['_last_enrichment_attempt'] == day(-3)
    assert entry['_enrichment_status'] == 'failed'
    assert not entry.get('hidden') and '_jw_unconfirmed' not in entry
    assert nrw.track(PREY) == before
    assert nrw.deferred_reasons('Prey of Wrath') == ['jw_error_retry']


@pytest.mark.parametrize('prior_attempts', [0, 1, 2],
                         ids=['put_back_today', 'one_prior_failure', 'two_prior_failures'])
def test_film_deferred_by_jw_error_is_checked_and_shown_on_the_next_run(nrw, prior_attempts):
    """'retrying next run (no strike)': a film deferred because JustWatch errored is
    picked up again the next day, once JustWatch answers, and shown. prior_attempts =
    failed enrichment attempts the wall entry already had (0 = put back today).
    (v1: the first two cases were never retried / retried 3 days late.)"""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    if prior_attempts:
        from constants import RETRY_BACKOFF_DAYS
        nrw.edit_wall_entry(PREY, _enrichment_status='failed', _enrichment_attempts=prior_attempts,
                            _last_enrichment_attempt=day(-RETRY_BACKOFF_DAYS[prior_attempts - 1]))
        nrw.nothing_new_today(today())

    nrw.jw.mode = 'connection_error'          # day 1: JustWatch down during enrichment
    nrw.enrich()
    assert nrw.deferred_reasons('Prey of Wrath') == ['jw_error_retry']
    assert nrw.lane(PREY) == ('HIDDEN' if prior_attempts == 0 else 'MAIN WALL')

    nrw.jw.mode = 'up'                        # day 2: JustWatch back; nothing new discovered
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()

    entry = nrw.wall()[PREY]
    assert entry.get('_enrichment_status') == 'completed', (
        f"day-2 enrichment never re-checked the deferred film (status "
        f"{entry.get('_enrichment_status')!r}, attempts {entry.get('_enrichment_attempts')}, "
        f"last attempt {entry.get('_last_enrichment_attempt')})")
    assert entry['watch_links'].get('vod'), 'film still has no watch links'
    assert not entry.get('hidden') and '_jw_unconfirmed' not in entry, 'checked film still hidden'
    assert nrw.lane(PREY) == 'MAIN WALL'
    rec = nrw.track(PREY)
    assert rec['status'] == 'available' and rec.get('enriched') is True


def test_hidden_film_stays_hidden_while_justwatch_is_still_down(nrw):
    """Day 1 and day 2 JustWatch is down: the put-back stays hidden, is re-checked first
    each run (catch-up), keeps its first unconfirmed day, gets no strike and uses no
    attempt. Day 3 JustWatch answers: it is shown."""
    before = _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.jw.mode = 'connection_error'
    nrw.enrich()                                         # day 1
    assert nrw.lane(PREY) == 'HIDDEN'

    nrw.jw.mode = 'graphql_errors'                       # day 2: still down (throttled)
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()
    assert nrw.jw.queried('Prey of Wrath', mode='graphql_errors'), 'not re-checked on day 2'
    entry = nrw.wall()[PREY]
    assert entry.get('hidden') is True and entry['_jw_unconfirmed'] == today()
    assert entry.get('_enrichment_attempts', 0) == 0
    assert nrw.track(PREY) == before, 'a JustWatch outage changed the tracking record'
    assert nrw.deferred_reasons('Prey of Wrath') == ['jw_error_retry']

    nrw.jw.mode = 'up'                                   # day 3
    nrw.shift_clock(2)
    nrw.nothing_new_today(day(2))
    nrw.enrich()
    assert nrw.lane(PREY) == 'MAIN WALL'
    assert nrw.wall()[PREY]['_enrichment_status'] == 'completed'


@pytest.mark.parametrize('first_day', ['connection_error', 'up'], ids=['jw_error_day1', 'control_jw_up'])
def test_unconfirmed_pvod_putback_is_pulled_once_its_check_runs(nrw, first_day):
    """Sense and Sensibility (real JustWatch offers: in theaters + $19.99 rentals live on
    Amazon) is put back by discovery. Owner, Nov 2026: a $19.99 rental is rentable -- the old
    $15+ PVOD block is gone, and the pre-order labeler finds Amazon's rental live: it STAYS on
    the main wall through enrichment. If JustWatch errors in enrichment, it waits hidden for
    its check (never shown unconfirmed, no strike) and is shown once the check passes.
    (Test name kept from the PVOD-block era.)"""
    nrw.seed(SENSE)
    nrw.jw.catalog['Sense and Sensibility'] = [jw_node('Sense and Sensibility')]
    nrw.discover()
    assert nrw.track(SENSE)['status'] == 'available' and nrw.lane(SENSE) == 'MAIN WALL', \
        'setup: discovery puts the rentable film back on the main wall'

    nrw.jw.mode = first_day
    nrw.enrich()
    if first_day == 'connection_error':
        assert nrw.lane(SENSE) == 'HIDDEN', 'published unconfirmed during a JustWatch error'
        assert nrw.track(SENSE)['status'] == 'available'
        nrw.jw.mode = 'up'                               # day 2
        nrw.shift_clock(1)
        nrw.nothing_new_today(day(1))
        nrw.enrich()

    rec = nrw.track(SENSE)
    assert rec['status'] == 'available' and rec.get('_jw_revert_reason') != 'justwatch_theatrical_pvod', rec
    assert nrw.lane(SENSE) == 'MAIN WALL'


@pytest.mark.parametrize('mode', ['up', 'connection_error'])
def test_buyonly_putback_never_lands_on_the_main_wall_unchecked(nrw, mode):
    """Sukma is put back by discovery on a BUY-only Amazon offer (SYNTHETIC, $19.99), out of
    theaters. Buy-only is buyable (owner, Nov 2026): JustWatch up, enrichment's labeler keeps it
    on the main wall. JustWatch error: it waits hidden for its check (never shown unconfirmed)."""
    url = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.7807a066-4a24-45b9-bfa4-14914ebac370'
    node = jw_node('Sukma')
    node['offers'] = [_offer('BUY', 'Amazon Video', 'amazon', url, price='$19.99', created=stamp(-1))]
    _put_back_today(nrw, SUKMA, 'Sukma', node)
    assert nrw.lane(SUKMA) == 'MAIN WALL'

    nrw.jw.mode = mode
    nrw.enrich()

    if mode == 'up':
        assert nrw.lane(SUKMA) == 'MAIN WALL'
        assert not nrw.wall()[SUKMA].get('_buyonly_preorder')
        assert nrw.track(SUKMA)['status'] == 'available'
    else:
        assert nrw.lane(SUKMA) == 'HIDDEN'
        assert nrw.wall()[SUKMA]['_jw_unconfirmed'] == today()
        assert nrw.track(SUKMA)['status'] == 'available'


def test_unconfirmed_preorder_deferred_by_jw_outage_is_rechecked_next_run(nrw):
    """(v1: strict xfail -- an unconfirmed pre-order sat on the wall after an outage.)
    Wildcards is a HELD pre-order: v2 gives it no pre-order bypass, so discovery asks
    JustWatch every run -- on the outage day it waits in tracking (no strike), never on
    the wall; the next day JustWatch's "no offer" is counted. After This Death is a
    non-held pending pre-order that still graduates unchecked: the outage during its only
    JustWatch check (enrichment's Step 0) hides it, and the next day's check (JustWatch
    up, still no offer) pulls it into tracking."""
    nrw.seed(WILDCARDS, AFTER_DEATH)
    nrw.put_on_wall(WALL_78303FD6[AFTER_DEATH])
    nrw.jw.catalog['Wildcards'] = [jw_node('Wildcards')]                # real: no offers yet
    nrw.jw.catalog['After This Death'] = [synthetic_node(AFTER_DEATH, 'After This Death', 2025,
                                                         'after-this-death')]
    nrw.jw.mode = 'connection_error'          # day 1: JustWatch down all day
    nrw.discover()
    nrw.enrich()

    assert nrw.jw.queried('Wildcards', mode='connection_error'), 'held pre-order skipped JustWatch'
    wild = nrw.track(WILDCARDS)
    assert wild['status'] == 'tracking' and WILDCARDS not in nrw.wall()
    assert wild['_jw_revert_count'] == TRACKING_78303FD6[WILDCARDS]['_jw_revert_count'], 'outage counted'
    assert nrw.lane(AFTER_DEATH) == 'HIDDEN'
    assert nrw.track(AFTER_DEATH)['status'] == 'available'
    assert nrw.deferred_reasons('After This Death') == ['jw_error_retry']

    nrw.jw.mode = 'up'                        # day 2: JustWatch back, still no offer
    nrw.next_day(1)
    nrw.discover()
    nrw.enrich()

    wild = nrw.track(WILDCARDS)
    assert wild['status'] == 'tracking' and WILDCARDS not in nrw.wall()
    assert wild['_jw_revert_count'] == TRACKING_78303FD6[WILDCARDS]['_jw_revert_count'] + 1
    assert wild['_jw_last_checked'] == day(1) and wild['_jw_last_refuted'] == day(1)
    assert nrw.jw.queried('After This Death', mode='up'), 'nobody asked JustWatch about it on day 2'
    rec = nrw.track(AFTER_DEATH)
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'justwatch_no_valid_offers'
    assert AFTER_DEATH not in nrw.wall(), 'film with no JustWatch offer is still on the wall'


def test_jw_error_on_a_pending_catchup_entry_hides_it(nrw):
    """An entry discovery wrote on an earlier run but enrichment never got to (still
    'pending': its run was cut short) is retried by catch-up on a JustWatch-down day: it
    never got its JustWatch check either, so it waits hidden too."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    assert nrw.wall()[PREY]['_enrichment_status'] == 'pending'
    nrw.shift_clock(1)                                    # next run, nothing new
    nrw.nothing_new_today(day(1))

    nrw.jw.mode = 'connection_error'
    nrw.enrich()

    entry = nrw.wall()[PREY]
    assert entry.get('hidden') is True and entry['_jw_unconfirmed'] == day(1)
    assert nrw.track(PREY)['status'] == 'available' and '_jw_revert_count' not in nrw.track(PREY)


def test_unconfirmed_preorder_arrival_is_shown_as_coming_soon_once_justwatch_answers(nrw):
    """A this-run arrival that is a pre-order -- After This Death surfaced by TMDB dating it
    10 days out (SYNTHETIC: its pending pre-order fields dropped) -- waits hidden after a
    JustWatch error like any arrival. Next run JustWatch answers: it lists the film with no
    offer yet, and the date is near: Step 0's 'coming soon' answer is a real check, so the
    hide lifts and it shows in the PRE-ORDER lane (not pulled, nothing counted)."""
    nrw.seed(AFTER_DEATH, **{AFTER_DEATH: {'digital_date': None, '_type4_pending': None,
                                           '_is_preorder': None, 'enriched': False}})
    nrw.tmdb.release_dates[AFTER_DEATH] = _us_dates(AFTER_DEATH, (4, day(10)))
    nrw.jw.catalog['After This Death'] = [synthetic_node(AFTER_DEATH, 'After This Death', 2025,
                                                         'after-this-death')]
    nrw.discover()
    assert nrw.lane(AFTER_DEATH) == 'PRE-ORDER', 'setup'
    nrw.jw.mode = 'connection_error'
    nrw.enrich()
    assert nrw.lane(AFTER_DEATH) == 'HIDDEN' and nrw.wall()[AFTER_DEATH]['_jw_unconfirmed'] == today()

    nrw.jw.mode = 'up'                                   # next run: listed, no offer yet
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    mark = nrw.mark()
    nrw.enrich()

    assert 'After This Death' in nrw.queried_since(mark)
    entry, rec = nrw.wall()[AFTER_DEATH], nrw.track(AFTER_DEATH)
    assert nrw.lane(AFTER_DEATH) == 'PRE-ORDER' and '_jw_unconfirmed' not in entry
    assert entry['digital_date'] == day(10)
    assert rec['status'] == 'tracking' and rec.get('_type4_pending') is True, 'no longer waiting for its date'
    assert '_jw_revert_count' not in rec, 'the error day or the coming-soon answer counted against it'


@pytest.mark.parametrize('dated', ['over_90_days_ago', 'today'])
def test_unconfirmed_film_is_requeued_until_its_attempts_run_out(nrw, dated):
    """Round 2b: a film hidden after a JustWatch error is re-queued FIRST every run, whatever
    the retry backoff -- but only while it has enrichment attempts left
    (MAX_ENRICHMENT_ATTEMPTS = 5). Here TMDB's details call then fails every day (real: Them
    Bones' tmdb_fetch_failed on 2026-08-14, 08-15, 08-18, 08-25, 09-08 -- production's
    metrics/enrichment_run.json history), so its check never runs: each run uses one
    attempt, it stays hidden (never shown unchecked) and nothing counts against it. After
    the fifth it is no longer queued:
      over_90_days_ago: Prey of Wrath (dated 2026-05-20) -- the 90-day archive, which kept
        it while it waited, now takes it;
      today: Sukma (put back on a Tubi offer recorded today, SYNTHETIC) -- it stays hidden
        in data.json and the morning report lists it as stuck (-> Concerns)."""
    from constants import MAX_ENRICHMENT_ATTEMPTS
    if dated == 'today':
        tubi = _offer('ADS', 'Tubi TV', 'tubitv', 'https://tubitv.com/movies/100000001/sukma',
                      created=stamp(0, hour=0))
        mid, title = SUKMA, 'Sukma'
        before = _put_back_today(nrw, SUKMA, 'Sukma', jw_node('Sukma', [tubi]))
    else:
        mid, title = PREY, 'Prey of Wrath'
        before = _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.jw.mode = 'connection_error'
    nrw.enrich()                                          # day 0: hidden, no attempt used
    assert nrw.lane(mid) == 'HIDDEN' and nrw.wall()[mid].get('_enrichment_attempts', 0) == 0
    after_day0 = nrw.mark()

    nrw.jw.mode = 'up'
    nrw.tmdb.down.add('details')                          # TMDB fails every day from now on
    for n in range(1, MAX_ENRICHMENT_ATTEMPTS + 2):       # days 1 .. 6
        nrw.shift_clock(n, 'enricher', 'archive')
        nrw.nothing_new_today(day(n))
        calls = len(nrw.tmdb.calls)
        nrw.enrich()
        queued = (mid, 'details') in nrw.tmdb.calls[calls:]
        entry = nrw.wall()[mid]
        if n <= MAX_ENRICHMENT_ATTEMPTS:
            assert queued, f'day {n}: the hidden film was not re-queued'
            assert entry['_enrichment_attempts'] == n and entry['_enrichment_status'] == 'failed'
        else:
            assert not queued, f'day {n}: still re-queued after {MAX_ENRICHMENT_ATTEMPTS} attempts'
        assert entry.get('hidden') is True and entry['_jw_unconfirmed'] == today(), f'day {n}: shown unchecked'
        assert nrw.track(mid) == before, f'day {n}: a failure counted against the film'
        if n == MAX_ENRICHMENT_ATTEMPTS - 1:
            nrw.archive_old()
            assert mid in nrw.wall() and mid not in nrw.archived_ids(), 'archived with retries left'
    assert title not in nrw.queried_since(after_day0), 'setup: TMDB fails before the JustWatch check'

    nrw.archive_old()                                     # day 6
    if dated == 'over_90_days_ago':
        assert mid not in nrw.wall() and mid in nrw.archived_ids()
    else:
        assert nrw.lane(mid) == 'HIDDEN' and mid not in nrw.archived_ids()
        out = nrw.morning_report()
        assert ('⚠ Hidden and stuck (→ Concerns): 1 — enrichment failed 5 times since they arrived, '
                'so they are no longer retried (/enrich <id> retries one):') in out, out
        assert f'  • Sukma (2025) — hidden since {today()}; last enrichment: failed' in out
        assert 'Waiting hidden for a JustWatch check' not in out


# ---------------------------------------------------------------------------
# (b) Unverified answers are checked against the canary first
# ---------------------------------------------------------------------------

def test_no_match_during_jw_block_is_not_a_strike(nrw):
    """JustWatch starts answering HTTP 200 + zero results for everything (the datacenter-IP
    block) between discovery and enrichment. Enrichment's 'no match' for the film must be
    checked against the fresh-client canary and, with the canary failing too, cause no
    revert and no strike; the film waits hidden."""
    before = _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))

    nrw.jw.mode = 'blocked'
    nrw.enrich()

    assert all(nrw.jw.queried(q, mode='blocked') for q in CANARY_QUERIES), 'canary was not consulted'
    entry = nrw.wall().get(PREY)
    assert entry is not None and entry.get('_enrichment_status') != 'reverted'
    assert entry.get('hidden') is True and entry['_jw_unconfirmed'] == today()
    assert nrw.track(PREY) == before
    assert nrw.deferred_reasons('Prey of Wrath') == ['jw_error_retry']


def test_offers_only_outage_is_checked_against_the_canary(nrw):
    """JustWatch finds every title but returns NO offers for any of them (the canary's
    control titles included). Enrichment's 'no valid offers' must be checked against the
    canary too (round 2: every unverified answer, not only 'no match'): no strike, no
    "not out yet" day, the film waits hidden."""
    before = _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))

    nrw.jw.mode = 'empty_offers'
    nrw.enrich()

    assert all(nrw.jw.queried(q, mode='empty_offers') for q in CANARY_QUERIES), 'canary was not consulted'
    assert nrw.track(PREY) == before, 'offers-only outage counted against the film'
    assert nrw.lane(PREY) == 'HIDDEN'
    assert nrw.deferred_reasons('Prey of Wrath') == ['jw_error_retry']


def test_no_offers_with_a_healthy_canary_is_a_real_answer(nrw):
    """Control for the test above: only the film comes back with no offers while the
    canary's control titles still have theirs. That is JustWatch's real answer: the film
    is pulled, the check is counted, and today is recorded as a day it was not out."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.jw.catalog['Prey of Wrath'][0]['offers'] = []

    nrw.enrich()

    rec = nrw.track(PREY)
    assert rec['status'] == 'tracking'
    assert rec['_jw_revert_reason'] == 'justwatch_no_valid_offers'
    assert rec['_jw_revert_count'] == 1 and rec['_jw_last_checked'] == today()
    assert rec['_jw_last_refuted'] == today()
    assert PREY not in nrw.wall() and PREY in nrw.archived_ids()


# ---------------------------------------------------------------------------
# (c) Apple Music Live specials (a JustWatch blind spot)
# ---------------------------------------------------------------------------

def test_apple_music_live_special_is_not_pulled_by_justwatch_no_match(nrw):
    """Troye Sivan's Apple Music Live special (real: JustWatch has no entry for it; it was
    re-added and purged 10 days running). After discovery puts it on the wall, enrichment's
    JustWatch 'no match' must not pull it."""
    nrw.seed(TROYE)
    nrw.jw.catalog['Apple Music Live: Troye Sivan'] = copy.deepcopy(JW_NODES['Apple Music Live: Troye Sivan'])
    nrw.discover()
    assert TROYE in nrw.wall()

    nrw.enrich()

    assert nrw.jw.queried('Apple Music Live: Troye Sivan'), 'JustWatch pre-check never ran'
    entry = nrw.wall().get(TROYE)
    assert entry is not None, 'Apple Music Live special was pulled from the wall'
    assert entry['_enrichment_status'] == 'completed'
    rec = nrw.track(TROYE)
    assert rec['status'] == 'available' and rec.get('enriched') is True
    assert '_jw_revert_reason' not in rec and '_jw_revert_count' not in rec


def test_apple_music_live_special_with_zero_watch_links_is_kept(nrw):
    """Same special, but the Apple TV page scrape (Playwright) returns a junk href, so the
    Apple Music Live link rule falls through and enrichment ends with zero watch links.
    The zero-links check must not pull an Apple Music Live special either."""
    nrw.seed(TROYE)
    nrw.jw.catalog['Apple Music Live: Troye Sivan'] = copy.deepcopy(JW_NODES['Apple Music Live: Troye Sivan'])
    nrw.vod.links[('Apple Music Live: Troye Sivan', 'Apple TV')] = 'javascript:void(0)'
    nrw.discover()

    nrw.enrich()

    assert ('Apple Music Live: Troye Sivan', 'Apple TV') in nrw.vod.calls
    entry = nrw.wall().get(TROYE)
    assert entry is not None, 'Apple Music Live special was pulled for having zero links'
    links = entry.get('watch_links') or {}
    assert not any(links.get(k) for k in ('streaming', 'vod')), 'setup: expected zero watch links'
    assert entry['_enrichment_status'] == 'completed'
    rec = nrw.track(TROYE)
    assert rec['status'] == 'available'
    assert rec.get('_jw_revert_reason') != 'zero_watch_links'


# ---------------------------------------------------------------------------
# (d) Put-back dates survive enrichment
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('records', ['no_record_dates', 'jw_record_dates'])
def test_putback_date_survives_enrichment(nrw, records):
    """Prey of Wrath: held 'no valid offers' daily from 2026-05-10 (10 checks, so the last
    'no offer' day was 2026-05-19); TMDB says digital 2026-05-01, a day before that.
      no_record_dates: JustWatch gives no record dates (the captured offers) -- TMDB's
        date is refuted, so discovery dates it the day after the hold (2026-05-20,
        putback_after_hold), flagged for review (the old skip left it unchecked).
      jw_record_dates: JustWatch first recorded Xumo 2026-06-02 and Amazon 2026-07-08
        (SYNTHETIC) -- dated 2026-06-02 (jw_first_offer).
    Enrichment must keep that date, not re-stamp TMDB's 2026-05-01."""
    from pipeline import putback
    held = TRACKING_78303FD6[PREY]
    assert putback.last_refuted_day(held) == '2026-05-19'
    created = {'xumoplay': '2026-06-02T09:00:00Z', 'amazon': '2026-07-08T13:13:43Z'}
    node = jw_node('Prey of Wrath', created=created if records == 'jw_record_dates' else None)
    expected = {'no_record_dates': ('2026-05-20', putback.AFTER_HOLD),
                'jw_record_dates': ('2026-06-02', putback.FIRST_OFFER)}[records]

    rec = _put_back_today(nrw, PREY, 'Prey of Wrath', node)
    assert (rec['digital_date'], rec['_digital_date_source']) == expected
    assert rec.get('_date_needs_review') is (True if records == 'no_record_dates' else None)

    nrw.enrich()

    entry = nrw.wall()[PREY]
    assert entry['_enrichment_status'] == 'completed'
    assert (entry['digital_date'], entry['_digital_date_source']) == expected, \
        f"re-dated to {entry['digital_date']} ({entry['_digital_date_source']})"


@pytest.mark.parametrize('tubi_record', ['recorded_today', 'jw_placeholder'])
def test_putback_date_survives_a_later_enrichment_retry(nrw, tubi_record):
    """Sukma: held 'no valid offers' (checked daily; its only offer was an Amazon channel).
    Day 1: Tubi lists it (SYNTHETIC offer) and there is no TMDB date, so discovery dates
    the put-back today -- from JustWatch's record of the offer (jw_first_offer), or, when
    JustWatch only has its 2000-07-14 placeholder, as the day JustWatch first confirmed it
    (jw_first_verified). TMDB's API is down for enrichment. Day 2: catch-up retries
    enrichment and TMDB now lists a US digital date of 2026-11-11 (a day JustWatch showed
    no offer). The put-back date must stay."""
    from pipeline import putback
    created = stamp(0, hour=0) if tubi_record == 'recorded_today' else JW_PLACEHOLDER_DATE
    tubi = _offer('ADS', 'Tubi TV', 'tubitv', 'https://tubitv.com/movies/100000001/sukma', created=created)
    # Checked daily (every run since Nov 2026): its last check was yesterday. Its real record
    # predates the daily stamp, so its estimated last check aged with the calendar -- this test
    # passed on 11-15 and failed on 11-16 without it (dated for review, not confirmed).
    rec = _put_back_today(nrw, SUKMA, 'Sukma', jw_node('Sukma', [tubi]),
                          **{SUKMA: {'_jw_last_checked': day(-1)}})
    source = putback.FIRST_OFFER if tubi_record == 'recorded_today' else putback.CONFIRMED
    put_back_on = rec['digital_date']
    assert (put_back_on, rec['_digital_date_source']) == (today(), source)

    nrw.tmdb.down.add('details')               # day 1: TMDB unavailable during enrichment
    nrw.enrich()
    assert nrw.wall()[SUKMA]['_enrichment_status'] == 'failed'

    nrw.tmdb.down.clear()                      # day 2: TMDB back, with a newly entered date
    nrw.tmdb.release_dates[SUKMA] = _us_dates(SUKMA, (4, '2026-11-11'))
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()

    entry = nrw.wall()[SUKMA]
    assert entry['_enrichment_status'] == 'completed', 'catch-up did not retry the film'
    assert entry['digital_date'] == put_back_on, f"re-dated to {entry['digital_date']}"
    assert entry['_digital_date_source'] == source


@pytest.mark.parametrize('rental_record', ['recorded_today', 'recorded_on_tmdb_date'])
def test_held_preorder_put_back_is_not_dated_before_the_last_no_offer_day(nrw, rental_record):
    """Wildcards was held as a pre-order: JustWatch showed no offer through 2026-11-13
    (tracking row: _jw_reverted_at 2026-11-13, 5 checks, reason no_valid_offers). Today
    JustWatch lists an Amazon rental (SYNTHETIC offer), recorded today or (a pre-order
    listing) on TMDB's 2026-11-09. A held film gets no pre-order bypass: discovery asks
    JustWatch, puts it back, and dates it from evidence -- never on or before the last day
    JustWatch showed no offer -- so the wall must not show TMDB's 2026-11-09.
    (v1: bypassed JustWatch and dated 2026-11-09.)"""
    from pipeline import putback
    created = stamp(0, hour=0) if rental_record == 'recorded_today' else '2026-11-09T05:00:00Z'
    nrw.seed(WILDCARDS)
    nrw.jw.catalog['Wildcards'] = [jw_node('Wildcards', amazon_rental(WILDCARDS, created=created))]
    nrw.discover()
    assert nrw.jw.queried('Wildcards'), 'held pre-order skipped JustWatch'
    nrw.enrich()

    entry = nrw.wall().get(WILDCARDS)
    assert entry is not None and entry['_enrichment_status'] == 'completed', 'setup: film not put back'
    expected = putback.putback_date(copy.deepcopy(TRACKING_78303FD6[WILDCARDS]), False, '2026-11-09',
                                    [created[:10]], '2026-08-27', today())
    assert entry['digital_date'] > '2026-11-13', (
        f"put back dated {entry['digital_date']} ({entry.get('_digital_date_source')})")
    assert (entry['digital_date'], entry['_digital_date_source']) == expected
    assert nrw.track(WILDCARDS)['_put_back_on'] == today()


# ---------------------------------------------------------------------------
# (e) A genuine JustWatch answer is recorded as a check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('jw_answer, reason, refuted', [
    ('real node, no offers', 'justwatch_no_valid_offers', True),
    ('only other films (canary healthy)', 'justwatch_no_match', False),
])
def test_held_preorder_is_checked_by_discovery_every_run(nrw, jw_answer, reason, refuted):
    """Wildcards (held pre-order) no longer reaches the wall through the pre-order bypass
    (v1 let it through every night): discovery asks JustWatch, which shows no offer (or no
    such title while the canary is healthy). It stays held, the check is counted and
    stamped, and only a 'no offer' answer is recorded as a day it was not out."""
    nrw.seed(WILDCARDS)
    nrw.jw.catalog['Wildcards'] = ([jw_node('Wildcards')] if refuted
                                   else copy.deepcopy(JW_NODES['Wildcards (other films only)']))
    nrw.discover()

    assert nrw.jw.queried('Wildcards')
    rec = nrw.track(WILDCARDS)
    assert rec['status'] == 'tracking'
    assert rec['_jw_revert_reason'] == reason
    assert rec['_jw_last_checked'] == today()
    assert rec['_jw_revert_count'] == TRACKING_78303FD6[WILDCARDS]['_jw_revert_count'] + 1
    # A no-match is not a "not out yet" day; only the hold's OLD last no-offer day is kept
    # (persisted before the reason changes -- round 2c).
    from pipeline import putback as _pb
    assert rec.get('_jw_last_refuted') == (
        today() if refuted else _pb.last_refuted_day(TRACKING_78303FD6[WILDCARDS], today()))
    assert WILDCARDS not in nrw.wall()
    assert json.load(open(nrw.root / 'metrics' / 'newly_available.json'))['movie_ids'] == []


@pytest.mark.parametrize('jw_answer, reason, refuted', [
    ('real node, no offers', 'justwatch_no_valid_offers', True),
    ('only other films (canary healthy)', 'justwatch_no_match', False),
    ('title mismatch (first_result)', 'justwatch_no_match', False),
])
def test_genuine_step0_revert_stamps_the_check(nrw, jw_answer, reason, refuted):
    """After This Death is a non-held pending pre-order; TMDB moves its date to today and
    discovery lets it through without JustWatch, so enrichment's Step 0 decides. JustWatch
    shows no offer / no such title (canary healthy) / a different film's result. It is
    pulled, the check is counted and stamped; only 'no offer' is a day it was proven not
    out (round 2: a title mismatch is a no-match, not 'no valid offers')."""
    _graduating_preorder(nrw, AFTER_DEATH, 'After This Death')
    if jw_answer.startswith('only other films'):
        nrw.jw.catalog['After This Death'] = copy.deepcopy(JW_NODES['Wildcards (other films only)'])
    elif jw_answer.startswith('title mismatch'):
        nrw.jw_answers['After This Death'] = TITLE_MISMATCH

    nrw.enrich()

    rec = nrw.track(AFTER_DEATH)
    assert rec['status'] == 'tracking'
    assert rec['_jw_revert_reason'] == reason
    assert rec['_jw_last_checked'] == today()
    assert rec['_jw_revert_count'] == 1
    assert rec.get('_jw_last_refuted') == (today() if refuted else None)
    assert AFTER_DEATH not in nrw.wall() and AFTER_DEATH in nrw.archived_ids()


# ---------------------------------------------------------------------------
# (f) A zero-watch-links revert is recorded as a check
# ---------------------------------------------------------------------------

def test_zero_links_revert_stamps_last_checked_and_refuted(nrw):
    """Lemonade Blessing (one of the films the old 4-strike skip dropped) is confirmed and
    put back, but JustWatch's only offer is an Amazon rental whose link is Amazon's
    placeholder page (SYNTHETIC; ASIN from constants.PLACEHOLDER_ASINS), so enrichment
    ends with zero usable watch links. The film is pulled and today is recorded as its
    last 'no offer' day (persistently: _jw_last_refuted), so the next put-back cannot be
    dated on or before it."""
    from pipeline import putback
    node = jw_node('Lemonade Blessing', amazon_placeholder(), drop_cinema=True)
    _put_back_today(nrw, LEMONADE, 'Lemonade Blessing', node)
    count_before = nrw.track(LEMONADE).get('_jw_revert_count', 0)

    nrw.enrich()

    rec = nrw.track(LEMONADE)
    assert rec['status'] == 'tracking'
    assert rec['_jw_revert_reason'] == 'zero_watch_links'
    assert rec['_jw_last_checked'] == today()
    assert rec['_jw_revert_count'] == count_before + 1
    assert rec['_jw_last_refuted'] == today()
    assert putback.last_refuted_day(rec) == today()
    assert LEMONADE not in nrw.wall()


def test_put_back_floor_survives_a_later_non_refuting_pull(nrw):
    """Prey of Wrath is put back (floor: its last 'no offer' day, 2026-05-19) and then
    pulled by enrichment as a no-match (canary healthy) -- a reason that proves nothing.
    The 2026-05-19 floor must survive both the put-back and the no-match pull, so a later
    put-back can't land on TMDB's refuted 2026-05-01."""
    from pipeline import putback
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    assert nrw.track(PREY)['_jw_last_refuted'] == '2026-05-19'
    nrw.jw.catalog['Prey of Wrath'] = copy.deepcopy(JW_NODES['Wildcards (other films only)'])

    nrw.enrich()

    rec = nrw.track(PREY)
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'justwatch_no_match'
    assert rec['_jw_last_refuted'] == '2026-05-19'
    day_, source = putback.putback_date(copy.deepcopy(rec), False, '2026-05-01', [], None, today())
    assert day_ > '2026-05-19', f'next put-back would be dated {day_} ({source})'


# ---------------------------------------------------------------------------
# (g) Films not checked this run are not judged this run
# ---------------------------------------------------------------------------

def test_post_loop_does_not_pull_a_jw_deferred_film_for_zero_links(nrw):
    """After This Death (a completed pre-order entry with zero watch links) graduates
    unchecked; JustWatch lists an Amazon rental (SYNTHETIC) but errors during enrichment.
    The post-loop zero-links check must skip it (round 2: _jw_deferred) -- no release-day
    pull, no strike, no false "not out yet" day. Next run JustWatch answers: shown with
    its link."""
    _graduating_preorder(nrw, AFTER_DEATH, 'After This Death',
                         amazon_rental(AFTER_DEATH, available_from=stamp(-1), created=stamp(-1)))
    before = nrw.track(AFTER_DEATH)

    nrw.jw.mode = 'connection_error'
    nrw.enrich()

    assert nrw.deferred_reasons('After This Death') == ['jw_error_retry'], 'zero-links check ran on it'
    rec = nrw.track(AFTER_DEATH)
    assert rec == before, 'tracking changed for a film nobody could check'
    assert nrw.lane(AFTER_DEATH) == 'HIDDEN'

    nrw.jw.mode = 'up'                                   # day 2
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()

    entry = nrw.wall()[AFTER_DEATH]
    assert nrw.lane(AFTER_DEATH) == 'MAIN WALL'
    assert entry['_enrichment_status'] == 'completed' and entry['watch_links'].get('vod')
    assert nrw.track(AFTER_DEATH)['status'] == 'available'


def _two_arrivals_and_a_putback(nrw):
    """Day 1 discovery: Sukma (no hold; SYNTHETIC Tubi offer) and Lemonade Blessing (no
    hold; SYNTHETIC Tubi offer) are new arrivals, Prey of Wrath is put back after its
    hold. Discovery queues non-held films first, held films last."""
    no_hold = {k: None for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at',
                                 '_skip_provider_discovery')}
    nrw.seed(SUKMA, LEMONADE, PREY, **{SUKMA: dict(no_hold), LEMONADE: dict(no_hold)})
    nrw.jw.catalog['Sukma'] = [jw_node('Sukma', [_offer(
        'ADS', 'Tubi TV', 'tubitv', 'https://tubitv.com/movies/100000001/sukma', created=stamp(-1))])]
    nrw.jw.catalog['Lemonade Blessing'] = [jw_node('Lemonade Blessing', [_offer(
        'ADS', 'Tubi TV', 'tubitv', 'https://tubitv.com/movies/100000002/lemonade-blessing',
        created=stamp(-1))], drop_cinema=True)]
    nrw.jw.catalog['Prey of Wrath'] = [jw_node('Prey of Wrath')]
    nrw.discover()
    queue = json.load(open(nrw.root / 'metrics' / 'newly_available.json'))['movie_ids']
    assert queue == [SUKMA, LEMONADE, PREY], f'setup: queue {queue}'
    assert nrw.track(PREY)['_put_back_on'] == today()
    assert not nrw.track(SUKMA).get('_put_back_on') and not nrw.track(LEMONADE).get('_put_back_on')


def test_batch_cut_hides_only_todays_putbacks_and_rechecks_them_first(nrw, monkeypatch, capsys):
    """Enrichment's batch limit (simulated as 1 for a 3-film day) cuts Lemonade Blessing
    (a new arrival) and Prey of Wrath (put back today). The put-back -- often still a PVOD
    or pre-order rental that only Step 0 catches -- waits hidden; the plain new arrival
    stays as production leaves it. Next run catch-up checks the hidden put-back first,
    then the other, and shows it."""
    import pipeline.enricher as enricher_mod
    _two_arrivals_and_a_putback(nrw)
    monkeypatch.setattr(enricher_mod, 'MAX_ENRICHMENT_BATCH', 1)
    capsys.readouterr()
    day1 = nrw.mark()

    nrw.enrich()

    out = capsys.readouterr().out
    assert 'Batch limit: 2 deferred to the next run (2 new, 0 catch-up)' in out
    assert nrw.wall()[SUKMA]['_enrichment_status'] == 'completed'
    assert nrw.lane(PREY) == 'HIDDEN' and nrw.wall()[PREY]['_jw_unconfirmed'] == today()
    assert nrw.lane(LEMONADE) == 'MAIN WALL' and '_jw_unconfirmed' not in nrw.wall()[LEMONADE]
    checked = nrw.queried_since(day1)
    assert 'Prey of Wrath' not in checked and 'Lemonade Blessing' not in checked, \
        f'a cut film was checked anyway: {checked}'
    assert nrw.track(PREY)['status'] == 'available' and '_jw_revert_count' not in nrw.track(PREY), \
        'the batch cut counted against the put-back'

    monkeypatch.setattr(enricher_mod, 'MAX_ENRICHMENT_BATCH', 100)   # day 2
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    day2 = nrw.mark()
    nrw.enrich()

    order = list(dict.fromkeys(q for q in nrw.queried_since(day2) if q in ('Prey of Wrath', 'Lemonade Blessing')))
    assert order == ['Prey of Wrath', 'Lemonade Blessing'], f'hidden put-back not re-checked first: {order}'
    assert nrw.lane(PREY) == 'MAIN WALL' and nrw.wall()[PREY]['_enrichment_status'] == 'completed'
    assert nrw.wall()[LEMONADE]['_enrichment_status'] == 'completed'


@pytest.mark.parametrize('timeout_after', [0, 1], ids=['before_any_film', 'after_the_first_film'])
def test_loop_timeout_hides_only_todays_putbacks_among_the_remaining(nrw, timeout_after):
    """Enrichment's loop timeout (simulated) stops the run before any film / after the
    first one. Of the films left unchecked, only the put-back (Prey of Wrath) waits
    hidden; a plain new arrival stays as production leaves it; a film that was checked
    before the timeout is enriched normally."""
    _two_arrivals_and_a_putback(nrw)
    before_enrich = nrw.mark()

    nrw.enrich(timeout_after=timeout_after)

    assert nrw.lane(PREY) == 'HIDDEN' and nrw.wall()[PREY]['_jw_unconfirmed'] == today()
    checked = nrw.queried_since(before_enrich)
    assert 'Prey of Wrath' not in checked and 'Lemonade Blessing' not in checked, \
        f'a film the timeout left unchecked was checked anyway: {checked}'
    assert nrw.lane(LEMONADE) == 'MAIN WALL' and '_jw_unconfirmed' not in nrw.wall()[LEMONADE]
    sukma = nrw.wall()[SUKMA]
    if timeout_after:
        assert sukma['_enrichment_status'] == 'completed' and '_jw_unconfirmed' not in sukma
    else:
        assert sukma['_enrichment_status'] == 'pending' and '_jw_unconfirmed' not in sukma
    assert nrw.track(PREY)['status'] == 'available' and '_jw_revert_count' not in nrw.track(PREY)


def _queen_graduates(nrw):
    """Queen at Sea (buy-only pre-order on the wall: completed entry, pre-order links,
    no watch links). JustWatch now lists a live Amazon rental (SYNTHETIC): discovery's
    daily buy-only check graduates it and puts it on the wall."""
    nrw.seed(QUEEN)
    nrw.put_on_wall(WALL_78303FD6[QUEEN])
    nrw.jw.catalog['Queen at Sea'] = [synthetic_node(QUEEN, 'Queen at Sea', 2026, 'queen-at-sea',
                                                     amazon_rental(QUEEN, available_from=stamp(-1),
                                                                   created=stamp(-1)),
                                                     director='Lance Hammer')]
    nrw.discover()
    rec, entry = nrw.track(QUEEN), nrw.wall()[QUEEN]
    assert rec['status'] == 'available' and not rec.get('_buyonly_preorder'), 'setup: did not graduate'
    assert not entry.get('_buyonly_preorder') and not entry.get('pre_order_links'), 'setup: entry not synced'
    assert entry['_enrichment_status'] == 'completed' and not entry.get('watch_links')
    return rec


def test_buyonly_graduation_gets_its_links_in_enrichment(nrw):
    """Control: Queen at Sea graduates in discovery (round 2 syncs its wall entry: the
    pre-order flags go), enrichment's Step 0 confirms it and it gets its rental link."""
    _queen_graduates(nrw)

    nrw.enrich()

    entry = nrw.wall()[QUEEN]
    assert nrw.lane(QUEEN) == 'MAIN WALL'
    assert entry['_enrichment_status'] == 'completed' and entry['watch_links'].get('vod')
    assert nrw.track(QUEEN)['status'] == 'available'


def test_film_left_unchecked_by_the_loop_timeout_is_not_judged(nrw):
    """(Round 2: strict xfail -- the post-loop zero-links check judged films the loop never
    reached. Round 2b: only films the loop processed (`_processed`) are judged.)
    Queen at Sea graduates in discovery (JustWatch: a live Amazon rental) with a completed
    entry and no watch links yet. Enrichment's loop timeout (simulated) fires before it is
    checked. It was not checked this run, so it must not be pulled, get a strike, or have
    today recorded as a day it was proven not out (owner rules 4/5: that floor would date
    its next put-back tomorrow)."""
    _queen_graduates(nrw)
    before = nrw.mark()

    nrw.enrich(timeout_after=0)

    assert 'Queen at Sea' not in nrw.queried_since(before), 'setup: the timeout should fire before any film'
    rec = nrw.track(QUEEN)
    assert QUEEN in nrw.wall() and nrw.wall()[QUEEN].get('_enrichment_status') != 'reverted', \
        'pulled without being checked'
    assert rec['status'] == 'available'
    assert '_jw_revert_count' not in rec and '_jw_last_refuted' not in rec, \
        f"recorded a check that never happened: {rec.get('_jw_revert_reason')} / {rec.get('_jw_last_refuted')}"
    assert nrw.deferred_reasons('(1 movies)') == ['loop_timeout']


# ---------------------------------------------------------------------------
# (h) Past-date pre-orders: re-checked, never dropped onto the main wall unchecked
# ---------------------------------------------------------------------------

def _vile_graduated_unenriched(nrw):
    """The Vile (completed pre-order entry with an Amazon pre-order link) and Prey of
    Wrath: TMDB moves The Vile's date to today and discovery lets it through unchecked
    (pre-order bypass); Prey is put back. That day's enrichment never ran (crashed /
    killed). Next run nothing new is discovered."""
    nrw.seed(VILE, PREY)
    nrw.put_on_wall(WALL_78303FD6[VILE])
    nrw.jw.catalog['Prey of Wrath'] = [jw_node('Prey of Wrath')]
    nrw.discover()
    assert nrw.track(VILE)['status'] == 'available' and not nrw.jw.queried('The Vile')
    assert nrw.lane(VILE) == 'PRE-ORDER' and nrw.wall()[VILE]['digital_date'] == today()
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))


@pytest.mark.parametrize('jw_offer', ['none', 'amazon_rental'])
def test_past_date_preorder_is_rechecked_on_a_quiet_day(nrw, jw_offer):
    """Next run, The Vile is a past-date pre-order nobody checked. Catch-up force-queues
    it (round 2), so its JustWatch check runs even on a day with nothing else to enrich:
    no offer -> pulled and held; a live Amazon rental (SYNTHETIC) -> graduates to the
    main wall. (Round 1: on a quiet day it sat in the PRE-ORDER lane past its date,
    never checked; on a busy day it dropped onto the main wall unchecked.)"""
    offers = amazon_rental(VILE, available_from=stamp(-1), created=stamp(0, 0)) if jw_offer != 'none' else ()
    nrw.jw.catalog['The Vile'] = [synthetic_node(VILE, 'The Vile', 2025, 'the-vile', offers)]
    _vile_graduated_unenriched(nrw)
    nrw.edit_wall_entry(PREY, _enrichment_status='completed')   # a quiet day: only The Vile is due

    nrw.enrich()

    assert nrw.jw.queried('The Vile'), 'past-date pre-order never re-checked'
    if jw_offer == 'none':
        rec = nrw.track(VILE)
        assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'justwatch_no_valid_offers'
        assert VILE not in nrw.wall()
    else:
        assert nrw.lane(VILE) == 'MAIN WALL'
        entry = nrw.wall()[VILE]
        assert entry['_enrichment_status'] == 'completed' and not entry.get('pre_order_links')
        assert not nrw.track(VILE).get('_is_preorder')


def test_past_date_preorder_cut_by_the_batch_limit_keeps_its_preorder_flags(nrw, monkeypatch):
    """Same next run, but the batch limit (simulated as 1) cuts The Vile behind Prey of
    Wrath's pending catch-up. Its pre-order flags are cleared only once its check passes
    (round 2b; round 2: once queued), so it stays in the PRE-ORDER lane instead of dropping
    onto the main wall unchecked; the run after, it is checked (no offer: pulled)."""
    import pipeline.enricher as enricher_mod
    nrw.jw.catalog['The Vile'] = [synthetic_node(VILE, 'The Vile', 2025, 'the-vile')]
    _vile_graduated_unenriched(nrw)
    monkeypatch.setattr(enricher_mod, 'MAX_ENRICHMENT_BATCH', 1)

    nrw.enrich()

    assert not nrw.jw.queried('The Vile'), 'setup: The Vile should have been cut'
    entry = nrw.wall()[VILE]
    assert nrw.lane(VILE) == 'PRE-ORDER', 'past-date pre-order dropped onto the main wall unchecked'
    assert entry.get('pre_order_links') and nrw.track(VILE).get('_is_preorder') is True

    monkeypatch.setattr(enricher_mod, 'MAX_ENRICHMENT_BATCH', 100)
    nrw.shift_clock(2)
    nrw.nothing_new_today(day(2))
    nrw.enrich()
    assert nrw.jw.queried('The Vile')
    assert VILE not in nrw.wall() and nrw.track(VILE)['status'] == 'tracking'


@pytest.mark.parametrize('trouble', ['jw_error', 'tmdb_details_down', 'loop_timeout'])
def test_past_date_preorder_stays_a_preorder_when_its_check_cannot_run(nrw, trouble):
    """(Round 2 review, high: the force-queue popped a past-date pre-order's flags BEFORE its
    JustWatch check, so a JustWatch error, a TMDB failure or the loop timeout dropped it onto
    the MAIN WALL unconfirmed -- and, its entry 'completed', nothing re-checked it.)
    Round 2b keeps the flags until Step 0 passes. Next run, The Vile is a past-date pre-order
    nobody checked; this run its check can't happen. It stays in the PRE-ORDER lane, flags
    intact (entry and tracking), nothing counted against it. The run after, its check runs
    (JustWatch: a live Amazon rental, SYNTHETIC) and it graduates cleanly."""
    nrw.jw.catalog['The Vile'] = [synthetic_node(VILE, 'The Vile', 2025, 'the-vile', amazon_rental(
        VILE, available_from=stamp(-1), created=stamp(0, 0)))]
    _vile_graduated_unenriched(nrw)
    nrw.edit_wall_entry(PREY, _enrichment_status='completed')   # a quiet day: only The Vile is due
    before = nrw.track(VILE)
    assert before['status'] == 'available' and before.get('_is_preorder') is True
    mark = nrw.mark()

    if trouble == 'jw_error':
        nrw.jw.mode = 'connection_error'
        nrw.enrich()
        assert nrw.deferred_reasons('The Vile') == ['jw_error_retry']
    elif trouble == 'tmdb_details_down':
        nrw.tmdb.down.add('details')
        nrw.enrich()
        assert 'The Vile' not in nrw.queried_since(mark), 'setup: TMDB fails before the JustWatch check'
    else:
        nrw.enrich(timeout_after=0)
        assert 'The Vile' not in nrw.queried_since(mark), 'setup: the timeout should fire first'

    entry = nrw.wall()[VILE]
    assert nrw.lane(VILE) == 'PRE-ORDER', f'{trouble}: past-date pre-order left the PRE-ORDER lane unchecked'
    assert entry.get('_is_preorder') is True and entry.get('pre_order_links'), f'{trouble}: flags dropped'
    assert nrw.track(VILE) == before, f'{trouble}: tracking changed for a film nobody could check'

    nrw.jw.mode = 'up'                                   # the run after: everything answers
    nrw.tmdb.down.clear()
    nrw.shift_clock(2)
    nrw.nothing_new_today(day(2))
    mark = nrw.mark()
    nrw.enrich()
    assert 'The Vile' in nrw.queried_since(mark), 'not re-checked the run after'
    entry = nrw.wall()[VILE]
    assert nrw.lane(VILE) == 'MAIN WALL' and entry['_enrichment_status'] == 'completed'
    assert entry['watch_links'].get('vod') and not entry.get('pre_order_links')
    assert not nrw.track(VILE).get('_is_preorder')


BEWARE_AMAZON = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb'
BEWARE_APPLE = ('https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt?at=1000l3V2'
                '&ct=app_tv&itscg=30200&itsct=justwatch_tv&playableId=tvs.sbd.9001%3A6812862855')
BEWARE_FANDANGO = 'https://athome.fandango.com/content/browse/details/Beware-Boi-na/5214925'


def _beware_on_wall(nrw, offers, **edits):
    """Beware Boiúna as at 78303fd6 (buy-only pre-order, real $14.99 buy links on its entry,
    TMDB date 2026-11-03 passed). JustWatch lists those three purchases (the stores and links
    of its entry; SYNTHETIC record dates) plus `offers` (SYNTHETIC). `edits`: tracking-row
    changes, as in seed()."""
    nrw.seed(BEWARE, **({BEWARE: edits} if edits else {}))
    nrw.put_on_wall(WALL_78303FD6[BEWARE])
    buys = [_offer('BUY', 'Amazon Video', 'amazon', BEWARE_AMAZON, price='$14.99',
                   available_from='2026-10-20T07:00:00Z', created='2026-10-20T07:00:00Z'),
            _offer('BUY', 'Apple TV Store', 'itunes', BEWARE_APPLE, price='$14.99',
                   created='2026-10-20T07:00:00Z'),
            _offer('BUY', 'Fandango At Home', 'vudu', BEWARE_FANDANGO, price='$14.99',
                   created='2026-10-20T07:00:00Z')]
    nrw.jw.catalog['Beware Boiúna'] = [synthetic_node(BEWARE, 'Beware Boiúna', 2026, 'titan-2024',
                                                      buys + list(offers), director='Mike P. Nelson')]


@pytest.mark.parametrize('discovery_jw', ['preorder_rental', 'connection_error'])
def test_buyonly_preorder_with_links_and_a_passed_date_never_graduates_in_catchup(nrw, discovery_jw):
    """(Round 2 review, high: catch-up graduated a buy-only pre-order on ANY JustWatch rental,
    the same run discovery's live-rental rule had said "still waiting".) Beware Boiúna, a
    buy-only pre-order with links and a passed date. Today JustWatch adds a Fandango At Home
    rental (SYNTHETIC) -- the DreamQuil pattern: a store's pre-order rental listed as a plain
    RENT offer, its page unreadable (page check inconclusive) -- or JustWatch errors.
    Discovery's daily buy-only check keeps it waiting (still buy-only = a day it was not
    out; an error records nothing). Enrichment's catch-up must not graduate it: a buy-only
    pre-order graduates only in discovery's check. It stays in the PRE-ORDER lane, flags
    and date intact, not even looked up."""
    _beware_on_wall(nrw, [_offer('RENT', 'Fandango At Home', 'vudu', BEWARE_FANDANGO, price='$5.99',
                                 created=stamp(0, hour=0))])
    nrw.jw.mode = 'up' if discovery_jw == 'preorder_rental' else 'connection_error'
    nrw.discover()
    rec = nrw.track(BEWARE)
    if discovery_jw == 'preorder_rental':
        # Round 2f+ (owner, Nov 2026: "buy-only is buyable"): its real Amazon/Apple/Fandango
        # purchases, out of theaters, make it OUT whatever the Fandango rental is -- discovery's
        # labeler graduates it, dated 2026-11-03 (TMDB's digital date), and enrichment keeps it.
        assert rec['status'] == 'available' and rec['digital_date'] == '2026-11-03', rec
        nrw.enrich()
        assert nrw.lane(BEWARE) == 'MAIN WALL' and nrw.wall()[BEWARE]['digital_date'] == '2026-11-03'
        return
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder') is True, 'setup: discovery graduated it'
    assert '_jw_last_checked' not in rec and '_jw_last_refuted' not in rec, 'an error was recorded as a check'

    nrw.jw.mode = 'up'
    mark = nrw.mark()
    nrw.enrich()

    assert 'Beware Boiúna' not in nrw.queried_since(mark), 'catch-up queued a buy-only pre-order'
    entry = nrw.wall()[BEWARE]
    assert nrw.lane(BEWARE) == 'PRE-ORDER'
    assert entry.get('_buyonly_preorder') is True and entry.get('pre_order_links')
    assert entry['digital_date'] == '2026-11-03'
    rec = nrw.track(BEWARE)
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder') is True and rec.get('_is_preorder') is True


def test_buyonly_graduation_keeps_its_first_rental_day_through_enrichment(nrw):
    """(Round 2 review: enrichment's TMDB Type 4 refresh re-dated a buy-only graduation to
    TMDB's earlier buy-only date.) Beware Boiúna: yesterday discovery's daily check found it
    still buy-only (SYNTHETIC: _jw_last_checked / _jw_last_refuted = yesterday, as v2 records
    them). Today JustWatch shows an Amazon rental live since midnight (SYNTHETIC): discovery
    graduates it dated today. Enrichment must keep today -- never TMDB's 2026-11-03, a day
    before one a check proved it buy-only (owner rule 4)."""
    _beware_on_wall(nrw, amazon_rental(BEWARE, available_from=stamp(0, hour=0), created=stamp(0, hour=0)),
                    _jw_last_checked=day(-1), _jw_last_refuted=day(-1))
    nrw.discover()
    rec = nrw.track(BEWARE)
    assert rec['status'] == 'available' and rec['digital_date'] == today(), 'setup: did not graduate today'
    assert nrw.wall()[BEWARE]['digital_date'] == today()

    nrw.enrich()

    entry = nrw.wall()[BEWARE]
    assert nrw.lane(BEWARE) == 'MAIN WALL' and entry['watch_links'].get('vod')
    assert entry['digital_date'] == today(), \
        f"re-dated to {entry['digital_date']} ({entry.get('_digital_date_source')})"
    rec = nrw.track(BEWARE)
    assert rec['digital_date'] == today() and rec['_jw_last_refuted'] == day(-1)


@pytest.mark.parametrize('film', ['put_back_today', 'past_date_preorder'])
def test_single_movie_enrichment_runs_its_justwatch_check(nrw, film):
    """`generate_data.py --enrich-id` (the /enrich command) enriches one film. Its JustWatch
    pre-check runs and the run completes -- round 2b initialises the pre-order graduation
    state for this mode too (the loop reads it for every film)."""
    if film == 'put_back_today':
        mid, title = PREY, 'Prey of Wrath'
        _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    else:
        mid, title = VILE, 'The Vile'
        nrw.jw.catalog['The Vile'] = [synthetic_node(VILE, 'The Vile', 2025, 'the-vile', amazon_rental(
            VILE, available_from=stamp(-1), created=stamp(0, 0)))]
        _vile_graduated_unenriched(nrw)
    mark = nrw.mark()

    enriched = nrw.new_generator().enrich_newly_available_movies(target_id=mid)

    assert title in nrw.queried_since(mark), 'its JustWatch pre-check did not run'
    entry = nrw.wall()[mid]
    assert enriched == 1 and entry['_enrichment_status'] == 'completed', entry.get('_enrichment_status')
    assert nrw.lane(mid) == 'MAIN WALL' and entry['watch_links'].get('vod')


def test_manual_preorder_override_is_not_force_queued(nrw):
    """A curator's preorder_overrides[id] = true keeps The Vile a pre-order: catch-up does
    not force its JustWatch re-check and leaves its pre-order flags alone."""
    nrw.jw.catalog['The Vile'] = [synthetic_node(VILE, 'The Vile', 2025, 'the-vile')]
    _vile_graduated_unenriched(nrw)
    nrw.set_config(preorder_overrides={VILE: True})
    nrw.edit_wall_entry(PREY, _enrichment_status='completed')

    nrw.enrich()

    assert not nrw.jw.queried('The Vile')
    assert nrw.lane(VILE) == 'PRE-ORDER' and nrw.wall()[VILE].get('pre_order_links')


# ---------------------------------------------------------------------------
# (i) Returned festival screenings: checked like any release
# ---------------------------------------------------------------------------

def _returned_screening(nrw, offers, stale_flags=False):
    """Disposable Humanity: its Eventive screening ended 2026-11-01 (wall entry: hidden,
    expired). The screening check returns it to tracking; JustWatch lists its own Eventive
    page as a "rental" plus `offers` (SYNTHETIC); discovery puts it back. stale_flags:
    force the festival flags the 170 expired screenings carried at 78303fd6 back onto the
    wall entry (the enricher's own guards, defence in depth -- discovery's sync clears them)."""
    nrw.seed(DISPOSABLE)
    nrw.put_on_wall(WALL_78303FD6[DISPOSABLE])
    nrw.jw.catalog['Disposable Humanity'] = [synthetic_node(
        DISPOSABLE, 'Disposable Humanity', 2025, 'disposable-humanity',
        [eventive_rental()] + list(offers), director='Cameron S. Mitchell')]
    nrw.check_screenings()
    rec = nrw.track(DISPOSABLE)
    assert rec['status'] == 'tracking' and rec['_screening_expired'] and rec['_screening_ended'] == '2026-11-01'
    nrw.discover()
    rec, entry = nrw.track(DISPOSABLE), nrw.wall()[DISPOSABLE]
    assert rec['status'] == 'available' and rec['_put_back_on'] == today(), 'setup: not put back'
    assert all('Eventive' in excl and 'Shift72' in excl for excl in nrw.excluded_for('Disposable Humanity'))
    assert not entry.get('hidden') and not (entry.get('filters') or {}).get('is_virtual_screening')
    assert not any('eventive' in (v.get('link') or '') for v in (entry.get('watch_links') or {}).get('vod', []))
    if stale_flags:
        filters = dict(entry.get('filters') or {}, is_virtual_screening=True)
        nrw.edit_wall_entry(DISPOSABLE, filters=filters, _virtual_screening=True)
    nrw.jw_calls.clear()
    return rec


RETURNED_SCREENING_LINK_DEFECT = (
    "CODE: enrichment's watch-link step (pipeline/enrichment.py _get_watch_links_impl -> "
    "_try_justwatch_api ~455) asks JustWatch again WITHOUT the festival exclusion when Step 0's "
    "cached links fail validation (here Amazon's placeholder ASIN), so a returned screening's own "
    "expired Eventive page comes back as its only watch link: the zero-links check passes, the "
    "display step re-flags it a virtual screening and -- with Eventive's real end date -- hides it "
    "and re-dates it to the old screening start while tracking stays 'available': never checked "
    "again (a wait turned into a drop). Fix: for a _screening_expired record, drop festival links "
    "(Eventive/Shift72/festivalplayer) from get_enrichment_only_fields' watch_links (the "
    "_sync_entry_on_transition predicate), or pass FESTIVAL_PLATFORMS to that JustWatch call.")


@pytest.mark.parametrize('stale_flags', [False, True], ids=['synced_entry', 'stale_festival_flags'])
def test_returned_screening_is_not_kept_by_its_own_festival_page(nrw, stale_flags):
    """JustWatch lists the film's own (expired) Eventive page plus an Amazon rental whose
    link is Amazon's placeholder page: it verifies, but leaves no usable link. Step 0 must
    not count the Eventive page (festival platforms excluded for _screening_expired), and
    the film must not end up kept by it: with no usable link it is pulled
    (zero_watch_links) and checked again daily, never left on the wall with a dead
    festival link."""
    _returned_screening(nrw, amazon_placeholder(created='2026-11-10T05:00:00Z'), stale_flags)

    nrw.enrich()

    excl = nrw.excluded_for('Disposable Humanity')
    assert excl and 'Eventive' in excl[0] and 'Shift72' in excl[0], f'Step 0 asked with {excl}'
    entry = nrw.wall().get(DISPOSABLE) or {}
    festival = [v for v in (entry.get('watch_links') or {}).get('vod', []) if 'eventive' in (v.get('link') or '')]
    assert not festival, f'kept on the wall by its own expired festival page: {festival}'
    rec = nrw.track(DISPOSABLE)
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'zero_watch_links'
    assert DISPOSABLE not in nrw.wall()


def test_returned_screening_kept_by_its_festival_page_is_never_checked_again(nrw):
    """What the owner sees from the defect above, with the Eventive festival page answering
    as it really does (the screening ran 2026-09-04 .. 2026-11-01): the film must not end
    hidden under its old screening date while tracking says it is out -- held films are
    re-checked every run (owner rules 1 and 2)."""
    import pipeline.generator as generator_mod
    _returned_screening(nrw, amazon_placeholder(created='2026-11-10T05:00:00Z'))
    nrw.mp.setattr(generator_mod.DataGenerator, '_fetch_eventive_screening_info',
                   lambda self, slug: {'available_start': '2026-09-04', 'available_end': '2026-11-01',
                                       'name': 'Disposable Humanity'}, raising=False)
    nrw.enrich()
    nrw.next_day(1)                                      # next run: screenings, discovery
    nrw.nothing_new_today(day(1))
    m = nrw.mark()
    nrw.check_screenings()
    nrw.discover()

    entry, rec = nrw.wall().get(DISPOSABLE), nrw.track(DISPOSABLE)
    stuck = entry is not None and entry.get('hidden') and rec['status'] == 'available'
    assert not stuck, (f"hidden on the wall dated {entry.get('digital_date')} while tracking says "
                       f"'available': {nrw.queried_since(m).count('Disposable Humanity')} JustWatch checks since")
    assert 'Disposable Humanity' in nrw.queried_since(m), 'not re-checked on JustWatch the next run'


def test_returned_screening_with_stale_flags_gets_no_zero_links_exemption(nrw):
    """Round 2: the zero-links check's virtual-screening guard is off for a returned
    screening. By enrichment JustWatch's only offer is an Amazon rental on Amazon's
    placeholder page (no usable link; its Eventive listing is gone), and the entry still
    carries the festival flags the expired screenings had at 78303fd6: pulled for zero
    links (a day it was not out), not kept as a 'screening'."""
    _returned_screening(nrw, amazon_placeholder(created='2026-11-10T05:00:00Z'), stale_flags=True)
    nrw.jw.catalog['Disposable Humanity'][0]['offers'] = amazon_placeholder(created='2026-11-10T05:00:00Z')

    nrw.enrich()

    rec = nrw.track(DISPOSABLE)
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'zero_watch_links'
    assert rec['_jw_last_refuted'] == today()
    assert DISPOSABLE not in nrw.wall()


@pytest.mark.parametrize('stale_flags', [False, True], ids=['synced_entry', 'stale_festival_flags'])
def test_returned_screening_gets_no_festival_exemption_from_the_pvod_gate(nrw, stale_flags):
    """JustWatch lists theaters + a $19.99 Amazon rental, live (SYNTHETIC): a returned screening
    is judged like any film (no virtual-screening exemption for _screening_expired, even with
    stale festival flags on its entry) -- and a live $19.99 rental is out."""
    url = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-000001376929'
    offers = [_offer('CINEMA', 'Fandango', 'fandango', 'https://www.fandango.com/disposable-humanity',
                     ptype='CANVAS'),
              _offer('RENT', 'Amazon Video', 'amazon', url, price='$19.99', available_from='2026-11-10T05:00:00Z',
                     created='2026-11-10T05:00:00Z'),
              _offer('BUY', 'Amazon Video', 'amazon', url, price='$24.99', available_from='2026-11-10T05:00:00Z',
                     created='2026-11-10T05:00:00Z')]
    _returned_screening(nrw, offers, stale_flags)

    nrw.enrich()

    # A $19.99 rental live on Amazon while still in theaters is out (owner, Nov 2026): no PVOD
    # pull, and no festival exemption either -- the labeler decides like for any film.
    rec = nrw.track(DISPOSABLE)
    assert rec['status'] == 'available' and rec.get('_jw_revert_reason') != 'justwatch_theatrical_pvod', rec
    assert nrw.lane(DISPOSABLE) == 'MAIN WALL'


def test_returned_screening_step0_ignores_its_festival_page_as_an_offer(nrw):
    """Discovery confirmed a $4.99 Amazon rental (SYNTHETIC); by enrichment JustWatch only
    lists the film's own Eventive page. With festival platforms excluded, Step 0 finds no
    valid offer: pulled, and today is a day it was proven not out."""
    _returned_screening(nrw, amazon_rental(DISPOSABLE, price='$4.99', created='2026-11-10T05:00:00Z'))
    nrw.jw.catalog['Disposable Humanity'][0]['offers'] = [eventive_rental()]

    nrw.enrich()

    rec = nrw.track(DISPOSABLE)
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == 'justwatch_no_valid_offers'
    assert rec['_jw_last_refuted'] == today()
    assert DISPOSABLE not in nrw.wall()


def test_returned_screening_with_stale_flags_is_deferred_on_a_jw_error(nrw):
    """A JustWatch error during the returned screening's Step 0: no festival exemption
    from the deferral either (round 1: the stale flag skipped it and left the film on the
    main wall with no links) -- it waits hidden, tracking untouched."""
    url = 'https://watch.amazon.com/detail?gti=amzn1.dv.gti.00000000-0000-4000-8000-000001376929'
    _returned_screening(nrw, [_offer('RENT', 'Amazon Video', 'amazon', url, price='$4.99')], stale_flags=True)
    before = nrw.track(DISPOSABLE)

    nrw.jw.mode = 'connection_error'
    nrw.enrich()

    assert nrw.lane(DISPOSABLE) == 'HIDDEN' and nrw.wall()[DISPOSABLE]['_jw_unconfirmed'] == today()
    assert nrw.track(DISPOSABLE) == before
    assert nrw.deferred_reasons('Disposable Humanity') == ['jw_error_retry']


# ---------------------------------------------------------------------------
# (j) The 90-day archive never takes a film still waiting for its check
# ---------------------------------------------------------------------------

def test_archive_keeps_a_putback_waiting_for_its_justwatch_check(nrw):
    """Prey of Wrath is put back dated 2026-05-20 (over 90 days ago) and JustWatch errors
    in enrichment: it waits hidden. The 90-day archive must keep it in data.json --
    archived unchecked, nothing would ever check it again. Once its check passes the next
    day, it ages into the archive as usual (dated over 90 days ago)."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    assert nrw.wall()[PREY]['digital_date'] == '2026-05-20'
    nrw.jw.mode = 'connection_error'
    nrw.enrich()
    assert nrw.lane(PREY) == 'HIDDEN'

    nrw.archive_old()
    assert PREY in nrw.wall() and PREY not in nrw.archived_ids(), 'archived before its JustWatch check'

    nrw.jw.mode = 'up'
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()
    assert nrw.wall()[PREY]['_enrichment_status'] == 'completed' and not nrw.wall()[PREY].get('hidden')
    nrw.archive_old()
    assert PREY not in nrw.wall() and PREY in nrw.archived_ids()


# ---------------------------------------------------------------------------
# (k) The morning report says what happened
# ---------------------------------------------------------------------------

def test_morning_report_shows_a_putback_waiting_hidden_for_its_check(nrw):
    """After a JustWatch error in enrichment the report counts the film waiting hidden,
    lists it under 'Put back today' as hidden-waiting (not 'wall'), and flags the
    deferral under Concerns."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.jw.mode = 'connection_error'
    nrw.enrich()

    out = nrw.morning_report()

    assert 'Waiting hidden for a JustWatch check (error or enrichment limit): 1' in out
    assert 'Put back today (came out after a hold): 1' in out
    line = next(ln for ln in out.splitlines() if 'Prey of Wrath (2026)' in ln and 'held since' in ln)
    assert line.endswith('| hidden — waiting for a JustWatch check'), line
    assert 'dated 2026-05-20' in line
    assert 'Other enrichment deferrals (→ Concerns): 1' in out
    assert 'Prey of Wrath — jw_error_retry' in out


def test_morning_report_shows_the_putback_on_the_wall_once_checked(nrw):
    """Same run, JustWatch up: no 'waiting' line, and the put-back's 'where' is the wall."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.enrich()

    out = nrw.morning_report()

    assert 'Waiting hidden for a JustWatch check' not in out
    line = next(ln for ln in out.splitlines() if 'Prey of Wrath (2026)' in ln and 'held since' in ln)
    assert line.endswith('| wall'), line


def test_morning_report_new_releases_say_where_each_film_is(nrw):
    """(Round 2 review: New Releases called a film hidden for its JustWatch check 'shown'.)
    Same run: Prey of Wrath is put back and its JustWatch lookup errors in enrichment (it
    waits hidden; JustWatch answers for every other title); After This Death arrives as a
    pre-order (SYNTHETIC: its pending pre-order fields dropped and TMDB dating it 10 days
    out, so discovery surfaces it fresh). The curator has locked After This Death not-slop
    (is_slop False, /marknotslop), so its line shows its lane rather than 'slop'."""
    nrw.seed(PREY, AFTER_DEATH, **{AFTER_DEATH: {'digital_date': None, '_type4_pending': None,
                                                 '_is_preorder': None, 'enriched': False}})
    nrw.tmdb.release_dates[AFTER_DEATH] = _us_dates(AFTER_DEATH, (4, day(10)))
    nrw.jw.catalog['Prey of Wrath'] = [jw_node('Prey of Wrath')]
    nrw.jw.catalog['After This Death'] = [synthetic_node(AFTER_DEATH, 'After This Death', 2025,
                                                         'after-this-death')]
    nrw.discover()
    assert nrw.lane(PREY) == 'MAIN WALL' and nrw.lane(AFTER_DEATH) == 'PRE-ORDER', 'setup'
    nrw.edit_wall_entry(AFTER_DEATH, is_slop=False)
    nrw.jw.failing.add('Prey of Wrath')

    nrw.enrich()

    assert nrw.lane(PREY) == 'HIDDEN' and nrw.lane(AFTER_DEATH) == 'PRE-ORDER'
    out = nrw.morning_report()
    assert 'New Releases: 2' in out
    assert '  • Prey of Wrath (2026) — hidden — waiting for a JustWatch check' in out, out
    assert '  • After This Death (2025) — pre-order' in out, out
    assert '— shown' not in out


def test_morning_report_names_a_review_dated_putback_in_plain_words(nrw):
    """(Round 2 review: the putback_review date source printed as the raw key.) Sukma, held
    on the old permanent skip (SYNTHETIC: _skip_provider_discovery set on its real row), so
    it was not checked daily; TMDB has no US date. JustWatch now lists it on Tubi
    (SYNTHETIC offer) with only JustWatch's 2000-07-14 no-record placeholder as its record
    date. Dated today with no evidence, flagged for the owner (putback_review): the report
    says so in words."""
    from pipeline import putback
    tubi = _offer('ADS', 'Tubi TV', 'tubitv', 'https://tubitv.com/movies/100000001/sukma',
                  created=JW_PLACEHOLDER_DATE)
    nrw.seed(SUKMA, **{SUKMA: {'_skip_provider_discovery': True}})
    nrw.jw.catalog['Sukma'] = [jw_node('Sukma', [tubi])]
    nrw.discover()
    rec = nrw.track(SUKMA)
    assert (rec['digital_date'], rec['_digital_date_source']) == (today(), putback.REVIEW), 'setup'
    assert rec['_date_needs_review'] is True
    nrw.enrich()

    out = nrw.morning_report()

    line = next(ln for ln in out.splitlines() if 'Sukma (2025)' in ln and 'held since' in ln)
    assert (f'DATE NEEDS REVIEW — dated {today()} (no date evidence — the day JustWatch confirmed it): '
            'weak evidence') in line, line
    assert line.endswith('| wall'), line
    assert putback.REVIEW not in out


def test_morning_report_counts_films_the_owner_sent_back_as_held(nrw):
    """The owner's Revert ('not out yet' -- the opposite of Remove) sends a put-back film back
    to waiting: putback.owner_revert, the rule the admin button, scripts/revert_movie.py and
    /revert apply. The report counts it with the held films, in words."""
    from pipeline import putback
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.enrich()
    rec = nrw.track(PREY)
    assert putback.owner_revert(rec) is True
    nrw.put_track(PREY, rec)

    out = nrw.morning_report()

    assert 'Held, checked daily until they come out: 1 (1 you sent it back (not out yet))' in out, out
    assert 'Put back today' not in out, 'a film the owner sent back is still listed as put back'


@pytest.mark.parametrize('failure, expected', [
    ('connection_error', '⚠ JustWatch trouble during discovery (→ Concerns): 1 lookup error(s) — '
                         'those films wait for the next run (no strike)'),
    ('malformed', '⚠ JustWatch trouble during discovery (→ Concerns): 1 lookup error(s) — '
                  'those films wait for the next run (no strike)'),
    ('blocked', '⚠ JustWatch trouble during discovery (→ Concerns): 0 lookup error(s); outage detected — '
                'those films wait for the next run (no strike)'),
    ('up', None),
])
def test_morning_report_flags_justwatch_trouble_during_discovery(nrw, failure, expected):
    """JustWatch fails while discovery checks a held film: the film just waits (no strike,
    not on the wall), and the report says JustWatch had trouble (lookup errors from
    metrics/discovery_run.json results.jw_errors; an outage from jw_healthy False)."""
    nrw.seed(WILDCARDS)
    nrw.jw.catalog['Wildcards'] = [jw_node('Wildcards')]
    nrw.jw.mode = failure
    nrw.discover()

    rec = nrw.track(WILDCARDS)
    out = nrw.morning_report()
    if expected:
        assert rec['_jw_revert_count'] == TRACKING_78303FD6[WILDCARDS]['_jw_revert_count'], 'error counted'
        assert expected in out, out
    else:
        assert 'JustWatch trouble' not in out
    assert WILDCARDS not in nrw.wall()


# ---------------------------------------------------------------------------
# (k2) Owner rules (Nov 15): Remove and Revert are opposites
#      Remove = never on the wall again (status 'removed', set only by the owner).
#      Revert = back to waiting, back on the wall the day it's really out.
# ---------------------------------------------------------------------------

def _admin_remove(nrw, mid):
    """The owner's admin-panel Remove (the real Flask route) on the tmp checkout."""
    nrw.mp.setattr(logging.getLogger('admin'), 'handlers', [logging.NullHandler()])  # no log file
    from admin import create_app
    app = create_app()
    app.testing = True
    with app.test_client() as client:
        return client.post('/remove-movie', json={'movie_id': int(mid)}).get_json()


REMOVED_REVIVED_DEFECT = (
    "CODE: pipeline/enricher.py never checks a record's status 'removed'. A removed title whose "
    "wall entry outlives the Remove (a running process writes back the data.json it loaded before, "
    "or the route's own data.json write fails) is re-queued by catch-up -- every run while it waits "
    "hidden (_jw_unconfirmed) or is a past-date pre-order (force-queued) -- and when JustWatch shows "
    "no offer, Step 0's revert sets its tracking status to 'tracking' (enricher.py ~1320; the "
    "buy-only soft revert ~1229 and catch-up's buy-only revert ~935 do the same): the removed title "
    "is held again, checked daily, and discovery puts it back on the wall. Fix: leave status "
    "'removed' records out of the catch-up queue and skip them at the top of the per-film loop "
    "(`if movie_data.get('status') == 'removed': continue`); the end-of-run purge then drops the entry.")


@pytest.mark.parametrize('waiting_as', ['hidden_for_its_check', 'past_date_preorder'])
def test_enrichment_never_brings_a_removed_title_back(nrw, waiting_as):
    """Owner rule: nothing may bring a removed title back. The owner removes a film whose wall
    entry is waiting for its JustWatch check -- Prey of Wrath, hidden after a JustWatch error,
    or The Vile, a past-date pre-order -- with the admin Remove (the real route). A process
    that loaded data.json before the Remove then writes its copy back (the stale-wall case the
    plumbing tests use), so the entry is still there at the next run. That run JustWatch shows
    no offer for it. The record must stay 'removed' and the entry go; the run after, when
    JustWatch lists it, discovery must neither check it nor put it back."""
    if waiting_as == 'hidden_for_its_check':
        mid, title = PREY, 'Prey of Wrath'
        _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
        nrw.jw.mode = 'connection_error'
        nrw.enrich()
        nrw.jw.mode = 'up'
        assert nrw.lane(PREY) == 'HIDDEN'
        nrw.next_day(1)
        nrw.nothing_new_today(day(1))
    else:
        mid, title = VILE, 'The Vile'
        nrw.jw.catalog['The Vile'] = [synthetic_node(VILE, 'The Vile', 2025, 'the-vile')]
        _vile_graduated_unenriched(nrw)                  # next run: The Vile is past its date
        nrw.edit_wall_entry(PREY, _enrichment_status='completed')
    stale = json.load(open(nrw.root / 'data.json'))
    body = _admin_remove(nrw, mid)
    assert body['success'] is True and mid not in nrw.wall(), body
    nrw._write('data.json', stale)                       # the stale copy written back
    removed = nrw.track(mid)
    assert removed['status'] == 'removed'
    nrw.jw.catalog[title][0]['offers'] = []              # JustWatch: no offer today

    nrw.enrich()

    rec = nrw.track(mid)
    assert rec['status'] == 'removed', f"a removed title is waiting again: status {rec['status']!r} " \
                                       f"({rec.get('_jw_revert_reason')})"
    assert mid not in nrw.wall()

    nrw.jw.catalog[title][0]['offers'] = amazon_rental(mid, available_from=stamp(-1), created=stamp(0, 0))
    nrw.next_day(2)                                      # the run after: JustWatch lists it
    mark = nrw.mark()
    nrw.discover()
    assert title not in nrw.queried_since(mark) and mid not in nrw.wall()
    assert nrw.track(mid)['status'] == 'removed'


def test_enrichment_purges_an_owner_reverted_film_and_leaves_it_waiting(nrw):
    """Revert is the opposite of Remove: the owner sends a film back because it isn't out yet
    (putback.owner_revert + putback.revert_wall_entry, what the admin button and
    scripts/revert_movie.py apply). The next enrichment run purges its wall entry like any
    reverted film -- it never becomes 'removed' -- and discovery keeps checking it on
    JustWatch every run: put back the day it is really out, dated after the revert."""
    from pipeline import putback
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.enrich()
    rec = nrw.track(PREY)
    assert putback.owner_revert(rec) is True
    nrw.put_track(PREY, rec)
    site = json.load(open(nrw.root / 'data.json'))
    assert putback.revert_wall_entry(site, PREY) is True
    nrw._write('data.json', site)
    assert nrw.lane(PREY) == 'HIDDEN'

    nrw.next_day(1)                                      # next run: nothing new, catch-up only
    nrw.nothing_new_today(day(1))
    nrw.enrich()

    rec = nrw.track(PREY)
    assert PREY not in nrw.wall() and PREY in nrw.archived_ids(), 'the reverted entry was not purged'
    assert rec['status'] == 'tracking' and rec['_jw_revert_reason'] == putback.OWNER_REVERT
    assert rec['_jw_last_refuted'] == today()

    nrw.next_day(2)                                      # it comes out: Amazon's rental goes live
    # (a real Amazon offer always carries its offer start: 18 of 18 in the Nov 13/14 captures)
    nrw.jw.catalog['Prey of Wrath'][0]['offers'].extend(
        amazon_rental(PREY, available_from=stamp(2, 0), created=stamp(2, 0)))
    mark = nrw.mark()
    nrw.discover()
    assert 'Prey of Wrath' in nrw.queried_since(mark)
    rec = nrw.track(PREY)
    assert rec['status'] == 'available' and PREY in nrw.wall()
    assert rec['digital_date'] > today(), f"put back dated {rec['digital_date']}, on/before the revert day"
    assert (rec['digital_date'], rec['_digital_date_source']) == (day(2), putback.OFFER_START)


# ---------------------------------------------------------------------------
# (l) Curation lists leave out films waiting hidden for their check
# ---------------------------------------------------------------------------

def test_curation_lists_skip_a_film_waiting_hidden_for_its_check(nrw):
    """(Round 2 review: /curate, /flow, /today and the quote/capsule batches listed films
    hidden for a JustWatch check.) curate_list._in_window -- the one window rule /curate's
    stages, /flow, /today, the morning backlog and the batch quote/capsule scripts share --
    leaves out a film waiting hidden (_jw_unconfirmed): not on the wall, nothing to curate
    yet. Once its check passes the next run, the put-back (an old date, landed this week)
    is a curation candidate again."""
    _put_back_today(nrw, PREY, 'Prey of Wrath', jw_node('Prey of Wrath'))
    nrw.jw.mode = 'connection_error'
    nrw.enrich()
    assert nrw.lane(PREY) == 'HIDDEN'
    curate_list = nrw.script('curate_list')

    def listed():
        return {'window': curate_list._in_window(nrw.wall()[PREY], day(-7), today()),
                'selects': PREY in {str(m.get('id')) for m in curate_list.review_rows('selects')},
                'capsule': PREY in {str(m.get('id')) for m, _ in curate_list.capsule_queue()},
                'backlog': 'Prey of Wrath (2026)' in nrw.morning_report('backlog')}

    assert listed() == {'window': False, 'selects': False, 'capsule': False, 'backlog': False}

    nrw.jw.mode = 'up'                                   # next run: its check passes
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()
    assert nrw.lane(PREY) == 'MAIN WALL'
    assert listed() == {'window': True, 'selects': True, 'capsule': True, 'backlog': True}


# ---------------------------------------------------------------------------
# (m) Enrichment stops itself before the daily run kills it
# ---------------------------------------------------------------------------

def test_enrichment_loop_timeout_fires_before_the_daily_orchestrator_kill(nrw):
    """Round 2b: constants.ENRICHMENT_LOOP_TIMEOUT_MINUTES 120 -> 50. daily_orchestrator.py
    kills `generate_data.py --enrich` after its phase timeout, and a killed run saves nothing
    (every hide, revert and enrichment of the run is lost). The loop timeout plus the film in
    progress (its per-film alarm) must fit inside that kill. (The loop clock starts after the
    pre-order link finder and the IMDb preload; their time is not counted here.)"""
    import constants
    src = open(f'{WT}/daily_orchestrator.py').read()
    kill = re.search(r'"python3 generate_data\.py --enrich",[^)]*?timeout=(\d+)', src)
    assert kill, 'daily_orchestrator.py: no timeout found for the --enrich phase'
    per_film = re.search(r'_PER_MOVIE_TIMEOUT_S = (\d+)', open(f'{WT}/pipeline/enricher.py').read())
    assert per_film, 'pipeline/enricher.py: per-film alarm not found'
    budget = constants.ENRICHMENT_LOOP_TIMEOUT_MINUTES * 60 + int(per_film.group(1))
    assert budget < int(kill.group(1)), (f'loop timeout {constants.ENRICHMENT_LOOP_TIMEOUT_MINUTES} min + '
                                         f'{per_film.group(1)} s per film >= the {kill.group(1)} s kill')


# ---------------------------------------------------------------------------
# (n) Round-2 holes fixed in round 2b (were strict xfail)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('mode', ['connection_error', 'up'], ids=['jw_error', 'control_jw_up'])
def test_jw_error_hide_survives_the_coming_soon_uncap(nrw, mode):
    """(Round 2: strict xfail -- the display step's Coming Soon un-hide, run inside
    enrichment, undid the JustWatch-error hide. Round 2b: it never un-hides a
    _jw_unconfirmed entry.)
    After This Death was surfaced while dated more than 30 days out, so the display step's
    Coming Soon cap hid it (hidden + _coming_soon_capped; SYNTHETIC dates). TMDB then moves
    its digital date to today (it comes out early: discovery lets it through unchecked).
      jw_error: JustWatch errors during enrichment -- it must wait hidden, still marked
        unconfirmed, and the next run's passing check shows it.
      control_jw_up: JustWatch lists a live Amazon rental (SYNTHETIC) -- shown the same
        run, cap marker gone (the un-cap still works for a film that was checked)."""
    nrw.seed(AFTER_DEATH, **{AFTER_DEATH: {'digital_date': day(40)}})
    nrw.put_on_wall(dict(WALL_78303FD6[AFTER_DEATH], digital_date=day(40), hidden=True,
                         _coming_soon_capped=True))
    nrw.jw.catalog['After This Death'] = [synthetic_node(
        AFTER_DEATH, 'After This Death', 2025, 'after-this-death',
        amazon_rental(AFTER_DEATH, available_from=stamp(-1), created=stamp(0, 0)))]
    nrw.discover()
    assert nrw.track(AFTER_DEATH)['status'] == 'available'

    nrw.jw.mode = mode
    nrw.enrich()

    entry = nrw.wall()[AFTER_DEATH]
    if mode == 'up':
        assert nrw.lane(AFTER_DEATH) == 'MAIN WALL' and '_jw_unconfirmed' not in entry
        assert '_coming_soon_capped' not in entry and entry['watch_links'].get('vod')
        return
    assert entry.get('_jw_unconfirmed') == today()
    assert entry.get('hidden') is True, 'published unconfirmed: the Coming Soon un-hide undid the hide'

    nrw.jw.mode = 'up'                                   # next run: JustWatch answers
    nrw.shift_clock(1)
    nrw.nothing_new_today(day(1))
    nrw.enrich()
    entry = nrw.wall()[AFTER_DEATH]
    assert nrw.lane(AFTER_DEATH) == 'MAIN WALL', 'checked film still hidden'
    assert '_jw_unconfirmed' not in entry and '_coming_soon_capped' not in entry


@pytest.mark.parametrize('store, live', [
    ('itunes', False),                 # Apple's store ('Apple TV Store' / itunes): offer start = theatrical date
    ('vudu', False),                   # Fandango At Home: a RENT offer proves nothing (pre-orders)
    ('amazon', True),                  # Amazon, offer start passed (real: 2026-11-03)
    ('amazon_future', False),          # Amazon, offer start not reached (a pre-order listing)
])
def test_live_rental_detection_uses_justwatchs_real_store_names(nrw, store, live):
    """Sense and Sensibility's real JustWatch offers (2026-11-14), keeping one store's. Amazon's
    rental, live since 2026-11-03 (its digital date), counts as a live rental. Apple's does not
    (round 2c): its offer start is 2026-10-16, the THEATRICAL date -- Apple's store lists rentals
    from the theater opening, so it proves nothing about today. Neither does Fandango At Home's
    (stores list pre-order rentals as plain RENT offers). amazon_future: the same Amazon offers
    with their start moved a week out (SYNTHETIC) -- not live yet."""
    from pipeline.justwatch import JustWatchClient
    node = jw_node('Sense and Sensibility')
    tech = 'amazon' if store == 'amazon_future' else store
    node['offers'] = [o for o in node['offers'] if o['package']['technicalName'] == tech]
    if store == 'amazon_future':
        for o in node['offers']:
            o['availableFromTime'] = stamp(7)
    nrw.jw.catalog['Sense and Sensibility'] = [node]

    r = JustWatchClient(logger=logging.getLogger('test')).verify_availability(
        'Sense and Sensibility', 2026, tmdb_id=SENSE)

    assert r['verified'] is True and r['has_rent']
    assert r['has_live_rent'] is live, f"{store}: has_live_rent={r['has_live_rent']} ({r['provider_names']['rent']})"
