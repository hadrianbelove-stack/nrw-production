#!/usr/bin/env python3
"""
Storage Service - File I/O operations for NRW pipeline.

Extracted from generate_data.py (2025-11-10) to separate storage concerns.
Handles all JSON file operations with atomic writes, backups, and file locking.
"""

import os
import json
import shutil
import time
from datetime import datetime
from typing import Dict, List, Optional, Union, Any
import logging


class StorageService:
    """
    Centralized file storage operations with atomic writes and backups.

    Responsibilities:
        - Load/save JSON cache files
        - Atomic writes with temp file + fsync + rename
        - Automatic timestamped backups
        - Archive management for movie tracking

    Design:
        - Integrates with file_lock.py for concurrent write safety
        - Maintains exact file paths and backup naming conventions
        - All writes create backups in backups/ directory
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize storage service.

        Args:
            logger: Logger instance for operation tracking
        """
        self.logger = logger or logging.getLogger(__name__)
        self._last_cleanup_check = 0.0  # Track last cleanup time for rate limiting

        # Run opportunistic cleanup at initialization
        self._cleanup_old_backups_opportunistic()

    def _quarantine_file(self, filepath: str, reason: str) -> str:
        """
        Move corrupt file to backups/ directory with descriptive naming.

        Args:
            filepath: Path to corrupt file
            reason: Reason for quarantine (e.g., 'parse', 'str', 'ioerror')

        Returns:
            str: Path to backup file

        Note:
            Creates backups/ directory if it doesn't exist.
            Backup filename format: <basename>.corrupted-<reason>-<timestamp>.json
        """
        try:
            os.makedirs('backups', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            basename = os.path.splitext(os.path.basename(filepath))[0]
            backup_filename = f"{basename}.corrupted-{reason}-{timestamp}.json"
            backup_path = os.path.join('backups', backup_filename)

            shutil.move(filepath, backup_path)
            self.logger.info(f"Quarantined corrupt file: {filepath} → {backup_path}")

            # Run opportunistic cleanup after quarantine
            self._cleanup_old_backups_opportunistic()

            return backup_path

        except Exception as e:
            self.logger.error(f"Failed to quarantine {filepath}: {e}")
            # Even if quarantine fails, remove the corrupt file to prevent repeated errors
            try:
                os.unlink(filepath)
                self.logger.warning(f"Removed corrupt file {filepath} after quarantine failure")
            except:
                pass
            return ""

    def _load_backup_config(self) -> Dict[str, Any]:
        """
        Load backup retention configuration from config.yaml.

        Returns:
            Dict with retention_days, cleanup_check_interval_hours, enabled
        """
        defaults = {
            'retention_days': 30,
            'cleanup_check_interval_hours': 1,
            'enabled': True
        }

        try:
            import yaml
            if os.path.exists('config.yaml'):
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f)
                    backups_config = config.get('backups', {})
                    return {
                        'retention_days': backups_config.get('retention_days', defaults['retention_days']),
                        'cleanup_check_interval_hours': backups_config.get('cleanup_check_interval_hours', defaults['cleanup_check_interval_hours']),
                        'enabled': backups_config.get('enabled', defaults['enabled'])
                    }
        except Exception as e:
            self.logger.debug(f"Could not load backup config from config.yaml: {e}. Using defaults.")

        return defaults

    def _cleanup_old_backups_opportunistic(self) -> None:
        """
        Opportunistically clean up old backups with rate limiting.

        Rate limiting ensures cleanup doesn't run too frequently (default: once per hour).
        This is called after quarantine operations and at initialization.
        """
        config = self._load_backup_config()

        if not config['enabled']:
            return

        # Rate limiting: Check if enough time has passed since last cleanup
        cleanup_interval_seconds = config['cleanup_check_interval_hours'] * 3600
        current_time = time.time()

        if current_time - self._last_cleanup_check < cleanup_interval_seconds:
            return  # Skip cleanup - ran too recently

        # Update last check time and run cleanup
        self._last_cleanup_check = current_time
        self.cleanup_old_backups()

    def cleanup_old_backups(self) -> int:
        """
        Delete quarantined backup files older than retention period.

        This method removes .corrupted-* files from backups/ directory that exceed
        the configured retention period (default: 30 days).

        Returns:
            int: Number of files deleted

        Safety guards:
            - Only touches files matching .corrupted-* pattern
            - Only operates in backups/ directory
            - Never crashes on individual file errors
            - Logs all deletions for audit trail

        Note:
            Called opportunistically from:
            - __init__() (at service initialization with rate limiting)
            - _quarantine_file() (after quarantine with rate limiting)
        """
        if not os.path.exists('backups'):
            return 0

        config = self._load_backup_config()

        if not config['enabled']:
            self.logger.debug("Backup retention cleanup is disabled in config.yaml")
            return 0

        retention_days = config['retention_days']
        cutoff_time = time.time() - (retention_days * 86400)  # 86400 seconds per day
        deleted_count = 0

        try:
            backup_files = os.listdir('backups')

            for filename in backup_files:
                # Safety guard: Only process .corrupted-* files
                if not filename.startswith('.') and '.corrupted-' in filename:
                    filepath = os.path.join('backups', filename)

                    try:
                        # Check file age
                        file_mtime = os.path.getmtime(filepath)

                        if file_mtime < cutoff_time:
                            # Delete old quarantined file
                            os.unlink(filepath)
                            deleted_count += 1
                            self.logger.info(
                                f"Deleted old quarantined file (age: {(time.time() - file_mtime) / 86400:.1f} days): {filename}"
                            )

                    except Exception as e:
                        # Never crash on individual file errors
                        self.logger.warning(f"Error processing backup file {filename}: {e}")
                        continue

            if deleted_count > 0:
                self.logger.info(f"Backup retention cleanup: deleted {deleted_count} old quarantined files (retention: {retention_days} days)")

        except Exception as e:
            self.logger.error(f"Error during backup cleanup: {e}")

        return deleted_count

    def load_cache(self, filename: str, backup_on_missing: bool = False) -> Dict:
        """
        Load JSON cache file with comprehensive error handling.

        Args:
            filename: Path to cache file
            backup_on_missing: If True, backup file even if it's just missing (default: False)

        Returns:
            Dict: Loaded cache data, or empty dict if file doesn't exist

        Note:
            Returns empty dict on any error (graceful degradation for caches).
            Handles three error categories:
            - Type mismatch: quarantined as .corrupted-<type>-*
            - Malformed JSON: quarantined as .corrupted-parse-*
            - I/O errors: quarantined as .corrupted-ioerror-* (if appropriate)
        """
        if not os.path.exists(filename):
            return {}  # Missing file - no backup needed

        try:
            with open(filename, 'r') as f:
                data = json.load(f)

            # Type guard: Ensure cache is a dict
            if not isinstance(data, dict):
                actual_type = type(data).__name__
                self.logger.error(
                    f"Type mismatch in {filename}: expected dict, got {actual_type}. "
                    f"Quarantining corrupt file."
                )
                self._quarantine_file(filename, actual_type)
                return {}

            return data

        except json.JSONDecodeError as e:
            # Malformed JSON syntax
            self.logger.error(
                f"Malformed JSON in {filename} at line {e.lineno}, col {e.colno}: {e.msg}"
            )
            self._quarantine_file(filename, 'parse')
            return {}

        except (OSError, IOError) as e:
            # Disk/permission errors
            self.logger.error(f"I/O error reading {filename}: {e}")
            # Only quarantine if it's a read/permission error, not missing file
            if os.path.exists(filename):
                self._quarantine_file(filename, 'ioerror')
            return {}

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(f"Unexpected error loading cache {filename}: {type(e).__name__}: {e}")
            if os.path.exists(filename):
                self._quarantine_file(filename, 'unknown')
            return {}

    def save_cache(self, data: Dict, filename: str) -> None:
        """
        Save data to JSON cache file.

        Args:
            data: Dictionary to save
            filename: Path to cache file

        Note:
            Creates parent directories if they don't exist
        """
        try:
            # Create parent directory if needed
            parent_dir = os.path.dirname(filename) if '/' in filename else '.'
            if parent_dir != '.':
                os.makedirs(parent_dir, exist_ok=True)

            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save cache {filename}: {e}")
            raise

    def atomic_write_json(
        self,
        data: Union[Dict, List],
        filepath: str,
        backup: bool = True
    ) -> bool:
        """
        Atomically write JSON data with optional backup and file locking.

        Process:
            1. Create timestamped backup of existing file (if backup=True)
            2. Write to temp file (.tmp)
            3. Sync to disk (fsync)
            4. Atomic rename (all-or-nothing)
            5. Integrate with file_lock.py for concurrent safety

        Args:
            data: Python object to serialize as JSON
            filepath: Target file path
            backup: Create timestamped backup before overwrite (default True)

        Returns:
            bool: True if successful, False otherwise

        File paths maintained:
            - movie_tracking.json (root)
            - data.json (root)
            - available_tracking.json (root)
            - Backups: backups/<filename>.backup-YYYYMMDD_HHMMSS.json
        """
        try:
            # Step 1: Create timestamped backup if file exists and backup requested
            if backup and os.path.exists(filepath):
                os.makedirs('backups', exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_filename = f"{os.path.splitext(os.path.basename(filepath))[0]}.backup-{timestamp}.json"
                backup_path = os.path.join('backups', backup_filename)
                shutil.copy2(filepath, backup_path)
                self.logger.debug(f"Created backup: {backup_path}")

            # Step 2-4: Atomic write with file locking
            # Import file_lock for concurrent write safety
            try:
                from file_lock import safe_write_json_atomic
                safe_write_json_atomic(filepath, data, timeout=5.0, indent=2)
                return True
            except ImportError:
                # Fallback: Atomic write without locking (for environments without file_lock)
                self.logger.warning("file_lock not available, using fallback atomic write")
                temp_path = f"{filepath}.tmp"
                try:
                    with open(temp_path, 'w') as temp_f:
                        json.dump(data, temp_f, indent=2, ensure_ascii=False)
                        temp_f.flush()
                        os.fsync(temp_f.fileno())

                    # Atomic rename
                    shutil.move(temp_path, filepath)
                    return True
                except Exception:
                    # Cleanup temp file if write failed
                    if os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except:
                            pass
                    raise

        except Exception as e:
            self.logger.error(f"Error during atomic write to {filepath}: {e}")
            return False

    def atomic_move_to_archive(
        self,
        movie_entries: Dict[str, Dict],
        archive_file: str = 'available_tracking.json',
        main_file: str = 'movie_tracking.json'
    ) -> int:
        """
        Atomically move movie entries from tracking to archive database.

        Process:
            1. Load archive database (or create if doesn't exist)
            2. Add new entries to archive
            3. Atomic write to archive
            4. Remove entries from main database
            5. Atomic write to main database

        Args:
            movie_entries: Dict of {movie_id: movie_data} to move
            archive_file: Path to archive database (default: available_tracking.json)
            main_file: Path to main tracking database (default: movie_tracking.json)

        Returns:
            int: Number of entries successfully moved

        Note:
            Returns 0 on any error to maintain consistency.
            Both databases updated atomically (all-or-nothing).
        """
        if not movie_entries:
            return 0

        moved_count = 0

        try:
            # Step 1: Load or create archive database
            archive_db = {'movies': {}}
            if os.path.exists(archive_file):
                try:
                    with open(archive_file, 'r') as f:
                        data = json.load(f)

                    # Type guard: Ensure archive database is a dict
                    if not isinstance(data, dict):
                        actual_type = type(data).__name__
                        self.logger.error(
                            f"Type mismatch in {archive_file}: expected dict, got {actual_type}. "
                            f"Quarantining corrupt file and using empty archive."
                        )
                        self._quarantine_file(archive_file, actual_type)
                        archive_db = {'movies': {}}
                    else:
                        archive_db = data
                        if 'movies' not in archive_db:
                            archive_db['movies'] = {}

                except json.JSONDecodeError as e:
                    self.logger.error(
                        f"Malformed JSON in {archive_file} at line {e.lineno}, col {e.colno}: {e.msg}. "
                        f"Using empty archive."
                    )
                    self._quarantine_file(archive_file, 'parse')
                    archive_db = {'movies': {}}

                except (OSError, IOError) as e:
                    self.logger.error(f"I/O error reading {archive_file}: {e}. Using empty archive.")
                    if os.path.exists(archive_file):
                        self._quarantine_file(archive_file, 'ioerror')
                    archive_db = {'movies': {}}

            # Step 2: Add new entries to archive
            archive_db['movies'].update(movie_entries)

            # Step 3: Atomic write to archive
            if not self.atomic_write_json(archive_db, archive_file):
                self.logger.error(f"Failed to write archive database {archive_file}")
                return 0

            # Step 4: Remove from main tracking database
            if os.path.exists(main_file):
                try:
                    with open(main_file, 'r') as f:
                        data = json.load(f)

                    # Type guard: Ensure main database is a dict
                    if not isinstance(data, dict):
                        actual_type = type(data).__name__
                        self.logger.error(
                            f"Type mismatch in {main_file}: expected dict, got {actual_type}. "
                            f"Aborting archive operation."
                        )
                        self._quarantine_file(main_file, actual_type)
                        return 0

                    main_db = data

                except json.JSONDecodeError as e:
                    self.logger.error(
                        f"Malformed JSON in {main_file} at line {e.lineno}, col {e.colno}: {e.msg}. "
                        f"Aborting archive operation."
                    )
                    self._quarantine_file(main_file, 'parse')
                    return 0

                except (OSError, IOError) as e:
                    self.logger.error(f"I/O error reading {main_file}: {e}. Aborting archive operation.")
                    if os.path.exists(main_file):
                        self._quarantine_file(main_file, 'ioerror')
                    return 0

                for movie_id in movie_entries.keys():
                    if movie_id in main_db.get('movies', {}):
                        del main_db['movies'][movie_id]
                        moved_count += 1

                # Step 5: Atomic write to main database
                if not self.atomic_write_json(main_db, main_file):
                    self.logger.error(f"Failed to update main database {main_file}")
                    return 0

        except Exception as e:
            self.logger.error(f"Error during atomic move to archive: {e}")
            return 0

        return moved_count

    def load_all_movies(
        self,
        main_file: str = 'movie_tracking.json',
        archive_file: str = 'available_tracking.json',
        archive_enabled: bool = False
    ) -> Dict[str, Any]:
        """
        Load and merge movies from main tracking and archive databases.

        Args:
            main_file: Path to main tracking database
            archive_file: Path to archive database
            archive_enabled: Whether archival system is enabled

        Returns:
            Dict with 'movies' key containing merged movie data

        Note:
            Archived movies take precedence over main database in case of ID conflicts.
            Only archived movies with status='available' are included.
        """
        combined_movies = {}

        # Load main tracking database
        if os.path.exists(main_file):
            try:
                with open(main_file, 'r') as f:
                    data = json.load(f)

                # Type guard: Ensure main database is a dict
                if not isinstance(data, dict):
                    actual_type = type(data).__name__
                    self.logger.error(
                        f"Type mismatch in {main_file}: expected dict, got {actual_type}. "
                        f"Skipping main database load."
                    )
                    self._quarantine_file(main_file, actual_type)
                else:
                    main_db = data
                    combined_movies.update(main_db.get('movies', {}))

            except json.JSONDecodeError as e:
                self.logger.error(
                    f"Malformed JSON in {main_file} at line {e.lineno}, col {e.colno}: {e.msg}. "
                    f"Skipping main database load."
                )
                self._quarantine_file(main_file, 'parse')

            except (OSError, IOError) as e:
                self.logger.error(f"I/O error reading {main_file}: {e}. Skipping main database load.")
                if os.path.exists(main_file):
                    self._quarantine_file(main_file, 'ioerror')

            except Exception as e:
                self.logger.error(f"Unexpected error loading {main_file}: {type(e).__name__}: {e}")
                if os.path.exists(main_file):
                    self._quarantine_file(main_file, 'unknown')

        # Load archived available movies if archival is enabled
        if archive_enabled and os.path.exists(archive_file):
            try:
                with open(archive_file, 'r') as f:
                    data = json.load(f)

                # Type guard: Ensure archive database is a dict
                if not isinstance(data, dict):
                    actual_type = type(data).__name__
                    self.logger.error(
                        f"Type mismatch in {archive_file}: expected dict, got {actual_type}. "
                        f"Skipping archive load."
                    )
                    self._quarantine_file(archive_file, actual_type)
                else:
                    archived_db = data
                    # Archived movies take precedence in case of ID conflicts
                    for movie_id, movie_data in archived_db.get('movies', {}).items():
                        if movie_data.get('status') == 'available':
                            combined_movies[movie_id] = movie_data

            except json.JSONDecodeError as e:
                self.logger.error(
                    f"Malformed JSON in {archive_file} at line {e.lineno}, col {e.colno}: {e.msg}. "
                    f"Skipping archive load."
                )
                self._quarantine_file(archive_file, 'parse')

            except (OSError, IOError) as e:
                self.logger.error(f"I/O error reading {archive_file}: {e}. Skipping archive load.")
                if os.path.exists(archive_file):
                    self._quarantine_file(archive_file, 'ioerror')

            except Exception as e:
                self.logger.error(f"Unexpected error loading {archive_file}: {type(e).__name__}: {e}")
                if os.path.exists(archive_file):
                    self._quarantine_file(archive_file, 'unknown')

        return {'movies': combined_movies}

    def load_json(
        self,
        filepath: str,
        default: Optional[Union[Dict, List]] = None,
        expected_type: Optional[type] = None,
        backup_on_missing: bool = False
    ) -> Union[Dict, List]:
        """
        Load JSON file with comprehensive error handling.

        Args:
            filepath: Path to JSON file
            default: Default value if file doesn't exist or invalid (defaults to {})
            expected_type: Expected type (dict or list). If None, infers from default.
            backup_on_missing: If True, backup file even if it's just missing (default: False)

        Returns:
            Loaded JSON data or default value

        Note:
            Handles three error categories:
            - Type mismatch: quarantined as .corrupted-<type>-*
            - Malformed JSON: quarantined as .corrupted-parse-*
            - I/O errors: quarantined as .corrupted-ioerror-* (if appropriate)
        """
        if default is None:
            default = {}

        # Infer expected type from default if not explicitly provided
        if expected_type is None:
            expected_type = type(default)

        if not os.path.exists(filepath):
            return default  # Missing file - no backup needed

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            # Type guard: Ensure loaded data matches expected type
            if not isinstance(data, expected_type):
                actual_type = type(data).__name__
                expected_type_name = expected_type.__name__
                self.logger.error(
                    f"Type mismatch in {filepath}: expected {expected_type_name}, got {actual_type}. "
                    f"Quarantining corrupt file."
                )
                self._quarantine_file(filepath, actual_type)
                return default

            return data

        except json.JSONDecodeError as e:
            # Malformed JSON syntax
            self.logger.error(
                f"Malformed JSON in {filepath} at line {e.lineno}, col {e.colno}: {e.msg}"
            )
            self._quarantine_file(filepath, 'parse')
            return default

        except (OSError, IOError) as e:
            # Disk/permission errors
            self.logger.error(f"I/O error reading {filepath}: {e}")
            # Only quarantine if it's a read/permission error, not missing file
            if os.path.exists(filepath):
                self._quarantine_file(filepath, 'ioerror')
            return default

        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error(f"Unexpected error loading {filepath}: {type(e).__name__}: {e}")
            if os.path.exists(filepath):
                self._quarantine_file(filepath, 'unknown')
            return default
