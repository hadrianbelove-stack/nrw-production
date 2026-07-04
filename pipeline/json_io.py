"""Concurrency-safe JSON file access for shared NRW data files.

Multiple curation windows read-modify-write the same JSON files (data.json,
admin/*.json, cache/*.json). Two failure modes this module prevents:

  - torn writes: a reader (or a git commit) catches a half-written file
    -> atomic_dump() writes to a temp file, validates it, then swaps it in
  - lost updates: window A saves from a stale in-memory copy, silently
    erasing window B's save -> json_edit() holds an exclusive lock across
    the whole load-modify-save cycle

Use json_edit() for every read-modify-write. Use atomic_dump() alone only
for files no other process writes concurrently. The lock is one coarse
file for all shared JSON — hold times are ~1-2s, so simple beats granular.
The OS releases the lock automatically if a process dies mid-edit.
"""
import fcntl
import json
import os
import time
from contextlib import contextmanager

LOCK_PATH = '.nrw_data.lock'
LOCK_TIMEOUT = 30  # seconds a writer will wait for another window's turn


@contextmanager
def data_lock(timeout=LOCK_TIMEOUT):
    """Exclusive cross-process lock. NOT re-entrant — never nest."""
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.time() > deadline:
                    raise TimeoutError(
                        f"another window has held {LOCK_PATH} for over "
                        f"{timeout}s — investigate before retrying")
                time.sleep(0.2)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_dump(obj, path):
    """Write JSON so no reader can ever see a partial file."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    with open(tmp) as f:
        json.load(f)  # must round-trip before it may replace the real file
    os.replace(tmp, path)


def load_json(path, retries=3, default=None):
    """Read JSON, retrying briefly (a legacy writer can still tear a file)."""
    for i in range(retries):
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError:
            if i == retries - 1:
                raise
            time.sleep(0.5)


@contextmanager
def json_edit(path, default=None):
    """Lock -> load -> yield for mutation in place -> atomic save.

    The whole read-modify-write is exclusive, so concurrent windows take
    turns instead of overwriting each other. If the body raises, nothing
    is written.
    """
    with data_lock():
        obj = load_json(path, default=default)
        yield obj
        atomic_dump(obj, path)
