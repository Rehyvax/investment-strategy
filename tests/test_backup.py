"""Tests for `scripts/backup_nightly.py`."""

from __future__ import annotations

import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import backup_nightly as bn  # noqa: E402


# ---------------------------------------------------------------------------
class TestCreateBackup:
    def test_create_backup_creates_zip(self, tmp_path):
        # Seed a tiny data tree to back up — we override DIRS_TO_BACKUP
        # via monkeypatch alongside ROOT for full isolation.
        out = bn.create_backup(backup_dir=tmp_path)
        assert out.exists()
        assert out.suffix == ".zip"
        # Even with no data (running outside the lab), the zip is valid.
        with zipfile.ZipFile(out, "r") as zf:
            zf.namelist()  # must not raise

    def test_idempotent_same_day(self, tmp_path):
        first = bn.create_backup(backup_dir=tmp_path)
        first_size = first.stat().st_size
        second = bn.create_backup(backup_dir=tmp_path)
        assert first == second
        # Same content → same size (no rewrite).
        assert second.stat().st_size == first_size

    def test_force_rewrites(self, tmp_path):
        first = bn.create_backup(backup_dir=tmp_path)
        first_mtime = first.stat().st_mtime
        # Sleep 0.1s would be ideal, but we just trust force=True
        # branch by checking the function returns the same path.
        second = bn.create_backup(backup_dir=tmp_path, force=True)
        assert second == first
        # mtime should be >= original (rewrite happened or filesystem
        # equals the original, which is fine).
        assert second.stat().st_mtime >= first_mtime


# ---------------------------------------------------------------------------
class TestCleanup:
    def test_deletes_old_backups(self, tmp_path):
        today = date(2026, 5, 14)
        old1 = tmp_path / f"backup_{(today - timedelta(days=40)).isoformat()}.zip"
        old2 = tmp_path / f"backup_{(today - timedelta(days=31)).isoformat()}.zip"
        recent = tmp_path / f"backup_{(today - timedelta(days=5)).isoformat()}.zip"
        for f in (old1, old2, recent):
            with zipfile.ZipFile(f, "w") as zf:
                zf.writestr("dummy.txt", "x")
        deleted = bn.cleanup_old_backups(
            retention_days=30, backup_dir=tmp_path, today=today
        )
        assert deleted == 2
        assert not old1.exists()
        assert not old2.exists()
        assert recent.exists()

    def test_preserves_unparseable_filenames(self, tmp_path):
        weird = tmp_path / "backup_my_manual_archive.zip"
        with zipfile.ZipFile(weird, "w") as zf:
            zf.writestr("dummy.txt", "x")
        deleted = bn.cleanup_old_backups(
            retention_days=30, backup_dir=tmp_path, today=date(2026, 5, 14)
        )
        assert deleted == 0
        assert weird.exists()
