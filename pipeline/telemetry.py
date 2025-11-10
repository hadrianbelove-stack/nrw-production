#!/usr/bin/env python3
"""
Telemetry Service - Structured logging and metrics for NRW pipeline.

Provides unified telemetry across Storage, Validation, and Enrichment services with:
- Structured event logging (service, action, file, item_id, result, duration_ms, error)
- Counter management (quarantined_files, validated_items, enriched_items, retry_count)
- Summary reporting with configurable sinks
- JSONL output for log aggregation systems
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import logging
from collections import defaultdict


class TelemetryService:
    """
    Centralized telemetry and metrics tracking for pipeline services.

    Responsibilities:
        - Emit structured log events with consistent schema
        - Track counters across all services
        - Generate summary reports
        - Write telemetry to configurable sinks (console, file, metrics dir)

    Design:
        - Shared instance across all pipeline services
        - Thread-safe counter updates
        - Configurable output destinations
        - JSONL format for easy parsing
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize telemetry service.

        Args:
            logger: Logger instance for operation tracking
            config: Configuration dict with telemetry settings
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = config or {}

        # Load telemetry configuration
        telemetry_config = self.config.get('telemetry', {})
        self.enabled = telemetry_config.get('enabled', True)
        self.console_enabled = telemetry_config.get('console', True)
        self.file_enabled = telemetry_config.get('file', True)
        self.metrics_dir = telemetry_config.get('metrics_dir', 'metrics')
        self.file_path = telemetry_config.get('file_path', 'metrics/telemetry.jsonl')

        # Initialize counters
        self.counters: Dict[str, int] = defaultdict(int)

        # Event buffer (for summary reporting)
        self.events: List[Dict[str, Any]] = []

        # Session metadata
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_start = time.time()

        # Create metrics directory if enabled
        if self.enabled and self.file_enabled:
            os.makedirs(os.path.dirname(self.file_path) if '/' in self.file_path else self.metrics_dir, exist_ok=True)

    def emit(
        self,
        service: str,
        action: str,
        result: str,
        file: Optional[str] = None,
        item_id: Optional[Union[str, int]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit a structured telemetry event.

        Args:
            service: Service name (storage, validation, enrichment)
            action: Action being performed (load_cache, validate_schema, get_watch_links)
            result: Result status (success, failure, warning, skip)
            file: File path being operated on (optional)
            item_id: Item identifier (movie_id, cache_key, etc) (optional)
            duration_ms: Operation duration in milliseconds (optional)
            error: Error message if result=failure (optional)
            metadata: Additional context (optional)

        Example:
            telemetry.emit(
                service='storage',
                action='load_cache',
                result='success',
                file='cache/watch_links_cache.json',
                duration_ms=15.2
            )
        """
        if not self.enabled:
            return

        # Build event structure
        event = {
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'service': service,
            'action': action,
            'result': result,
        }

        # Add optional fields
        if file:
            event['file'] = file
        if item_id is not None:
            event['item_id'] = str(item_id)
        if duration_ms is not None:
            event['duration_ms'] = round(duration_ms, 2)
        if error:
            event['error'] = error
        if metadata:
            event['metadata'] = metadata

        # Store event for summary
        self.events.append(event)

        # Write to file sink (JSONL format)
        if self.file_enabled:
            try:
                with open(self.file_path, 'a') as f:
                    f.write(json.dumps(event) + '\n')
            except Exception as e:
                self.logger.warning(f"Failed to write telemetry event to {self.file_path}: {e}")

        # Console output (structured)
        if self.console_enabled:
            self._log_event_to_console(event)

    def _log_event_to_console(self, event: Dict[str, Any]) -> None:
        """
        Log structured event to console with appropriate log level.

        Args:
            event: Event dict with all fields
        """
        result = event.get('result', 'unknown')
        service = event.get('service', 'unknown')
        action = event.get('action', 'unknown')
        item_id = event.get('item_id', '')
        duration = event.get('duration_ms', '')
        error = event.get('error', '')

        # Build log message
        parts = [f"{service}.{action}"]
        if item_id:
            parts.append(f"[{item_id}]")
        parts.append(f"→ {result}")
        if duration:
            parts.append(f"({duration}ms)")
        if error:
            parts.append(f"- {error}")

        log_msg = " ".join(parts)

        # Log at appropriate level
        if result == 'failure':
            self.logger.error(log_msg)
        elif result == 'warning':
            self.logger.warning(log_msg)
        elif result == 'skip':
            self.logger.debug(log_msg)
        else:
            self.logger.debug(log_msg)

    def increment(self, counter: str, amount: int = 1) -> None:
        """
        Increment a named counter.

        Args:
            counter: Counter name (e.g., 'quarantined_files', 'validated_items')
            amount: Amount to increment by (default: 1)

        Common counters:
            - quarantined_files: Files moved to backups/ due to corruption
            - validated_items: Items that passed schema validation
            - enriched_items: Items successfully enriched with watch links
            - retry_count: Number of retry attempts
            - cache_hits: Cache hits across services
            - api_calls: External API calls made
        """
        if not self.enabled:
            return
        self.counters[counter] += amount

    def get_counter(self, counter: str) -> int:
        """
        Get current value of a counter.

        Args:
            counter: Counter name

        Returns:
            int: Current counter value
        """
        return self.counters.get(counter, 0)

    def get_all_counters(self) -> Dict[str, int]:
        """
        Get all counters as a dict.

        Returns:
            Dict: All counters and their current values
        """
        return dict(self.counters)

    def reset_counters(self) -> None:
        """Reset all counters to zero."""
        self.counters.clear()

    def get_summary(self) -> Dict[str, Any]:
        """
        Generate summary report of telemetry data.

        Returns:
            Dict: Summary statistics including:
                - session_id: Unique session identifier
                - duration_seconds: Total session duration
                - event_count: Total events emitted
                - events_by_service: Event count grouped by service
                - events_by_result: Event count grouped by result
                - counters: All counter values
                - top_errors: Most frequent errors
        """
        session_duration = time.time() - self.session_start

        # Count events by service
        events_by_service = defaultdict(int)
        for event in self.events:
            events_by_service[event.get('service', 'unknown')] += 1

        # Count events by result
        events_by_result = defaultdict(int)
        for event in self.events:
            events_by_result[event.get('result', 'unknown')] += 1

        # Find top errors
        error_counts = defaultdict(int)
        for event in self.events:
            if event.get('error'):
                error_counts[event['error']] += 1
        top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            'session_id': self.session_id,
            'duration_seconds': round(session_duration, 2),
            'event_count': len(self.events),
            'events_by_service': dict(events_by_service),
            'events_by_result': dict(events_by_result),
            'counters': self.get_all_counters(),
            'top_errors': [{'error': err, 'count': count} for err, count in top_errors]
        }

    def print_summary(self) -> None:
        """
        Print formatted summary report to console.

        Displays:
            - Session metadata
            - Event statistics by service and result
            - All counters
            - Top errors
        """
        summary = self.get_summary()

        print("\n" + "="*80)
        print("TELEMETRY SUMMARY")
        print("="*80)

        print(f"\nSession: {summary['session_id']}")
        print(f"Duration: {summary['duration_seconds']}s")
        print(f"Total Events: {summary['event_count']}")

        # Events by service
        if summary['events_by_service']:
            print("\nEvents by Service:")
            for service, count in sorted(summary['events_by_service'].items()):
                print(f"  {service}: {count}")

        # Events by result
        if summary['events_by_result']:
            print("\nEvents by Result:")
            for result, count in sorted(summary['events_by_result'].items()):
                icon = {
                    'success': '✓',
                    'failure': '✗',
                    'warning': '⚠',
                    'skip': '⊘'
                }.get(result, '•')
                print(f"  {icon} {result}: {count}")

        # Counters
        if summary['counters']:
            print("\nCounters:")
            for counter, value in sorted(summary['counters'].items()):
                print(f"  {counter}: {value}")

        # Top errors
        if summary['top_errors']:
            print("\nTop Errors:")
            for item in summary['top_errors']:
                error_msg = item['error']
                # Truncate long errors
                if len(error_msg) > 60:
                    error_msg = error_msg[:57] + "..."
                print(f"  [{item['count']}x] {error_msg}")

        print("\n" + "="*80)

    def save_summary(self, filepath: Optional[str] = None) -> str:
        """
        Save summary report to JSON file.

        Args:
            filepath: Path to save summary (default: metrics/summary-{session_id}.json)

        Returns:
            str: Path where summary was saved
        """
        if not filepath:
            filepath = os.path.join(self.metrics_dir, f"summary-{self.session_id}.json")

        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath) if '/' in filepath else self.metrics_dir, exist_ok=True)

        summary = self.get_summary()

        try:
            with open(filepath, 'w') as f:
                json.dump(summary, f, indent=2)
            self.logger.info(f"Saved telemetry summary to {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to save telemetry summary to {filepath}: {e}")
            return ""


# Singleton instance (optional - can also be passed as dependency injection)
_telemetry_instance: Optional[TelemetryService] = None


def init_telemetry(logger: Optional[logging.Logger] = None, config: Optional[Dict] = None) -> TelemetryService:
    """
    Initialize global telemetry singleton.

    Args:
        logger: Logger instance
        config: Configuration dict

    Returns:
        TelemetryService: Initialized telemetry instance
    """
    global _telemetry_instance
    _telemetry_instance = TelemetryService(logger=logger, config=config)
    return _telemetry_instance


def get_telemetry() -> Optional[TelemetryService]:
    """
    Get global telemetry singleton.

    Returns:
        TelemetryService or None: Telemetry instance if initialized
    """
    return _telemetry_instance
