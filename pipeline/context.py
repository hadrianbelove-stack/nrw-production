"""
Shared context object for pipeline modules.

Bundles the dependencies that every extracted module needs,
so each module takes one PipelineContext instead of 10+ constructor args.
"""

from dataclasses import dataclass, field
import logging


@dataclass
class PipelineContext:
    """Shared dependencies passed to all pipeline modules."""
    config: dict
    logger: logging.Logger
    storage: object          # StorageService instance
    enrichment_service: object  # EnrichmentService (JustWatch client, watch link cache, etc.)
    tmdb_key: str
    intake_stats: dict = field(default_factory=dict)
