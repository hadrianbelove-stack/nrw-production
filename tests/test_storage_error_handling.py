#!/usr/bin/env python3
"""
Comprehensive error handling tests for StorageService.

Tests parse errors, missing files, permission errors, type mismatches,
and archive operation edge cases.
"""

import pytest
import json
import os
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.storage import StorageService


@pytest.fixture
def storage_service():
    """Create StorageService with real logger."""
    logger = logging.getLogger('test_storage')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    handler = logging.StreamHandler()
    logger.addHandler(handler)

    # Disable opportunistic cleanup for predictable testing
    with patch.object(StorageService, '_cleanup_old_backups_opportunistic'):
        return StorageService(logger)


class TestParseErrors:
    """Test handling of malformed JSON files."""

    def test_truncated_json_creates_quarantine(self, tmp_path, storage_service):
        """Truncated JSON should be quarantined as .corrupted-parse-*."""
        os.chdir(tmp_path)

        corrupt_file = tmp_path / "truncated.json"
        corrupt_file.write_text('{"incomplete": ')

        result = storage_service.load_cache(str(corrupt_file))

        assert result == {}
        assert not corrupt_file.exists()

        backups = list((tmp_path / "backups").glob("*.corrupted-parse-*.json"))
        assert len(backups) == 1
        assert "truncated" in backups[0].name

    def test_unclosed_json_array(self, tmp_path, storage_service):
        """Unclosed JSON array should be quarantined."""
        os.chdir(tmp_path)

        corrupt_file = tmp_path / "unclosed.json"
        corrupt_file.write_text('{"data": [1, 2, 3')

        result = storage_service.load_cache(str(corrupt_file))

        assert result == {}
        backups = list((tmp_path / "backups").glob("*.corrupted-parse-*.json"))
        assert len(backups) == 1

    def test_completely_invalid_json(self, tmp_path, storage_service):
        """Non-JSON content should be quarantined."""
        os.chdir(tmp_path)

        corrupt_file = tmp_path / "garbage.json"
        corrupt_file.write_text('This is not JSON at all!')

        result = storage_service.load_cache(str(corrupt_file))

        assert result == {}
        backups = list((tmp_path / "backups").glob("*.corrupted-parse-*.json"))
        assert len(backups) == 1


class TestMissingFiles:
    """Test that missing files do NOT create backups."""

    def test_missing_file_returns_empty_dict(self, tmp_path, storage_service):
        """Missing file should return {} without creating backup."""
        os.chdir(tmp_path)

        result = storage_service.load_cache("nonexistent.json")

        assert result == {}

        # No backup should be created
        backups_dir = tmp_path / "backups"
        if backups_dir.exists():
            assert len(list(backups_dir.glob("*.json"))) == 0

    def test_load_json_missing_returns_default(self, tmp_path, storage_service):
        """load_json with missing file should return custom default."""
        os.chdir(tmp_path)

        custom_default = {"default": "value"}
        result = storage_service.load_json("missing.json", default=custom_default)

        assert result == custom_default

        backups_dir = tmp_path / "backups"
        if backups_dir.exists():
            assert len(list(backups_dir.glob("*.json"))) == 0


class TestPermissionErrors:
    """Test handling of permission errors."""

    def test_unreadable_file_quarantined(self, tmp_path, storage_service):
        """File without read permissions should be handled gracefully."""
        os.chdir(tmp_path)

        restricted_file = tmp_path / "restricted.json"
        restricted_file.write_text('{"data": "value"}')

        if os.name != 'nt':  # Unix only
            os.chmod(restricted_file, 0o000)

            try:
                result = storage_service.load_cache(str(restricted_file))
                assert result == {}
            finally:
                # Restore permissions only if file still exists (it gets moved to backups)
                if restricted_file.exists():
                    os.chmod(restricted_file, 0o644)
        else:
            pytest.skip("Permission test requires Unix-like OS")


class TestTypeMismatches:
    """Test handling of type mismatches."""

    def test_list_instead_of_dict(self, tmp_path, storage_service):
        """JSON list should be quarantined when dict expected."""
        os.chdir(tmp_path)

        wrong_type = tmp_path / "list.json"
        wrong_type.write_text('[1, 2, 3]')

        result = storage_service.load_cache(str(wrong_type))

        assert result == {}
        backups = list((tmp_path / "backups").glob("*.corrupted-list-*.json"))
        assert len(backups) == 1

    def test_string_instead_of_dict(self, tmp_path, storage_service):
        """JSON string should be quarantined when dict expected."""
        os.chdir(tmp_path)

        wrong_type = tmp_path / "string.json"
        wrong_type.write_text('"just a string"')

        result = storage_service.load_cache(str(wrong_type))

        assert result == {}
        backups = list((tmp_path / "backups").glob("*.corrupted-str-*.json"))
        assert len(backups) == 1

    def test_null_instead_of_dict(self, tmp_path, storage_service):
        """JSON null should be quarantined when dict expected."""
        os.chdir(tmp_path)

        null_file = tmp_path / "null.json"
        null_file.write_text('null')

        result = storage_service.load_cache(str(null_file))

        assert result == {}
        backups = list((tmp_path / "backups").glob("*.corrupted-NoneType-*.json"))
        assert len(backups) == 1

    def test_load_json_accepts_expected_list(self, tmp_path, storage_service):
        """load_json should accept list when expected_type=list."""
        os.chdir(tmp_path)

        list_file = tmp_path / "valid.json"
        list_file.write_text('[1, 2, 3]')

        result = storage_service.load_json(str(list_file), default=[], expected_type=list)

        assert result == [1, 2, 3]

        backups_dir = tmp_path / "backups"
        if backups_dir.exists():
            assert len(list(backups_dir.glob("*.corrupted-*.json"))) == 0


class TestAtomicMoveToArchive:
    """Test edge cases in atomic_move_to_archive."""

    def test_corrupt_archive_database(self, tmp_path, storage_service):
        """Corrupt archive should be quarantined and recreated."""
        os.chdir(tmp_path)

        archive = tmp_path / "archive.json"
        archive.write_text('{"corrupt": ')

        main = tmp_path / "main.json"
        main.write_text(json.dumps({"movies": {"m1": {"title": "Test"}}}))

        movies_to_move = {"m2": {"title": "New"}}

        moved = storage_service.atomic_move_to_archive(
            movies_to_move,
            archive_file=str(archive),
            main_file=str(main)
        )

        # Archive was corrupt, got quarantined
        backups = list((tmp_path / "backups").glob("*.corrupted-parse-*.json"))
        assert len(backups) == 1

        # New archive should exist
        assert archive.exists()
        with open(archive) as f:
            data = json.load(f)
        assert "m2" in data["movies"]

    def test_corrupt_main_database(self, tmp_path, storage_service):
        """Corrupt main DB should abort operation."""
        os.chdir(tmp_path)

        archive = tmp_path / "archive.json"
        archive.write_text(json.dumps({"movies": {}}))

        main = tmp_path / "main.json"
        main.write_text('{"corrupt": ')

        moved = storage_service.atomic_move_to_archive(
            {"m1": {"title": "Test"}},
            archive_file=str(archive),
            main_file=str(main)
        )

        assert moved == 0
        backups = list((tmp_path / "backups").glob("main.corrupted-parse-*.json"))
        assert len(backups) == 1

    def test_both_databases_corrupt(self, tmp_path, storage_service):
        """Both corrupt should handle gracefully."""
        os.chdir(tmp_path)

        archive = tmp_path / "archive.json"
        archive.write_text('[1, 2, 3]')

        main = tmp_path / "main.json"
        main.write_text('{"incomplete": ')

        moved = storage_service.atomic_move_to_archive(
            {"m1": {"title": "Test"}},
            archive_file=str(archive),
            main_file=str(main)
        )

        assert moved == 0
        backups = list((tmp_path / "backups").glob("*.corrupted-*.json"))
        assert len(backups) == 2

    def test_empty_movie_entries(self, tmp_path, storage_service):
        """Empty entries should return 0 immediately."""
        os.chdir(tmp_path)

        moved = storage_service.atomic_move_to_archive({})
        assert moved == 0


class TestLoadAllMovies:
    """Test load_all_movies error handling."""

    def test_corrupt_main_skipped(self, tmp_path, storage_service):
        """Corrupt main should be quarantined and skipped."""
        os.chdir(tmp_path)

        main = tmp_path / "main.json"
        main.write_text('{"corrupt": ')

        archive = tmp_path / "archive.json"
        archive.write_text(json.dumps({
            "movies": {"a1": {"title": "Archived", "status": "available"}}
        }))

        result = storage_service.load_all_movies(
            main_file=str(main),
            archive_file=str(archive),
            archive_enabled=True
        )

        assert "a1" in result["movies"]
        assert len(result["movies"]) == 1

        backups = list((tmp_path / "backups").glob("main.corrupted-parse-*.json"))
        assert len(backups) == 1

    def test_corrupt_archive_skipped(self, tmp_path, storage_service):
        """Corrupt archive should be quarantined and skipped."""
        os.chdir(tmp_path)

        main = tmp_path / "main.json"
        main.write_text(json.dumps({"movies": {"m1": {"title": "Main"}}}))

        archive = tmp_path / "archive.json"
        archive.write_text('[1, 2, 3]')

        result = storage_service.load_all_movies(
            main_file=str(main),
            archive_file=str(archive),
            archive_enabled=True
        )

        assert "m1" in result["movies"]
        backups = list((tmp_path / "backups").glob("archive.corrupted-list-*.json"))
        assert len(backups) == 1


class TestQuarantineSystem:
    """Test the quarantine mechanism itself."""

    def test_quarantine_creates_backups_dir(self, tmp_path, storage_service):
        """Quarantine should create backups/ if missing."""
        os.chdir(tmp_path)

        assert not (tmp_path / "backups").exists()

        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text('{"invalid": ')
        storage_service.load_cache(str(corrupt))

        assert (tmp_path / "backups").exists()

    def test_quarantine_filename_format(self, tmp_path, storage_service):
        """Quarantine files have correct naming."""
        os.chdir(tmp_path)

        corrupt = tmp_path / "test_file.json"
        corrupt.write_text('{"invalid": ')
        storage_service.load_cache(str(corrupt))

        backups = list((tmp_path / "backups").glob("*.json"))
        assert len(backups) == 1

        name = backups[0].name
        assert name.startswith("test_file.corrupted-parse-")
        assert name.endswith(".json")

    def test_quarantine_preserves_data(self, tmp_path, storage_service):
        """Quarantined files preserve corrupt data for forensics."""
        os.chdir(tmp_path)

        corrupt_content = '{"incomplete": '
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text(corrupt_content)
        storage_service.load_cache(str(corrupt))

        backups = list((tmp_path / "backups").glob("*.json"))
        assert backups[0].read_text() == corrupt_content

    def test_multiple_quarantines_unique_names(self, tmp_path, storage_service):
        """Multiple quarantines create unique filenames."""
        import time
        os.chdir(tmp_path)

        for i in range(3):
            corrupt = tmp_path / "corrupt.json"
            corrupt.write_text('{"invalid": ')
            storage_service.load_cache(str(corrupt))
            time.sleep(1.1)  # Ensure timestamp changes (resolution is 1 second)

        backups = list((tmp_path / "backups").glob("*.json"))
        assert len(backups) == 3

        names = [b.name for b in backups]
        assert len(names) == len(set(names))


class TestEdgeCases:
    """Additional edge cases."""

    def test_empty_file(self, tmp_path, storage_service):
        """Empty file should be quarantined."""
        os.chdir(tmp_path)

        empty = tmp_path / "empty.json"
        empty.write_text('')

        result = storage_service.load_cache(str(empty))
        assert result == {}

        backups = list((tmp_path / "backups").glob("*.corrupted-parse-*.json"))
        assert len(backups) == 1

    def test_large_corrupt_file(self, tmp_path, storage_service):
        """Large corrupt files should be handled."""
        os.chdir(tmp_path)

        large = tmp_path / "large.json"
        with open(large, 'w') as f:
            f.write('{"data": [')
            f.write(','.join(str(i) for i in range(10000)))
            # Don't close - make it corrupt

        result = storage_service.load_cache(str(large))
        assert result == {}

        backups = list((tmp_path / "backups").glob("*.corrupted-parse-*.json"))
        assert len(backups) == 1
        assert backups[0].stat().st_size > 10000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
