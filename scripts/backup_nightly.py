"""Nightly backup of the lab's source-of-truth data.

Writes a compressed zip of:
- data/snapshots/   (all portfolios)
- data/events/      (theses, trades, debates, reflections, news…)
- data/charters/    (immutable mandates)
- data/agents/      (agent state)
- dashboard/data/   (cerebro_state.json + history)
- MEMORY.md         (root)
- .env.example      (root)

Naming: backups/backup_YYYY-MM-DD.zip — one per day.
Retention: 30 days. Older zips are auto-deleted.
Idempotent: skips if today's zip already exists.

CLI:
    python scripts/backup_nightly.py
    python scripts/backup_nightly.py --retention 60
    python scripts/backup_nightly.py --force        # rewrite today's zip
"""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

BACKUP_DIR = ROOT / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

DIRS_TO_BACKUP = (
    "data/snapshots",
    "data/events",
    "data/charters",       # may not exist yet — backup skips with warning
    "data/agents",         # may not exist yet — backup skips with warning
    "data/memory",         # per-agent curated MEMORY.md per CLAUDE.md §3
    "dashboard/data",
)

ROOT_FILES_TO_INCLUDE = ("MEMORY.md", ".env.example")

DEFAULT_RETENTION_DAYS = 30

logger = logging.getLogger("backup_nightly")


def _configure_logger() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        LOGS_DIR / "backup_nightly.log", encoding="utf-8"
    )
    sh = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


def create_backup(
    *, force: bool = False, backup_dir: Path | None = None,
    target_date: date | None = None,
) -> Path:
    """Create the daily zip. Returns the path written. When `force`
    is False and today's zip already exists, returns the existing path
    without rewriting."""
    backup_dir = backup_dir or BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    today = target_date or date.today()
    backup_path = backup_dir / f"backup_{today.isoformat()}.zip"
    if backup_path.exists() and not force:
        logger.info(f"Backup for {today} already exists: {backup_path}")
        return backup_path

    files_added = 0
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in DIRS_TO_BACKUP:
            dpath = ROOT / d
            if not dpath.exists():
                logger.warning(f"Skipping missing dir: {d}")
                continue
            for f in dpath.rglob("*"):
                if not f.is_file():
                    continue
                # Skip in-flight tmp files.
                if f.suffix in {".tmp", ".lock"}:
                    continue
                arcname = f.relative_to(ROOT)
                zf.write(f, arcname)
                files_added += 1
        for fname in ROOT_FILES_TO_INCLUDE:
            f = ROOT / fname
            if f.exists():
                zf.write(f, fname)
                files_added += 1
    size_mb = backup_path.stat().st_size / (1024 * 1024)
    logger.info(
        f"Backup created: {backup_path.name} "
        f"({files_added} files, {size_mb:.2f} MB)"
    )
    return backup_path


def cleanup_old_backups(
    retention_days: int = DEFAULT_RETENTION_DAYS,
    *,
    backup_dir: Path | None = None,
    today: date | None = None,
) -> int:
    """Delete backup_YYYY-MM-DD.zip files older than retention. Returns
    count of deletions. Files whose name doesn't parse to a date are
    left alone (manual user backups, etc.)."""
    backup_dir = backup_dir or BACKUP_DIR
    if not backup_dir.exists():
        return 0
    today = today or date.today()
    cutoff = today - timedelta(days=retention_days)
    deleted = 0
    for f in backup_dir.glob("backup_*.zip"):
        stem = f.stem.replace("backup_", "", 1)
        try:
            backup_date = date.fromisoformat(stem)
        except ValueError:
            continue
        if backup_date < cutoff:
            try:
                f.unlink()
                deleted += 1
                logger.info(f"Deleted old backup: {f.name}")
            except OSError as exc:
                logger.warning(f"Could not delete {f.name}: {exc}")
    if deleted:
        logger.info(f"Cleanup: deleted {deleted} backup(s) older than {retention_days}d")
    return deleted


def main(argv: list[str] | None = None) -> int:
    _configure_logger()
    p = argparse.ArgumentParser(description="Nightly data backup.")
    p.add_argument(
        "--retention",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Days to keep (default {DEFAULT_RETENTION_DAYS}).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Rewrite today's backup even if it already exists.",
    )
    args = p.parse_args(argv)
    create_backup(force=args.force)
    cleanup_old_backups(retention_days=args.retention)
    return 0


if __name__ == "__main__":
    sys.exit(main())
