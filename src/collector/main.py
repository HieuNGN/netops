"""NetOps FastAPI Application - Network topology discovery and monitoring."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field, EmailStr, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import ServerConfig
from .discovery import (
    add_discovered_devices,
    rescan_and_replace,
    rescan_and_merge,
)
from .host_detect import detect_host_network
from .host_state import detect_and_compare, set_host_state
from .network_watcher import NetworkWatcher
from .snmp_poller import SNMPPoller
from .topology_builder import TopologyBuilder
from .utils import logger
from src.api.services.auth import hash_password, verify_password, create_access_token, decode_token, current_user as need_auth

# Prometheus metrics
METRICS_POLLS = Counter("netops_polls_total", "Total number of SNMP polls")
METRICS_TOPOLOGY_CHANGES = Counter("netops_topology_changes_total", "Total topology changes")
METRICS_DEVICES = Gauge("netops_devices_total", "Total number of monitored devices")
METRICS_CHECKS = Gauge("netops_service_checks_total", "Total number of service checks")
METRICS_ALERTS = Gauge("netops_alerts_total", "Total number of alert configurations")

# Rate limiter for auth endpoints
limiter = Limiter(key_func=get_remote_address)

# Global state
poller: Optional[SNMPPoller] = None
check_scheduler: Optional[Any] = None
db_client: Optional[Any] = None
alert_service: Optional[Any] = None
anomaly_detector: Optional[Any] = None
topology_subscribers: list[asyncio.Queue] = []
event_subscribers: list[asyncio.Queue] = []
_startup_complete: bool = False


def _get_trap_listener(app_obj) -> Optional["SNMPTrapListener"]:
    """Return the app-scoped trap listener, if any."""
    return getattr(app_obj.state, "trap_listener", None)


async def broadcast_event(event_type: str, payload: dict[str, Any]) -> None:
    """Fan an event out to every /events/stream subscriber."""
    if not event_subscribers:
        return
    message = json.dumps({"type": event_type, **payload})
    await asyncio.gather(
        *[q.put(message) for q in event_subscribers],
        return_exceptions=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global poller, check_scheduler, db_client, alert_service, anomaly_detector, _startup_complete

    escalation_task = None  # Initialize for cleanup safety

    # Startup
    logger.info("Starting NetOps API server...")    # Auto-migrate: run Alembic upgrade head on startup (env-gated).
    # Default: enabled (1). Set NETOPS_AUTO_MIGRATE=0 to disable for
    # stricter change-control in production.
    auto_migrate = os.environ.get("NETOPS_AUTO_MIGRATE", "1") != "0"
    if auto_migrate:
        try:
            from scripts.migrate import upgrade as alembic_upgrade
            await asyncio.to_thread(alembic_upgrade, "head")
            logger.info("Alembic migrations applied (head)")
        except Exception as e:
            logger.error(f"Auto-migration failed: {e}")
            # In dev, continue with whatever schema init_db() provides.
            # In prod, this is fatal — surface it loudly.
            if os.environ.get("NETOPS_REQUIRE_MIGRATIONS", "0") == "1":
                raise

    # Initialize database client.
    #
    # PostgreSQL is the primary backend. SQLite is available as an
    # opt-in fallback for zero-dependency dev and test isolation
    # (NETOPS_USE_SQLITE=1).  When active, NETOPS_SQLITE_PATH can
    # override the default data/netops.db location (used by test
    # fixtures to avoid leaking into the real DB).
    if os.environ.get("NETOPS_USE_SQLITE") == "1":
        from src.storage.sqlite_client import AsyncSQLiteClient

        sqlite_path = os.environ.get("NETOPS_SQLITE_PATH") or "data/netops.db"
        db_client = AsyncSQLiteClient(db_path=sqlite_path)
        await db_client.connect()
        await db_client.init_db()
        logger.info(f"SQLite connected (NETOPS_USE_SQLITE=1, {sqlite_path})")
    else:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            from src.storage.database import AsyncPostgresClient
            try:
                db_client = AsyncPostgresClient(connection_string=database_url)
                await db_client.connect()
                await db_client.init_db()
                logger.info("PostgreSQL connected via DATABASE_URL")
            except Exception as e:
                logger.error(f"DATABASE_URL set but PostgreSQL unreachable: {e}")
                raise RuntimeError(
                    f"DATABASE_URL is set but PostgreSQL is unreachable: {e}"
                )
        else:
            from src.storage.database import AsyncPostgresClient
            db_client = AsyncPostgresClient()
            await db_client.connect()
            await db_client.init_db()
            logger.info("PostgreSQL connected with defaults")

    # Initialize alert service
    from src.api.services.alert_service import AlertService

    alert_service = AlertService(db_client)
    logger.info("Alert service initialized")

    # Initialize anomaly detector
    from src.api.services.anomaly_detector import AnomalyDetector

    anomaly_detector = AnomalyDetector(window_size=100, z_threshold=3.0)
    logger.info("Anomaly detector initialized")

    # Bootstrap default admin user if none exists
    try:
        admin = await db_client.get_user_by_username("admin")
        if not admin:
            await db_client.create_user("admin", hash_password("admin"), must_change_password=True)
            logger.info("Default admin user created (admin / admin) - password change required on first login")
    except Exception as e:
        logger.warning(f"Failed to bootstrap admin user: {e}")

    # Phase 4: ensure topology_history and poll_history have the
    # partitions the application expects. Gated by
    # NETOPS_PHASE4_PARTITIONED_HISTORY=1 so existing deployments
    # opt in explicitly. Best-effort: a failure here is logged but
    # does not stop the app.
    try:
        if getattr(db_client, "phase4_partitioning_enabled", False):
            if hasattr(db_client, "maintain_topology_partitions"):
                created = await db_client.maintain_topology_partitions()
                if created > 0:
                    logger.info(
                        f"Created {created} topology_history partitions ahead"
                    )
            if hasattr(db_client, "maintain_poll_history_partitions"):
                created = await db_client.maintain_poll_history_partitions()
                if created > 0:
                    logger.info(
                        f"Created {created} poll_history partitions ahead"
                    )
    except Exception as e:
        logger.warning(f"Failed to maintain partitions: {e}")

    # Read config from DB, fall back to defaults. Phase 1 keys come
    # from per-key app_settings rows; legacy keys come from the
    # 'config' JSON blob.
    config: dict = {}
    try:
        config = await db_client.get_settings()
    except Exception:
        pass
    # Phase 1: pull per-key settings (overrides the legacy blob).
    for k in (
        "topology_interval", "discovery_full_interval",
        "discovery_incremental_interval", "poll_history_retention_days",
        "topology_history_retention_days", "check_intervals",
    ):
        if hasattr(db_client, "get_setting"):
            try:
                v = await db_client.get_setting(k)
                if v is not None:
                    config[k] = v
            except Exception:
                pass

    poll_interval = int(config.get("topology_interval", 30))
    snmp_timeout = int(config.get("snmp_timeout", 5))
    snmp_retries = int(config.get("snmp_retries", 3))

    async def _on_status_change(change: dict[str, Any]) -> None:
        event_type = (
            "device_online" if change.get("new_status") == "online"
            else "device_offline"
        )
        try:
            await broadcast_event(event_type, {
                "device_id": change.get("device_id"),
                "ip_address": change.get("ip_address"),
                "name": change.get("name", ""),
                "old_status": change.get("old_status"),
                "new_status": change.get("new_status"),
                "error": change.get("error"),
                "response_time_ms": change.get("response_time_ms", 0),
            })
        except Exception as e:
            logger.warning(f"status change broadcast failed: {e}")

    # Initialize and start poller
    poller = SNMPPoller(db_client, poll_interval=poll_interval, timeout=snmp_timeout, retries=snmp_retries)
    poller.set_topology_change_handler(on_topology_change)
    poller.set_status_change_handler(_on_status_change)
    poller.set_anomaly_detector(anomaly_detector)
    await poller.start()
    logger.info(f"SNMP poller started with {poll_interval}s interval, timeout={snmp_timeout}s, retries={snmp_retries}s")

    # Initialize and start service check scheduler
    from src.collector.checks.scheduler import CheckScheduler

    check_scheduler = CheckScheduler(db_client)
    # Phase 2: apply per-type defaults if the user set them.
    check_intervals = config.get("check_intervals")
    if isinstance(check_intervals, dict):
        check_scheduler.apply_check_intervals(check_intervals)
    check_scheduler.set_check_result_handler(on_check_result)
    await check_scheduler.start()
    logger.info("Service check scheduler initialized")

    async def escalation_loop():
        """Check for alert escalations every 60 seconds."""
        while True:
            try:
                if alert_service:
                    stats = await alert_service.check_escalations()
                    if stats.get("escalated", 0) > 0:
                        logger.info(f"Escalated {stats['escalated']} alerts")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Escalation loop error: {e}")
    
    escalation_task = asyncio.create_task(escalation_loop())

    # Phase 4: start the SNMP trap listener if enabled.
    try:
        from .snmp_trap_listener import SNMPTrapListener
        listener = SNMPTrapListener()
        # Configure from app_settings.
        if hasattr(db_client, "get_setting"):
            bind_host = await db_client.get_setting("traps_bind_host", "0.0.0.0")
            port = int(await db_client.get_setting("traps_port", 162) or 162)
            community = await db_client.get_setting("traps_community", "public") or "public"
            enabled = bool(await db_client.get_setting("traps_enabled", False))
            listener.configure(bind_host=bind_host, port=port, community=community)

        async def _on_trap(trap: dict) -> None:
            """Trap handler: update device.last_polled + emit SSE event.

            We don't have a full linkUp/linkDown topology model yet;
            the current handler updates the source device's
            `last_polled` timestamp and broadcasts a `trap_received`
            SSE so the frontend can show live updates.
            """
            try:
                if db_client is not None:
                    device = await db_client.get_device(trap["source_ip"])
                    if device:
                        await db_client.update_device(
                            device["id"],
                            {"last_polled": trap["timestamp"]},
                        )
                await broadcast_event("trap_received", trap)
                # Record in topology_history (if the helper exists)
                if db_client is not None and hasattr(
                    db_client, "record_topology_change"
                ):
                    try:
                        await db_client.record_topology_change(
                            event_type=f"trap_{trap['trap_type']}",
                            source_ip=trap["source_ip"],
                            details=trap,
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Trap handler error: {e}")

        listener.set_trap_handler(_on_trap)
        app.state.trap_listener = listener
        # Only start if traps_enabled and the app state has a running
        # loop. On bind failure (port 162 root-required), the
        # listener logs and the app continues without traps.
        enabled = bool(await db_client.get_setting("traps_enabled", False)) \
            if hasattr(db_client, "get_setting") else False
        if enabled:
            started = await listener.start()
            if started:
                logger.info("SNMP trap listener active")
        else:
            logger.info("SNMP trap listener disabled (traps_enabled=false)")
    except Exception as e:
        logger.warning(f"Failed to set up trap listener: {e}")

    network_watcher: Optional[NetworkWatcher] = None

    async def _register_detected_network(detected: dict[str, Any]) -> None:
        cidr = detected.get("cidr")
        if not cidr or not hasattr(db_client, "list_networks"):
            return
        try:
            existing_networks = await db_client.list_networks()
        except Exception:
            return
        for n in existing_networks or []:
            if n.get("cidr") == cidr:
                return
        try:
            await db_client.create_network({
                "name": f"Detected ({cidr})",
                "cidr": cidr,
                "description": "Auto-registered from host network detection",
                "is_default": True,
            })
            logger.info(f"Registered detected network {cidr} as default")
        except Exception as e:
            logger.warning(f"create_network for detected CIDR failed: {e}")

    async def _emit_profile_guess() -> None:
        if not hasattr(db_client, "list_devices") or not hasattr(db_client, "set_setting"):
            return
        try:
            from .config import EnvironmentProfile, detect_profile
            current_profile = await db_client.get_setting("profile")
            confirmed = await db_client.get_setting("profile_confirmed")
            devices = await db_client.list_devices()
            guessed = detect_profile(len(devices))
            guessed_str = guessed.value
            if current_profile != guessed_str:
                await db_client.set_setting("profile_guess", guessed_str)
            await broadcast_event(
                "profile_guessed",
                {
                    "profile": guessed_str,
                    "device_count": len(devices),
                    "confirmed": bool(confirmed),
                },
            )
        except Exception as e:
            logger.warning(f"Profile guess failed: {e}")

    async def _startup_auto_discover():
        try:
            snap = await detect_and_compare(db_client)
            detected = snap.get("detected", {}) or {}
            previous = snap.get("previous", {}) or {}
            changed = bool(snap.get("changed"))
            first_seen = bool(snap.get("first_seen"))

            host_ip = detected.get("host_ip")
            cidr = detected.get("cidr", "192.168.1.0/24")
            hostname = detected.get("hostname") or "Current Device"
            gateway = detected.get("gateway")

            logger.info(
                f"Host detected: {hostname} @ {host_ip}, CIDR {cidr}, "
                f"gateway={gateway}, first_seen={first_seen}, changed={changed}, "
                f"prev_cidr={previous.get('host_cidr')}"
            )

            mode = os.environ.get("NETOPS_AUTO_DISCOVER_MODE", "merge").lower()
            if mode not in ("merge", "replace"):
                mode = "merge"

            should_scan = changed or first_seen

            if should_scan and changed:
                await broadcast_event("network_changed", {
                    "old_cidr": previous.get("host_cidr"),
                    "old_gateway": previous.get("host_gateway"),
                    "new_cidr": cidr,
                    "new_gateway": gateway,
                    "source": "startup",
                })
                # Dispatch alert for network change at startup
                if alert_service:
                    try:
                        await alert_service.dispatch_alerts([{
                            "alert_type": "network_changed",
                            "severity": "warning",
                            "title": "Network Change Detected",
                            "message": f"Host network changed from {previous.get('host_cidr', 'unknown')} to {cidr}",
                            "old_cidr": previous.get("host_cidr"),
                            "new_cidr": cidr,
                            "old_gateway": previous.get("host_gateway"),
                            "new_gateway": gateway,
                        }])
                    except Exception as e:
                        logger.warning(f"Startup network change alert failed: {e}")

            if not should_scan:
                logger.info(
                    f"Network unchanged (fingerprint={snap.get('fingerprint')}); "
                    "skipping auto-discover"
                )
                await _emit_profile_guess()
                return

            existing = await db_client.list_devices() if hasattr(db_client, "list_devices") else []
            mock_ids = []
            for d in existing:
                method = (d.get("discovery_method") or "").lower()
                name = d.get("name") or ""
                if method == "simulated" or name in {
                    "Core-Router-1", "Core-Router-2",
                    "Distribution-SW-1", "Distribution-SW-2",
                    "Access-SW-1", "Access-SW-2", "Access-SW-3",
                    "Firewall-1",
                }:
                    mock_ids.append(d.get("id") or d.get("ip_address"))
            if mock_ids:
                removed = await db_client.bulk_delete_devices(mock_ids)
                logger.info(f"Auto-removed {removed} stale mock devices on startup")

            if hasattr(db_client, "prune_orphan_topology"):
                try:
                    orphaned = await db_client.prune_orphan_topology()
                    if orphaned:
                        logger.info(f"Pruned {orphaned} orphan topology nodes on startup")
                except Exception as e:
                    logger.warning(f"prune_orphan_topology failed: {e}")

            if host_ip and hasattr(db_client, "get_device"):
                existing_host = await db_client.get_device(host_ip)
                if not existing_host:
                    try:
                        await db_client.create_device({
                            "ip_address": host_ip,
                            "name": hostname,
                            "status": "online",
                            "discovery_method": "auto",
                            "sys_descr": f"NetOps host ({hostname})",
                        })
                        logger.info(f"Registered host device {hostname} ({host_ip})")
                    except Exception as e:
                        logger.warning(f"Register host failed: {e}")

            await broadcast_event("rescan_started", {
                "network_range": cidr, "source": "startup", "mode": mode,
            })

            async def _stale_emitter(payload: dict) -> None:
                await broadcast_event("device_stale", payload)

            async def _device_found_emitter(payload: dict) -> None:
                event_type = payload.pop("type", "device_found")
                await broadcast_event(event_type, payload)

            if mode == "replace":
                stats = await rescan_and_replace(
                    db_client, cidr, timeout=2.0, max_concurrent=50, method="all",
                    device_found_event_emitter=_device_found_emitter,
                )
            else:
                stats = await rescan_and_merge(
                    db_client, cidr, timeout=2.0, max_concurrent=50, method="all",
                    preserve_manual=True,
                    stale_event_emitter=_stale_emitter,
                    device_found_event_emitter=_device_found_emitter,
                )
            logger.info(
                f"Auto-rescan {cidr} (mode={mode}): "
                f"found={stats.get('found', 0)}, added={stats.get('added', 0)}, "
                f"updated={stats.get('updated', 0)}, marked_offline={stats.get('marked_offline', 0)}"
            )

            if host_ip and hasattr(db_client, "get_device"):
                existing_host = await db_client.get_device(host_ip)
                if not existing_host:
                    try:
                        await db_client.create_device({
                            "ip_address": host_ip,
                            "name": hostname,
                            "status": "online",
                            "discovery_method": "auto",
                            "sys_descr": f"NetOps host ({hostname})",
                        })
                    except Exception:
                        pass

            if gateway:
                try:
                    gw_existing = await db_client.get_device(gateway)
                    if not gw_existing:
                        await db_client.create_device({
                            "ip_address": gateway,
                            "name": f"Gateway ({gateway})",
                            "status": "online",
                            "discovery_method": "auto",
                            "sys_descr": "Default gateway",
                        })
                except Exception as e:
                    logger.warning(f"Register gateway failed: {e}")

            await _register_detected_network(detected)
            await set_host_state(db_client, cidr, gateway)

            await broadcast_event("devices_refresh", {
                "stats": stats, "source": "startup_auto", "mode": mode,
            })
            await _emit_profile_guess()
        except Exception as e:
            logger.warning(f"Startup auto-discover failed: {e}")

    asyncio.create_task(_startup_auto_discover())

    async def _watcher_on_change(snap: dict[str, Any]) -> None:
        detected = snap.get("detected", {}) or {}
        previous = snap.get("previous", {}) or {}
        cidr = detected.get("cidr")
        gateway = detected.get("gateway")
        if not cidr:
            return
        await broadcast_event("network_changed", {
            "old_cidr": previous.get("host_cidr"),
            "old_gateway": previous.get("host_gateway"),
            "new_cidr": cidr,
            "new_gateway": gateway,
            "source": "watcher",
        })
        await _register_detected_network(detected)

        # Dispatch alert for network change
        if alert_service:
            try:
                await alert_service.dispatch_alerts([{
                    "alert_type": "network_changed",
                    "severity": "warning",
                    "title": "Network Change Detected",
                    "message": f"Host network changed from {previous.get('host_cidr', 'unknown')} to {cidr}",
                    "old_cidr": previous.get("host_cidr"),
                    "new_cidr": cidr,
                    "old_gateway": previous.get("host_gateway"),
                    "new_gateway": gateway,
                }])
            except Exception as e:
                logger.warning(f"Network change alert dispatch failed: {e}")

        async def _run_rescan():
            try:
                async def _stale_emitter(payload: dict) -> None:
                    await broadcast_event("device_stale", payload)
                async def _device_found_emitter(payload: dict) -> None:
                    event_type = payload.pop("type", "device_found")
                    await broadcast_event(event_type, payload)
                await broadcast_event("rescan_started", {
                    "network_range": cidr, "source": "watcher", "mode": "merge",
                })
                stats = await rescan_and_merge(
                    db_client, cidr, timeout=2.0, max_concurrent=50, method="all",
                    preserve_manual=True,
                    stale_event_emitter=_stale_emitter,
                    device_found_event_emitter=_device_found_emitter,
                )
                await broadcast_event("devices_refresh", {
                    "stats": stats, "source": "network_watcher", "cidr": cidr,
                })
            except Exception as e:
                logger.warning(f"Watcher rescan failed: {e}")

        asyncio.create_task(_run_rescan())

    network_watcher = NetworkWatcher(db_client, _watcher_on_change)
    app.state.network_watcher = network_watcher
    await network_watcher.start()

    _startup_complete = True
    logger.info("Startup complete — server ready")

    yield

    logger.info("Shutting down NetOps API server...")
    if network_watcher is not None:
        try:
            await network_watcher.stop()
        except Exception:
            pass
    if poller:
        await poller.stop()
    if check_scheduler:
        await check_scheduler.stop()
    if escalation_task:
        escalation_task.cancel()
        try:
            await escalation_task
        except asyncio.CancelledError:
            pass
    listener = getattr(app.state, "trap_listener", None)
    if listener is not None:
        try:
            await listener.stop()
        except Exception:
            pass
    if db_client:
        await db_client.close()


async def on_check_result(result: Any):
    """Handle service check results."""
    # Evaluate and dispatch alerts based on check results
    if alert_service and result:
        await alert_service.on_check_result(result)


async def on_topology_change(changes: dict[str, int], topology: dict[str, list]):
    """Handle topology changes - notify subscribers and dispatch alerts."""
    # Notify SSE subscribers only when there are structural changes
    has_changes = any(v > 0 for v in changes.values())
    if topology_subscribers and has_changes:
        message = json.dumps({"type": "topology_change", "changes": changes, "topology": topology})
        # Fan out to all subscribers concurrently
        await asyncio.gather(
            *[queue.put(message) for queue in topology_subscribers],
            return_exceptions=True,
        )

    # Always dispatch alerts — status flips need alert evaluation
    if alert_service:
        await alert_service.on_topology_change(changes, topology)


# Request/Response models
class DeviceCreate(BaseModel):
    name: str
    ip_address: str
    community: str = "public"
    snmp_version: str = "2c"
    snmpv3_username: Optional[str] = None
    snmpv3_auth_protocol: Optional[str] = None
    snmpv3_auth_key: Optional[str] = None
    snmpv3_priv_protocol: Optional[str] = None
    snmpv3_priv_key: Optional[str] = None
    node_type: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    community: Optional[str] = None
    status: Optional[str] = None
    snmp_version: Optional[str] = None
    snmpv3_username: Optional[str] = None
    snmpv3_auth_protocol: Optional[str] = None
    snmpv3_auth_key: Optional[str] = None
    snmpv3_priv_protocol: Optional[str] = None
    snmpv3_priv_key: Optional[str] = None
    node_type: Optional[str] = None


class BulkImportRequest(BaseModel):
    devices: list[DeviceCreate]


class BulkImportResult(BaseModel):
    total: int
    created: int
    skipped: int
    errors: list[str]


class AlertConfigCreate(BaseModel):
    name: str
    alert_type: str = Field(..., description="Type: device_down, device_up, link_down, topology_change")
    channel: str = Field(..., description="Channel: webhook, slack, telegram, whatsapp, email")
    config: dict[str, Any] = {}
    integration_id: Optional[str] = None
    enabled: bool = True
    escalation_minutes: Optional[int] = Field(None, description="Minutes before auto-escalate (null = disabled)")
    escalated_severity: Optional[str] = Field(None, description="Severity to escalate to (e.g., 'critical')")

    def model_validate(self, values):
        """Validate channel is supported."""
        valid_channels = {"webhook", "slack", "telegram", "whatsapp", "email"}
        if values.get("channel") not in valid_channels:
            raise ValueError(f"Unsupported channel. Must be one of: {valid_channels}")
        return super().model_validate(values)


class AlertConfigUpdate(BaseModel):
    name: Optional[str] = None
    alert_type: Optional[str] = None
    channel: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    integration_id: Optional[str] = None
    enabled: Optional[bool] = None
    escalation_minutes: Optional[int] = None
    escalated_severity: Optional[str] = None


class IntegrationCreate(BaseModel):
    type: str = Field(..., description="Channel type: telegram, slack, webhook, email, whatsapp")
    name: str
    secrets_json: dict[str, Any] = {}
    enabled: bool = True

    def model_validate(self, values):
        valid_types = {"webhook", "slack", "telegram", "whatsapp", "email"}
        if values.get("type") not in valid_types:
            raise ValueError(f"Unsupported integration type. Must be one of: {valid_types}")
        return super().model_validate(values)


class IntegrationUpdate(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    secrets_json: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


class DiscoveryRequest(BaseModel):
    network_range: str
    community: str = "public"
    method: str = "all"


class NetworkCreate(BaseModel):
    name: str
    cidr: Optional[str] = None
    description: Optional[str] = None


class NetworkUpdate(BaseModel):
    name: Optional[str] = None
    cidr: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    network_type: Optional[str] = None
    tags: Optional[list[str]] = None


app = FastAPI(
    title="NetOps API",
    description="Network topology discovery and monitoring",
    version="0.5.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Health endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    result = {"status": "ok", "startup_complete": _startup_complete}
    if poller:
        result["poller"] = poller.get_stats()
    if alert_service:
        result["alert_service"] = {"initialized": True}
    watcher = getattr(app.state, "network_watcher", None)
    if watcher is not None:
        result["watcher"] = watcher.get_status()
    return result



# Readiness endpoint — returns 503 until startup is fully complete.
# The FE uses this to gate API calls and avoid spurious errors during
# the initial boot (auto-discover, PG connection, migrations).
@app.get("/api/health/ready")
async def readiness_check():
    if not _startup_complete or not db_client:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "startup_complete": _startup_complete},
            headers={"Retry-After": "2"},
        )
    db_ok = False
    try:
        hc = await db_client.healthcheck()
        db_ok = hc.get("status") == "connected"
    except Exception:
        pass
    return {
        "status": "ready" if db_ok else "degraded",
        "startup_complete": _startup_complete,
        "db_connected": db_ok,
    }


# Database health endpoint (Phase 3 spec). Returns the active
# backend's connection pool stats and a probe-query latency.
@app.get("/api/health/db")
async def db_health_check():
    """Database health: backend, latency, pool stats.

    Returns 200 with `status: connected` on success, 503 on
    disconnected, 500 on error. Operators use this to wire up
    monitoring alerts.
    """
    if not db_client:
        return JSONResponse(
            status_code=503,
            content={"status": "disconnected", "message": "Database not initialized"},
        )
    if hasattr(db_client, "healthcheck"):
        info = await db_client.healthcheck()
    else:
        # Fallback: client has no healthcheck method (custom subclass).
        return {"status": "unknown", "backend": type(db_client).__name__}
    status = info.get("status", "unknown")
    if status == "error":
        return JSONResponse(status_code=500, content=info)
    if status == "disconnected":
        return JSONResponse(status_code=503, content=info)
    return info


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _username_safe(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Za-z0-9_.-]+$", v):
            raise ValueError("username may only contain letters, digits, _.-")
        return v

    @field_validator("password")
    @classmethod
    def _password_strong(cls, v: str) -> str:
        import re
        if not re.search(r"[a-z]", v):
            raise ValueError("password must include a lowercase letter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must include an uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must include a digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("password must include a symbol")
        return v


class ConfigUpdate(BaseModel):
    # Legacy fields (kept for backward compat).
    topology_interval: Optional[int] = None
    check_interval: Optional[int] = None
    snmp_timeout: Optional[int] = None
    snmp_retries: Optional[int] = None
    snmp_community: Optional[str] = None
    # Phase 1 fields.
    profile: Optional[str] = None
    discovery_full_interval: Optional[int] = None
    discovery_incremental_interval: Optional[int] = None
    poll_history_retention_days: Optional[int] = None
    topology_history_retention_days: Optional[int] = None
    # Phase 4 trap config.
    traps_enabled: Optional[bool] = None
    traps_bind_host: Optional[str] = None
    traps_port: Optional[int] = None
    traps_community: Optional[str] = None
    traps_destination_ip: Optional[str] = None


class ProfileRequest(BaseModel):
    profile: str
    confirmado: bool = False


class StaleActionRequest(BaseModel):
    action: str  # "delete" | "keep"


class TrapConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    bind_host: Optional[str] = None
    port: Optional[int] = None
    community: Optional[str] = None
    destination_ip: Optional[str] = None


VALID_PROFILES = {"homelab", "small_business", "datacenter"}


@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, req: LoginRequest):
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    user = await db_client.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(req.username)
    resp = JSONResponse({
        "username": req.username,
        "role": user.get("role", "admin"),
        "must_change_password": user.get("must_change_password", False),
    })
    cookie_secure = os.environ.get("NETOPS_COOKIE_SECURE", "0") != "0"
    resp.set_cookie(
        "token",
        token,
        httponly=True,
        samesite="lax",
        secure=cookie_secure,
        path="/",
        max_age=86400,
    )
    return resp


@app.post("/api/auth/signup", status_code=201)
@limiter.limit("3/minute")
async def auth_signup(request: Request, req: SignupRequest):
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if await db_client.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    if await db_client.get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = await db_client.create_user(
        req.username, hash_password(req.password), email=req.email, name=req.name,
    )
    token = create_access_token(req.username)
    resp = JSONResponse(
        status_code=201,
        content={
            "username": user["username"],
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role", "admin"),
        },
    )
    resp.set_cookie(
        "token",
        token,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("NETOPS_COOKIE_SECURE", "0") != "0",
        path="/",
        max_age=86400,
    )
    return resp


@app.get("/api/auth/me")
async def auth_me(user: str = Depends(need_auth)):
    if db_client:
        row = await db_client.get_user_by_username(user)
        if row:
            return {
                "username": row["username"],
                "email": row.get("email"),
                "name": row.get("name"),
                "role": row.get("role", "admin"),
                "authenticated": True,
            }
    return {"username": user, "authenticated": True}


@app.post("/api/auth/logout")
async def auth_logout():
    resp = JSONResponse({"logged_out": True})
    resp.delete_cookie("token")
    return resp


@app.post("/api/auth/change-password")
@limiter.limit("3/minute")
async def auth_change_password(request: Request, req: PasswordChangeRequest, user: str = Depends(need_auth)):
    """Change user password. Clears must_change_password flag."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    # Verify current password
    user_data = await db_client.get_user_by_username(user)
    if not user_data or not verify_password(req.current_password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    # Update password
    new_hash = hash_password(req.new_password)
    success = await db_client.update_user_password(user, new_hash)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update password")
    
    return {"status": "password_changed", "must_change_password": False}


@app.get("/api/config")
async def get_config(user: str = Depends(need_auth)):
    if not db_client:
        raise HTTPException(status_code=503)
    return await db_client.get_settings()


@app.put("/api/config")
async def save_config(cfg: ConfigUpdate, user: str = Depends(need_auth)):
    if not db_client:
        raise HTTPException(status_code=503)
    # The legacy 'config' JSON blob — kept for backward compat.
    existing = await db_client.get_settings()
    for key in (
        "topology_interval", "check_interval",
        "snmp_timeout", "snmp_retries", "snmp_community",
    ):
        v = getattr(cfg, key, None)
        if v is not None:
            existing[key] = v
    await db_client.update_settings(existing)

    # Phase 1+ per-key settings (each row in app_settings).
    per_key = {
        "profile": cfg.profile,
        "discovery_full_interval": cfg.discovery_full_interval,
        "discovery_incremental_interval": cfg.discovery_incremental_interval,
        "poll_history_retention_days": cfg.poll_history_retention_days,
        "topology_history_retention_days": cfg.topology_history_retention_days,
        "traps_enabled": cfg.traps_enabled,
        "traps_bind_host": cfg.traps_bind_host,
        "traps_port": cfg.traps_port,
        "traps_community": cfg.traps_community,
        "traps_destination_ip": cfg.traps_destination_ip,
    }
    for k, v in per_key.items():
        if v is not None:
            await db_client.set_setting(k, v)
    return {"saved": True, "config": existing}


@app.get("/api/config/profiles")
async def list_profiles():
    """Return all profiles + active/detected for the FE EnvironmentProfileCard.

    Shape:
      {
        profiles: [{name, description, is_default, settings: {...}}, ...],
        active_profile: "homelab" | "small_business" | "datacenter",
        detected_profile: "...",
        is_guessed: bool,
      }
    """
    from .config import ENVIRONMENT_PROFILES, EnvironmentProfile
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    profiles = []
    for p, defaults in ENVIRONMENT_PROFILES.items():
        profiles.append({
            "name": p.value,
            "description": (
                "Up to 15 devices. Polling every 30s, rescans every 6h."
                if p == EnvironmentProfile.HOMELAB
                else "Up to 80 devices. Polling every 60s, rescans every 2h."
                if p == EnvironmentProfile.SMALL_BUSINESS
                else "Unlimited devices. Polling every 60s, rescans every 1h."
            ),
            "is_default": p == EnvironmentProfile.HOMELAB,
            "settings": {
                "topology_interval": defaults["topology_interval"],
                "discovery_full_interval": defaults["discovery_full_interval"],
                "discovery_incremental_interval": defaults["discovery_incremental_interval"],
                "check_intervals": defaults["check_intervals"],
                "poll_history_retention_days": defaults["poll_history_retention_days"],
            },
        })
    active = "homelab"
    detected = "homelab"
    is_guessed = False
    if hasattr(db_client, "get_setting"):
        try:
            v = await db_client.get_setting("profile")
            if isinstance(v, str) and v:
                active = v
        except Exception:
            pass
        try:
            v = await db_client.get_setting("profile_guess")
            detected = v if isinstance(v, str) and v else active
        except Exception:
            detected = active
        try:
            c = await db_client.get_setting("profile_confirmed")
            is_guessed = not c
        except Exception:
            is_guessed = True
    return {
        "profiles": profiles,
        "active_profile": active,
        "detected_profile": detected,
        "is_guessed": is_guessed,
    }


@app.put("/api/config/profile")
async def set_profile(req: ProfileRequest, user: str = Depends(need_auth)):
    """Apply an environment profile. Resets all interval defaults.

    `confirmado=True`: persist active profile + persist
    `profile_confirmed=true` so the FE `is_guessed` flag clears.
    `confirmado=False` (preview): update `profile_guess` only, do
    not touch the active profile, return `applied=False`.
    """
    from .config import EnvironmentProfile, NetOpsConfig
    if req.profile not in VALID_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid profile. Must be one of: {VALID_PROFILES}",
        )
    profile = EnvironmentProfile(req.profile)
    cfg = NetOpsConfig.from_profile(profile)

    if not req.confirmado:
        if hasattr(db_client, "set_setting"):
            try:
                await db_client.set_setting("profile_guess", profile.value)
            except Exception:
                pass
        return {
            "saved": True,
            "applied": False,
            "profile": profile.value,
            "is_guess": True,
        }

    await db_client.set_setting("profile", profile.value)
    await db_client.set_setting("topology_interval", cfg.topology_interval)
    await db_client.set_setting("discovery_full_interval", cfg.discovery_full_interval)
    await db_client.set_setting(
        "discovery_incremental_interval", cfg.discovery_incremental_interval
    )
    await db_client.set_setting("check_intervals", cfg.check_intervals)
    await db_client.set_setting(
        "poll_history_retention_days", cfg.poll_history_retention_days
    )
    if hasattr(db_client, "set_setting"):
        try:
            await db_client.set_setting("profile_confirmed", "true")
        except Exception:
            pass
    if poller:
        poller.poll_interval = cfg.topology_interval
    if check_scheduler:
        check_scheduler.apply_check_intervals(cfg.check_intervals)
    return {
        "saved": True,
        "applied": True,
        "profile": profile.value,
        "is_guess": False,
        "config": {
            "topology_interval": cfg.topology_interval,
            "discovery_full_interval": cfg.discovery_full_interval,
            "discovery_incremental_interval": cfg.discovery_incremental_interval,
            "check_intervals": cfg.check_intervals,
            "poll_history_retention_days": cfg.poll_history_retention_days,
        },
    }


# ---------------------------------------------------------------------------
# Phase 4: SNMP trap configuration endpoints.
# Trap config lives in app_settings keys (traps_enabled,
# traps_bind_host, traps_port, traps_community, traps_destination_ip).
# The actual UDP listener is managed by the lifespan handler.
# ---------------------------------------------------------------------------

@app.get("/api/config/traps")
async def get_trap_config(user: str = Depends(need_auth)):
    """Return current trap configuration."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not hasattr(db_client, "get_setting"):
        raise HTTPException(status_code=501, detail="Backend does not support per-key settings")
    keys = ("traps_enabled", "traps_bind_host", "traps_port",
            "traps_community", "traps_destination_ip")
    out: dict[str, Any] = {}
    for k in keys:
        v = await db_client.get_setting(k)
        out[k.replace("traps_", "")] = v
    # Reflect the runtime status of the listener, if any.
    out["listener_running"] = bool(getattr(app.state, "trap_listener", None)) and bool(
        getattr(app.state.trap_listener, "_running", False)
    )
    return out


@app.put("/api/config/traps")
async def set_trap_config(cfg: TrapConfigUpdate, user: str = Depends(need_auth)):
    """Update trap configuration. Restarts the listener if running."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not hasattr(db_client, "set_setting"):
        raise HTTPException(status_code=501, detail="Backend does not support per-key settings")
    # Validate inputs. bind_host must be a valid IP literal or empty
    # (which means "all interfaces" in inet_pton). port must be 1-65535.
    # community and destination_ip are strings; we length-cap to prevent
    # the config blob from getting out of hand.
    import ipaddress as _ip
    if cfg.bind_host is not None and cfg.bind_host != "":
        try:
            _ip.ip_address(cfg.bind_host)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"bind_host must be a valid IP address, got {cfg.bind_host!r}",
            )
    if cfg.port is not None and not (1 <= int(cfg.port) <= 65535):
        raise HTTPException(
            status_code=400,
            detail=f"port must be in 1-65535, got {cfg.port}",
        )
    if cfg.community is not None and len(cfg.community) > 128:
        raise HTTPException(
            status_code=400,
            detail="community must be <= 128 chars",
        )
    if cfg.destination_ip is not None and cfg.destination_ip != "":
        try:
            _ip.ip_address(cfg.destination_ip)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"destination_ip must be a valid IP address, got {cfg.destination_ip!r}",
            )
    if cfg.enabled is not None:
        await db_client.set_setting("traps_enabled", bool(cfg.enabled))
    if cfg.bind_host is not None:
        await db_client.set_setting("traps_bind_host", cfg.bind_host)
    if cfg.port is not None:
        await db_client.set_setting("traps_port", int(cfg.port))
    if cfg.community is not None:
        await db_client.set_setting("traps_community", cfg.community)
    if cfg.destination_ip is not None:
        await db_client.set_setting("traps_destination_ip", cfg.destination_ip)
    # Restart the listener with the new config (if any).
    listener = getattr(app.state, "trap_listener", None)
    if listener is not None:
        try:
            await listener.stop()
        except Exception:
            pass
        try:
            bind_host = await db_client.get_setting("traps_bind_host", "0.0.0.0")
            port = int(await db_client.get_setting("traps_port", 162) or 162)
            community = await db_client.get_setting("traps_community", "public") or "public"
            listener.configure(bind_host=bind_host, port=port, community=community)
            enabled = bool(await db_client.get_setting("traps_enabled", False))
            if enabled:
                started = await listener.start()
                return {
                    "saved": True,
                    "listener_started": started,
                    "bind_host": bind_host,
                    "port": port,
                }
        except Exception as e:
            logger.warning(f"Failed to restart trap listener: {e}")
    return {"saved": True, "listener_running": False}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    # Update gauges from current state
    if db_client:
        try:
            devices = await db_client.list_devices()
            METRICS_DEVICES.set(len(devices))
        except Exception:
            pass
        try:
            checks = await db_client.list_service_checks()
            METRICS_CHECKS.set(len(checks))
        except Exception:
            pass
        try:
            alerts = await db_client.list_alert_configs()
            METRICS_ALERTS.set(len(alerts))
        except Exception:
            pass
    if poller:
        stats = poller.get_stats()
        METRICS_POLLS.inc(stats.get("polls", 0))
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Topology endpoints
@app.get("/topology")
async def get_topology(user: str = Depends(need_auth)):
    """Get current network topology."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    topology = await db_client.list_topology()
    return topology


@app.get("/topology/stream")
async def stream_topology(delta: bool = False, user: str = Depends(need_auth)):
    """Stream topology updates via Server-Sent Events.

    Args:
        delta: If True, stream only change summaries without full topology payload.
    """

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        topology_subscribers.append(queue)

        try:
            # Send initial topology
            current = await db_client.list_topology() if db_client else {"nodes": [], "links": []}
            yield f"data: {json.dumps({'type': 'initial', 'topology': current})}\n\n"

            # Stream updates
            while True:
                raw_message = await queue.get()
                if delta:
                    # Strip full topology to reduce bandwidth for lightweight consumers
                    try:
                        payload = json.loads(raw_message)
                        if payload.get("type") == "topology_change":
                            payload.pop("topology", None)
                            raw_message = json.dumps(payload)
                    except Exception:
                        pass
                yield f"data: {raw_message}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            topology_subscribers.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/topology/refresh")
async def refresh_topology(user: str = Depends(need_auth)):
    """Trigger an immediate topology poll."""
    if not poller:
        raise HTTPException(status_code=503, detail="Poller not initialized")

    await poller.poll_now()
    return {"status": "refreshed", "topology": await db_client.list_topology() if db_client else {}}


@app.post("/topology/simulate")
async def simulate_topology(user: str = Depends(need_auth)):
    """Generate simulated network topology for demo purposes."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Simulated devices representing a typical network hierarchy
    simulated_devices = [
        {"name": "Core-Router-1", "ip_address": "192.168.1.1", "community": "public"},
        {"name": "Core-Router-2", "ip_address": "192.168.1.2", "community": "public"},
        {"name": "Distribution-SW-1", "ip_address": "192.168.1.10", "community": "public"},
        {"name": "Distribution-SW-2", "ip_address": "192.168.1.11", "community": "public"},
        {"name": "Access-SW-1", "ip_address": "192.168.1.100", "community": "public"},
        {"name": "Access-SW-2", "ip_address": "192.168.1.101", "community": "public"},
        {"name": "Access-SW-3", "ip_address": "192.168.1.102", "community": "public"},
        {"name": "Firewall-1", "ip_address": "192.168.1.254", "community": "public"},
    ]

    # Build topology nodes directly (will be upserted)
    # Assign hierarchy levels for visual layout: 0=edge, 1=core, 2=distribution, 3=access
    def get_level(name: str) -> int:
        if "Firewall" in name:
            return 0
        if "Core" in name:
            return 1
        if "Distribution" in name:
            return 2
        return 3

    nodes = []
    for dev in simulated_devices:
        node_type = "router" if "Router" in dev["name"] else "firewall" if "Firewall" in dev["name"] else "switch"
        nodes.append({
            "id": dev["ip_address"],
            "device_id": dev["ip_address"],
            "label": dev["name"],
            "node_type": node_type,
            "status": "online",
            "level": get_level(dev["name"]),
        })

    # Build topology links (hierarchical network design)
    links_data = [
        ("192.168.1.254", "192.168.1.1", "eth0", "ge-0/0/0"),
        ("192.168.1.254", "192.168.1.2", "eth1", "ge-0/0/0"),
        ("192.168.1.1", "192.168.1.2", "ge-0/0/1", "ge-0/0/1"),
        ("192.168.1.1", "192.168.1.10", "ge-0/0/2", "xe-0/0/1"),
        ("192.168.1.2", "192.168.1.11", "ge-0/0/2", "xe-0/0/1"),
        ("192.168.1.10", "192.168.1.100", "ge-0/0/1", "ge-0/0/1"),
        ("192.168.1.10", "192.168.1.101", "ge-0/0/2", "ge-0/0/1"),
        ("192.168.1.11", "192.168.1.102", "ge-0/0/1", "ge-0/0/1"),
    ]

    links = []
    for src_ip, tgt_ip, src_port, tgt_port in links_data:
        links.append({
            "id": f"{src_ip}-{tgt_ip}",
            "source": src_ip,
            "target": tgt_ip,
            "source_port": src_port,
            "target_port": tgt_port,
            "status": "active",
        })

    # Retry with backoff to handle poller DB contention
    max_retries = 10
    for attempt in range(max_retries):
        try:
            changes = await db_client.upsert_topology(nodes, links)
            return {
                "status": "simulated",
                "nodes": len(nodes),
                "links": len(links),
                "changes": changes,
            }
        except Exception as e:
            if attempt < max_retries - 1:
                # Wait longer between retries (2s, 4s, 6s...)
                await asyncio.sleep(2.0 * (attempt + 1))
            else:
                raise HTTPException(status_code=503, detail=f"Database busy: {str(e)}")


# Device endpoints
@app.get("/devices")
async def list_devices(limit: Optional[int] = None, offset: Optional[int] = None, user: str = Depends(need_auth)):
    """List configured devices with optional pagination."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_devices(limit=limit, offset=offset)


@app.get("/devices/{device_id}")
async def get_device(device_id: str, user: str = Depends(need_auth)):
    """Get a specific device by ID or IP."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@app.get("/devices/{device_id}/history")
async def get_device_history(device_id: str, limit: int = 100, user: str = Depends(need_auth)):
    """Get poll history for a specific device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    history = await db_client.get_device_poll_history(device_id, limit=limit)
    return {"device_id": device_id, "history": history}


@app.post("/devices")
async def create_device(device: DeviceCreate, user: str = Depends(need_auth)):
    """Add a new device to monitor."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    existing = await db_client.get_device(device.ip_address)
    if existing:
        raise HTTPException(status_code=409, detail="Device already exists")

    return await db_client.create_device(device.model_dump() | {"status": "unknown"})


@app.post("/devices/import")
async def bulk_import(req: BulkImportRequest, user: str = Depends(need_auth)):
    """Bulk import devices from JSON/CSV."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    result = BulkImportResult(total=len(req.devices), created=0, skipped=0, errors=[])

    for d in req.devices:
        try:
            existing = await db_client.get_device(d.ip_address)
            if existing:
                result.skipped += 1
                continue
            await db_client.create_device(d.model_dump() | {"status": "unknown"})
            result.created += 1
        except Exception as e:
            result.errors.append(f"{d.ip_address}: {e}")

    return result


@app.put("/devices/{device_id}")
async def update_device(device_id: str, device: DeviceUpdate, user: str = Depends(need_auth)):
    """Update an existing device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    existing = await db_client.get_device(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = {k: v for k, v in device.model_dump().items() if v is not None}
    return await db_client.update_device(device_id, update_data)


@app.delete("/devices/{device_id}")
async def delete_device(device_id: str, user: str = Depends(need_auth)):
    """Delete a device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    if not await db_client.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    return {"status": "deleted"}


# Network endpoints
@app.get("/networks")
async def list_networks(user: str = Depends(need_auth)):
    """List all networks."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.list_networks()


@app.get("/networks/{network_id}")
async def get_network(network_id: str, user: str = Depends(need_auth)):
    """Get network by ID."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    network = await db_client.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return network


@app.post("/networks")
async def create_network(network: NetworkCreate, user: str = Depends(need_auth)):
    """Create a new network."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    created = await db_client.create_network(network.model_dump())

    # If the network has a CIDR, auto-rescan it in the background and
    # emit a devices_refresh SSE event when discovery finishes.
    # Security: cap the range to <= 4096 hosts so a hostile /0 or /8
    # cidr can't tie up the event loop / exhaust memory.
    import ipaddress as _ip_net
    cidr = (created or {}).get("cidr")
    if cidr:
        try:
            net = _ip_net.ip_network(cidr, strict=False)
            if net.num_addresses > 4096:
                logger.warning(
                    f"Skipping auto-rescan for {cidr}: "
                    f"{net.num_addresses} hosts exceeds 4096-host cap"
                )
                cidr = None
        except ValueError:
            # Non-CIDR string — pass through; the underlying scanner
            # has its own 4096-host cap.
            pass
    if cidr:
        async def _auto_scan():
            try:
                async def _device_found_emitter(payload: dict) -> None:
                    event_type = payload.pop("type", "device_found")
                    await broadcast_event(event_type, payload)
                await broadcast_event(
                    "rescan_started",
                    {"network_range": cidr, "network_id": created.get("id")},
                )
                stats = await add_discovered_devices(
                    db_client, cidr, timeout=2.0, max_concurrent=50, method="all",
                    device_found_event_emitter=_device_found_emitter,
                )
                await broadcast_event(
                    "rescan_completed",
                    {
                        "network_range": cidr,
                        "network_id": created.get("id"),
                        "stats": stats,
                    },
                )
                await broadcast_event(
                    "devices_refresh",
                    {"stats": stats, "source": "auto_rescan", "network_range": cidr},
                )
            except Exception as e:
                logger.warning(f"auto-rescan failed for {cidr}: {e}")

        asyncio.create_task(_auto_scan())

    return created


VALID_NETWORK_TYPES = {"lan", "wan", "wifi", "sfp", "console", "bmc", "mgmt", "dmz", "vlan", "vpn", "custom"}

@app.put("/networks/{network_id}")
async def update_network(network_id: str, network: NetworkUpdate, user: str = Depends(need_auth)):
    """Update a network."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    existing = await db_client.get_network(network_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Network not found")

    update_data: dict[str, Any] = {k: v for k, v in network.model_dump().items() if v is not None}

    if "network_type" in update_data and update_data["network_type"] not in VALID_NETWORK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid network_type. Must be one of: {VALID_NETWORK_TYPES}")

    if "tags" in update_data:
        tags = update_data["tags"]
        if len(tags) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 tags allowed")
        for tag in tags:
            if len(tag) > 20:
                raise HTTPException(status_code=400, detail="Tags must be 20 characters or less")
        update_data["tags"] = json.dumps(tags)

    if update_data:
        return await db_client.update_network(network_id, update_data)
    return existing


@app.delete("/networks/{network_id}")
async def delete_network(network_id: str, user: str = Depends(need_auth)):
    """Delete a network."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not await db_client.delete_network(network_id):
        raise HTTPException(status_code=404, detail="Network not found")
    return {"status": "deleted"}


@app.post("/networks/{network_id}/default")
async def set_default_network(network_id: str, user: str = Depends(need_auth)):
    """Set a network as the default."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    existing = await db_client.get_network(network_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Network not found")
    await db_client.set_default_network(network_id)
    return await db_client.get_network(network_id)


@app.post("/devices/{device_id}/network/{network_id}")
async def assign_device_network(device_id: str, network_id: str, user: str = Depends(need_auth)):
    """Assign a device to a network."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    network = await db_client.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    await db_client.set_device_network(device_id, network_id)
    return await db_client.get_device(device_id)


# Topology history endpoint (Phase 6)
@app.get("/topology/history")
async def get_topology_history(
    limit: int = 100,
    event_type: str = None,
    from_time: str = None,
    to_time: str = None,
    offset: int = 0,
    user: str = Depends(need_auth),
):
    """Get topology change history for auditing and trend analysis."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    events = await db_client.get_topology_history(limit, event_type, from_time, to_time, offset)
    total = len(events)  # Simplified; ideally a separate COUNT query
    return {"events": events, "total": total}


@app.get("/topology/snapshot/{event_id}")
async def get_topology_snapshot(event_id: int, user: str = Depends(need_auth)):
    """Get topology nodes+links that existed at a specific history event."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    event = await db_client.get_topology_history(limit=1, offset=event_id - 1)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Return current topology as the "after" snapshot
    topology = await db_client.list_topology()
    return {
        "event": event[0],
        "topology": topology,
    }


# Discovery endpoint
@app.post("/discover")
async def discover_network(request: DiscoveryRequest, user: str = Depends(need_auth)):
    """Discover devices in a network range."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    # Cap the scan range to avoid DoS via 16M-host scan.
    try:
        import ipaddress as _ip
        net = _ip.ip_network(request.network_range, strict=False)
        if net.num_addresses > 4096:
            raise HTTPException(
                status_code=400,
                detail=f"network_range too large ({net.num_addresses} addresses); "
                       "max 4096 hosts per scan (use a smaller CIDR)",
            )
    except ValueError:
        pass

    async def _device_found_emitter(payload: dict) -> None:
        event_type = payload.pop("type", "device_found")
        await broadcast_event(event_type, payload)

    stats = await add_discovered_devices(
        db_client,
        request.network_range,
        request.community,
        timeout=2.0,
        max_concurrent=50,
        method=request.method,
        device_found_event_emitter=_device_found_emitter,
    )

    await broadcast_event("devices_refresh", {"stats": stats, "source": "discover"})
    return stats


class RescanRequest(BaseModel):
    network_range: str
    community: str = "public"
    method: str = "all"
    replace: bool = True
    mode: str = "merge"  # "merge" (Phase 1 default) | "replace" (admin emergency)


@app.post("/discover/rescan")
async def rescan_network(request: RescanRequest, user: str = Depends(need_auth)):
    """Rescan the supplied range.

    mode=merge (Phase 1 default): non-destructive. Preserves manual
        devices, marks missing auto devices offline, emits device_stale
        events for devices offline >= 72h.
    mode=replace: legacy destructive path. Wipes stored devices
        and re-discovers from scratch. Admin-only intent.
    """
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    # Cap the scan range to avoid DoS (16.7M hosts in a /8 is enough to
    # tie up the event loop for days). Mirrors the per-host cap in
    # expand_cidr_hosts but enforced at the API boundary.
    try:
        import ipaddress as _ip
        net = _ip.ip_network(request.network_range, strict=False)
        if net.num_addresses > 4096:
            raise HTTPException(
                status_code=400,
                detail=f"network_range too large ({net.num_addresses} addresses); "
                       "max 4096 hosts per scan (use a smaller CIDR)",
            )
    except ValueError:
        # Not a CIDR — fall through, the underlying scanner will validate
        pass

    async def _stale_emitter(payload: dict) -> None:
        # Fan out via the global SSE event channel.
        await broadcast_event("device_stale", payload)

    async def _device_found_emitter(payload: dict) -> None:
        event_type = payload.pop("type", "device_found")
        await broadcast_event(event_type, payload)

    if request.mode == "replace":
        stats = await rescan_and_replace(
            db_client,
            request.network_range,
            request.community,
            timeout=2.0,
            max_concurrent=50,
            method=request.method,
            device_found_event_emitter=_device_found_emitter,
        )
    else:
        stats = await rescan_and_merge(
            db_client,
            request.network_range,
            request.community,
            timeout=2.0,
            max_concurrent=50,
            method=request.method,
            preserve_manual=True,
            stale_event_emitter=_stale_emitter,
            device_found_event_emitter=_device_found_emitter,
        )

    await broadcast_event(
        "devices_refresh",
        {"stats": stats, "source": "rescan", "network_range": request.network_range},
    )
    return stats


@app.post("/devices/{device_id}/stale-action")
async def stale_device_action(device_id: str, req: StaleActionRequest, user: str = Depends(need_auth)):
    """Handle a stale device user decision: delete or keep."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if req.action not in ("delete", "keep"):
        raise HTTPException(
            status_code=400, detail="action must be 'delete' or 'keep'",
        )
    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if req.action == "delete":
        await db_client.delete_device(device_id)
        await broadcast_event(
            "device_stale", {
                "type": "device_stale_resolved",
                "device_id": device_id,
                "action": "delete",
            },
        )
        return {"success": True, "action": "delete", "device_id": device_id}
    # keep: reset offline_since, mark as manual so future rescans
    # never mark it offline again.
    await db_client.update_device(
        device_id,
        {"offline_since": None, "discovery_method": "manual"},
    )
    await broadcast_event(
        "device_stale", {
            "type": "device_stale_resolved",
            "device_id": device_id,
            "action": "keep",
        },
    )
    return {"success": True, "action": "keep", "device_id": device_id}


@app.get("/events/stream")
async def stream_events(user: str = Depends(need_auth)):
    """Generic SSE feed: devices_refresh, rescan_started, rescan_completed."""

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        event_subscribers.append(queue)
        try:
            yield f"data: {json.dumps({'type': 'hello'})}\n\n"
            while True:
                msg = await queue.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            event_subscribers.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/devices")
async def clear_all_devices(user: str = Depends(need_auth)):
    """Drop every device + orphan topology. Used by 'Reset / Rescan' UI."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    removed = await db_client.clear_all_devices()
    await broadcast_event("devices_refresh", {"stats": {"cleared": removed, "added": 0}, "source": "clear_all"})
    return {"status": "cleared", "removed": removed}


@app.post("/devices/clear-mocks")
async def clear_mock_devices(user: str = Depends(need_auth)):
    """Remove devices inserted by simulate_devices.py / /topology/simulate.

    Heuristic: anything with discovery_method='simulated' or a 192.168.1.x IP and
    name matching the demo set, or any 'Core-Router-*'/'Access-SW-*'/'Firewall-*'
    device. Falls back to clearing every device if nothing else remains.
    """
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    devices = await db_client.list_devices()
    mock_names = {
        "Core-Router-1", "Core-Router-2",
        "Distribution-SW-1", "Distribution-SW-2",
        "Access-SW-1", "Access-SW-2", "Access-SW-3",
        "Firewall-1",
    }

    targets: list[str] = []
    for d in devices:
        name = d.get("name", "") or ""
        ip = d.get("ip_address", "") or ""
        method = d.get("discovery_method", "") or ""
        if method == "simulated":
            targets.append(d.get("id") or ip)
        elif name in mock_names:
            targets.append(d.get("id") or ip)
        elif name.startswith(("Core-Router-", "Distribution-SW-", "Access-SW-", "Firewall-")):
            targets.append(d.get("id") or ip)

    if not targets:
        return {"status": "noop", "removed": 0, "matched": 0}

    removed = await db_client.bulk_delete_devices(targets)
    await broadcast_event(
        "devices_refresh",
        {"stats": {"cleared": removed, "matched": len(targets)}, "source": "clear_mocks"},
    )
    return {"status": "cleared", "matched": len(targets), "removed": removed}


# Poller stats endpoint
@app.get("/stats")
def get_poller_stats(user: str = Depends(need_auth)):
    """Get poller statistics."""
    if not poller:
        raise HTTPException(status_code=503, detail="Poller not initialized")

    return poller.get_stats()


# Alert endpoints
@app.get("/alerts")
async def list_alerts(limit: Optional[int] = None, offset: Optional[int] = None, user: str = Depends(need_auth)):
    """List alert configurations with optional pagination."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_alert_configs(limit=limit, offset=offset)


@app.post("/alerts")
async def create_alert(alert: AlertConfigCreate, user: str = Depends(need_auth)):
    """Create a new alert configuration."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Validate channel
    valid_channels = {"webhook", "slack", "telegram", "whatsapp", "email"}
    if alert.channel not in valid_channels:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported channel. Must be one of: {valid_channels}",
        )

    # Validate integration_id belongs to same channel type, if provided
    if alert.integration_id:
        integration = await db_client.get_integration(alert.integration_id)
        if not integration:
            raise HTTPException(status_code=400, detail="Unknown integration_id")
        if integration.get("type") != alert.channel:
            raise HTTPException(
                status_code=400,
                detail=f"Integration type '{integration.get('type')}' does not match channel '{alert.channel}'",
            )

    # Dedup: same (alert_type, channel, config) means duplicate rule
    existing = await db_client.find_alert_config_by_signature(
        alert.alert_type, alert.channel, alert.config,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "An alert rule with the same alert_type, channel, and config already exists",
                "existing_id": existing["id"],
                "existing_name": existing.get("name"),
            },
        )

    return await db_client.create_alert_config(
        {
            "name": alert.name,
            "alert_type": alert.alert_type,
            "channel": alert.channel,
            "config": alert.config,
            "integration_id": alert.integration_id,
            "enabled": alert.enabled,
            "escalation_minutes": alert.escalation_minutes,
            "escalated_severity": alert.escalated_severity,
        }
    )


@app.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, alert: AlertConfigUpdate, user: str = Depends(need_auth)):
    """Update an existing alert configuration."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    update_data = alert.model_dump(exclude_unset=True)

    if "channel" in update_data:
        valid_channels = {"webhook", "slack", "telegram", "whatsapp", "email"}
        if update_data["channel"] not in valid_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported channel. Must be one of: {valid_channels}",
            )

    if update_data.get("integration_id"):
        integration = await db_client.get_integration(update_data["integration_id"])
        if not integration:
            raise HTTPException(status_code=400, detail="Unknown integration_id")
        target_channel = update_data.get("channel")
        existing = await db_client._get_alert_config(alert_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Alert not found")
        if target_channel is None:
            target_channel = existing.get("channel")
        if integration.get("type") != target_channel:
            raise HTTPException(
                status_code=400,
                detail=f"Integration type '{integration.get('type')}' does not match channel '{target_channel}'",
            )

    # Check dedup if relevant fields change
    if any(k in update_data for k in ("alert_type", "channel", "config")):
        existing = await db_client._get_alert_config(alert_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Alert not found")
        merged_type = update_data.get("alert_type", existing.get("alert_type"))
        merged_channel = update_data.get("channel", existing.get("channel"))
        merged_config = update_data.get("config", existing.get("config_json") or {})
        dup = await db_client.find_alert_config_by_signature(
            merged_type, merged_channel, merged_config, exclude_id=alert_id,
        )
        if dup:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "An alert rule with the same alert_type, channel, and config already exists",
                    "existing_id": dup["id"],
                    "existing_name": dup.get("name"),
                },
            )

    result = await db_client.update_alert_config(alert_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


@app.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, user: str = Depends(need_auth)):
    """Delete an alert configuration and its history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    deleted = await db_client.delete_alert_config(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "deleted", "id": alert_id}


@app.get("/alerts/history")
async def get_alert_history(limit: int = 50, user: str = Depends(need_auth)):
    """Get recent alert history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.get_alert_history(limit)


@app.get("/alerts/active")
async def get_active_alerts(user: str = Depends(need_auth)):
    """Get currently firing (active) alerts."""
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")
    return {"alerts": alert_service.get_active_alerts()}


@app.post("/alerts/active/{alert_key}/acknowledge")
async def acknowledge_alert(alert_key: str, user: str = Depends(need_auth)):
    """Acknowledge an active alert to suppress repeated notifications."""
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")
    success = alert_service.acknowledge_alert(alert_key)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
    return {"status": "acknowledged", "key": alert_key}


@app.post("/alerts/active/{alert_key}/resolve")
async def resolve_alert(alert_key: str, user: str = Depends(need_auth)):
    """Manually resolve an active alert."""
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")
    success = alert_service.resolve_alert(alert_key)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "resolved", "key": alert_key}


# Anomaly Detection Endpoints
@app.get("/anomalies")
async def get_anomalies(user: str = Depends(need_auth)):
    """Get all currently active anomalies."""
    if not anomaly_detector:
        return {"anomalies": []}
    return {"anomalies": await anomaly_detector.get_active_anomalies()}


@app.get("/anomalies/{metric_type}/{target_id}")
async def get_anomaly(metric_type: str, target_id: str, user: str = Depends(need_auth)):
    """Get anomaly status for a specific metric."""
    if not anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detector not initialized")
    anomaly = await anomaly_detector.get_anomaly(metric_type, target_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="No active anomaly")
    return anomaly


@app.get("/anomalies/{metric_type}/{target_id}/baseline")
async def get_baseline(metric_type: str, target_id: str, user: str = Depends(need_auth)):
    """Get baseline statistics for a metric."""
    if not anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detector not initialized")
    baseline = await anomaly_detector.get_baseline(metric_type, target_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Not enough data for baseline")
    return baseline


@app.post("/alerts/{alert_id}/test")
async def test_alert(alert_id: str, user: str = Depends(need_auth)):
    """Send a test alert."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")

    config = await db_client._get_alert_config(alert_id)
    if not config:
        raise HTTPException(status_code=404, detail="Alert config not found")

    from src.api.services.notifications.base import NotificationMessage

    message = NotificationMessage(
        title="Test Alert",
        message="This is a test alert from NetOps",
        severity="info",
        alert_type="test",
    )

    channel = await alert_service.get_notification_channel(
        config["channel"],
        config["config_json"],
        integration_id=config.get("integration_id"),
        db_client=db_client,
    )
    if not channel:
        raise HTTPException(status_code=400, detail="Invalid channel type")

    valid, error = channel.validate_config()
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid config: {error}")

    try:
        if config["channel"].lower() == "email":
            success = channel.send(message)
        else:
            success = await channel.send(message)

        return {"sent": success, "channel": config["channel"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Integration endpoints
@app.get("/integrations")
async def list_integrations(type: Optional[str] = None, user: str = Depends(need_auth)):
    """List integrations, optionally filtered by type."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.list_integrations(type=type)


@app.post("/integrations")
async def create_integration(data: IntegrationCreate, user: str = Depends(need_auth)):
    """Create a new integration (Telegram bot, Slack webhook, etc.)."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    try:
        return await db_client.create_integration({
            "type": data.type,
            "name": data.name,
            "secrets_json": data.secrets_json,
            "enabled": data.enabled,
        })
    except Exception as e:
        if "UNIQUE" in str(e) or "unique" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"An integration of type '{data.type}' with name '{data.name}' already exists",
            )
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/integrations/{integration_id}")
async def get_integration(integration_id: str, user: str = Depends(need_auth)):
    """Get a single integration by ID."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    result = await db_client.get_integration(integration_id)
    if not result:
        raise HTTPException(status_code=404, detail="Integration not found")
    return result


@app.put("/integrations/{integration_id}")
async def update_integration(integration_id: str, data: IntegrationUpdate, user: str = Depends(need_auth)):
    """Update an existing integration."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    update_data = data.model_dump(exclude_unset=True)
    if "type" in update_data:
        valid_types = {"webhook", "slack", "telegram", "whatsapp", "email"}
        if update_data["type"] not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported integration type. Must be one of: {valid_types}",
            )
    try:
        result = await db_client.update_integration(integration_id, update_data)
    except Exception as e:
        if "UNIQUE" in str(e) or "unique" in str(e):
            raise HTTPException(status_code=409, detail="Name collision with existing integration")
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Integration not found")
    return result


@app.delete("/integrations/{integration_id}")
async def delete_integration(integration_id: str, user: str = Depends(need_auth)):
    """Delete an integration. Blocked if alert rules reference it."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    success, err = await db_client.delete_integration(integration_id)
    if not success:
        if err == "not found":
            raise HTTPException(status_code=404, detail="Integration not found")
        raise HTTPException(status_code=409, detail=err)
    return {"status": "deleted", "id": integration_id}


@app.post("/integrations/{integration_id}/test")
async def test_integration(integration_id: str, user: str = Depends(need_auth)):
    """Send a test message through the integration."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")

    integration = await db_client.get_integration(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    from src.api.services.notifications.base import NotificationMessage

    message = NotificationMessage(
        title="NetOps Integration Test",
        message="This is a test from NetOps. If you see this, the integration is configured correctly.",
        severity="info",
        alert_type="integration_test",
    )

    channel = await alert_service.get_notification_channel(
        integration["type"],
        integration.get("secrets_json") or {},
        db_client=db_client,
    )
    if not channel:
        raise HTTPException(status_code=400, detail="Invalid integration type")

    valid, error = channel.validate_config()
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid config: {error}")

    try:
        if integration["type"].lower() == "email":
            success = channel.send(message)
        else:
            success = await channel.send(message)
        return {"sent": success, "type": integration["type"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Maintenance Windows endpoints
class MaintenanceWindowCreate(BaseModel):
    name: str
    start_time: str = Field(..., description="ISO 8601 datetime")
    end_time: str = Field(..., description="ISO 8601 datetime")
    description: str = ""


@app.get("/maintenance-windows")
async def list_maintenance_windows(user: str = Depends(need_auth)):
    """List all maintenance windows."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"windows": await db_client.list_maintenance_windows()}


@app.post("/maintenance-windows")
async def create_maintenance_window(window: MaintenanceWindowCreate, user: str = Depends(need_auth)):
    """Create a new maintenance window."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    from datetime import datetime
    try:
        datetime.fromisoformat(window.start_time.replace("Z", "+00:00"))
        datetime.fromisoformat(window.end_time.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO 8601.")
    data = await db_client.create_maintenance_window(window.model_dump())
    return {"status": "created", "window": data}


@app.delete("/maintenance-windows/{window_id}")
async def delete_maintenance_window(window_id: str, user: str = Depends(need_auth)):
    """Delete a maintenance window."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    success = await db_client.delete_maintenance_window(window_id)
    if not success:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    return {"status": "deleted", "id": window_id}


# Poll history endpoint
@app.get("/poll-history")
async def get_poll_history(limit: int = 100, user: str = Depends(need_auth)):
    """Get recent poll history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.get_poll_history(limit)


# Service Check endpoints
class ServiceCheckCreate(BaseModel):
    name: str
    check_type: str = Field(..., description="Type: http, tcp, dns, ping, ssl")
    target: str
    interval_seconds: Optional[int] = None  # None -> apply Phase 2 type default
    timeout_seconds: int = 10
    enabled: bool = True
    config: dict[str, Any] = {}

    @field_validator("interval_seconds", mode="before")
    @classmethod
    def apply_type_default(cls, v, info):
        if v is not None:
            return v
        from .checks.base import default_interval_for
        check_type = (info.data or {}).get("check_type", "http")
        return default_interval_for(check_type)


class ServiceCheckUpdate(BaseModel):
    name: Optional[str] = None
    interval_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    config: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


@app.get("/checks")
async def list_service_checks(limit: Optional[int] = None, offset: Optional[int] = None, user: str = Depends(need_auth)):
    """List service checks with optional pagination."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_service_checks(limit=limit, offset=offset)


@app.get("/api/checks/defaults")
async def get_check_defaults(user: str = Depends(need_auth)):
    """Phase 2: return current profile's per-type check interval defaults.

    Reads the per-key `check_intervals` row from app_settings; if
    missing, falls back to the static `DEFAULT_CHECK_INTERVALS`.
    """
    from .checks.base import DEFAULT_CHECK_INTERVALS
    if not db_client:
        return {"defaults": DEFAULT_CHECK_INTERVALS}
    profile = "homelab"
    intervals = DEFAULT_CHECK_INTERVALS.copy()
    if hasattr(db_client, "get_setting"):
        try:
            v = await db_client.get_setting("check_intervals")
            if isinstance(v, dict) and v:
                intervals.update({k: int(v[k]) for k in v if isinstance(v[k], (int, float))})
            p = await db_client.get_setting("profile")
            if isinstance(p, str) and p:
                profile = p
        except Exception:
            pass
    return {"profile": profile, "defaults": intervals}


@app.get("/checks/{check_id}")
async def get_service_check(check_id: str, user: str = Depends(need_auth)):
    """Get a specific service check."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    check = await db_client.get_service_check(check_id)
    if not check:
        raise HTTPException(status_code=404, detail="Service check not found")

    return check


@app.post("/checks")
async def create_service_check(check: ServiceCheckCreate, user: str = Depends(need_auth)):
    """Create a new service check."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Validate check type
    valid_types = {"http", "tcp", "dns", "ping", "ssl"}
    if check.check_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid check type. Must be one of: {valid_types}",
        )

    result = await db_client.create_service_check(
        {
            "name": check.name,
            "check_type": check.check_type,
            "target": check.target,
            "interval_seconds": check.interval_seconds,
            "timeout_seconds": check.timeout_seconds,
            "config": check.config,
            "enabled": check.enabled,
        }
    )

    # Add to scheduler if enabled
    if check_scheduler and result:
        from src.collector.checks.base import CheckDefinition

        definition = CheckDefinition(
            id=result["id"],
            name=result["name"],
            check_type=result["check_type"],
            target=result["target"],
            interval_seconds=result["interval_seconds"],
            timeout_seconds=result["timeout_seconds"],
            enabled=result["enabled"],
            config=result.get("config_json", {}),
        )
        check_scheduler.add_check(definition)

    return result


@app.put("/checks/{check_id}")
async def update_service_check(check_id: str, check: ServiceCheckUpdate, user: str = Depends(need_auth)):
    """Update an existing service check."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    existing = await db_client.get_service_check(check_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Service check not found")

    update_data = {k: v for k, v in check.model_dump().items() if v is not None}
    result = await db_client.update_service_check(check_id, update_data)

    # Update scheduler if enabled status changed
    if check_scheduler and result:
        if check.enabled is False:
            check_scheduler.remove_check(check_id)
        elif check.enabled is True:
            from src.collector.checks.base import CheckDefinition

            definition = CheckDefinition(
                id=result["id"],
                name=result["name"],
                check_type=result["check_type"],
                target=result["target"],
                interval_seconds=result["interval_seconds"],
                timeout_seconds=result["timeout_seconds"],
                enabled=result["enabled"],
                config=result.get("config_json", {}),
            )
            check_scheduler.add_check(definition)

    return result


@app.delete("/checks/{check_id}")
async def delete_service_check(check_id: str, user: str = Depends(need_auth)):
    """Delete a service check."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Remove from scheduler first
    if check_scheduler:
        check_scheduler.remove_check(check_id)

    if not await db_client.delete_service_check(check_id):
        raise HTTPException(status_code=404, detail="Service check not found")

    return {"status": "deleted"}


@app.post("/checks/{check_id}/run")
async def run_service_check_now(check_id: str, user: str = Depends(need_auth)):
    """Run a service check immediately."""
    if not check_scheduler:
        raise HTTPException(status_code=503, detail="Check scheduler not initialized")

    result = await check_scheduler.run_check_now(check_id)
    if not result:
        raise HTTPException(status_code=404, detail="Service check not found")

    return {
        "target_id": result.target_id,
        "check_type": result.check_type,
        "status": result.status.value,
        "response_time_ms": result.response_time_ms,
        "message": result.message,
        "details": result.details,
        "error": result.error,
    }


@app.get("/checks/{check_id}/results")
async def get_check_results(check_id: str, limit: int = 100, user: str = Depends(need_auth)):
    """Get recent check results."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.get_check_results(check_id, limit)


@app.get("/checks/stats")
async def get_check_stats(user: str = Depends(need_auth)):
    """Get check scheduler statistics."""
    if not check_scheduler:
        raise HTTPException(status_code=503, detail="Check scheduler not initialized")

    return check_scheduler.get_stats()
