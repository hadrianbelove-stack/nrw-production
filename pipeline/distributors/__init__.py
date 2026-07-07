"""Distributor release-calendar sources for proactive restoration discovery.

physicalmedia.fetch() returns deduped restoration-lane rows:
    {source_title, title, year, release_date, distributor, formats, kind, source_url}
(googlenews.collect() and kinolorber.fetch() are prototypes with non-conforming
rows — not yet Pass-E-ready.)

See docs/DISTRIBUTOR_TRACKING_PLAN.md. physicalmedia + tmdb_match feed intake
Pass E (pipeline/intake.py, gated by intake.enable_pass_e); the modules
themselves stay read-only.
"""
