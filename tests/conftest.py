"""Shared pytest fixtures for NetOps.

The migration ownership change in PR A removed the imperative
DDL from `init_db()` (it is now a no-op). Tests that previously
relied on `init_db()` to bootstrap the schema now use the
`migrated_sqlite_db` fixture below, which runs Alembic migrations
against a fresh SQLite file.
"""

import os
import sys
import tempfile

import pytest
import pytest_asyncio

# Ensure project root is on sys.path so `from src...` works in test
# helpers and so `scripts.migrate` is importable.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.storage.sqlite_client import AsyncSQLiteClient  # noqa: E402


def _run_alembic_upgrade_head(db_path: str) -> None:
    """Run `alembic upgrade head` synchronously against a SQLite URL.

    Uses the synchronous Alembic command path with a sync engine. The
    async path is not needed for SQLite — `alembic upgrade head` works
    fine with the plain sqlite:// driver.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(
        os.path.join(_PROJECT_ROOT, "src", "storage", "alembic.ini")
    )
    config.set_main_option(
        "script_location",
        os.path.join(_PROJECT_ROOT, "src", "storage", "migrations"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "head")


@pytest_asyncio.fixture
async def migrated_sqlite_db():
    """Fresh SQLite DB with the full migration chain applied.

    Yields an AsyncSQLiteClient connected to a temp file. The DB is
    removed after the test. Use this fixture in place of the old
    `init_db()`-based fixture.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _run_alembic_upgrade_head(tmp.name)
    db = AsyncSQLiteClient(db_path=tmp.name)
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
        os.unlink(tmp.name)
