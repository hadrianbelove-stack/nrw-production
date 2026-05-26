"""
TrackingDB — SQLite-backed store for movie_tracking.json data.

Usage in pipeline code (has self.storage):
    db = self.storage.tracking_db.load_all()

Usage in admin routes / scripts (no pipeline context):
    from pipeline.tracking_db import get_tracking_db
    tdb = get_tracking_db()
    db = tdb.load_all()

Drop-in replacement for the raw JSON file. Maintains the same
{'movies': {id: data_dict}} dict interface so callers need minimal changes.

Git strategy: movie_tracking.db is gitignored. movie_tracking.json is
still exported after every save and committed by GitHub Actions.
On a fresh checkout (CI, new machine), the DB auto-imports from JSON.
"""

import json
import logging
import os
import shutil
import sqlite3
from typing import Dict, List, Optional, Tuple, Any


class TrackingDB:
    """SQLite wrapper for the movie tracking database."""

    def __init__(
        self,
        db_path: str = 'movie_tracking.db',
        json_path: str = 'movie_tracking.json',
        logger: Optional[logging.Logger] = None,
    ):
        self.db_path = db_path
        self.json_path = json_path
        self.logger = logger or logging.getLogger(__name__)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        """Create table + indexes. Auto-import from JSON if DB is brand-new."""
        db_existed = os.path.exists(self.db_path)

        conn = self._connect()
        # WAL mode persists on disk — set once here, never again per connection
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id           TEXT PRIMARY KEY,
                status       TEXT,
                digital_date TEXT,
                enriched     INTEGER DEFAULT 0,
                data         TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON movies(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_digital_date ON movies(digital_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_enriched ON movies(enriched)")
        conn.commit()
        conn.close()

        if not db_existed and os.path.exists(self.json_path):
            self.logger.info(f"TrackingDB: fresh DB — importing from {self.json_path}")
            count = self.import_json(self.json_path)
            self.logger.info(f"TrackingDB: imported {count} movies from JSON")

    # ------------------------------------------------------------------
    # Bulk load/save  (matches the old 'load whole file / save whole file'
    # pattern so existing pipeline code needs minimal changes)
    # ------------------------------------------------------------------

    def load_all(self) -> Dict[str, Any]:
        """Return {'movies': {id: data_dict}} — same shape as the old JSON."""
        conn = self._connect()
        movies = {}
        for row in conn.execute("SELECT id, data FROM movies"):
            movies[row[0]] = json.loads(row[1])
        conn.close()
        return {'movies': movies}

    def save_all(self, db_dict: Dict[str, Any], export_json: bool = True) -> bool:
        """
        Persist the full {'movies': {...}} dict to SQLite.

        Replaces the entire table in one transaction (fast for <100k rows).
        Also re-exports movie_tracking.json so Git commits still work.
        """
        movies = db_dict.get('movies', {})
        conn = self._connect()
        try:
            conn.execute("BEGIN EXCLUSIVE")
            conn.execute("DELETE FROM movies")
            conn.executemany(
                "INSERT INTO movies (id, status, digital_date, enriched, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    (
                        str(mid),
                        data.get('status'),
                        data.get('digital_date'),
                        1 if data.get('enriched') else 0,
                        json.dumps(data, ensure_ascii=False),
                    )
                    for mid, data in movies.items()
                ),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"TrackingDB.save_all failed: {e}")
            return False
        finally:
            conn.close()

        if export_json:
            try:
                # Pass db_dict directly — avoids re-reading all rows from SQLite
                self.export_json(self.json_path, data=db_dict)
            except Exception as e:
                self.logger.warning(f"TrackingDB: JSON export failed (DB write succeeded): {e}")

        return True

    # ------------------------------------------------------------------
    # Single-record operations (for Admin panel, scripts, etc.)
    # ------------------------------------------------------------------

    def get(self, movie_id: str) -> Optional[Dict]:
        """Return one movie dict, or None if not found."""
        conn = self._connect()
        row = conn.execute(
            "SELECT data FROM movies WHERE id = ?", (str(movie_id),)
        ).fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def set(self, movie_id: str, data: Dict, export_json: bool = True) -> None:
        """Upsert a single movie record."""
        conn = self._connect()
        try:
            conn.execute("BEGIN EXCLUSIVE")
            conn.execute(
                "INSERT OR REPLACE INTO movies (id, status, digital_date, enriched, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(movie_id),
                    data.get('status'),
                    data.get('digital_date'),
                    1 if data.get('enriched') else 0,
                    json.dumps(data, ensure_ascii=False),
                ),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"TrackingDB.set failed for {movie_id}: {e}")
            raise
        finally:
            conn.close()
        if export_json:
            try:
                self.export_json(self.json_path)
            except Exception as e:
                self.logger.warning(f"TrackingDB: JSON export failed after set(): {e}")

    def delete(self, movie_id: str, export_json: bool = True) -> None:
        """Delete a movie record by ID."""
        conn = self._connect()
        conn.execute("DELETE FROM movies WHERE id = ?", (str(movie_id),))
        conn.commit()
        conn.close()
        if export_json:
            try:
                self.export_json(self.json_path)
            except Exception as e:
                self.logger.warning(f"TrackingDB: JSON export failed after delete(): {e}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def find_by_status(self, status: str) -> List[Tuple[str, Dict]]:
        """Return [(id, data_dict), ...] for all movies with the given status."""
        conn = self._connect()
        results = [
            (row[0], json.loads(row[1]))
            for row in conn.execute(
                "SELECT id, data FROM movies WHERE status = ?", (status,)
            )
        ]
        conn.close()
        return results

    def count(self, status: Optional[str] = None) -> int:
        """Return total row count, or count for a specific status."""
        conn = self._connect()
        if status:
            n = conn.execute(
                "SELECT COUNT(*) FROM movies WHERE status = ?", (status,)
            ).fetchone()[0]
        else:
            n = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        conn.close()
        return n

    # ------------------------------------------------------------------
    # Import / export
    # ------------------------------------------------------------------

    def export_json(self, path: str, data: Optional[Dict] = None) -> None:
        """
        Dump all records to a JSON file (atomic write).

        Called automatically by save_all/set/delete so movie_tracking.json
        stays in sync for Git commits.

        Pass `data` to skip re-reading from SQLite (save_all uses this).
        """
        if not path:
            raise ValueError("TrackingDB.export_json: path is required")
        db_dict = data if data is not None else self.load_all()
        temp_path = path + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(db_dict, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        shutil.move(temp_path, path)

    def import_json(self, path: str) -> int:
        """
        Bulk-import from a JSON file (migration + CI fresh-checkout startup).

        Returns the number of records imported.
        """
        with open(path, 'r', encoding='utf-8') as f:
            db_dict = json.load(f)
        self.save_all(db_dict, export_json=False)
        return len(db_dict.get('movies', {}))


# ---------------------------------------------------------------------------
# Module-level singleton — for use outside the pipeline (admin routes, scripts)
# ---------------------------------------------------------------------------

_shared_instance: Optional['TrackingDB'] = None


def get_tracking_db(logger: Optional[logging.Logger] = None) -> 'TrackingDB':
    """
    Return the shared TrackingDB instance (created on first call).

    Pass `logger` on first call to attach a logger — ignored on subsequent calls
    since the singleton already exists.
    """
    global _shared_instance
    if _shared_instance is None:
        _shared_instance = TrackingDB(logger=logger)
    return _shared_instance
