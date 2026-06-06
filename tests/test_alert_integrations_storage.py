"""Storage layer tests for alert config dedup/delete/update and integrations."""

import os
import tempfile
import pytest
import pytest_asyncio

from src.storage.sqlite_client import AsyncSQLiteClient
from tests.conftest import _run_alembic_upgrade_head


@pytest_asyncio.fixture
async def fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _run_alembic_upgrade_head(tmp.name)
    db = AsyncSQLiteClient(db_path=tmp.name)
    await db.connect()
    yield db
    await db.close()
    os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_alert_config_crud_cycle(fresh_db):
    created = await fresh_db.create_alert_config({
        "name": "Router Slack",
        "alert_type": "device_down",
        "channel": "slack",
        "config": {"webhook_url": "https://hooks.slack.com/x"},
        "enabled": True,
    })
    assert created["id"]
    assert created["name"] == "Router Slack"

    fetched = await fresh_db._get_alert_config(created["id"])
    assert fetched["channel"] == "slack"

    updated = await fresh_db.update_alert_config(created["id"], {
        "name": "Router Slack Renamed",
        "enabled": False,
    })
    assert updated["name"] == "Router Slack Renamed"
    assert not updated["enabled"]

    deleted = await fresh_db.delete_alert_config(created["id"])
    assert deleted is True
    assert await fresh_db._get_alert_config(created["id"]) is None
    assert await fresh_db.delete_alert_config(created["id"]) is False


@pytest.mark.asyncio
async def test_find_alert_config_by_signature_matches_duplicates(fresh_db):
    await fresh_db.create_alert_config({
        "name": "First",
        "alert_type": "device_down",
        "channel": "slack",
        "config": {"webhook_url": "https://hooks.slack.com/a"},
    })
    dup = await fresh_db.create_alert_config({
        "name": "Second (dup)",
        "alert_type": "device_down",
        "channel": "slack",
        "config": {"webhook_url": "https://hooks.slack.com/a"},
    })
    found = await fresh_db.find_alert_config_by_signature(
        "device_down", "slack", {"webhook_url": "https://hooks.slack.com/a"},
    )
    assert found is not None
    assert found["id"] != dup["id"]


@pytest.mark.asyncio
async def test_find_alert_config_signature_excludes_self(fresh_db):
    created = await fresh_db.create_alert_config({
        "name": "Self",
        "alert_type": "device_down",
        "channel": "slack",
        "config": {"webhook_url": "https://hooks.slack.com/b"},
    })
    found = await fresh_db.find_alert_config_by_signature(
        "device_down", "slack", {"webhook_url": "https://hooks.slack.com/b"},
        exclude_id=created["id"],
    )
    assert found is None


@pytest.mark.asyncio
async def test_find_alert_config_signature_key_order_independent(fresh_db):
    await fresh_db.create_alert_config({
        "name": "Ordered",
        "alert_type": "device_down",
        "channel": "telegram",
        "config": {"a": 1, "b": 2},
    })
    found = await fresh_db.find_alert_config_by_signature(
        "device_down", "telegram", {"b": 2, "a": 1},
    )
    assert found is not None


@pytest.mark.asyncio
async def test_delete_alert_removes_history(fresh_db):
    cfg = await fresh_db.create_alert_config({
        "name": "x",
        "alert_type": "device_down",
        "channel": "slack",
        "config": {},
    })
    await fresh_db.record_alert_history(cfg["id"], "test")
    assert len(await fresh_db.get_alert_history(10)) == 1
    await fresh_db.delete_alert_config(cfg["id"])
    assert await fresh_db.get_alert_history(10) == []


@pytest.mark.asyncio
async def test_integrations_crud(fresh_db):
    created = await fresh_db.create_integration({
        "type": "telegram",
        "name": "Ops Bot",
        "secrets_json": {"bot_token": "abc", "chat_id": "12345"},
        "enabled": True,
    })
    assert created["id"]
    assert created["secrets_json"]["bot_token"] == "abc"

    fetched = await fresh_db.get_integration(created["id"])
    assert fetched["name"] == "Ops Bot"

    updated = await fresh_db.update_integration(created["id"], {
        "name": "Ops Bot v2",
        "secrets_json": {"bot_token": "xyz"},
    })
    assert updated["name"] == "Ops Bot v2"
    assert updated["secrets_json"]["bot_token"] == "xyz"

    listed = await fresh_db.list_integrations(type="telegram")
    assert len(listed) == 1

    ok, err = await fresh_db.delete_integration(created["id"])
    assert ok is True
    assert err == ""


@pytest.mark.asyncio
async def test_integration_unique_per_type_name(fresh_db):
    await fresh_db.create_integration({
        "type": "telegram", "name": "Bot", "secrets_json": {},
    })
    import pytest as _pt
    with _pt.raises(Exception):
        await fresh_db.create_integration({
            "type": "telegram", "name": "Bot", "secrets_json": {},
        })


@pytest.mark.asyncio
async def test_integration_delete_blocked_when_referenced(fresh_db):
    integ = await fresh_db.create_integration({
        "type": "telegram", "name": "Bot", "secrets_json": {"bot_token": "x"},
    })
    await fresh_db.create_alert_config({
        "name": "UsesBot",
        "alert_type": "device_down",
        "channel": "telegram",
        "config": {"chat_id": "999"},
        "integration_id": integ["id"],
    })
    ok, err = await fresh_db.delete_integration(integ["id"])
    assert ok is False
    assert "referenced" in err

    # Remove the alert, then delete should succeed
    alerts = await fresh_db.list_alert_configs(include_disabled=True)
    await fresh_db.delete_alert_config(alerts[0]["id"])
    ok, err = await fresh_db.delete_integration(integ["id"])
    assert ok is True


@pytest.mark.asyncio
async def test_integration_merge_with_alert_override(fresh_db):
    integ = await fresh_db.create_integration({
        "type": "telegram",
        "name": "Bot",
        "secrets_json": {"bot_token": "SECRET", "chat_id": "111"},
    })
    alert = await fresh_db.create_alert_config({
        "name": "Override",
        "alert_type": "device_down",
        "channel": "telegram",
        "config": {"chat_id": "OVERRIDE-999"},
        "integration_id": integ["id"],
    })
    merged = await fresh_db.get_integration_for_alert(alert)
    assert merged["bot_token"] == "SECRET"
    assert merged["chat_id"] == "OVERRIDE-999"


@pytest.mark.asyncio
async def test_alert_without_integration_returns_own_config(fresh_db):
    alert = await fresh_db.create_alert_config({
        "name": "Direct",
        "alert_type": "device_down",
        "channel": "webhook",
        "config": {"url": "https://example.com/hook"},
    })
    merged = await fresh_db.get_integration_for_alert(alert)
    assert merged == {"url": "https://example.com/hook"}
