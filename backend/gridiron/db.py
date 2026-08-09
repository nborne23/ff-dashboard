"""Async SQLAlchemy engine + session factory for `sqlite+aiosqlite`.

WAL mode and a `busy_timeout` are set on every new DBAPI connection so the single
scheduler writer and concurrent web readers don't hit `database is locked` errors
(see design.md D6).
"""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.gridiron.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_db_path() -> Path:
    """Resolve `settings.gridiron_db_path` to an absolute path, creating its parent dir."""
    settings = get_settings()
    db_path = Path(settings.gridiron_db_path)
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def make_engine(db_path: Path | None = None) -> AsyncEngine:
    """Build an async engine with WAL mode + busy_timeout wired via a `connect` listener."""
    path = db_path if db_path is not None else resolve_db_path()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


engine = make_engine()
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped `AsyncSession`."""
    async with async_session_factory() as session:
        yield session
