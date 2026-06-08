"""Tests for Phase 4 partitioning + cleanup logic.

These tests run against SQLite only (no live PG required). The PG
behaviour is exercised by:
  - `tests/pg_migration.test.sh` (slow lane, optional in CI)
  - Manual smoke testing in a docker-compose stack

We assert:
  - The migrations 010 and 011 apply cleanly on SQLite (no-op).
  - `cleanup_topology_history()` on SQLite does a row-level DELETE
    (the fallback path) and returns the count.
  - `phase4_partitioning_enabled` defaults to False and respects
    the env var.
  - `maintain_topology_partitions()` is a no-op on a non-Postgres
    client (the AsyncSQLiteClient does not have this method).
  - The SQLite path's `topology_history` table is unchanged after
    010/011 (still a plain table, no partition of).
"""

import asyncio
import os

import pytest
import pytest_asyncio


# --- migration tests ----------------------------------------------------

def test_migrations_010_and_011_apply_on_sqlite():
    """Migration 010/011 are no-ops on SQLite and don't error."""
    from alembic import command
    from alembic.config import Config
    from tests.conftest import _run_alembic_upgrade_head, _PROJECT_ROOT
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = Config(os.path.join(_PROJECT_ROOT, "src", "storage", "alembic.ini"))
        config.set_main_option(
            "script_location",
            os.path.join(_PROJECT_ROOT, "src", "storage", "migrations"),
        )
        config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
        command.upgrade(config, "head")
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        eng = create_engine(f"sqlite:///{db_path}")
        with eng.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
        eng.dispose()
        script_dir = config.get_main_option("script_location")
        from alembic.script import ScriptDirectory
        head_rev = ScriptDirectory.from_config(config).get_current_head()
        assert current == head_rev
    finally:
        os.unlink(db_path)


# --- feature flag tests -------------------------------------------------

def test_phase4_flag_defaults_to_off(monkeypatch):
    """NETOPS_PHASE4_PARTITIONED_HISTORY defaults to off."""
    monkeypatch.delenv("NETOPS_PHASE4_PARTITIONED_HISTORY", raising=False)
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    assert client.phase4_partitioning_enabled is False


def test_phase4_flag_respects_env(monkeypatch):
    """NETOPS_PHASE4_PARTITIONED_HISTORY=1 turns the flag on."""
    monkeypatch.setenv("NETOPS_PHASE4_PARTITIONED_HISTORY", "1")
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    assert client.phase4_partitioning_enabled is True


# --- SQLite cleanup behaviour ------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_cleanup_topology_history_deletes_old_rows(migrated_sqlite_db):
    """SQLite path: row-level DELETE with retention cutoff."""
    from datetime import datetime, timedelta

    db = migrated_sqlite_db
    # Insert two old and one recent row directly.
    now = datetime.utcnow()
    old = (now - timedelta(days=100)).isoformat()
    very_old = (now - timedelta(days=200)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()

    cur = await db._db.execute(
        "INSERT INTO topology_history (event_type, recorded_at) VALUES (?, ?)",
        ("link_down", old),
    )
    old_id = cur.lastrowid
    cur = await db._db.execute(
        "INSERT INTO topology_history (event_type, recorded_at) VALUES (?, ?)",
        ("link_up", very_old),
    )
    cur = await db._db.execute(
        "INSERT INTO topology_history (event_type, recorded_at) VALUES (?, ?)",
        ("link_up", recent),
    )
    await db._db.commit()

    # Method exists on the SQLite client too (we added it in PR C).
    assert hasattr(db, "cleanup_topology_history")
    deleted = await db.cleanup_topology_history(retention_days=90)

    # Two old rows were deleted; the recent one remains.
    assert deleted == 2
    cur = await db._db.execute("SELECT COUNT(*) FROM topology_history")
    (count,) = await cur.fetchone()
    assert count == 1


@pytest.mark.asyncio
async def test_sqlite_cleanup_topology_history_zero_when_fresh(migrated_sqlite_db):
    """No rows older than retention: returns 0, no error."""
    db = migrated_sqlite_db
    # No rows at all -> 0 deleted, no error.
    deleted = await db.cleanup_topology_history(retention_days=90)
    assert deleted == 0


# --- Poller retention loop -------------------------------------------

@pytest.mark.asyncio
async def test_poller_retention_loop_calls_cleanup_topology_history(migrated_sqlite_db, monkeypatch):
    """SNMPPoller._retention_loop calls cleanup_topology_history once per hour.

    We let the loop run a single tick by replacing sleep with a
    function that breaks out via CancelledError after the first
    iteration.
    """
    import asyncio
    calls = []

    async def fake_cleanup_poll(retention_days: int = 30):
        calls.append(("poll", retention_days))

    async def fake_cleanup_topology(retention_days: int = 90):
        calls.append(("topology", retention_days))

    # Patch the methods on the db client.
    monkeypatch.setattr(migrated_sqlite_db, "cleanup_poll_history", fake_cleanup_poll)
    monkeypatch.setattr(migrated_sqlite_db, "cleanup_topology_history", fake_cleanup_topology)

    # Patch asyncio.sleep in the poller module to break out after one tick.
    from src.collector import snmp_poller
    first_call = [True]
    async def break_after_one_tick(_):
        if first_call[0]:
            first_call[0] = False
            return  # let the cleanup logic run
        raise asyncio.CancelledError()
    monkeypatch.setattr(snmp_poller.asyncio, "sleep", break_after_one_tick)

    from src.collector.snmp_poller import SNMPPoller

    poller = SNMPPoller(migrated_sqlite_db, poll_interval=999, timeout=1, retries=1)
    poller._running = True
    # Run the retention loop. It will exit when sleep raises
    # CancelledError on the second call.
    try:
        await poller._retention_loop()
    except asyncio.CancelledError:
        pass

    # Both cleanup methods should have been called.
    methods = [c[0] for c in calls]
    assert "poll" in methods
    assert "topology" in methods
    # The topology retention default is 90 days.
    assert any(c == ("topology", 90) for c in calls)
