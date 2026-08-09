"""Alembic environment: async SQLite engine wired to Settings.gridiron_db_path.

`target_metadata` points at `backend.gridiron.models.Base.metadata` so `alembic revision
--autogenerate` picks up ORM model changes.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make `backend.*` importable regardless of the cwd alembic is invoked from.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.gridiron.config import get_settings  # noqa: E402
from backend.gridiron.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_db_url() -> str:
    settings = get_settings()
    db_path = (REPO_ROOT / settings.gridiron_db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=get_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_db_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
