#!/usr/bin/env python3
"""
Safe file locking utility for NRW production code.

Prevents race conditions when multiple processes write to the same file.
Cross-platform support (Unix fcntl + Windows msvcrt).
"""

import os
import time
import json
import logging
from contextlib import contextmanager
from typing import Any, Union, Dict, List

logger = logging.getLogger(__name__)

# Platform-specific imports
try:
    import fcntl  # Unix/Linux/macOS
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt  # Windows
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


@contextmanager
def safe_file_lock(file_handle, timeout: float = 5.0, operation: str = "write"):
    """
    Context manager for safe file locking with timeout.

    Args:
        file_handle: Open file handle to lock
        timeout: Maximum seconds to wait for lock (default 5.0)
        operation: Description of operation for logging

    Raises:
        TimeoutError: If lock cannot be acquired within timeout

    Usage:
        with open('file.json', 'r+') as f:
            with safe_file_lock(f, timeout=5.0):
                data = json.load(f)
                # ... modify data ...
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
    """
    acquired = False
    start_time = time.time()

    try:
        # Try to acquire lock with timeout
        while time.time() - start_time < timeout:
            try:
                if HAS_FCNTL:
                    # Unix/Linux/macOS: fcntl advisory locking
                    fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                elif HAS_MSVCRT:
                    # Windows: msvcrt locking
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                else:
                    # No locking available, log warning and proceed
                    logger.warning(f"File locking not available on this platform for {operation}")
                    acquired = True  # Proceed without lock
                    break
            except (IOError, OSError):
                # Lock held by another process, wait and retry
                time.sleep(0.1)

        if not acquired:
            elapsed = time.time() - start_time
            raise TimeoutError(
                f"Could not acquire file lock for {operation} after {elapsed:.1f}s. "
                f"Another process may be holding the lock."
            )

        # Yield control to the caller
        yield

    finally:
        # Release lock
        if acquired:
            try:
                if HAS_FCNTL:
                    fcntl.flock(file_handle, fcntl.LOCK_UN)
                elif HAS_MSVCRT:
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (IOError, OSError) as e:
                logger.warning(f"Error releasing file lock: {e}")


def safe_write_json_atomic(
    filepath: str,
    data: Union[Dict, List],
    timeout: float = 5.0,
    indent: int = 2
) -> None:
    """
    Safely write JSON data to file with locking and atomic operation.

    Args:
        filepath: Path to JSON file
        data: Data to write (dict or list)
        timeout: Lock timeout in seconds
        indent: JSON indentation level

    Raises:
        TimeoutError: If lock cannot be acquired
        IOError: If file cannot be written

    Usage:
        safe_write_json_atomic('movie_tracking.json', data, timeout=5.0)
    """
    # Create parent directory if needed
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

    # Write to temporary file first (atomic rename later)
    temp_file = f"{filepath}.tmp"

    try:
        # Open for write (create if not exists)
        with open(temp_file, 'w') as f:
            with safe_file_lock(f, timeout=timeout, operation=f"write {filepath}"):
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

        # Atomic rename (all-or-nothing)
        os.replace(temp_file, filepath)
        logger.debug(f"Successfully wrote {filepath} with file lock")

    except TimeoutError:
        # Clean up temp file on timeout
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise
    except Exception as e:
        # Clean up temp file on error
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        raise IOError(f"Failed to write {filepath}: {e}")


def safe_read_json_locked(filepath: str, timeout: float = 5.0) -> Union[Dict, List]:
    """
    Safely read JSON data with file locking.

    Useful when reading data that might be concurrently written.

    Args:
        filepath: Path to JSON file
        timeout: Lock timeout in seconds

    Returns:
        Loaded JSON data (dict or list)

    Raises:
        FileNotFoundError: If file doesn't exist
        TimeoutError: If lock cannot be acquired
        json.JSONDecodeError: If JSON is invalid

    Usage:
        data = safe_read_json_locked('movie_tracking.json')
    """
    with open(filepath, 'r') as f:
        with safe_file_lock(f, timeout=timeout, operation=f"read {filepath}"):
            return json.load(f)


# Backwards compatibility with existing safe_write_json
def safe_write_json(filepath: str, data: Union[Dict, List], indent: int = 2, max_backups: int = 10) -> bool:
    """
    Legacy wrapper for safe_write_json_atomic with backup creation.

    Maintains compatibility with existing admin.py code.
    Creates timestamped backups and cleans up old ones.

    Args:
        filepath: Path to JSON file
        data: Data to write
        indent: JSON indentation
        max_backups: Maximum backup files to keep

    Returns:
        True on success

    Raises:
        Exception: On write failure
    """
    import shutil
    from datetime import datetime
    import glob

    try:
        # Create timestamped backup if original exists
        if os.path.exists(filepath):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{filepath}.backup.{timestamp}"
            shutil.copy2(filepath, backup_file)

        # Write with locking
        safe_write_json_atomic(filepath, data, timeout=5.0, indent=indent)

        # Cleanup old backups
        try:
            backup_pattern = f"{filepath}.backup.*"
            backup_files = glob.glob(backup_pattern)
            if len(backup_files) > max_backups:
                backup_files.sort(reverse=True)
                for old_backup in backup_files[max_backups:]:
                    os.remove(old_backup)
        except Exception:
            pass  # Backup cleanup failure shouldn't fail the write

        return True

    except Exception:
        raise
