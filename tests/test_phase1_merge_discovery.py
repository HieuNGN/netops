"""Tests for Phase 1 rescan_and_merge discovery."""

import os
import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from src.collector import discovery


@pytest_asyncio.fixture
async def db_with_devices(migrated_sqlite_db):
    """Seed a few devices in different states."""
    db = migrated_sqlite_db
    # 3 devices: one manual (preserve), one auto online, one auto offline
    await db.create_device({
        "ip_address": "10.0.0.1", "name": "manual-host",
        "discovery_method": "manual", "status": "online",
    })
    await db.create_device({
        "ip_address": "10.0.0.2", "name": "auto-online",
        "discovery_method": "auto", "status": "online",
    })
    await db.create_device({
        "ip_address": "10.0.0.3", "name": "auto-offline",
        "discovery_method": "auto", "status": "offline",
        "offline_since": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
    })
    return db


def test_rescan_and_merge_signature(migrated_sqlite_db):
    """The function exists, has the expected signature, and is async."""
    import inspect
    sig = inspect.signature(discovery.rescan_and_merge)
    assert "db_client" in sig.parameters
    assert "network_range" in sig.parameters
    assert "preserve_manual" in sig.parameters
    assert "stale_event_emitter" in sig.parameters
    assert "method" in sig.parameters
    assert inspect.iscoroutinefunction(discovery.rescan_and_merge)


@pytest.mark.asyncio
async def test_rescan_and_merge_preserves_manual(db_with_devices, monkeypatch):
    """Manual devices are never touched by merge, even if not in the probe set."""
    db = db_with_devices

    # Stub discover_devices to return only 10.0.0.2 (auto-online).
    # Manual 10.0.0.1 should be preserved.
    async def fake_discover(*args, **kwargs):
        return [{
            "ip_address": "10.0.0.2",
            "sys_descr": "updated",
            "discovery_method": "snmp",
            "open_ports": [],
        }]
    monkeypatch.setattr(discovery, "discover_devices", fake_discover)

    stale_events = []

    async def fake_emitter(payload):
        stale_events.append(payload)

    stats = await discovery.rescan_and_merge(
        db, "10.0.0.0/24",
        preserve_manual=True,
        stale_event_emitter=fake_emitter,
    )

    # Manual preserved
    assert stats["preserved"] == 1
    # Auto online updated (now "found" again, status online)
    devs = await db.list_devices()
    by_ip = {d["ip_address"]: d for d in devs}
    assert by_ip["10.0.0.1"]["discovery_method"] == "manual"
    assert by_ip["10.0.0.2"]["sys_descr"] == "updated"
    assert by_ip["10.0.0.3"]["status"] == "offline"
    assert stats["stale"] == 0
    assert stale_events == []


@pytest.mark.asyncio
async def test_rescan_and_merge_marks_missing_offline(db_with_devices, monkeypatch):
    """An auto/online device not in the probe set is marked offline.

    The original fixture's 10.0.0.3 is already offline, so a naive
    test would pass trivially. We mutate 10.0.0.2 to online/auto and
    then probe only 10.0.0.3 — proving 10.0.0.2 actually flips offline.
    """
    db = db_with_devices
    # Put 10.0.0.2 (originally online/auto) into a known online state.
    dev2 = next(d for d in await db.list_devices() if d["ip_address"] == "10.0.0.2")
    await db.update_device(dev2["id"], {"status": "online", "offline_since": None})

    async def fake_discover(*args, **kwargs):
        return [{
            "ip_address": "10.0.0.3",  # 10.0.0.2 is now missing
            "sys_descr": "still here",
            "discovery_method": "snmp",
            "open_ports": [],
        }]
    monkeypatch.setattr(discovery, "discover_devices", fake_discover)

    stats = await discovery.rescan_and_merge(db, "10.0.0.0/24")

    devs = await db.list_devices()
    by_ip = {d["ip_address"]: d for d in devs}
    # 10.0.0.2 should have been flipped to offline by the merge.
    assert by_ip["10.0.0.2"]["status"] == "offline"
    assert by_ip["10.0.0.2"]["offline_since"] is not None
    assert stats["marked_offline"] == 1
    # 10.0.0.3 was probed this round → online.
    assert by_ip["10.0.0.3"]["status"] == "online"


@pytest.mark.asyncio
async def test_rescan_and_merge_emits_stale_event(db_with_devices, monkeypatch):
    """A device offline >= 72h triggers a device_stale event."""
    db = db_with_devices
    # Mark 10.0.0.3 as offline 73h ago
    devs = await db.list_devices()
    target = next(d for d in devs if d["ip_address"] == "10.0.0.3")
    long_ago = (datetime.utcnow() - timedelta(hours=73)).isoformat()
    await db.update_device(target["id"], {"offline_since": long_ago})

    async def fake_discover(*args, **kwargs):
        return [{
            "ip_address": "10.0.0.2",
            "sys_descr": "x",
            "discovery_method": "snmp",
            "open_ports": [],
        }]
    monkeypatch.setattr(discovery, "discover_devices", fake_discover)

    stale_events = []

    async def fake_emitter(payload):
        stale_events.append(payload)

    stats = await discovery.rescan_and_merge(
        db, "10.0.0.0/24",
        stale_event_emitter=fake_emitter,
    )

    assert stats["stale"] == 1
    assert len(stale_events) == 1
    assert stale_events[0]["ip_address"] == "10.0.0.3"
    assert stale_events[0]["offline_hours"] >= 72


@pytest.mark.asyncio
async def test_rescan_and_merge_adds_new_device(db_with_devices, monkeypatch):
    """An IP returned by the probe but not in the DB gets created."""
    db = db_with_devices

    async def fake_discover(*args, **kwargs):
        return [
            {
                "ip_address": "10.0.0.99",  # new IP not in DB
                "sys_descr": "newly discovered",
                "discovery_method": "snmp",
                "open_ports": [],
            },
        ]
    monkeypatch.setattr(discovery, "discover_devices", fake_discover)

    stats = await discovery.rescan_and_merge(db, "10.0.0.0/24")

    assert stats["added"] == 1
    dev = await db.get_device("10.0.0.99")
    assert dev is not None
    assert dev["status"] == "online"
    assert dev["sys_descr"] == "newly discovered"


def test_environment_profile_config():
    """Phase 1: EnvironmentProfile + detect_profile work as locked."""
    from src.collector.config import (
        EnvironmentProfile, detect_profile, ENVIRONMENT_PROFILES,
    )
    # 5 devices => homelab
    assert detect_profile(5) == EnvironmentProfile.HOMELAB
    # 15 devices => boundary, still homelab
    assert detect_profile(15) == EnvironmentProfile.HOMELAB
    # 16 devices => small_business
    assert detect_profile(16) == EnvironmentProfile.SMALL_BUSINESS
    # 80 devices => boundary, still small_business
    assert detect_profile(80) == EnvironmentProfile.SMALL_BUSINESS
    # 150 devices => datacenter
    assert detect_profile(150) == EnvironmentProfile.DATACENTER

    # SSL default is 24h for all profiles (locked spec)
    for p in EnvironmentProfile:
        assert ENVIRONMENT_PROFILES[p]["check_intervals"]["ssl"] == 86400

    # NetOpsConfig.from_profile populates all fields
    from src.collector.config import NetOpsConfig
    cfg = NetOpsConfig.from_profile(EnvironmentProfile.DATACENTER)
    assert cfg.profile == EnvironmentProfile.DATACENTER
    assert cfg.topology_interval == 60
    assert cfg.poll_history_retention_days == 30


def test_default_check_intervals():
    """Phase 2: DEFAULT_CHECK_INTERVALS per type."""
    from src.collector.checks.base import DEFAULT_CHECK_INTERVALS, default_interval_for
    assert DEFAULT_CHECK_INTERVALS["ssl"] == 86400  # 24h
    assert DEFAULT_CHECK_INTERVALS["ping"] == 60
    assert DEFAULT_CHECK_INTERVALS["http"] == 60
    assert DEFAULT_CHECK_INTERVALS["tcp"] == 60
    assert DEFAULT_CHECK_INTERVALS["dns"] == 300
    # Unknown type falls back to 60s
    assert default_interval_for("unknown") == 60
