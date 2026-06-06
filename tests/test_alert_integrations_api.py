"""API endpoint tests for alert config dedup, update, delete, and integrations."""

import os
import tempfile
import uuid

os.environ.setdefault("JWT_SECRET", "test-secret-for-tests-only-32chars")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager


@pytest_asyncio.fixture(scope="function")
async def client():
    # Isolated SQLite per test — stops data from leaking into ./data/netops.db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["NETOPS_SQLITE_PATH"] = tmp.name

    from src.collector.main import app

    try:
        async with LifespanManager(app) as manager:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac
    finally:
        os.unlink(tmp.name)


def _uniq_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class TestAlertEndpointsExtended:
    """Extended tests for /alerts covering delete/update/dedup."""

    @pytest.mark.asyncio
    async def test_create_then_delete_alert(self, client):
        name = _uniq_name("del")
        create = await client.post("/alerts", json={
            "name": name,
            "alert_type": "device_down",
            "channel": "webhook",
            "config": {"url": f"https://example.com/{uuid.uuid4().hex}"},
        })
        assert create.status_code == 200
        alert_id = create.json()["id"]

        delete = await client.delete(f"/alerts/{alert_id}")
        assert delete.status_code == 200
        assert delete.json()["status"] == "deleted"

        get_again = await client.delete(f"/alerts/{alert_id}")
        assert get_again.status_code == 404

    @pytest.mark.asyncio
    async def test_update_alert(self, client):
        name = _uniq_name("upd")
        create = await client.post("/alerts", json={
            "name": name,
            "alert_type": "device_down",
            "channel": "webhook",
            "config": {"url": f"https://example.com/{uuid.uuid4().hex}"},
        })
        assert create.status_code == 200
        alert_id = create.json()["id"]

        update = await client.put(f"/alerts/{alert_id}", json={
            "name": name + "-renamed",
            "enabled": False,
        })
        assert update.status_code == 200
        body = update.json()
        assert body["name"] == name + "-renamed"
        assert not body["enabled"]

    @pytest.mark.asyncio
    async def test_update_alert_not_found(self, client):
        update = await client.put("/alerts/nonexistent-id", json={"name": "x"})
        assert update.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_alert_returns_409(self, client):
        cfg = {"url": f"https://example.com/{uuid.uuid4().hex}"}
        first = await client.post("/alerts", json={
            "name": _uniq_name("dup1"),
            "alert_type": "device_down",
            "channel": "webhook",
            "config": cfg,
        })
        assert first.status_code == 200

        second = await client.post("/alerts", json={
            "name": _uniq_name("dup2"),
            "alert_type": "device_down",
            "channel": "webhook",
            "config": cfg,
        })
        assert second.status_code == 409
        detail = second.json()["detail"]
        assert detail["existing_id"] == first.json()["id"]
        assert "same" in detail["message"].lower() or "exists" in detail["message"].lower()

    @pytest.mark.asyncio
    async def test_create_alert_with_bad_integration_returns_400(self, client):
        response = await client.post("/alerts", json={
            "name": _uniq_name("bad-int"),
            "alert_type": "device_down",
            "channel": "telegram",
            "config": {},
            "integration_id": "no-such-integration",
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_alert_dedup_excluding_self(self, client):
        cfg = {"url": f"https://example.com/{uuid.uuid4().hex}"}
        create = await client.post("/alerts", json={
            "name": _uniq_name("selfupd"),
            "alert_type": "device_down",
            "channel": "webhook",
            "config": cfg,
        })
        assert create.status_code == 200
        alert_id = create.json()["id"]

        update = await client.put(f"/alerts/{alert_id}", json={
            "name": "Renamed",
        })
        assert update.status_code == 200


class TestIntegrationEndpoints:
    """Tests for /integrations CRUD + test endpoint."""

    @pytest.mark.asyncio
    async def test_create_get_update_delete_integration(self, client):
        name = _uniq_name("int")
        create = await client.post("/integrations", json={
            "type": "telegram",
            "name": name,
            "secrets_json": {"bot_token": "abc", "chat_id": "123"},
            "enabled": True,
        })
        assert create.status_code == 200
        iid = create.json()["id"]

        get = await client.get(f"/integrations/{iid}")
        assert get.status_code == 200
        assert get.json()["name"] == name

        update = await client.put(f"/integrations/{iid}", json={
            "name": name + "-v2",
        })
        assert update.status_code == 200
        assert update.json()["name"] == name + "-v2"

        delete = await client.delete(f"/integrations/{iid}")
        assert delete.status_code == 200

    @pytest.mark.asyncio
    async def test_list_integrations_with_type_filter(self, client):
        await client.post("/integrations", json={
            "type": "slack", "name": _uniq_name("sl"), "secrets_json": {},
        })
        resp = await client.get("/integrations?type=slack")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        for item in resp.json():
            assert item["type"] == "slack"

    @pytest.mark.asyncio
    async def test_integration_unique_name_returns_409(self, client):
        name = _uniq_name("uniq")
        first = await client.post("/integrations", json={
            "type": "telegram", "name": name, "secrets_json": {},
        })
        assert first.status_code == 200
        second = await client.post("/integrations", json={
            "type": "telegram", "name": name, "secrets_json": {},
        })
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_alert_uses_integration_secrets(self, client):
        integ = await client.post("/integrations", json={
            "type": "telegram",
            "name": _uniq_name("merge"),
            "secrets_json": {"bot_token": "BASE-TOKEN", "chat_id": "BASE-CHAT"},
        })
        assert integ.status_code == 200
        iid = integ.json()["id"]

        alert = await client.post("/alerts", json={
            "name": _uniq_name("uses-merge"),
            "alert_type": "device_down",
            "channel": "telegram",
            "config": {"chat_id": "OVERRIDE-CHAT"},
            "integration_id": iid,
        })
        assert alert.status_code == 200

        # Cleanup: delete integration should be blocked
        blocked = await client.delete(f"/integrations/{iid}")
        assert blocked.status_code == 409

        # Cleanup: delete alert first
        await client.delete(f"/alerts/{alert.json()['id']}")
        ok = await client.delete(f"/integrations/{iid}")
        assert ok.status_code == 200

    @pytest.mark.asyncio
    async def test_test_integration_invalid_config(self, client):
        integ = await client.post("/integrations", json={
            "type": "telegram",
            "name": _uniq_name("test-int"),
            "secrets_json": {},
        })
        assert integ.status_code == 200
        iid = integ.json()["id"]

        test = await client.post(f"/integrations/{iid}/test")
        assert test.status_code == 400

        await client.delete(f"/integrations/{iid}")

    @pytest.mark.asyncio
    async def test_test_integration_not_found(self, client):
        test = await client.post("/integrations/nope-id/test")
        assert test.status_code == 404
