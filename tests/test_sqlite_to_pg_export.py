"""Tests for the SQLite -> PostgreSQL data exporter and the dedup tool.

These tests do not require a live PostgreSQL server. The exporter is
unit-tested by patching the asyncpg.connect function to return a
fake connection that records INSERT statements. This is faster and
deterministic.

The exporter's `asyncpg` import is gated behind `if __name__` flow,
so we patch at the import location: `asyncpg.connect`.
"""

import asyncio
import json
import os
import sys
import tempfile

import pytest
import pytest_asyncio


# --- helpers ------------------------------------------------------------

class _FakeAsyncpgConnection:
    """Records every execute() call and returns canned responses."""

    def __init__(self) -> None:
        self.inserts: list[tuple[str, tuple]] = []
        self.fetchrow_responses: list[tuple] = [
            ("alembic_version",),  # _ensure_target_schema
        ]

    async def fetchrow(self, sql: str, *args):
        if self.fetchrow_responses:
            return self.fetchrow_responses.pop(0)
        return None

    async def execute(self, sql: str, *args):
        if sql.strip().upper().startswith("INSERT"):
            self.inserts.append((sql, args))
        return "INSERT 0 1"

    async def close(self):
        pass


class _FakeAsyncpgConnect:
    def __init__(self) -> None:
        self.conn = _FakeAsyncpgConnection()

    async def __call__(self, *args, **kwargs):
        return self.conn


# --- fixtures -----------------------------------------------------------

@pytest_asyncio.fixture
async def populated_sqlite_db():
    """SQLite DB with the migration chain applied and a few rows inserted."""
    from tests.conftest import _run_alembic_upgrade_head
    from src.storage.sqlite_client import AsyncSQLiteClient

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _run_alembic_upgrade_head(tmp.name)
    db = AsyncSQLiteClient(db_path=tmp.name)
    await db.connect()

    # Insert a user and a device so the exporter has something to copy.
    from src.api.services.auth import hash_password
    await db.create_user("alice", hash_password("Sup3r$ecret!"), email="a@x.com", name="Alice")
    await db.create_device({
        "ip_address": "10.0.0.1",
        "name": "Test-Device",
        "status": "online",
        "discovery_method": "manual",
        "sys_descr": "Test sysDescr",
    })

    yield tmp.name
    await db.close()
    os.unlink(tmp.name)


@pytest.fixture
def fake_asyncpg(monkeypatch):
    """Patch asyncpg.connect to return a fake connection."""
    fake = _FakeAsyncpgConnect()

    # The exporter imports asyncpg at top of main(); patch the symbol
    # it binds to.
    import scripts.sqlite_to_pg_export as exporter
    monkeypatch.setattr(exporter, "asyncpg", type("M", (), {"connect": fake}))
    return fake


# --- tests --------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_copies_all_tables(populated_sqlite_db, fake_asyncpg, monkeypatch):
    """Happy path: exporter copies every table listed in EXPORT_ORDER."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake/fake")
    monkeypatch.setattr("sys.argv", ["sqlite_to_pg_export.py", "--sqlite", populated_sqlite_db])

    from scripts.sqlite_to_pg_export import main as exporter_main
    rc = await exporter_main()
    assert rc == 0

    inserts = fake_asyncpg.conn.inserts
    # We inserted a user and a device, so at least those tables
    # should have INSERTs.
    insert_sqls = " ".join(sql for sql, _ in inserts)
    assert "INSERT INTO" in insert_sqls.upper()
    assert "users" in insert_sqls
    assert "devices" in insert_sqls


@pytest.mark.asyncio
async def test_export_fails_without_database_url(populated_sqlite_db, monkeypatch, capsys):
    """No DATABASE_URL and no --database-url: error message, exit 1."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["sqlite_to_pg_export.py", "--sqlite", populated_sqlite_db])

    from scripts.sqlite_to_pg_export import main as exporter_main
    rc = await exporter_main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "DATABASE_URL" in captured.err or "database-url" in captured.err.lower()


@pytest.mark.asyncio
async def test_export_fails_when_source_sqlite_missing(monkeypatch, capsys):
    """Source file not present: error, exit 1."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake/fake")
    monkeypatch.setattr(
        "sys.argv",
        ["sqlite_to_pg_export.py", "--sqlite", "/tmp/does-not-exist.db"],
    )

    from scripts.sqlite_to_pg_export import main as exporter_main
    rc = await exporter_main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()


@pytest.mark.asyncio
async def test_export_fails_when_target_schema_missing(populated_sqlite_db, fake_asyncpg, monkeypatch):
    """Target PG has no alembic_version: error, exception raised."""
    # Override fetchrow to return None (no alembic_version).
    fake_asyncpg.conn.fetchrow_responses = [None]

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake/fake")
    monkeypatch.setattr("sys.argv", ["sqlite_to_pg_export.py", "--sqlite", populated_sqlite_db])

    from scripts.sqlite_to_pg_export import main as exporter_main
    with pytest.raises(RuntimeError, match="alembic_version"):
        await exporter_main()


@pytest.mark.asyncio
async def test_export_handles_json_columns(populated_sqlite_db, fake_asyncpg, monkeypatch):
    """JSON columns are coerced to native Python objects before insert."""
    # Add a service_check with a JSON config_json value.
    import aiosqlite
    conn = await aiosqlite.connect(populated_sqlite_db)
    await conn.execute(
        "INSERT INTO service_checks (id, name, check_type, target, config_json) "
        "VALUES (?, ?, ?, ?, ?)",
        ("check-1", "test", "http", "https://example.com", '{"url": "https://x"}'),
    )
    await conn.commit()
    await conn.close()

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake@fake/fake")
    monkeypatch.setattr("sys.argv", ["sqlite_to_pg_export.py", "--sqlite", populated_sqlite_db])

    from scripts.sqlite_to_pg_export import main as exporter_main
    rc = await exporter_main()
    assert rc == 0

    # Find the service_checks INSERT and verify config_json was parsed.
    service_check_inserts = [
        (sql, args) for sql, args in fake_asyncpg.conn.inserts
        if "service_checks" in sql
    ]
    assert service_check_inserts
    # The args tuple should contain a dict (parsed JSON) for config_json.
    found = False
    for sql, args in service_check_inserts:
        for arg in args:
            if isinstance(arg, dict) and arg.get("url") == "https://x":
                found = True
                break
    assert found, "JSON column not coerced to dict"


# --- dedupe tool --------------------------------------------------------

@pytest.mark.asyncio
async def test_dedupe_dry_run_finds_duplicates(populated_sqlite_db, monkeypatch, capsys):
    """Dry run: detects duplicates, does not delete."""
    import aiosqlite
    conn = await aiosqlite.connect(populated_sqlite_db)
    # Add a duplicate pair of alert_configs.
    await conn.executescript("""
        INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled)
        VALUES ('a1', 'dup1', 'device_offline', 'email', '{"to": "a@x.com"}', 1);
        INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled)
        VALUES ('a2', 'dup2', 'device_offline', 'email', '{"to": "a@x.com"}', 1);
    """)
    await conn.commit()
    await conn.close()

    monkeypatch.setattr("sys.argv", ["dedupe.py", "--sqlite", populated_sqlite_db])
    from scripts.dedupe_alert_configs import _apply_sqlite
    deleted = await _apply_sqlite(populated_sqlite_db, apply=False)
    assert deleted == 0  # dry run, nothing deleted

    # Verify the duplicates are still in the DB.
    conn2 = await aiosqlite.connect(populated_sqlite_db)
    rows = await (await conn2.execute("SELECT COUNT(*) FROM alert_configs")).fetchone()
    await conn2.close()
    assert rows[0] == 2  # both still present


@pytest.mark.asyncio
async def test_dedupe_apply_removes_duplicates(populated_sqlite_db, monkeypatch, capsys):
    """Apply mode: deletes the duplicate, keeps the oldest."""
    import aiosqlite
    conn = await aiosqlite.connect(populated_sqlite_db)
    await conn.executescript("""
        INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled, created)
        VALUES ('a1', 'oldest', 'device_offline', 'email', '{"to": "a@x.com"}', 1, '2024-01-01 00:00:00');
        INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled, created)
        VALUES ('a2', 'dup', 'device_offline', 'email', '{"to": "a@x.com"}', 1, '2024-01-02 00:00:00');
    """)
    await conn.commit()
    await conn.close()

    monkeypatch.setattr("sys.argv", ["dedupe.py", "--apply", "--sqlite", populated_sqlite_db])
    from scripts.dedupe_alert_configs import _apply_sqlite
    deleted = await _apply_sqlite(populated_sqlite_db, apply=True)
    assert deleted == 1

    # Verify only 'a1' (oldest) remains.
    conn2 = await aiosqlite.connect(populated_sqlite_db)
    rows = await (await conn2.execute("SELECT id FROM alert_configs ORDER BY id")).fetchall()
    await conn2.close()
    assert [r[0] for r in rows] == ["a1"]


@pytest.mark.asyncio
async def test_dedupe_idempotent(populated_sqlite_db, monkeypatch):
    """Re-running dedupe is a no-op (no duplicates left)."""
    import aiosqlite
    conn = await aiosqlite.connect(populated_sqlite_db)
    await conn.execute(
        "INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled) "
        "VALUES ('a1', 'unique', 'device_offline', 'email', '{}', 1)"
    )
    await conn.commit()
    await conn.close()

    monkeypatch.setattr("sys.argv", ["dedupe.py", "--apply", "--sqlite", populated_sqlite_db])
    from scripts.dedupe_alert_configs import _apply_sqlite
    deleted = await _apply_sqlite(populated_sqlite_db, apply=True)
    assert deleted == 0
