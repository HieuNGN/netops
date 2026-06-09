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
        self._history_purged: bool = False

    async def has_working_channel(self) -> bool:
        """Return True if at least one enabled alert config has valid credentials.

        Checks inline config_json and integration secrets_json. No side effects.
        """
        try:
            configs = await self.db_client.list_alert_configs()
        except Exception:
            return False
        for cfg in configs:
            if not cfg.get("enabled", True):
                continue
            channel = await self.get_notification_channel(
                cfg.get("channel", "webhook"),
                cfg.get("config_json") or {},
                integration_id=cfg.get("integration_id"),
            )
            if channel:
                ok, _ = channel.validate_config()
                if ok:
                    return True
        return False

    async def _maybe_purge_history(self) -> None:
        """Clear alert_history once when no working channel exists.

        Reset gate when a working channel is restored.
        """
        if await self.has_working_channel():
            self._history_purged = False
            return
        if not self._history_purged:
            try:
                await self.db_client.clear_alert_history()
            except Exception:
                pass  # Don't fail dispatch on cleanup errors
            self._history_purged = True

    async def get_notification_channel(
        self, channel_type: str, config: dict[str, Any],
        integration_id: Optional[str] = None,
        db_client: Any = None,
    ) -> Optional[NotificationChannel]:
        """Factory method to create notification channel instances.

        If integration_id is provided, merges integration secrets_json (base)
        with the per-rule config (overrides). Uses db_client passed in or
        self.db_client if db_client is None.
        """
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

        effective_config: dict[str, Any] = dict(config or {})
        if integration_id:
            target_db = db_client if db_client is not None else self.db_client
            if target_db and hasattr(target_db, "get_integration"):
                integration = await target_db.get_integration(integration_id)
                if integration and integration.get("secrets_json"):
                    base = dict(integration["secrets_json"])
                    base.update(effective_config)
                    effective_config = base
        return channel_class(effective_config)

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
        """Dispatch alerts to configured notification channels.

        Returns dispatch statistics. Silently skips external send when no
        working channel exists; purges stale alert_history in that case.
        """
        stats = {"sent": 0, "failed": 0, "skipped": 0}

        # Suppress alerts during maintenance windows
        try:
            if await self.db_client.is_in_maintenance_window():
                stats["skipped"] = len(alerts)
                return stats
        except Exception:
            pass  # Don't fail if maintenance window check errors

        # Purge history once when no working channel; skip external send
        await self._maybe_purge_history()
        if not await self.has_working_channel():
            stats["skipped"] = len(alerts)
            return stats

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
                channel = await self.get_notification_channel(
                    config.get("channel", "webhook"),
                    config.get("config_json", {}),
                    integration_id=config.get("integration_id"),
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
                "escalated": alert.get("escalated", False),
            }
            for key, alert in self._active_alerts.items()
        ]

    async def check_escalations(self) -> dict[str, int]:
        """Check for alerts that need escalation and escalate them.
        
        Returns stats: {"escalated": N, "failed": N}
        """
        import time
        stats = {"escalated": 0, "failed": 0}
        
        if not await self.has_working_channel():
            return stats
        
        alert_configs = await self.db_client.list_alert_configs()
        if not alert_configs:
            return stats
        
        now = time.time()
        
        for key, alert in list(self._active_alerts.items()):
            if alert["status"] != "firing":
                continue
            if alert.get("escalated"):
                continue
            
            fired_at = alert.get("fired_at", 0)
            age_minutes = (now - fired_at) / 60
            
            # Find first matching config with escalation enabled
            escalation_config = None
            for config in alert_configs:
                if config.get("alert_type") != alert["alert_type"]:
                    continue
                
                escalation_minutes = config.get("escalation_minutes")
                escalated_severity = config.get("escalated_severity")
                
                if not escalation_minutes or not escalated_severity:
                    continue
                
                if age_minutes < escalation_minutes:
                    continue
                
                escalation_config = config
                break  # Use first matching config, prevent double escalation
            
            if not escalation_config:
                continue
            
            config = escalation_config
            channel = await self.get_notification_channel(
                config.get("channel", "webhook"),
                config.get("config_json", {}),
                integration_id=config.get("integration_id"),
            )
            
            if not channel:
                stats["failed"] += 1
                continue
            
            valid, error = channel.validate_config()
            if not valid:
                stats["failed"] += 1
                continue
            
            escalated_alert = {
                **alert,
                "severity": config["escalated_severity"],
                "title": f"[ESCALATED] {alert['title']}",
                "message": f"{alert['message']} (escalated after {int(age_minutes)} minutes)",
            }
            
            message = NotificationMessage(
                title=escalated_alert["title"],
                message=escalated_alert["message"],
                severity=config["escalated_severity"],
                alert_type=alert["alert_type"],
                metadata=escalated_alert,
            )
            
            try:
                if config.get("channel", "").lower() == "email":
                    success = channel.send(message)
                else:
                    success = await channel.send(message)
                
                if success:
                    stats["escalated"] += 1
                    alert["escalated"] = True
                    alert["severity"] = config["escalated_severity"]
                    await self._record_alert(config.get("id"), escalated_alert)
                else:
                    stats["failed"] += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Escalation notification failed: {e}")
                stats["failed"] += 1
        
        return stats

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
            await self.db_client.record_alert_history(
                alert_config_id,
                alert.get("message", ""),
                status="triggered",
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
