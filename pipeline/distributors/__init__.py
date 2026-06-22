"""Distributor release-calendar sources for proactive restoration discovery.

Each module exposes a `fetch()` returning a list of normalized rows:
    {source_title, title, year, release_date, distributor, format, kind, source_url}

See docs/DISTRIBUTOR_TRACKING_PLAN.md. Prototype stage — read-only; nothing here
writes to the tracking DB or data.json yet.
"""
