"""Alert Service - Evaluates rules and dispatches notifications."""

import asyncio
from typing import Any, Optional

from .notifications.base import NotificationChannel, NotificationMessage
from .notifications.webhook import WebhookNotification
from .notifications.slack import SlackNotification
from .notifications.telegram import TelegramNotification
from .notifications.whatsapp import WhatsAppNotification
from .notifications.email import EmailNotification


class AlertService:
    """Service for evaluating alert rules and dispatching notifications."""

    def __init__(self, db_client: Any):
        self.db_client = db_client
        self._device_status_cache: dict[str, str] = {}  # device_id -> status
        self._link_status_cache: dict[str, str] = {}  # link_id -> status
        # Active alerts keyed by (alert_type, target_id) to prevent duplicates
        self._active_alerts: dict[str, dict[str, Any]] = {}

    def get_notification_channel(self, channel_type: str, config: dict[str, Any]) -> Optional[NotificationChannel]:
        """Factory method to create notification channel instances."""
        channels = {
            "webhook": WebhookNotification,
            "slack": SlackNotification,
            "telegram": TelegramNotification,
            "whatsapp": WhatsAppNotification,
            "email": EmailNotification,
        }

        channel_class = channels.get(channel_type.lower())
        if not channel_class:
            return None

        return channel_class(config)

    async def evaluate_topology_change(
        self,
        changes: dict[str, int],
        topology: dict[str, list],
        previous_device_statuses: dict[str, str],
        current_device_statuses: dict[str, str],
    ) -> list[dict[str, Any]]:
        """
        Evaluate topology changes and generate alerts.

        Returns list of triggered alerts.
        """
        alerts = []

        # Check for device status changes
        for device_id, current_status in current_device_statuses.items():
            previous_status = previous_device_statuses.get(device_id)

            if previous_status is None:
                # New device, no previous status
                continue

            if previous_status != current_status:
                if current_status == "offline":
                    alerts.append({
                        "alert_type": "device_down",
                        "severity": "critical",
                        "title": f"Device Offline",
                        "message": f"Device {device_id} is now offline",
                        "device_id": device_id,
                    })
                else:
                    alerts.append({
                        "alert_type": "device_up",
                        "severity": "info",
                        "title": f"Device Recovered",
                        "message": f"Device {device_id} is back online",
                        "device_id": device_id,
                    })

        # Check for topology changes (nodes/links added/removed)
        if changes.get("nodes_removed", 0) > 0:
            alerts.append({
                "alert_type": "topology_change",
                "severity": "warning",
                "title": "Topology Change Detected",
                "message": f"{changes['nodes_removed']} device(s) removed from topology",
                "changes": changes,
            })

        if changes.get("nodes_added", 0) > 0:
            alerts.append({
                "alert_type": "topology_change",
                "severity": "info",
                "title": "New Devices Discovered",
                "message": f"{changes['nodes_added']} new device(s) added to topology",
                "changes": changes,
            })

        if changes.get("links_removed", 0) > 0:
            alerts.append({
                "alert_type": "link_down",
                "severity": "warning",
                "title": "Link(s) Lost",
                "message": f"{changes['links_removed']} network link(s) removed",
                "changes": changes,
            })

        if changes.get("links_added", 0) > 0:
            alerts.append({
                "alert_type": "topology_change",
                "severity": "info",
                "title": "New Links Discovered",
                "message": f"{changes['links_added']} new network link(s) detected",
                "changes": changes,
            })

        return alerts

    async def dispatch_alerts(self, alerts: list[dict[str, Any]]) -> dict[str, int]:
        """
        Dispatch alerts to configured notification channels.

        Returns dispatch statistics.
        """
        stats = {"sent": 0, "failed": 0, "skipped": 0}

        # Get enabled alert configurations
        alert_configs = await self.db_client.list_alert_configs()

        if not alert_configs:
            stats["skipped"] = len(alerts)
            return stats

        for alert in alerts:
            for config in alert_configs:
                # Check if this alert type matches the config
                if config.get("alert_type") != alert.get("alert_type"):
                    continue

                # Create notification channel
                channel = self.get_notification_channel(
                    config.get("channel", "webhook"),
                    config.get("config_json", {}),
                )

                if not channel:
                    stats["failed"] += 1
                    continue

                # Validate channel config
                valid, error = channel.validate_config()
                if not valid:
                    stats["failed"] += 1
                    continue

                # Create notification message
                message = NotificationMessage(
                    title=alert.get("title", "NetOps Alert"),
                    message=alert.get("message", ""),
                    severity=alert.get("severity", "info"),
                    alert_type=alert.get("alert_type", ""),
                    metadata=alert,
                )

                # Send notification
                try:
                    if config.get("channel", "").lower() == "email":
                        # Email is synchronous
                        success = channel.send(message)
                    else:
                        success = await channel.send(message)

                    if success:
                        stats["sent"] += 1
                        # Record in alert history
                        await self._record_alert(config.get("id"), alert)
                    else:
                        stats["failed"] += 1
                except Exception:
                    stats["failed"] += 1

        return stats

    def get_active_alerts(self) -> list[dict[str, Any]]:
        """Return list of currently firing alerts."""
        return [
            {
                "key": key,
                "alert_type": alert["alert_type"],
                "target_id": alert["target_id"],
                "severity": alert["severity"],
                "title": alert["title"],
                "message": alert["message"],
                "status": alert["status"],
                "fired_at": alert["fired_at"],
            }
            for key, alert in self._active_alerts.items()
        ]

    def acknowledge_alert(self, alert_key: str) -> bool:
        """Acknowledge an active alert to suppress repeated notifications."""
        alert = self._active_alerts.get(alert_key)
        if alert and alert["status"] == "firing":
            alert["status"] = "acknowledged"
            return True
        return False

    def resolve_alert(self, alert_key: str) -> bool:
        """Manually resolve an active alert."""
        return self._active_alerts.pop(alert_key, None) is not None

    async def _record_alert(self, alert_config_id: str, alert: dict[str, Any]):
        """Record alert in history."""
        try:
            async with self.db_client._get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO alert_history (alert_config_id, message, status)
                    VALUES ($1, $2, 'triggered')
                    """,
                    alert_config_id, alert.get("message", ""),
                )
        except Exception:
            pass  # Don't fail on history recording

    def get_device_statuses(self, topology: dict[str, list]) -> dict[str, str]:
        """Extract device statuses from topology."""
        statuses = {}
        for node in topology.get("nodes", []):
            device_id = node.get("id", "")
            status = node.get("status", "unknown")
            if device_id:
                statuses[device_id] = status
        return statuses

    def _make_alert_key(self, alert_type: str, target_id: str) -> str:
        """Create unique key for deduplicating active alerts."""
        return f"{alert_type}:{target_id}"

    def _is_alert_active(self, alert_type: str, target_id: str) -> bool:
        """Check if an alert for this condition is already firing."""
        key = self._make_alert_key(alert_type, target_id)
        return key in self._active_alerts

    def _resolve_active_alert(self, alert_type: str, target_id: str) -> Optional[dict[str, Any]]:
        """Mark an active alert as resolved and return it."""
        key = self._make_alert_key(alert_type, target_id)
        return self._active_alerts.pop(key, None)

    async def on_topology_change(
        self,
        changes: dict[str, int],
        topology: dict[str, list],
    ):
        """
        Main entry point for topology change handling.

        Called by SNMPPoller when topology changes are detected.
        Implements alert state machine: firing -> acknowledged -> resolved.
        """
        # Get current device statuses
        current_statuses = self.get_device_statuses(topology)

        # Evaluate and generate alerts
        alerts = await self.evaluate_topology_change(
            changes,
            topology,
            self._device_status_cache,
            current_statuses,
        )

        # Deduplicate: skip alerts already firing for same condition
        new_alerts = []
        for alert in alerts:
            target_id = alert.get("device_id") or alert.get("check_id") or "topology"
            if not self._is_alert_active(alert["alert_type"], target_id):
                new_alerts.append(alert)

        # Dispatch new alerts
        if new_alerts:
            await self.dispatch_alerts(new_alerts)
            # Track as active
            for alert in new_alerts:
                target_id = alert.get("device_id") or alert.get("check_id") or "topology"
                key = self._make_alert_key(alert["alert_type"], target_id)
                self._active_alerts[key] = {
                    "alert_type": alert["alert_type"],
                    "target_id": target_id,
                    "severity": alert.get("severity", "info"),
                    "title": alert.get("title", ""),
                    "message": alert.get("message", ""),
                    "fired_at": __import__("time").time(),
                    "status": "firing",
                }

        # Auto-resolve recovered device_down alerts
        for device_id, current_status in current_statuses.items():
            if current_status == "online":
                resolved = self._resolve_active_alert("device_down", device_id)
                if resolved:
                    # Dispatch recovery notification
                    await self.dispatch_alerts([{
                        "alert_type": "device_up",
                        "severity": "info",
                        "title": "Device Recovered",
                        "message": f"Device {device_id} is back online",
                        "device_id": device_id,
                    }])

        # Update cache
        self._device_status_cache = current_statuses

    async def on_check_result(self, result: Any):
        """
        Handle service check results and generate alerts.

        Called by CheckScheduler when a check completes.
        """
        from src.collector.checks.base import CheckStatus

        # Auto-resolve if check recovers
        if result.status == CheckStatus.UP:
            resolved = self._resolve_active_alert("check_down", result.target_id)
            if resolved or self._resolve_active_alert("check_degraded", result.target_id):
                await self.dispatch_alerts([{
                    "alert_type": "device_up",
                    "severity": "info",
                    "title": "Service Check Recovered",
                    "message": f"{result.check_type} check for {result.target_id} is now passing",
                    "check_id": result.target_id,
                }])
            return

        alerts = []

        # Generate alerts based on check status
        if result.status == CheckStatus.DOWN:
            alerts.append({
                "alert_type": "check_down",
                "severity": "critical",
                "title": f"Service Check Failed",
                "message": f"{result.check_type} check for {result.target_id}: {result.message}",
                "check_id": result.target_id,
                "check_type": result.check_type,
            })
        elif result.status == CheckStatus.DEGRADED:
            alerts.append({
                "alert_type": "check_degraded",
                "severity": "warning",
                "title": f"Service Check Degraded",
                "message": f"{result.check_type} check for {result.target_id}: {result.message}",
                "check_id": result.target_id,
                "check_type": result.check_type,
            })

        # Deduplicate and dispatch
        new_alerts = []
        for alert in alerts:
            target_id = alert.get("check_id", "unknown")
            if not self._is_alert_active(alert["alert_type"], target_id):
                new_alerts.append(alert)
                key = self._make_alert_key(alert["alert_type"], target_id)
                self._active_alerts[key] = {
                    "alert_type": alert["alert_type"],
                    "target_id": target_id,
                    "severity": alert.get("severity", "info"),
                    "title": alert.get("title", ""),
                    "message": alert.get("message", ""),
                    "fired_at": __import__("time").time(),
                    "status": "firing",
                }

        if new_alerts:
            await self.dispatch_alerts(new_alerts)
