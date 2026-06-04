"""Unit tests for maintenance windows."""

import pytest
from datetime import datetime, timedelta


class TestMaintenanceWindows:
    """Tests for maintenance window API endpoints."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database client."""
        from unittest.mock import AsyncMock
        db = AsyncMock()
        db.list_maintenance_windows.return_value = []
        db.create_maintenance_window.side_effect = lambda data: {
            "id": "win1",
            **data,
        }
        db.delete_maintenance_window.return_value = True
        db.is_in_maintenance_window.return_value = False
        return db

    def test_is_window_active_logic(self):
        """Test the maintenance window active time check."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        past = (now - timedelta(hours=2)).isoformat()
        future = (now + timedelta(hours=2)).isoformat()

        # Window that spans now
        assert self._is_active(past, future) is True

        # Window entirely in past
        assert self._is_active(past, (now - timedelta(hours=1)).isoformat()) is False

        # Window entirely in future
        assert self._is_active((now + timedelta(hours=1)).isoformat(), future) is False

    def _is_active(self, start: str, end: str) -> bool:
        from datetime import timezone
        now = datetime.now(timezone.utc)
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        return now >= s and now <= e

    @pytest.mark.asyncio
    async def test_list_maintenance_windows(self, mock_db):
        """Test listing maintenance windows."""
        mock_db.list_maintenance_windows.return_value = [
            {
                "id": "win1",
                "name": "Scheduled Maintenance",
                "start_time": "2026-05-07T10:00:00",
                "end_time": "2026-05-07T12:00:00",
                "description": "Router upgrade",
                "created_at": "2026-05-07T08:00:00",
            }
        ]
        result = await mock_db.list_maintenance_windows()
        assert len(result) == 1
        assert result[0]["name"] == "Scheduled Maintenance"

    @pytest.mark.asyncio
    async def test_create_maintenance_window(self, mock_db):
        """Test creating a maintenance window."""
        data = {
            "name": "New Window",
            "start_time": "2026-05-08T02:00:00",
            "end_time": "2026-05-08T04:00:00",
            "description": "Firewall update",
        }
        result = await mock_db.create_maintenance_window(data)
        assert result["name"] == "New Window"
        assert result["start_time"] == "2026-05-08T02:00:00"

    @pytest.mark.asyncio
    async def test_delete_maintenance_window(self, mock_db):
        """Test deleting a maintenance window."""
        result = await mock_db.delete_maintenance_window("win1")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_in_maintenance_window(self, mock_db):
        """Test checking if currently in maintenance window."""
        mock_db.is_in_maintenance_window.return_value = True
        result = await mock_db.is_in_maintenance_window()
        assert result is True

    @pytest.mark.asyncio
    async def test_alert_dispatch_skips_during_maintenance(self, mock_db):
        """Test that alerts are suppressed during maintenance windows."""
        from src.api.services.alert_service import AlertService

        mock_db.is_in_maintenance_window.return_value = True
        mock_db.list_alert_configs.return_value = [
            {"id": "alert1", "alert_type": "device_down", "channel": "webhook", "config_json": {}}
        ]

        service = AlertService(mock_db)
        alerts = [{
            "alert_type": "device_down",
            "severity": "critical",
            "title": "Device Offline",
            "message": "Router down",
        }]

        stats = await service.dispatch_alerts(alerts)
        assert stats["skipped"] == 1
        assert stats["sent"] == 0
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_alert_dispatch_proceeds_outside_maintenance(self, mock_db):
        """Test that alerts dispatch normally outside maintenance windows."""
        from src.api.services.alert_service import AlertService
        from src.api.services.notifications.base import NotificationChannel, NotificationMessage

        mock_db.is_in_maintenance_window.return_value = False
        mock_db.list_alert_configs.return_value = [
            {"id": "alert1", "alert_type": "device_down", "channel": "webhook", "config_json": {"url": "http://example.com"}}
        ]

        # Create a mock notification channel that always succeeds
        class MockChannel(NotificationChannel):
            def validate_config(self):
                return True, ""
            async def send(self, message: NotificationMessage):
                return True

        service = AlertService(mock_db)

        async def _fake_channel(ch, cfg, **kwargs):
            return MockChannel(cfg)

        service.get_notification_channel = _fake_channel

        alerts = [{
            "alert_type": "device_down",
            "severity": "critical",
            "title": "Device Offline",
            "message": "Router down",
        }]

        stats = await service.dispatch_alerts(alerts)
        assert stats["skipped"] == 0
        assert stats["sent"] == 1
        assert stats["failed"] == 0
