"""Put-back rules for films held off the wall as "not available yet".

Owner's rule (Nov 2026): a film can't hit the wall until you can actually rent, buy
or stream it — and it must go on THE DAY it comes out. So:

  - anything held is checked every run (daily), forever — no strike limit, no
    permanent skip (the old 4-strike `_skip_provider_discovery` lost 443 films);
  - when a held film is confirmed, it is dated the day it actually became
    available, from evidence, never on a day JustWatch had already said "no offer".

Evidence: the day JustWatch first recorded a real way to watch it (its earliest
qualifying offer record — exact for fresh releases, and right for older films whose
Amazon offer start is a later re-listing: Dolly 2026-03-31, not Amazon's 2026-10-22),
and TMDB's earliest US digital date. The earlier one wins, except a JustWatch record
from the film's theater week when TMDB's digital date is later (a store pre-order
listing: Project Hail Mary's Apple rental was recorded on its 2026-03-20 opening day;
it came out 2026-05-12). Reissues never use JustWatch records (those belong to the
original release).

History: every past pre-release clean-up pulled films into a state nothing
re-checked (Jan 20, Mar 27, the April sweeps, May 28, June). See
docs/MISTAKES_LOG.md 2026-11-14.
"""
from datetime import datetime, timedelta, timezone

# Hold reasons where JustWatch had the film and showed NO qualifying offer: a real
# "not available that day". (No-match means JustWatch couldn't find the title,
# which says nothing about availability; a PVOD hold had live rentals.)
REFUTING_REASONS = frozenset({'justwatch_no_valid_offers', 'zero_watch_links'})

FIRST_OFFER = 'jw_first_offer'   # the day JustWatch first recorded a qualifying offer
EVIDENCE = 'putback_evidence'    # TMDB's earliest US digital date
CONFIRMED = 'jw_first_verified'  # the day JustWatch first confirmed it (checked daily)
AFTER_HOLD = 'putback_after_hold'  # evidence predates the last "not out yet" day: the day after
REVIEW = 'putback_review'        # no evidence, unchecked during the hold: owner confirms
OFFER_START = 'jw_offer_start'   # an owner-reverted film: the day Amazon's rental went live
PROTECTED_SOURCES = frozenset({FIRST_OFFER, EVIDENCE, CONFIRMED, AFTER_HOLD, REVIEW, OFFER_START})

THEATER_WEEK_DAYS = 7


def today_str():
    return datetime.now().strftime('%Y-%m-%d')


def _shift(day, n):
    return (datetime.strptime(day[:10], '%Y-%m-%d') + timedelta(days=n)).strftime('%Y-%m-%d')


def is_reissue(rec):
    """A reissue or restoration: confirmed in tracking, or one the owner reverted that the wall
    showed as a restoration (_revert_restoration, stamped by owner_revert)."""
    return bool(rec.get('_reissue') or rec.get('reissue_label') or rec.get('_reissue_deferred')
                or rec.get('_revert_restoration'))


def wall_restoration(entry):
    """The wall shows this film as a restoration or reissue (display.py: a year gap,
    admin/reissue_labels.json, a confirmed reissue) -- its tracking record may not say so."""
    e = entry or {}
    return bool(e.get('_reissue') or e.get('reissue_label') or (e.get('filters') or {}).get('is_restoration'))


def _jw_last_check(rec, today=None):
    """Last day a JustWatch check found nothing. `_jw_last_checked` is stamped on every
    failed check from Nov 2026 on; older holds were checked once a run from
    `_jw_reverted_at`, `_jw_revert_count` times — never later than yesterday (that field
    is sometimes re-set mid-hold, so cap it)."""
    if rec.get('_jw_last_checked'):
        return rec['_jw_last_checked'][:10]
    if rec.get('_jw_legacy_last_check'):
        return rec['_jw_legacy_last_check'][:10]
    first, n = rec.get('_jw_reverted_at'), int(rec.get('_jw_revert_count') or 0)
    if not first or n < 1:
        return None
    return min(_shift(first, n - 1), _shift(today or today_str(), -1))


def freeze_legacy_check(rec, today=None):
    """A hold from before Nov 2026 has no recorded check day, only the estimate above,
    which slides forward to "yesterday" every day. Freeze it the first time this code
    sees the hold, so a day it records nothing (a JustWatch error, the backlog limit)
    never becomes a "not out yet" day."""
    if rec.get('_jw_revert_count') and not rec.get('_jw_last_checked') and not rec.get('_jw_legacy_last_check'):
        est = _jw_last_check(rec, today)
        if est:
            rec['_jw_legacy_last_check'] = est


def last_check(rec, today=None):
    """The last day this held film was checked and found not out yet, or None. A store
    pre-order hold (`_rent_preorder_held`: the store page said "Pre-order") counts."""
    days = [d for d in (_jw_last_check(rec, today), (rec.get('_rent_preorder_held') or '')[:10]) if d]
    return max(days) if days else None


def note_refuted(rec, day):
    """Remember a day a check proved the film NOT out yet. Persistent: a later hold
    reason (a "no match", a PVOD pull) or a put-back never erases it, so no later
    put-back can be dated on or before it."""
    if day and (not rec.get('_jw_last_refuted') or day[:10] > rec['_jw_last_refuted']):
        rec['_jw_last_refuted'] = day[:10]


def last_refuted_day(rec, today=None):
    """The last day it was proven NOT out yet: JustWatch had it with no qualifying offer,
    a buy-only pre-order still had no rental, or the store page read "Pre-order". None
    when nothing proves it (a JustWatch no-match says nothing about availability; a PVOD
    hold had live rentals)."""
    days = [(rec.get('_jw_last_refuted') or '')[:10], (rec.get('_rent_preorder_held') or '')[:10]]
    if rec.get('_jw_revert_reason') in REFUTING_REASONS:
        days.append(_jw_last_check(rec, today))
    days = [d for d in days if d]
    return max(days) if days else None


def checked_daily(rec, was_skipped, today=None):
    """Was this held film being checked every day up to now? (A festival screening that
    just ended, or a film on the old permanent skip, was not.)"""
    if was_skipped:
        return False
    last = last_check(rec, today)
    if not last:
        return False
    gap = (datetime.strptime(today or today_str(), '%Y-%m-%d')
           - datetime.strptime(last, '%Y-%m-%d')).days
    return gap <= 2


def _jw_candidate(offer_dates, tmdb_digital, tmdb_theatrical, today):
    """Earliest JustWatch record that isn't a theater-week pre-order listing."""
    for d in sorted(x[:10] for x in (offer_dates or []) if x and x[:10] <= today):
        if (tmdb_theatrical and tmdb_theatrical[:10] <= d <= _shift(tmdb_theatrical, THEATER_WEEK_DAYS)
                and not (tmdb_digital and tmdb_digital[:10] <= d)):
            continue
        return d
    return None


def putback_date(rec, was_skipped, tmdb_digital, offer_dates, tmdb_theatrical=None, today=None):
    """Date for a held film JustWatch has just confirmed: (date, source).

    The earliest piece of evidence AFTER the last day it was proven not out yet: the
    day JustWatch first recorded a qualifying offer, or TMDB's earliest US digital date
    (for a returned festival screening, only a TMDB date after the screening ended — the
    festival date itself is not a release). Evidence that all falls on or before that day
    gives the day after it. With no evidence: a date this hold already got (a film pulled
    again after its put-back, e.g. a PVOD rental, keeps its first confirmed day), else
    today — as a confirmed date if it was checked daily, else flagged for the owner
    (source REVIEW): visible on the wall, so a wrong guess gets corrected instead of
    hiding a new film in the archive."""
    today = today or today_str()
    floor = last_refuted_day(rec, today)
    ended = (rec.get('_screening_ended') or '')[:10]
    after = [d[:10] for d in (offer_dates or []) if d and (not floor or d[:10] > floor)]
    jw = None if is_reissue(rec) else _jw_candidate(after, tmdb_digital, tmdb_theatrical, today)
    tmdb = tmdb_digital[:10] if tmdb_digital and not (ended and tmdb_digital[:10] <= ended) else None
    cands = sorted((d, src) for d, src in ((jw, FIRST_OFFER), (tmdb, EVIDENCE))
                   if d and d <= today and (not floor or d > floor))
    if cands:
        return cands[0]
    # Evidence exists but all of it is on or before the last "not out yet" day
    # (a pre-order listing, a stale record): it came out after that day.
    if floor and ((tmdb and tmdb <= today) or (offer_dates and not is_reissue(rec))):
        return min(_shift(floor, 1), today), AFTER_HOLD
    prev, prev_src = (rec.get('digital_date') or '')[:10], rec.get('_digital_date_source')
    if prev_src in (CONFIRMED, REVIEW) and prev and prev <= today and (not floor or prev > floor):
        return prev, prev_src
    return today, (CONFIRMED if checked_daily(rec, was_skipped, today) else REVIEW)


OWNER_REVERT = 'owner_revert'


def owner_revert(rec, today=None, wall_entry=None):
    """The owner sends a film back: it isn't really out yet (wrongly marked new, usually
    the pre-order problem). The OPPOSITE of a removal: it must come back on the wall the
    day it really comes out. Back to tracking as a held film (JustWatch checks it every
    run, no shortcut), never dated on or before today. Discovery puts it back only once
    JustWatch shows it watchable on something new since the revert (owner_revert_putback).
    A future TMDB date (pre-order) stays. Refuses a REMOVED title (removed = never back):
    returns False, changes nothing.

    wall_entry: its wall entry, when the caller has it -- the wall knows a restoration its
    tracking record may not (marked, so the revert's note explains how it comes back). A second click
    the same day (a retry to publish) keeps the first click's moment."""
    if rec.get('status') == 'removed':
        return False
    explicit_day = today
    today = today or today_str()
    same_day_retry = (is_owner_reverted(rec) and (rec.get('_reverted_by_owner') or '')[:10] == today
                      and bool(rec.get('_reverted_by_owner_at')))
    rec['status'] = 'tracking'
    if wall_restoration(wall_entry):
        rec['_revert_restoration'] = True   # JustWatch lists the original film (the note says so)
    rec['_jw_revert_reason'] = OWNER_REVERT
    rec.setdefault('_jw_reverted_at', today)
    rec['_jw_revert_count'] = max(1, int(rec.get('_jw_revert_count') or 0))
    rec['_jw_last_checked'] = today
    rec['_reverted_by_owner'] = today
    # The moment too: a release later the same day (an Amazon rental going live that
    # afternoon) is new since the revert even though its day isn't (revert_live_evidence).
    if explicit_day and explicit_day != today_str():
        rec.pop('_reverted_by_owner_at', None)   # a revert dated another day: compare days
    elif not same_day_retry:
        rec['_reverted_by_owner_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    note_refuted(rec, today)
    if (rec.get('digital_date') or '')[:10] <= today:
        rec.pop('digital_date', None)  # its wrong "new" date
    # _transitioned_at: the gap fill re-dated a pre-order to it. _added_manually: the
    # curator exemptions (no JustWatch check) would bring it straight back.
    for k in ('_put_back_on', '_held_since', '_date_needs_review', 'enrichment_date',
              '_transitioned_at', '_revert_page_preorder'):
        rec.pop(k, None)
    if rec.get('_added_manually'):
        rec['_added_manually_before_revert'] = rec.pop('_added_manually')
    rec['enriched'] = False
    return True


def is_owner_reverted(rec):
    """A film the owner sent back (Revert) that is still waiting to come out. Its wall entry
    stays off the wall (the purge drops it, enrichment never re-checks it) until discovery
    puts it back — that transition clears the flag."""
    return bool(rec) and rec.get('status') == 'tracking' and bool(rec.get('_reverted_by_owner'))


def _utc(stamp):
    """A JustWatch time ('2026-11-14T20:00:00Z') as an aware datetime; None for a bare date."""
    if not stamp or len(stamp) <= 10:
        return None
    try:
        t = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _new_since_revert(rec, stamp, today):
    """Did this offer record / offer start come after the owner's revert, and by today? By the
    moment when both are known (a rental going live the afternoon of a morning revert counts),
    else by the day: after the revert day."""
    day = (stamp or '')[:10]
    if not day or day > today:
        return False
    at, when = _utc(rec.get('_reverted_by_owner_at')), _utc(stamp)
    if at and when:
        return when > at
    return (rec.get('_reverted_by_owner') or '')[:10] < day


def revert_live_evidence(rec, stream_dates=(), live_rent_starts=(), today=None):
    """What JustWatch shows NEW since the owner's revert that makes the film watchable now: a
    streaming offer it recorded after the revert (FIRST_OFFER), or an Amazon rental whose offer
    start came after it and has passed — a pre-order going live (OFFER_START; a new Amazon
    tier going live counts too: it is a way to rent it now). Each may be a day or a full time
    (then compared with the moment of the revert). Sorted (day, source) pairs; a same-day one
    is dated after the revert day by the caller's floor."""
    today = today or today_str()
    return sorted({(d[:10], FIRST_OFFER) for d in (stream_dates or ()) if _new_since_revert(rec, d, today)}
                  | {(d[:10], OFFER_START) for d in (live_rent_starts or ()) if _new_since_revert(rec, d, today)})


def owner_revert_putback(rec, stream_dates=(), live_rent_starts=(), page_available=False,
                         tmdb_digital=None, today=None):
    """When a film the owner reverted comes back, and its date: (day, source), or None to keep
    waiting.

    Back only on something NEW since the revert that shows it watchable now
    (revert_live_evidence) — or, with nothing like that, its store page turning from
    "Pre-order" (read after the revert) to showing it for rent or sale (page_available: the
    caller checks).
    A new store listing alone never brings it back (Apple, Fandango At Home and Amazon list
    pre-order rentals as ordinary offers), nor does TMDB's date: that's what put it on the
    wall by mistake. A reissue the same way: JustWatch lists it under the original film, so
    the original's catalog changes count too (revert_caveat says so).

    Dated by that evidence: its earliest day after the last "not out yet" day, else the day
    after that day. On the store page's word alone: TMDB's date if it falls after that day,
    else today. Never on or before the revert day."""
    today = today or today_str()
    rev = (rec.get('_reverted_by_owner') or '')[:10]
    floor = last_refuted_day(rec, today) or rev
    if floor and floor >= today:
        return None   # proven not out today (reverted today, or a check said so)
    # A reissue / restoration too (owner, Nov 2026: no "you need to re-add it"): JustWatch lists
    # it under the original film, so something new there since the revert -- a new streaming
    # home, a new Amazon rental -- brings it back, even when it is the original's listing.
    live = revert_live_evidence(rec, stream_dates, live_rent_starts, today)
    if live:
        after = [c for c in live if c[0] > floor]
        return after[0] if after else (min(_shift(floor, 1), today), AFTER_HOLD)
    if not page_available:
        return None
    tmdb = (tmdb_digital or '')[:10]
    if tmdb and floor < tmdb <= today:
        return tmdb, EVIDENCE
    return today, CONFIRMED


def revert_caveat(rec, has_override=False):
    """A warning for the owner when the film just reverted may never come back by itself: a
    reissue (JustWatch can't tell the restoration from the original), or a film JustWatch may
    not list (a hand-added film, one with a watch-link override, an Apple Music Live special).
    None for an ordinary film."""
    if is_reissue(rec):
        return ("A reissue or restoration: JustWatch lists it under the original film, so it comes "
                "back the day something new to watch shows up there after today (a new streaming "
                "home, a new Amazon rental) -- now and then that is the original film's listing "
                "changing rather than the restoration itself.")
    if rec.get('_apple_music_live'):
        return ("Apple Music Live special: JustWatch doesn't list these, so it comes back when "
                "TMDB dates its release after today.")
    if rec.get('_added_manually_before_revert') or rec.get('_added_manually') or has_override:
        return ("This film was added by hand or has a watch-link override, so JustWatch may not "
                "list it: it comes back by itself only once JustWatch shows a new way to watch it. "
                "It is still checked daily.")
    return None


def mark_reverted_entry(m):
    """Mark a wall entry the way a revert does: hidden on every device, purged (and archived as
    a shell) by the next pipeline run."""
    m['_enrichment_status'] = 'reverted'
    m['_jw_reverted'] = True
    m['_jw_revert_reason'] = OWNER_REVERT
    m['status'] = 'tracking'
    m['hidden'] = True
    m.pop('_added_manually', None)   # enrichment would exempt it from JustWatch
    m.pop('_jw_unconfirmed', None)   # not "waiting for a JustWatch check": waiting to come out


def revert_wall_entry(site_data, movie_id):
    """Take a reverted film's wall entry off the wall now, through the normal revert path:
    hidden on every device and purged by the next pipeline run (tracking brings it back).
    True if the film had an entry."""
    found = False
    for m in site_data.get('movies', []):
        if str(m.get('id')) == str(movie_id):
            mark_reverted_entry(m)
            found = True
    return found


def needs_review(source, rec, was_skipped, today=None):
    """Should the owner check this put-back's date? A no-evidence date for a hold that
    went unchecked, or "the day after the last 'not out yet' day" when that day is only
    an estimate (the hold wasn't checked daily)."""
    return source == REVIEW or (source == AFTER_HOLD and not checked_daily(rec, was_skipped, today))
