"""Alembic environment configuration for async PostgreSQL.

Loads `.env` from the project root (if present) so that DATABASE_URL
and other env-var-based settings are available to migrations without
requiring explicit shell exports. Also enables type-drift detection
(compare_type=True) so autogenerate flags column-type changes such as
JSON -> JSONB.
"""

import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from src.storage.database import Base


# Load .env so DATABASE_URL is available to migrations.
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Strip optional inline comments after value.
        value = value.split("#", 1)[0].strip()
        os.environ.setdefault(key.strip(), value)


_load_dotenv()


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Two paths:
      - Async URL (e.g. `sqlite+aiosqlite`, `postgresql+asyncpg`):
        use the async engine via `asyncio.run`. This is the path
        used by the running app's lifespan.
      - Sync URL or no running loop: use a synchronous engine.
        This is the path used by test fixtures that run Alembic in a
        thread (where `asyncio.run` would conflict).
    """
    import asyncio

    url = config.get_main_option("sqlalchemy.url") or ""

    if "+aiosqlite" in url or "+asyncpg" in url:
        try:
            asyncio.get_running_loop()
            # Running loop is present and URL is async — fall through
            # to sync path to avoid `asyncio.run` conflict.
        except RuntimeError:
            # No running loop, async URL: standard async path.
            asyncio.run(run_async_migrations())
            return

    # Sync path: create a sync engine with the pysqlite driver.
    from sqlalchemy import create_engine

    sync_url = url.replace("+aiosqlite", "").replace("+asyncpg", "")
    if not sync_url:
        # Default: localhost PG from alembic.ini default
        sync_url = "postgresql://netops:netops@localhost:5432/netops"
    engine = create_engine(sync_url)
    with engine.connect() as connection:
        do_run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
