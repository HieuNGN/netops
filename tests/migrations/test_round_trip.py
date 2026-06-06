"""Migration round-trip tests.

These tests exercise the Alembic migration chain against a fresh
SQLite database. They assert:

  1. upgrade head → downgrade base → upgrade head works without error.
  2. The schema after upgrade contains every table the application
     expects (14 tables, 0 missing).
  3. The schema is the same on the second upgrade as it was on the
     first (idempotency).

These tests use SQLite because:
  - No external services are required.
  - The migration chain is dialect-aware but SQLite covers the common
    DDL subset (CREATE TABLE, ADD COLUMN, CREATE INDEX).

PG-specific tests (e.g. JSONB partitioning) live in the future
`tests/pg_migration.test.sh` slow-lane suite.
"""

import os
import tempfile

import pytest
from alembic import command
from alembic.config import Config


# Canonical list of tables the application expects post-migration.
EXPECTED_TABLES = {
    "devices",
    "topology_nodes",
    "topology_links",
    "poll_history",
    "alert_configs",
    "alert_history",
    "users",
    "app_settings",
    "topology_history",
    "integrations",
    "service_checks",
    "check_results",
    "networks",
    "maintenance_windows",
    # Alembic's own bookkeeping table.
    "alembic_version",
}


def _alembic_config_for_sqlite(path: str) -> Config:
    """Build an Alembic Config pointed at a fresh SQLite file."""
    config = Config(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "storage", "alembic.ini",
        )
    )
    config.set_main_option(
        "script_location",
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "storage", "migrations",
        ),
    )
    # Use the async SQLite URL — env.py always uses the async path
    # via `async_engine_from_config`, so the URL must be aiosqlite.
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path}")
    return config


def _tables_in(db_path: str) -> set[str]:
    """List user tables in a SQLite database via raw sqlite3."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def test_upgrade_creates_all_expected_tables():
    """Fresh DB -> alembic upgrade head -> all 14 application tables present."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = _alembic_config_for_sqlite(db_path)
        command.upgrade(config, "head")
        actual = _tables_in(db_path)
        missing = EXPECTED_TABLES - actual
        assert not missing, f"Missing tables after upgrade head: {missing}"
    finally:
        os.unlink(db_path)


def test_downgrade_to_base_drops_all_app_tables():
    """upgrade head -> downgrade base -> only alembic_version remains."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = _alembic_config_for_sqlite(db_path)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        actual = _tables_in(db_path)
        # After downgrade to base, the only table should be the
        # alembic bookkeeping table itself. Application tables
        # must all be gone.
        app_tables = actual - {"alembic_version"}
        assert not app_tables, f"Tables remaining after downgrade base: {app_tables}"
    finally:
        os.unlink(db_path)


def test_round_trip_upgrade_downgrade_upgrade_is_stable():
    """upgrade head -> downgrade base -> upgrade head produces the same schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = _alembic_config_for_sqlite(db_path)
        command.upgrade(config, "head")
        first = _tables_in(db_path)
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        second = _tables_in(db_path)
        assert first == second, f"Schema drift on round trip: {first ^ second}"
    finally:
        os.unlink(db_path)


def test_idempotent_re_upgrade_is_noop():
    """Running upgrade head twice in a row should not error and should not change the schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = _alembic_config_for_sqlite(db_path)
        command.upgrade(config, "head")
        first = _tables_in(db_path)
        command.upgrade(config, "head")
        second = _tables_in(db_path)
        assert first == second, "Re-running upgrade head changed the schema"
    finally:
        os.unlink(db_path)
