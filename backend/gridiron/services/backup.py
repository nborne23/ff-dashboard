"""Nightly SQLite backup (task 11.4).

`sqlite3.Connection.backup()` is WAL-safe — it uses SQLite's own online-backup API,
which takes a consistent snapshot regardless of a concurrent WAL checkpoint, unlike a
raw filesystem copy of the `.db` file — and works directly against the *live*, in-use
database with no need to stop the app or take an app-level lock.
"""

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

BACKUP_RETENTION = timedelta(days=7)
BACKUP_DIR_NAME = "backups"
BACKUP_FILENAME_FORMAT = "gridiron-%Y%m%d.db"
BACKUP_GLOB = "gridiron-*.db"


def backup_dir_for(db_path: Path) -> Path:
    return db_path.parent / BACKUP_DIR_NAME


def backup_path_for(db_path: Path, when: datetime) -> Path:
    return backup_dir_for(db_path) / when.strftime(BACKUP_FILENAME_FORMAT)


def _backup_sync(db_path: Path, dest_path: Path) -> None:
    """The actual `sqlite3` backup, run synchronously via `asyncio.to_thread` from
    `run_backup` so it never blocks the event loop."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(dest_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def _prune_old_backups(backup_dir: Path, now: datetime, retention: timedelta) -> list[Path]:
    """Delete backup files whose mtime is older than `retention`; returns what got
    deleted (for logging — never raises just because there's nothing to prune)."""
    if not backup_dir.is_dir():
        return []
    cutoff = now - retention
    deleted: list[Path] = []
    for path in sorted(backup_dir.glob(BACKUP_GLOB)):
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).replace(tzinfo=None)
        if mtime < cutoff:
            path.unlink()
            deleted.append(path)
    return deleted


async def run_backup(db_path: Path, now: datetime | None = None) -> Path:
    """Back up `db_path` to `<db-dir>/backups/gridiron-YYYYMMDD.db` and prune backups
    older than `BACKUP_RETENTION`. Returns the fresh backup's path."""
    now = now.replace(tzinfo=None) if now is not None else datetime.now(UTC).replace(tzinfo=None)
    dest_path = backup_path_for(db_path, now)
    await asyncio.to_thread(_backup_sync, db_path, dest_path)
    logger.info("backup_db wrote %s", dest_path)

    deleted = _prune_old_backups(backup_dir_for(db_path), now, BACKUP_RETENTION)
    if deleted:
        logger.info("backup_db pruned %d backup(s) older than %s", len(deleted), BACKUP_RETENTION)
    return dest_path
