"""Tests for alert dispatch gating: no external send until a working channel exists.

Active alerts (in-memory) continue to populate so the on-site UI still works.
Alert history is cleared once when the last working channel disappears.
"""

import pytest
from unittest.mock import AsyncMock

from src.api.services.alert_service import AlertService
from src.api.services.notifications.base import NotificationMessage


class MockDB:
    """Minimal async mock that supports the DB methods AlertService needs."""

    def __init__(self):
        self.list_alert_configs = AsyncMock(return_value=[])
        self.clear_alert_history = AsyncMock(return_value=0)
        self.record_alert_history = AsyncMock()
        self.is_in_maintenance_window = AsyncMock(return_value=False)
        self.get_integration = AsyncMock(return_value=None)

    def with_configs(self, configs: list):
        self.list_alert_configs.return_value = configs
        return self


@pytest.fixture
def service():
    return AlertService(MockDB())


@pytest.mark.asyncio
async def test_no_working_channel_skips_dispatch_and_clears_history():
    """Empty/invalid config → dispatch skipped, history cleared once."""
    db = MockDB().with_configs([
        {
            "id": "cfg-1",
            "name": "No-op webhook",
            "alert_type": "device_down",
            "channel": "webhook",
            "config_json": {},
            "enabled": True,
            "integration_id": None,
        },
    ])
    svc = AlertService(db)

    stats = await svc.dispatch_alerts([
        {"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"},
    ])

    assert stats["skipped"] == 1
    assert stats["sent"] == 0
    assert stats["failed"] == 0
    assert db.clear_alert_history.await_count == 1
    assert db.record_alert_history.await_count == 0


@pytest.mark.asyncio
async def test_working_channel_dispatches_normally():
    """Valid webhook config → alert sent, history recorded."""
    db = MockDB().with_configs([
        {
            "id": "cfg-2",
            "name": "Working webhook",
            "alert_type": "device_down",
            "channel": "webhook",
            "config_json": {"url": "https://httpbin.org/post"},
            "enabled": True,
            "integration_id": None,
        },
    ])
    svc = AlertService(db)

    stats = await svc.dispatch_alerts([
        {"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"},
    ])

    assert stats["skipped"] == 0
    assert stats["sent"] == 1
    assert stats["failed"] == 0
    assert db.clear_alert_history.await_count == 0
    assert db.record_alert_history.await_count == 1


@pytest.mark.asyncio
async def test_history_cleared_once_then_gate_stays_up():
    """History is cleared once; subsequent dispatches don't re-clear."""
    db = MockDB().with_configs([
        {
            "id": "cfg-3",
            "name": "Bad token",
            "alert_type": "device_down",
            "channel": "telegram",
            "config_json": {},
            "enabled": True,
            "integration_id": None,
        },
    ])
    svc = AlertService(db)

    # First dispatch — should clear
    await svc.dispatch_alerts([{"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"}])
    assert db.clear_alert_history.await_count == 1

    # Second dispatch — gate already up, no re-clear
    await svc.dispatch_alerts([{"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"}])
    assert db.clear_alert_history.await_count == 1


@pytest.mark.asyncio
async def test_history_gate_resets_when_channel_restored():
    """After adding a valid config, the purge gate resets and history records again."""
    db = MockDB().with_configs([
        {
            "id": "cfg-4",
            "name": "Broken",
            "alert_type": "device_down",
            "channel": "webhook",
            "config_json": {},
            "enabled": True,
            "integration_id": None,
        },
    ])
    svc = AlertService(db)

    # Broken → clear
    await svc.dispatch_alerts([{"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"}])
    assert db.clear_alert_history.await_count == 1

    # Fix the config
    db.with_configs([
        {
            "id": "cfg-5",
            "name": "Working",
            "alert_type": "device_down",
            "channel": "webhook",
            "config_json": {"url": "https://httpbin.org/post"},
            "enabled": True,
            "integration_id": None,
        },
    ])

    # Should dispatch normally
    stats = await svc.dispatch_alerts([{"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"}])
    assert stats["sent"] == 1
    assert db.record_alert_history.await_count == 1

    # Break again
    db.with_configs([
        {
            "id": "cfg-6",
            "name": "Broken again",
            "alert_type": "device_down",
            "channel": "webhook",
            "config_json": {},
            "enabled": True,
            "integration_id": None,
        },
    ])
    await svc.dispatch_alerts([{"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"}])
    assert db.clear_alert_history.await_count == 2  # re-cleared after gate reset


@pytest.mark.asyncio
async def test_active_alerts_still_populate_when_no_working_channel():
    """on_topology_change still fills _active_alerts even when dispatch is gated."""
    db = MockDB().with_configs([])
    svc = AlertService(db)

    # First call: n1 online — primes cache, no alert
    await svc.on_topology_change(
        changes={"nodes_removed": 0, "nodes_added": 0, "links_removed": 0, "links_added": 0},
        topology={
            "nodes": [
                {"id": "n1", "status": "online"},
                {"id": "n2", "status": "online"},
            ],
            "links": [],
        },
    )
    assert svc.get_active_alerts() == []

    # Second call: n1 goes offline — alert fires in-memory, but dispatch gated
    await svc.on_topology_change(
        changes={"nodes_removed": 0, "nodes_added": 0, "links_removed": 0, "links_added": 0},
        topology={
            "nodes": [
                {"id": "n1", "status": "offline"},
                {"id": "n2", "status": "online"},
            ],
            "links": [],
        },
    )

    active = svc.get_active_alerts()
    assert len(active) == 1
    assert active[0]["alert_type"] == "device_down"
    assert active[0]["target_id"] == "n1"
    # No external dispatch attempted → no history recorded
    assert db.record_alert_history.await_count == 0


@pytest.mark.asyncio
async def test_disabled_configs_are_ignored_for_channel_check():
    """Disabled configs don't count as a working channel."""
    db = MockDB().with_configs([
        {
            "id": "cfg-7",
            "name": "Disabled but valid",
            "alert_type": "device_down",
            "channel": "webhook",
            "config_json": {"url": "https://httpbin.org/post"},
            "enabled": False,
            "integration_id": None,
        },
    ])
    svc = AlertService(db)

    stats = await svc.dispatch_alerts([{"alert_type": "device_down", "severity": "critical", "title": "T", "message": "M"}])
    assert stats["skipped"] == 1
    assert db.clear_alert_history.await_count == 1
