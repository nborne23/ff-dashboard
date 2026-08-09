"""`services/backup.py` — nightly SQLite backup + prune (task 11.4), against a scratch
DB (invoking the coroutine directly, per the task's own instruction)."""

import os
import sqlite3
from datetime import datetime, timedelta

import pytest

from backend.gridiron.services import backup


def _make_scratch_db(path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO widgets (name) VALUES ('a'), ('b'), ('c')")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_run_backup_writes_a_dated_snapshot_with_the_same_data(tmp_path) -> None:
    db_path = tmp_path / "gridiron.db"
    _make_scratch_db(db_path)
    now = datetime(2026, 7, 16, 3, 0, 0)

    dest = await backup.run_backup(db_path, now=now)

    assert dest == tmp_path / "backups" / "gridiron-20260716.db"
    assert dest.is_file()
    conn = sqlite3.connect(str(dest))
    try:
        rows = conn.execute("SELECT name FROM widgets ORDER BY name").fetchall()
    finally:
        conn.close()
    assert rows == [("a",), ("b",), ("c",)]


@pytest.mark.asyncio
async def test_run_backup_is_wal_safe_against_a_wal_mode_db(tmp_path) -> None:
    """The backup must work against a live WAL-mode database (the app always runs in
    WAL mode, db.py's `make_engine`) — a raw file copy would risk missing
    not-yet-checkpointed pages; `sqlite3.Connection.backup()` must not."""
    db_path = tmp_path / "gridiron.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO widgets (name) VALUES ('wal-row')")
        conn.commit()
    finally:
        conn.close()

    dest = await backup.run_backup(db_path, now=datetime(2026, 7, 16, 3, 0, 0))

    conn = sqlite3.connect(str(dest))
    try:
        rows = conn.execute("SELECT name FROM widgets").fetchall()
    finally:
        conn.close()
    assert rows == [("wal-row",)]


@pytest.mark.asyncio
async def test_run_backup_prunes_backups_older_than_seven_days(tmp_path) -> None:
    db_path = tmp_path / "gridiron.db"
    _make_scratch_db(db_path)
    backup_dir = backup.backup_dir_for(db_path)
    backup_dir.mkdir(parents=True)

    now = datetime(2026, 7, 16, 3, 0, 0)
    old_file = backup_dir / "gridiron-20260101.db"
    old_file.write_text("stale")
    old_mtime = (now - timedelta(days=10)).timestamp()
    os.utime(old_file, (old_mtime, old_mtime))

    recent_file = backup_dir / "gridiron-20260710.db"
    recent_file.write_text("recent")
    recent_mtime = (now - timedelta(days=3)).timestamp()
    os.utime(recent_file, (recent_mtime, recent_mtime))

    await backup.run_backup(db_path, now=now)

    assert not old_file.exists()
    assert recent_file.exists()
    assert (backup_dir / "gridiron-20260716.db").exists()


@pytest.mark.asyncio
async def test_run_backup_keeps_a_backup_exactly_seven_days_old(tmp_path) -> None:
    db_path = tmp_path / "gridiron.db"
    _make_scratch_db(db_path)
    backup_dir = backup.backup_dir_for(db_path)
    backup_dir.mkdir(parents=True)

    now = datetime(2026, 7, 16, 3, 0, 0)
    boundary_file = backup_dir / "gridiron-20260709.db"
    boundary_file.write_text("boundary")
    boundary_mtime = (now - backup.BACKUP_RETENTION).timestamp()
    os.utime(boundary_file, (boundary_mtime, boundary_mtime))

    await backup.run_backup(db_path, now=now)

    assert boundary_file.exists()


def test_backup_path_for_uses_the_expected_filename_format(tmp_path) -> None:
    db_path = tmp_path / "data" / "gridiron.db"
    dest = backup.backup_path_for(db_path, datetime(2026, 1, 5))
    assert dest == tmp_path / "data" / "backups" / "gridiron-20260105.db"
