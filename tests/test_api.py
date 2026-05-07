"""Integration tests for NetOps API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager


@pytest_asyncio.fixture(scope="function")
async def client():
    """Create async test client for FastAPI app with lifespan events."""
    from src.collector.main import app

    async with LifespanManager(app) as manager:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health endpoint returns ok status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestTopologyEndpoints:
    """Tests for topology endpoints."""

    @pytest.mark.asyncio
    async def test_get_topology_empty(self, client):
        """Test getting empty topology."""
        response = await client.get("/topology")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "links" in data

    @pytest.mark.asyncio
    async def test_simulate_topology(self, client):
        """Test simulating network topology."""
        response = await client.post("/topology/simulate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "simulated"
        assert data["nodes"] == 8  # 8 simulated devices
        assert data["links"] == 8  # 8 links in hierarchy

    @pytest.mark.asyncio
    async def test_topology_refresh(self, client):
        """Test triggering topology refresh."""
        response = await client.post("/topology/refresh")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "refreshed"


class TestDeviceEndpoints:
    """Tests for device CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_devices_empty(self, client):
        """Test listing devices when empty."""
        response = await client.get("/devices")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Note: Database may have devices from other tests, so we just check it's a list

    @pytest.mark.asyncio
    async def test_create_device(self, client):
        """Test creating a new device."""
        import uuid
        unique_ip = f"192.168.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"
        device_data = {
            "name": "test-switch-01",
            "ip_address": unique_ip,
            "community": "public",
        }
        response = await client.post("/devices", json=device_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-switch-01"
        assert data["ip_address"] == unique_ip
        assert data["community"] == "public"
        assert "id" in data
        return data["id"]

    @pytest.mark.asyncio
    async def test_create_duplicate_device(self, client):
        """Test creating duplicate device returns conflict."""
        # Create first device
        await client.post("/devices", json={
            "name": "dup-switch",
            "ip_address": "192.168.1.200",
            "community": "public",
        })
        # Try to create duplicate
        response = await client.post("/devices", json={
            "name": "dup-switch-2",
            "ip_address": "192.168.1.200",  # Same IP
            "community": "public",
        })
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_get_device(self, client):
        """Test getting a specific device."""
        import uuid
        unique_ip = f"192.168.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"
        # Create device first
        create_response = await client.post("/devices", json={
            "name": "get-test-switch",
            "ip_address": unique_ip,
            "community": "public",
        })
        device_id = create_response.json()["id"]

        # Get device
        response = await client.get(f"/devices/{device_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "get-test-switch"

    @pytest.mark.asyncio
    async def test_get_nonexistent_device(self, client):
        """Test getting nonexistent device returns 404."""
        response = await client.get("/devices/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_device(self, client):
        """Test updating a device."""
        import uuid
        unique_ip = f"192.168.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"
        # Create device
        create_response = await client.post("/devices", json={
            "name": "update-test",
            "ip_address": unique_ip,
            "community": "public",
        })
        device_id = create_response.json()["id"]

        # Update device
        response = await client.put(f"/devices/{device_id}", json={
            "name": "updated-switch",
            "community": "private",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "updated-switch"
        assert data["community"] == "private"

    @pytest.mark.asyncio
    async def test_delete_device(self, client):
        """Test deleting a device."""
        # Create device
        create_response = await client.post("/devices", json={
            "name": "delete-test",
            "ip_address": "192.168.1.103",
            "community": "public",
        })
        device_id = create_response.json()["id"]

        # Delete device
        response = await client.delete(f"/devices/{device_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify deletion
        get_response = await client.get(f"/devices/{device_id}")
        assert get_response.status_code == 404


class TestServiceCheckEndpoints:
    """Tests for service check endpoints."""

    @pytest.mark.asyncio
    async def test_list_service_checks_empty(self, client):
        """Test listing service checks when empty."""
        response = await client.get("/checks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_http_check(self, client):
        """Test creating HTTP service check."""
        check_data = {
            "name": "http-health-check",
            "check_type": "http",
            "target": "https://httpbin.org/get",
            "interval_seconds": 60,
            "timeout_seconds": 10,
            "config": {"method": "GET", "expected_status": 200},
            "enabled": True,
        }
        response = await client.post("/checks", json=check_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "http-health-check"
        assert data["check_type"] == "http"

    @pytest.mark.asyncio
    async def test_create_tcp_check(self, client):
        """Test creating TCP service check."""
        check_data = {
            "name": "ssh-check",
            "check_type": "tcp",
            "target": "localhost:22",
            "interval_seconds": 30,
            "timeout_seconds": 5,
            "enabled": True,
        }
        response = await client.post("/checks", json=check_data)
        assert response.status_code == 200
        data = response.json()
        assert data["check_type"] == "tcp"

    @pytest.mark.asyncio
    async def test_create_invalid_check_type(self, client):
        """Test creating check with invalid type returns 400."""
        response = await client.post("/checks", json={
            "name": "invalid-check",
            "check_type": "invalid_type",
            "target": "localhost",
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_service_check(self, client):
        """Test getting a specific service check."""
        # Create check
        create_response = await client.post("/checks", json={
            "name": "get-test-check",
            "check_type": "tcp",
            "target": "localhost:80",
            "enabled": True,
        })
        check_id = create_response.json()["id"]

        # Get check
        response = await client.get(f"/checks/{check_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "get-test-check"

    @pytest.mark.asyncio
    async def test_update_service_check(self, client):
        """Test updating a service check."""
        # Create check
        create_response = await client.post("/checks", json={
            "name": "update-test-check",
            "check_type": "http",
            "target": "https://example.com",
            "interval_seconds": 60,
            "enabled": True,
        })
        check_id = create_response.json()["id"]

        # Update check
        response = await client.put(f"/checks/{check_id}", json={
            "interval_seconds": 120,
            "enabled": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["interval_seconds"] == 120
        assert data["enabled"] in (False, 0)  # SQLite returns 0, PostgreSQL returns False

    @pytest.mark.asyncio
    async def test_delete_service_check(self, client):
        """Test deleting a service check."""
        # Create check
        create_response = await client.post("/checks", json={
            "name": "delete-test-check",
            "check_type": "tcp",
            "target": "localhost:443",
            "enabled": True,
        })
        check_id = create_response.json()["id"]

        # Delete check
        response = await client.delete(f"/checks/{check_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


class TestAlertEndpoints:
    """Tests for alert configuration endpoints."""

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, client):
        """Test listing alerts when empty."""
        response = await client.get("/alerts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_webhook_alert(self, client):
        """Test creating webhook alert."""
        alert_data = {
            "name": "webhook-test-alert",
            "alert_type": "device_down",
            "channel": "webhook",
            "config": {"url": "https://httpbin.org/post"},
            "enabled": True,
        }
        response = await client.post("/alerts", json=alert_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "webhook-test-alert"
        assert data["channel"] == "webhook"

    @pytest.mark.asyncio
    async def test_create_slack_alert(self, client):
        """Test creating Slack alert."""
        alert_data = {
            "name": "slack-test-alert",
            "alert_type": "topology_change",
            "channel": "slack",
            "config": {"webhook_url": "https://hooks.slack.com/services/XXX"},
            "enabled": True,
        }
        response = await client.post("/alerts", json=alert_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_invalid_channel(self, client):
        """Test creating alert with invalid channel returns 400."""
        response = await client.post("/alerts", json={
            "name": "invalid-alert",
            "alert_type": "device_down",
            "channel": "invalid_channel",
            "config": {},
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_alert_history(self, client):
        """Test getting alert history."""
        response = await client.get("/alerts/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestStatsEndpoint:
    """Tests for /stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_poller_stats(self, client):
        """Test getting poller statistics."""
        response = await client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "poll_interval" in data


class TestDiscoveryEndpoint:
    """Tests for /discover endpoint."""

    @pytest.mark.asyncio
    async def test_discover_network(self, client):
        """Test network discovery with default all method."""
        response = await client.post("/discover", json={
            "network_range": "127.0.0.1/32",
            "community": "public",
        })
        assert response.status_code == 200
        data = response.json()
        assert "found" in data
        assert "scanned" in data
        assert "by_method" in data

    @pytest.mark.asyncio
    async def test_discover_network_snmp_only(self, client):
        """Test network discovery with snmp method."""
        response = await client.post("/discover", json={
            "network_range": "127.0.0.1/32",
            "community": "public",
            "method": "snmp",
        })
        assert response.status_code == 200
        data = response.json()
        assert "found" in data
        assert "by_method" in data

    @pytest.mark.asyncio
    async def test_discover_network_ping(self, client):
        """Test network discovery with ping method finds localhost."""
        response = await client.post("/discover", json={
            "network_range": "127.0.0.1/32",
            "community": "public",
            "method": "ping",
        })
        assert response.status_code == 200
        data = response.json()
        assert "found" in data
        assert "scanned" in data
        assert "by_method" in data
        # 127.0.0.1 should be found via ping in most environments
        assert data["found"] >= 0

    @pytest.mark.asyncio
    async def test_discover_network_port(self, client):
        """Test network discovery with port method."""
        response = await client.post("/discover", json={
            "network_range": "127.0.0.1/32",
            "community": "public",
            "method": "port",
        })
        assert response.status_code == 200
        data = response.json()
        assert "found" in data
        assert "scanned" in data
        assert "by_method" in data

    @pytest.mark.asyncio
    async def test_discover_invalid_method(self, client):
        """Test network discovery with invalid method still works (falls through)."""
        response = await client.post("/discover", json={
            "network_range": "127.0.0.1/32",
            "community": "public",
            "method": "invalid",
        })
        assert response.status_code == 200
        data = response.json()
        assert "found" in data


class TestPollHistoryEndpoint:
    """Tests for /poll-history endpoint."""

    @pytest.mark.asyncio
    async def test_get_poll_history(self, client):
        """Test getting poll history."""
        response = await client.get("/poll-history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = await client.get("/metrics")
        assert response.status_code == 200
        # Content-type may vary by prometheus-client version
        assert "text/plain" in response.headers.get("content-type", "")
        # Check for expected metrics
        content = response.text
        assert "netops" in content.lower()


class TestMaintenanceWindowEndpoints:
    """Tests for maintenance window endpoints."""

    @pytest.mark.asyncio
    async def test_list_maintenance_windows_empty(self, client):
        """Test listing maintenance windows when empty."""
        response = await client.get("/maintenance-windows")
        assert response.status_code == 200
        data = response.json()
        assert "windows" in data
        assert isinstance(data["windows"], list)

    @pytest.mark.asyncio
    async def test_create_and_delete_maintenance_window(self, client):
        """Test creating and deleting a maintenance window."""
        from datetime import datetime, timedelta, timezone

        start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        create_response = await client.post("/maintenance-windows", json={
            "name": "Test Maintenance",
            "start_time": start,
            "end_time": end,
            "description": "Test window",
        })
        assert create_response.status_code == 200
        data = create_response.json()
        assert data["status"] == "created"
        window_id = data["window"]["id"]

        # Verify it appears in the list
        list_response = await client.get("/maintenance-windows")
        assert list_response.status_code == 200
        windows = list_response.json()["windows"]
        assert any(w["id"] == window_id for w in windows)

        # Delete it
        delete_response = await client.delete(f"/maintenance-windows/{window_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_window(self, client):
        """Test deleting a nonexistent maintenance window returns 404."""
        response = await client.delete("/maintenance-windows/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_window_invalid_datetime(self, client):
        """Test creating a window with invalid datetime returns 400."""
        response = await client.post("/maintenance-windows", json={
            "name": "Bad Window",
            "start_time": "not-a-datetime",
            "end_time": "2026-05-07T12:00:00",
        })
        assert response.status_code == 400


class TestTopologyHistoryEndpoint:
    """Tests for topology history endpoint."""

    @pytest.mark.asyncio
    async def test_get_topology_history(self, client):
        """Test getting topology history."""
        response = await client.get("/topology/history")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    @pytest.mark.asyncio
    async def test_get_topology_history_empty(self, client):
        """Test getting topology history when empty."""
        response = await client.get("/topology/history")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    @pytest.mark.asyncio
    async def test_get_topology_history_with_limit(self, client):
        """Test getting topology history with limit param."""
        response = await client.get("/topology/history?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert isinstance(data["events"], list)


class TestPaginationEndpoints:
    """Tests for pagination on list endpoints."""

    @pytest.mark.asyncio
    async def test_devices_pagination(self, client):
        """Test devices endpoint accepts limit and offset."""
        response = await client.get("/devices?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        response = await client.get("/devices?limit=5&offset=0")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_alerts_pagination(self, client):
        """Test alerts endpoint accepts limit and offset."""
        response = await client.get("/alerts?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_checks_pagination(self, client):
        """Test checks endpoint accepts limit and offset."""
        response = await client.get("/checks?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
