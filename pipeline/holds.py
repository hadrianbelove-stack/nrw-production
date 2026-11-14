"""Hold bookkeeping for tracking films that JustWatch can't confirm yet.

Owner's rule: a film waits until you can actually rent / buy / stream it, then it
goes on the wall at that date. A hold is a WAIT, never a drop:

  - re-checked every run for its first HOLD_DAILY_CHECKS checks, then weekly;
  - only stops being checked HOLD_GIVE_UP_DAYS after it was first held;
  - JustWatch errors / outages never count as a check.

History (Nov 2026): a 4-strike permanent skip (`_skip_provider_discovery`) silently
dropped 443 films, and pre-order markers that survived a failed graduation looped
66 films on and off the wall every run. Every writer of hold fields goes through
this module so those rules can't drift apart again.
"""
from datetime import datetime

HOLD_DAILY_CHECKS = 4
HOLD_RECHECK_DAYS = 7
HOLD_GIVE_UP_DAYS = 365

HOLD_FIELDS = ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at', '_jw_last_checked')

# Pre-order markers that must not survive a recorded hold: a held film is not a live
# pre-order, and a leftover marker re-triggers discovery's pre-order bypass, which
# re-adds the film and purges it again every run.
PREORDER_FIELDS = ('_is_preorder', '_type4_pending', '_buyonly_preorder')

# Hold reasons where JustWatch showed no qualifying offer. The film wasn't confirmed
# watchable until JustWatch verified it, so that day is its wall date (not TMDB's
# earlier claimed date, which would also let the 90-day archive hide it instantly).
NO_OFFER_REASONS = frozenset({'justwatch_no_match', 'justwatch_no_valid_offers',
                              'zero_watch_links'})

JW_FIRST_VERIFIED = 'jw_first_verified'


def today_str():
    return datetime.now().strftime('%Y-%m-%d')


def days_between(start, end):
    """Whole days from start to end (YYYY-MM-DD prefixes); None if unparseable."""
    try:
        return (datetime.strptime(str(end)[:10], '%Y-%m-%d')
                - datetime.strptime(str(start)[:10], '%Y-%m-%d')).days
    except (TypeError, ValueError):
        return None


def due_for_check(rec, today=None):
    """True if this tracking film should get a JustWatch check this run."""
    if rec.get('_jw_revert_count', 0) < HOLD_DAILY_CHECKS:
        return True
    today = today or today_str()
    held = days_between(rec.get('_jw_reverted_at') or '', today)
    if held is not None and held > HOLD_GIVE_UP_DAYS:
        return False
    since = days_between(rec.get('_jw_last_checked') or '', today)
    return since is None or since >= HOLD_RECHECK_DAYS


def record_hold(rec, reason, today=None):
    """Record one failed JustWatch check on a tracking record. Returns the new count."""
    today = today or today_str()
    count = rec.get('_jw_revert_count', 0) + 1
    rec['_jw_revert_count'] = count
    rec['_jw_revert_reason'] = reason
    rec.setdefault('_jw_reverted_at', today)
    rec['_jw_last_checked'] = today
    rec.pop('_skip_provider_discovery', None)
    for k in PREORDER_FIELDS:
        rec.pop(k, None)
    return count


def clear_hold(rec):
    """Drop hold bookkeeping once JustWatch confirms the film.

    Returns the reason it was held (None if it wasn't held)."""
    reason = rec.get('_jw_revert_reason') if rec.get('_jw_revert_count') else None
    for k in HOLD_FIELDS:
        rec.pop(k, None)
    rec.pop('_skip_provider_discovery', None)
    return reason


RECENT_CHECK_DAYS = 14


def date_after_hold(rec, held_reason, recently_checked=True, today=None):
    """Set the wall date of a film that just passed JustWatch after a no-offer hold.

    recently_checked: JustWatch looked at it (and found nothing) within the last
    RECENT_CHECK_DAYS, so it became watchable between then and now: date it today.
    Otherwise — the pre-Nov-2026 backlog that nothing was checking — we can't tell
    when it arrived: keep the date it already had and flag it for the owner.

    Returns True if the date was changed."""
    if held_reason not in NO_OFFER_REASONS:
        return False
    today = today or today_str()
    dd = rec.get('digital_date') or ''
    if dd and dd >= today:
        return False
    if not recently_checked:
        rec['_date_needs_review'] = True
        if dd:
            return False
    if dd:
        rec['_date_before_hold'] = dd  # the unconfirmed date, kept for the report
    rec['digital_date'] = today
    rec['_digital_date_source'] = JW_FIRST_VERIFIED
    return True


def recently_checked(rec, was_skipped, today=None):
    """Did JustWatch look at this held film within RECENT_CHECK_DAYS?

    `_jw_last_checked` exists from Nov 2026 on. Before that, a film carrying the old
    permanent-skip flag had stopped being checked; any other held film was being
    checked every run."""
    last = rec.get('_jw_last_checked')
    if last:
        since = days_between(last, today or today_str())
        return since is not None and since <= RECENT_CHECK_DAYS
    return not was_skipped
