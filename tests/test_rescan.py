"""Tests for the wipe + rescan flow that replaces mocked devices with real ones."""

import os
import tempfile
import pytest
import pytest_asyncio

from src.storage.sqlite_client import AsyncSQLiteClient


@pytest_asyncio.fixture
async def fresh_db():
    """Isolated SQLite client per test, so wipes never leak between cases."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = AsyncSQLiteClient(db_path=tmp.name)
    await db.connect()
    await db.init_db()
    yield db
    await db.close()
    os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_clear_all_devices_wipes_topology(fresh_db):
    await fresh_db.create_device({"ip_address": "10.0.0.1", "name": "Dev-1"})
    await fresh_db.create_device({"ip_address": "10.0.0.2", "name": "Dev-2"})
    await fresh_db.upsert_topology(
        nodes=[{"id": "10.0.0.1", "label": "Dev-1"}, {"id": "10.0.0.2", "label": "Dev-2"}],
        links=[{"id": "a-b", "source": "10.0.0.1", "target": "10.0.0.2"}],
    )
    assert len(await fresh_db.list_devices()) == 2
    assert len((await fresh_db.list_topology())["nodes"]) == 2

    removed = await fresh_db.clear_all_devices()
    assert removed == 2
    assert await fresh_db.list_devices() == []
    topo = await fresh_db.list_topology()
    assert topo == {"nodes": [], "links": []}


@pytest.mark.asyncio
async def test_bulk_delete_only_targets_matching(fresh_db):
    await fresh_db.create_device({"ip_address": "10.0.0.1", "name": "Real-1"})
    await fresh_db.create_device({"ip_address": "10.0.0.2", "name": "Real-2"})
    await fresh_db.create_device(
        {"ip_address": "192.168.1.1", "name": "Core-Router-1", "discovery_method": "simulated"},
    )

    # Drop only the simulated record by id-or-ip
    removed = await fresh_db.bulk_delete_devices(["192.168.1.1"])
    assert removed == 1
    remaining = await fresh_db.list_devices()
    assert len(remaining) == 2
    assert all(d["name"].startswith("Real-") for d in remaining)


@pytest.mark.asyncio
async def test_bulk_delete_empty_is_noop(fresh_db):
    assert await fresh_db.bulk_delete_devices([]) == 0
    assert await fresh_db.list_devices() == []
