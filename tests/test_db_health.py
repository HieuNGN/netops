"""Tests for /api/health/db, healthcheck() on both clients, and
PG_POOL_MIN/PG_POOL_MAX env-var handling.
"""

import os
import tempfile

import pytest
import pytest_asyncio


# --- pool config env-var tests (no DB needed) --------------------------

def test_pg_pool_defaults():
    """PG_POOL_MIN/PG_POOL_MAX default to 4/25 when env is unset."""
    os.environ.pop("PG_POOL_MIN", None)
    os.environ.pop("PG_POOL_MAX", None)
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    assert client._min_pool_size == 4
    assert client._max_pool_size == 25


def test_pg_pool_env_override(monkeypatch):
    """PG_POOL_MIN/PG_POOL_MAX env vars are honored."""
    monkeypatch.setenv("PG_POOL_MIN", "8")
    monkeypatch.setenv("PG_POOL_MAX", "50")
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    assert client._min_pool_size == 8
    assert client._max_pool_size == 50


def test_pg_pool_constructor_args_override_env(monkeypatch):
    """Explicit constructor args win over env vars."""
    monkeypatch.setenv("PG_POOL_MIN", "8")
    monkeypatch.setenv("PG_POOL_MAX", "50")
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient(min_pool_size=2, max_pool_size=10)
    assert client._min_pool_size == 2
    assert client._max_pool_size == 10


def test_database_url_takes_priority_over_legacy(monkeypatch):
    """DATABASE_URL is preferred over POSTGRES_* env vars."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://override@host/db")
    monkeypatch.setenv("POSTGRES_HOST", "legacy-host")
    monkeypatch.setenv("POSTGRES_DB", "legacy-db")
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    assert "override" in client._connection_string
    assert "legacy-host" not in client._connection_string


# --- SQLite healthcheck ------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_healthcheck_connected(migrated_sqlite_db):
    """SQLite healthcheck returns connected + latency when DB is up."""
    info = await migrated_sqlite_db.healthcheck()
    assert info["status"] == "connected"
    assert info["backend"] == "sqlite"
    assert info["latency_ms"] >= 0
    assert info["path"]


@pytest.mark.asyncio
async def test_sqlite_healthcheck_disconnected():
    """SQLite healthcheck returns disconnected when DB is not connected."""
    from src.storage.sqlite_client import AsyncSQLiteClient
    db = AsyncSQLiteClient(db_path=tempfile.mktemp(suffix=".db"))
    # Note: connect() is NOT called.
    info = await db.healthcheck()
    assert info["status"] == "disconnected"
    assert info["backend"] == "sqlite"


# --- PG healthcheck (no real PG, exercise the disconnected path) -------

@pytest.mark.asyncio
async def test_pg_healthcheck_disconnected():
    """PG healthcheck returns disconnected when pool is not initialized."""
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient(connection_string="postgresql://nope@nowhere/db")
    info = await client.healthcheck()
    assert info["status"] == "disconnected"
    assert info["backend"] == "postgresql"


# --- /api/health/db endpoint -------------------------------------------

@pytest.mark.asyncio
async def test_api_health_db_endpoint_returns_503_when_no_client():
    """With no db_client, the endpoint returns 503."""
    from src.collector import main as main_mod
    original = main_mod.db_client
    main_mod.db_client = None
    try:
        from fastapi.testclient import TestClient
        client = TestClient(main_mod.app)
        resp = client.get("/api/health/db")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "disconnected"
    finally:
        main_mod.db_client = original


@pytest.mark.asyncio
async def test_api_health_db_endpoint_returns_connected_for_sqlite(migrated_sqlite_db):
    """With a connected SQLite client, the endpoint returns 200 + status."""
    from src.collector import main as main_mod
    original = main_mod.db_client
    main_mod.db_client = migrated_sqlite_db
    try:
        from fastapi.testclient import TestClient
        client = TestClient(main_mod.app)
        resp = client.get("/api/health/db")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "connected"
        assert body["backend"] == "sqlite"
    finally:
        main_mod.db_client = original
