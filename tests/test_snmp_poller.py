"""Unit tests for SNMPPoller."""

import asyncio
import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, patch

from src.collector.snmp_poller import SNMPPoller, PollResult, PollStats


class TestPollStats:
    def test_initial_state(self):
        stats = PollStats()
        assert stats.total_polls == 0
        assert stats.successful_polls == 0
        assert stats.failed_polls == 0
        assert stats.avg_response_time_ms == 0
        assert stats._response_times == []

    def test_add_response_time(self):
        stats = PollStats()
        stats.add_response_time(100.0)
        assert stats.avg_response_time_ms == 100.0
        stats.add_response_time(200.0)
        assert stats.avg_response_time_ms == 150.0

    def test_rolling_average_limit(self):
        stats = PollStats()
        for i in range(105):
            stats.add_response_time(float(i))
        assert len(stats._response_times) == 100
        assert stats.avg_response_time_ms == 54.5


class TestSNMPPoller:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.list_devices.return_value = []
        db.upsert_topology.return_value = {
            "nodes_added": 0, "nodes_removed": 0,
            "links_added": 0, "links_removed": 0,
        }
        return db

    @pytest.fixture
    def poller(self, mock_db):
        return SNMPPoller(mock_db, poll_interval=1)

    @pytest.mark.asyncio
    async def test_initial_state(self, poller):
        assert poller._running is False
        assert poller.stats.total_polls == 0
        assert poller._on_topology_change is None

    @pytest.mark.asyncio
    async def test_set_topology_change_handler(self, poller):
        handler = AsyncMock()
        poller.set_topology_change_handler(handler)
        assert poller._on_topology_change == handler

    @pytest.mark.asyncio
    async def test_start_stop(self, poller):
        await poller.start()
        assert poller._running is True
        assert poller._task is not None
        await poller.stop()
        assert poller._running is False
        assert poller._task is None

    @pytest.mark.asyncio
    async def test_poll_empty_devices(self, poller, mock_db):
        await poller._poll_all_devices()
        mock_db.list_devices.assert_called_once()
        mock_db.upsert_topology.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_device_success(self, poller, mock_db):
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()

        assert poller.stats.total_polls == 1
        assert poller.stats.successful_polls == 1
        assert poller.stats.failed_polls == 0
        mock_db.update_device.assert_called_with(
            "dev1",
            {"status": "online", "sys_descr": "Cisco IOS", "last_polled": ANY, "offline_since": None},
        )

    @pytest.mark.asyncio
    async def test_poll_device_failure(self, poller, mock_db):
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        with patch("src.collector.snmp_poller.get_sys_descr_async", side_effect=TimeoutError("No response")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", side_effect=TimeoutError("No response")):
                await poller._poll_all_devices()

        assert poller.stats.total_polls == 1
        assert poller.stats.successful_polls == 0
        assert poller.stats.failed_polls == 1
        call = mock_db.update_device.call_args
        assert call[0][0] == "dev1"
        assert call[0][1]["status"] == "offline"
        assert "offline_since" in call[0][1]
        assert call[0][1]["offline_since"] is not None

    @pytest.mark.asyncio
    async def test_status_change_handler_invoked(self, poller, mock_db):
        handler = AsyncMock()
        poller.set_status_change_handler(handler)
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()
        handler.assert_called_once()
        evt = handler.call_args[0][0]
        assert evt["device_id"] == "dev1"
        assert evt["new_status"] == "online"
        assert evt["old_status"] is None

    @pytest.mark.asyncio
    async def test_status_change_handler_no_emit_on_repeat(self, poller, mock_db):
        handler = AsyncMock()
        poller.set_status_change_handler(handler)
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()
                await poller._poll_all_devices()
        assert handler.call_count == 1

    @pytest.mark.asyncio
    async def test_poller_survives_add_poll_result_failure(self, poller, mock_db):
        """If add_poll_result raises, the poller must not crash the loop."""
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"},
            {"id": "dev2", "ip_address": "192.168.1.2", "name": "Router-2", "community": "public"},
        ]
        mock_db.add_poll_result = AsyncMock(side_effect=RuntimeError("DB locked"))
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()
        assert poller.stats.total_polls == 2
        assert poller.stats.successful_polls == 2

    @pytest.mark.asyncio
    async def test_poller_survives_upsert_topology_failure(self, poller, mock_db):
        """If upsert_topology raises, the poller must not crash the loop."""
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        mock_db.upsert_topology = AsyncMock(side_effect=RuntimeError("DB locked"))
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()
        assert poller.stats.total_polls == 1
        assert poller.stats.successful_polls == 1

    @pytest.mark.asyncio
    async def test_topology_change_detection(self, poller, mock_db):
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        mock_db.upsert_topology.return_value = {"nodes_added": 1, "nodes_removed": 0, "links_added": 0, "links_removed": 0}
        handler = AsyncMock()
        poller.set_topology_change_handler(handler)
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()

        handler.assert_called_once()
        call_args = handler.call_args[0]
        assert call_args[0]["nodes_added"] == 1

    @pytest.mark.asyncio
    async def test_handler_called_when_changes_exist(self, poller, mock_db):
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"},
            {"id": "dev2", "ip_address": "192.168.1.2", "name": "Router-2", "community": "public"},
        ]
        neighbors = [{"neighbor_name": "Router-2", "neighbor_port": "Gi0/1"}]
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=neighbors)):
                await poller._poll_all_devices()

        topology = poller._topology_builder.to_json()
        assert len(topology["links"]) == 1
        assert topology["links"][0]["source"] == "192.168.1.1"
        assert topology["links"][0]["target"] == "192.168.1.2"

    @pytest.mark.asyncio
    async def test_get_stats(self, poller, mock_db):
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                await poller._poll_all_devices()

        stats = poller.get_stats()
        assert stats["total_polls"] == 1
        assert stats["successful_polls"] == 1
        assert stats["failed_polls"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["running"] is False
        assert stats["poll_interval"] == 1

    @pytest.mark.asyncio
    async def test_poll_now(self, poller, mock_db):
        mock_db.list_devices.return_value = [
            {"id": "dev1", "ip_address": "192.168.1.1", "name": "Router-1", "community": "public"}
        ]
        with patch("src.collector.snmp_poller.get_sys_descr_async", AsyncMock(return_value="Cisco IOS")):
            with patch("src.collector.snmp_poller.walk_lldp_neighbors_async", AsyncMock(return_value=[])):
                results = await poller.poll_now()

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].sys_descr == "Cisco IOS"
