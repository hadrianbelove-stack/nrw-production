"""
Archive and purge module for the NRW pipeline.

Extracted from DataGenerator (pipeline/generator.py) for maintainability.
Handles the 90-day auto-archive, manual removal purging, and
safe (reload-merge) data.json writes.
"""

import json
import os
from datetime import datetime, timedelta


class ArchiveManager:
    """Manages data.json lifecycle: safe saves, archival, and purging.

    Parameters
    ----------
    ctx : PipelineContext
        Shared pipeline dependencies (config, logger, storage, enrichment_service, tmdb_key).
    """

    def __init__(self, ctx):
        self.ctx = ctx

    def safe_save_data_json(self, display_data, existing_movies, label="save"):
        """Save data.json with reload-merge to prevent lost updates.

        Reloads data.json from disk before saving. Any movies present on disk
        but missing from the in-memory copy are appended (rescued from being
        silently dropped). Uses atomic_write_json for crash-safe writes.

        Args:
            display_data: The full data.json dict (movies will be overwritten)
            existing_movies: The in-memory movies list to save
            label: Log label for this save point (e.g. "enrichment", "trailer")

        Returns:
            bool: True if save succeeded
        """
        try:
            # Reload from disk to catch any movies added since we loaded
            rescued = []
            if os.path.exists('data.json'):
                try:
                    with open('data.json', 'r') as f:
                        disk_data = json.load(f)
                    disk_movies = disk_data.get('movies', [])
                    in_memory_ids = {str(m.get('id', '')) for m in existing_movies if m.get('id')}
                    for dm in disk_movies:
                        dm_id = str(dm.get('id', ''))
                        if dm_id and dm_id not in in_memory_ids:
                            existing_movies.append(dm)
                            rescued.append(f"{dm.get('title', dm_id)} ({dm_id})")
                except Exception as reload_err:
                    self.ctx.logger.warning(f"Reload-merge failed during {label}: {reload_err}")

            if rescued:
                self.ctx.logger.warning(f"MERGE [{label}]: rescued {len(rescued)} movies that would have been lost: {rescued}")
                print(f"  \U0001f500 MERGE: rescued {len(rescued)} movies from being dropped")

            display_data['movies'] = existing_movies
            display_data['generated_at'] = datetime.now().isoformat()
            display_data['count'] = len(existing_movies)

            if not self.ctx.storage.atomic_write_json(display_data, 'data.json', backup=True):
                self.ctx.logger.error(f"Atomic write failed during {label}")
                return False

            self.ctx.logger.info(f"Safe save [{label}]: {len(existing_movies)} movies written")
            return True

        except Exception as e:
            self.ctx.logger.error(f"Failed safe save [{label}]: {e}")
            print(f"\u274c Error saving data.json ({label}): {e}")
            return False

    def archive_old_movies(self, days=90):
        """
        Move movies older than `days` from data.json into data_archive.json.

        Keeps data.json lean. Archive is append-only and deduped by movie ID.
        Pre-order movies (future dates) and movies without digital_date are never archived.
        """
        if not os.path.exists('data.json'):
            return

        with open('data.json', 'r') as f:
            data = json.load(f)

        movies = data.get('movies', [])
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')

        keep = []
        to_archive = []
        for m in movies:
            dd = m.get('digital_date') or ''
            # Archive if digital_date exists, is in the past, and older than cutoff
            if dd and dd <= today and dd < cutoff:
                to_archive.append(m)
            else:
                keep.append(m)

        if not to_archive:
            return

        # Load or create archive
        archive_path = 'data_archive.json'
        archive_movies = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, 'r') as f:
                    archive_data = json.load(f)
                archive_movies = archive_data.get('movies', [])
            except Exception:
                archive_movies = []

        # Dedupe by ID before appending
        existing_ids = {str(m.get('id')) for m in archive_movies}
        new_archived = [m for m in to_archive if str(m.get('id')) not in existing_ids]
        archive_movies.extend(new_archived)

        # Save archive FIRST (before modifying data.json) — atomic so a crash
        # mid-write doesn't destroy the archive before data.json is trimmed.
        archive_data = {
            'archived_at': datetime.now().isoformat(),
            'count': len(archive_movies),
            'movies': archive_movies
        }
        self.ctx.storage.atomic_write_json(archive_data, archive_path, backup=False)

        # Now slim down data.json (atomic write — archive IS the backup)
        data['movies'] = keep
        data['count'] = len(keep)
        self.ctx.storage.atomic_write_json(data, 'data.json', backup=False)

        print(f"\U0001f4e6 Archived {len(to_archive)} movies (>{days} days old) \u2192 data_archive.json")
        print(f"   data.json: {len(keep)} movies | archive: {len(archive_movies)} total")
        self.ctx.logger.info(f"Archived {len(to_archive)} movies older than {days} days")

    def purge_removed_movies(self, movies_list=None):
        """Remove movies with status='removed' or _enrichment_status='reverted'.

        Handles two cases:
        1. Manually removed movies (status='removed' in movie_tracking.json)
        2. JW-reverted movies (_enrichment_status='reverted') — discovered
           but only available on excluded platforms, shouldn't be on the wall

        When movies_list is provided, filters in-memory and returns the filtered list
        (caller is responsible for saving). When None, reads/writes data.json directly.
        Purged movies are archived to data_archive.json either way.

        Returns:
            Filtered list when movies_list provided, None otherwise.
        """
        # Get manually removed IDs from tracking
        removed_ids = set()
        if os.path.exists('movie_tracking.json'):
            with open('movie_tracking.json', 'r') as f:
                tracking = json.load(f)
            removed_ids = {str(mid) for mid, entry in tracking.get('movies', {}).items()
                           if isinstance(entry, dict) and entry.get('status') == 'removed'}

        if movies_list is not None:
            movies = movies_list
        elif os.path.exists('data.json'):
            with open('data.json', 'r') as f:
                data = json.load(f)
            movies = data.get('movies', [])
        else:
            return movies_list

        keep = []
        to_purge_removed = []
        to_purge_reverted = []
        for m in movies:
            if str(m.get('id')) in removed_ids:
                to_purge_removed.append(m)
            elif m.get('_enrichment_status') == 'reverted':
                to_purge_reverted.append(m)
            else:
                keep.append(m)

        all_purged = to_purge_removed + to_purge_reverted
        if not all_purged:
            return movies_list if movies_list is not None else None

        # Archive purged movies (same pattern as archive_old_movies)
        archive_path = 'data_archive.json'
        archive_movies = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, 'r') as f:
                    archive_data = json.load(f)
                archive_movies = archive_data.get('movies', [])
            except Exception:
                archive_movies = []

        existing_ids = {str(m.get('id')) for m in archive_movies}
        new_archived = [m for m in all_purged if str(m.get('id')) not in existing_ids]
        archive_movies.extend(new_archived)

        archive_data = {
            'archived_at': datetime.now().isoformat(),
            'count': len(archive_movies),
            'movies': archive_movies
        }
        self.ctx.storage.atomic_write_json(archive_data, archive_path, backup=False)

        if to_purge_removed:
            titles = [m.get('title', '?') for m in to_purge_removed]
            print(f"\U0001f5d1\ufe0f Purged {len(to_purge_removed)} manually removed movies \u2192 data_archive.json")
            for t in titles:
                print(f"   - {t}")
            self.ctx.logger.info(f"Purged {len(to_purge_removed)} removed movies: {titles}")

        if to_purge_reverted:
            titles = [m.get('title', '?') for m in to_purge_reverted]
            print(f"\U0001f504 Purged {len(to_purge_reverted)} JW-reverted movies from wall \u2192 data_archive.json")
            for t in titles:
                print(f"   - {t}")
            self.ctx.logger.info(f"Purged {len(to_purge_reverted)} reverted movies from wall: {titles}")

        if movies_list is not None:
            return keep
        else:
            data['movies'] = keep
            data['count'] = len(keep)
            self.ctx.storage.atomic_write_json(data, 'data.json', backup=False)
