"""
NRW Pipeline - Modular data generation pipeline.

Extracted from monolithic generate_data.py for better maintainability.
"""

from pipeline.storage import StorageService
from pipeline.validation import ValidationService
from pipeline.enrichment import EnrichmentService
from pipeline.generator import DataGenerator
from pipeline.telemetry import TelemetryService, init_telemetry, get_telemetry
from pipeline.justwatch import JustWatchClient
from pipeline.display import DisplayGenerator
from pipeline.archive import ArchiveManager

__all__ = [
    'StorageService',
    'ValidationService',
    'EnrichmentService',
    'DataGenerator',
    'TelemetryService',
    'init_telemetry',
    'get_telemetry',
    'JustWatchClient',
    'DisplayGenerator',
    'ArchiveManager',
]
