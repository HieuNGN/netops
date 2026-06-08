"""Tests for host_state + network_watcher."""

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collector.host_state import (
    compute_fingerprint,
    get_host_state,
    set_host_state,
    detect_and_compare,
)
from src.collector.network_watcher import NetworkWatcher


def test_compute_fingerprint_stable():
    a = compute_fingerprint("192.168.1.0/24", "192.168.1.1")
    b = compute_fingerprint("192.168.1.0/24", "192.168.1.1")
    assert a == b
    assert isinstance(a, str)
    assert len(a) == 16


def test_compute_fingerprint_changes_with_cidr():
    a = compute_fingerprint("192.168.1.0/24", "192.168.1.1")
    b = compute_fingerprint("192.168.2.0/24", "192.168.1.1")
    assert a != b


def test_compute_fingerprint_changes_with_gateway():
    a = compute_fingerprint("192.168.1.0/24", "192.168.1.1")
    b = compute_fingerprint("192.168.1.0/24", "192.168.1.254")
    assert a != b


def test_compute_fingerprint_no_cidr():
    assert compute_fingerprint(None, None) is None
    assert compute_fingerprint("", None) is None


@pytest.mark.asyncio
async def test_get_host_state_empty():
    db = MagicMock()
    db.get_setting = AsyncMock(return_value=None)
    out = await get_host_state(db)
    assert out == {
        "host_cidr": None,
        "host_gateway": None,
        "host_fingerprint": None,
        "host_last_seen": None,
    }


@pytest.mark.asyncio
async def test_set_host_state_writes_keys():
    db = MagicMock()
    db.set_setting = AsyncMock()
    fp = await set_host_state(db, "10.0.0.0/24", "10.0.0.1")
    assert isinstance(fp, str) and len(fp) == 16
    written_keys = {c.args[0] for c in db.set_setting.call_args_list}
    assert "host_cidr" in written_keys
    assert "host_gateway" in written_keys
    assert "host_fingerprint" in written_keys
    assert "host_last_seen" in written_keys


@pytest.mark.asyncio
async def test_detect_and_compare_first_seen():
    db = MagicMock()
    db.get_setting = AsyncMock(return_value=None)
    with patch(
        "src.collector.host_state.detect_host_network",
        AsyncMock(return_value={
            "host_ip": "10.0.0.5",
            "cidr": "10.0.0.0/24",
            "hostname": "h",
            "gateway": "10.0.0.1",
            "interface": "eth0",
        }),
    ):
        snap = await detect_and_compare(db)
    assert snap["first_seen"] is True
    assert snap["changed"] is False
    assert snap["fingerprint"] is not None
    assert snap["detected"]["cidr"] == "10.0.0.0/24"


@pytest.mark.asyncio
async def test_detect_and_compare_changed():
    db = MagicMock()

    async def _gs(key, default=None):
        if key == "host_fingerprint":
            return "oldfingerprint0"
        if key == "host_cidr":
            return "192.168.1.0/24"
        return default

    db.get_setting = AsyncMock(side_effect=_gs)
    with patch(
        "src.collector.host_state.detect_host_network",
        AsyncMock(return_value={
            "host_ip": "10.0.0.5",
            "cidr": "10.0.0.0/24",
            "hostname": "h",
            "gateway": "10.0.0.1",
            "interface": "eth0",
        }),
    ):
        snap = await detect_and_compare(db)
    assert snap["changed"] is True
    assert snap["first_seen"] is False


@pytest.mark.asyncio
async def test_detect_and_compare_unchanged():
    db = MagicMock()
    fp = compute_fingerprint("10.0.0.0/24", "10.0.0.1")

    async def _gs(key, default=None):
        if key == "host_fingerprint":
            return fp
        return default

    db.get_setting = AsyncMock(side_effect=_gs)
    with patch(
        "src.collector.host_state.detect_host_network",
        AsyncMock(return_value={
            "host_ip": "10.0.0.5",
            "cidr": "10.0.0.0/24",
            "hostname": "h",
            "gateway": "10.0.0.1",
            "interface": "eth0",
        }),
    ):
        snap = await detect_and_compare(db)
    assert snap["changed"] is False
    assert snap["first_seen"] is False


@pytest.mark.asyncio
async def test_watcher_initial_no_change():
    db = MagicMock()
    db.get_setting = AsyncMock(return_value=None)
    handler = AsyncMock()
    w = NetworkWatcher(db, handler, interval_seconds=0)
    with patch(
        "src.collector.network_watcher.detect_and_compare",
        AsyncMock(return_value={
            "detected": {
                "host_ip": "10.0.0.5", "cidr": "10.0.0.0/24",
                "hostname": "h", "gateway": "10.0.0.1", "interface": "eth0",
            },
            "previous": {},
            "fingerprint": "abc123",
            "changed": False,
            "first_seen": True,
        }),
    ):
        snap = await w.check_once()
    assert snap is None
    assert w._last_fingerprint == "abc123"
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_watcher_emits_on_subsequent_change():
    db = MagicMock()
    db.get_setting = AsyncMock(return_value=None)
    db.set_setting = AsyncMock()
    handler = AsyncMock()
    w = NetworkWatcher(db, handler, interval_seconds=0)
    w._last_fingerprint = "oldfingerprint0"
    with patch(
        "src.collector.network_watcher.detect_and_compare",
        AsyncMock(return_value={
            "detected": {
                "host_ip": "10.0.0.5", "cidr": "10.0.0.0/24",
                "hostname": "h", "gateway": "10.0.0.1", "interface": "eth0",
            },
            "previous": {"host_cidr": "192.168.1.0/24", "host_gateway": "192.168.1.1"},
            "fingerprint": "newfingerprint",
            "changed": True,
            "first_seen": False,
        }),
    ):
        snap = await w.check_once()
    assert snap is not None
    handler.assert_awaited_once()
    assert db.set_setting.await_count >= 4
