"""NetOps FastAPI Application - Network topology discovery and monitoring."""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field

from .config import ServerConfig
from .discovery import add_discovered_devices
from .snmp_poller import SNMPPoller
from .topology_builder import TopologyBuilder
from .utils import logger

# Prometheus metrics
METRICS_POLLS = Counter("netops_polls_total", "Total number of SNMP polls")
METRICS_TOPOLOGY_CHANGES = Counter("netops_topology_changes_total", "Total topology changes")
METRICS_DEVICES = Gauge("netops_devices_total", "Total number of monitored devices")
METRICS_CHECKS = Gauge("netops_service_checks_total", "Total number of service checks")
METRICS_ALERTS = Gauge("netops_alerts_total", "Total number of alert configurations")

# Global state
poller: Optional[SNMPPoller] = None
check_scheduler: Optional[Any] = None
db_client: Optional[Any] = None
alert_service: Optional[Any] = None
topology_subscribers: list[asyncio.Queue] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global poller, check_scheduler, db_client, alert_service

    # Startup
    logger.info("Starting NetOps API server...")

    # Initialize database client (PostgreSQL with SQLite fallback)
    try:
        from src.storage.database import AsyncPostgresClient

        db_client = AsyncPostgresClient()
        await db_client.connect()
        await db_client.init_db()
        logger.info("PostgreSQL database initialized")
    except Exception as e:
        logger.warning(f"PostgreSQL not available ({e}), falling back to SQLite")
        from src.storage.sqlite_client import AsyncSQLiteClient

        db_client = AsyncSQLiteClient()
        await db_client.connect()
        await db_client.init_db()
        logger.info("SQLite database initialized at ./data/netops.db")

    # Initialize alert service
    from src.api.services.alert_service import AlertService

    alert_service = AlertService(db_client)
    logger.info("Alert service initialized")

    # Initialize and start poller
    poller = SNMPPoller(db_client, poll_interval=30)
    poller.set_topology_change_handler(on_topology_change)
    await poller.start()
    logger.info("SNMP poller started with 30s interval")

    # Initialize and start service check scheduler
    from src.collector.checks.scheduler import CheckScheduler

    check_scheduler = CheckScheduler(db_client)
    check_scheduler.set_check_result_handler(on_check_result)
    await check_scheduler.start()
    logger.info("Service check scheduler initialized")

    yield

    # Shutdown
    logger.info("Shutting down NetOps API server...")
    if poller:
        await poller.stop()
    if check_scheduler:
        await check_scheduler.stop()
    if db_client:
        await db_client.close()


async def on_check_result(result: Any):
    """Handle service check results."""
    # Evaluate and dispatch alerts based on check results
    if alert_service and result:
        await alert_service.on_check_result(result)


async def on_topology_change(changes: dict[str, int], topology: dict[str, list]):
    """Handle topology changes - notify subscribers and dispatch alerts."""
    # Notify SSE subscribers (only serialize if there are subscribers)
    if topology_subscribers:
        message = json.dumps({"type": "topology_change", "changes": changes, "topology": topology})
        # Fan out to all subscribers concurrently
        await asyncio.gather(
            *[queue.put(message) for queue in topology_subscribers],
            return_exceptions=True,
        )

    # Dispatch alerts
    if alert_service:
        await alert_service.on_topology_change(changes, topology)


# Request/Response models
class DeviceCreate(BaseModel):
    name: str
    ip_address: str
    community: str = "public"


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    community: Optional[str] = None
    status: Optional[str] = None


class AlertConfigCreate(BaseModel):
    name: str
    alert_type: str = Field(..., description="Type: device_down, device_up, link_down, topology_change")
    channel: str = Field(..., description="Channel: webhook, slack, telegram, whatsapp, email")
    config: dict[str, Any] = {}
    enabled: bool = True

    def model_validate(self, values):
        """Validate channel is supported."""
        valid_channels = {"webhook", "slack", "telegram", "whatsapp", "email"}
        if values.get("channel") not in valid_channels:
            raise ValueError(f"Unsupported channel. Must be one of: {valid_channels}")
        return super().model_validate(values)


class DiscoveryRequest(BaseModel):
    network_range: str
    community: str = "public"
    method: str = "all"


app = FastAPI(
    title="NetOps API",
    description="Network topology discovery and monitoring",
    version="0.5.0",
    lifespan=lifespan,
)

# Health endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    result = {"status": "ok"}
    if poller:
        result["poller"] = poller.get_stats()
    if alert_service:
        result["alert_service"] = {"initialized": True}
    return result


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
async def get_topology():
    """Get current network topology."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    topology = await db_client.list_topology()
    return topology


@app.get("/topology/stream")
async def stream_topology(delta: bool = False):
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
async def refresh_topology():
    """Trigger an immediate topology poll."""
    if not poller:
        raise HTTPException(status_code=503, detail="Poller not initialized")

    await poller.poll_now()
    return {"status": "refreshed", "topology": await db_client.list_topology() if db_client else {}}


@app.post("/topology/simulate")
async def simulate_topology():
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
    nodes = []
    for dev in simulated_devices:
        node_type = "router" if "Router" in dev["name"] else "firewall" if "Firewall" in dev["name"] else "switch"
        nodes.append({
            "id": dev["ip_address"],
            "device_id": dev["ip_address"],
            "label": dev["name"],
            "node_type": node_type,
            "status": "online",
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
async def list_devices(limit: Optional[int] = None, offset: Optional[int] = None):
    """List configured devices with optional pagination."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_devices(limit=limit, offset=offset)


@app.get("/devices/{device_id}")
async def get_device(device_id: str):
    """Get a specific device by ID or IP."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@app.post("/devices")
async def create_device(device: DeviceCreate):
    """Add a new device to monitor."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Check if device already exists
    existing = await db_client.get_device(device.ip_address)
    if existing:
        raise HTTPException(status_code=409, detail="Device already exists")

    return await db_client.create_device(
        {
            "name": device.name,
            "ip_address": device.ip_address,
            "community": device.community,
            "status": "unknown",
        }
    )


@app.put("/devices/{device_id}")
async def update_device(device_id: str, device: DeviceUpdate):
    """Update an existing device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    existing = await db_client.get_device(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = {k: v for k, v in device.model_dump().items() if v is not None}
    return await db_client.update_device(device_id, update_data)


@app.delete("/devices/{device_id}")
async def delete_device(device_id: str):
    """Delete a device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    if not await db_client.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    return {"status": "deleted"}


# Topology history endpoint (Phase 6)
@app.get("/topology/history")
async def get_topology_history(limit: int = 100):
    """Get topology change history for auditing and trend analysis."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return {"events": await db_client.get_topology_history(limit)}


# Discovery endpoint
@app.post("/discover")
async def discover_network(request: DiscoveryRequest):
    """Discover devices in a network range."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    stats = await add_discovered_devices(
        db_client,
        request.network_range,
        request.community,
        timeout=2.0,
        max_concurrent=50,
        method=request.method,
    )

    return stats


# Poller stats endpoint
@app.get("/stats")
def get_poller_stats():
    """Get poller statistics."""
    if not poller:
        raise HTTPException(status_code=503, detail="Poller not initialized")

    return poller.get_stats()


# Alert endpoints
@app.get("/alerts")
async def list_alerts(limit: Optional[int] = None, offset: Optional[int] = None):
    """List alert configurations with optional pagination."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_alert_configs(limit=limit, offset=offset)


@app.post("/alerts")
async def create_alert(alert: AlertConfigCreate):
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

    return await db_client.create_alert_config(
        {
            "name": alert.name,
            "alert_type": alert.alert_type,
            "channel": alert.channel,
            "config": alert.config,
            "enabled": alert.enabled,
        }
    )


@app.get("/alerts/history")
async def get_alert_history(limit: int = 50):
    """Get recent alert history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.get_alert_history(limit)


@app.get("/alerts/active")
async def get_active_alerts():
    """Get currently firing (active) alerts."""
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")
    return {"alerts": alert_service.get_active_alerts()}


@app.post("/alerts/active/{alert_key}/acknowledge")
async def acknowledge_alert(alert_key: str):
    """Acknowledge an active alert to suppress repeated notifications."""
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")
    success = alert_service.acknowledge_alert(alert_key)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
    return {"status": "acknowledged", "key": alert_key}


@app.post("/alerts/active/{alert_key}/resolve")
async def resolve_alert(alert_key: str):
    """Manually resolve an active alert."""
    if not alert_service:
        raise HTTPException(status_code=503, detail="Alert service not initialized")
    success = alert_service.resolve_alert(alert_key)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "resolved", "key": alert_key}


@app.post("/alerts/{alert_id}/test")
async def test_alert(alert_id: str):
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

    channel = alert_service.get_notification_channel(config["channel"], config["config_json"])
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


# Maintenance Windows endpoints
class MaintenanceWindowCreate(BaseModel):
    name: str
    start_time: str = Field(..., description="ISO 8601 datetime")
    end_time: str = Field(..., description="ISO 8601 datetime")
    description: str = ""


@app.get("/maintenance-windows")
async def list_maintenance_windows():
    """List all maintenance windows."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"windows": await db_client.list_maintenance_windows()}


@app.post("/maintenance-windows")
async def create_maintenance_window(window: MaintenanceWindowCreate):
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
async def delete_maintenance_window(window_id: str):
    """Delete a maintenance window."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    success = await db_client.delete_maintenance_window(window_id)
    if not success:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    return {"status": "deleted", "id": window_id}


# Poll history endpoint
@app.get("/poll-history")
async def get_poll_history(limit: int = 100):
    """Get recent poll history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.get_poll_history(limit)


# Service Check endpoints
class ServiceCheckCreate(BaseModel):
    name: str
    check_type: str = Field(..., description="Type: http, tcp, dns, ping, ssl")
    target: str
    interval_seconds: int = 60
    timeout_seconds: int = 10
    config: dict[str, Any] = {}
    enabled: bool = True


class ServiceCheckUpdate(BaseModel):
    name: Optional[str] = None
    interval_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    config: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


@app.get("/checks")
async def list_service_checks(limit: Optional[int] = None, offset: Optional[int] = None):
    """List service checks with optional pagination."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_service_checks(limit=limit, offset=offset)


@app.get("/checks/{check_id}")
async def get_service_check(check_id: str):
    """Get a specific service check."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    check = await db_client.get_service_check(check_id)
    if not check:
        raise HTTPException(status_code=404, detail="Service check not found")

    return check


@app.post("/checks")
async def create_service_check(check: ServiceCheckCreate):
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
async def update_service_check(check_id: str, check: ServiceCheckUpdate):
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
async def delete_service_check(check_id: str):
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
async def run_service_check_now(check_id: str):
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
async def get_check_results(check_id: str, limit: int = 100):
    """Get recent check results."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.get_check_results(check_id, limit)


@app.get("/checks/stats")
async def get_check_stats():
    """Get check scheduler statistics."""
    if not check_scheduler:
        raise HTTPException(status_code=503, detail="Check scheduler not initialized")

    return check_scheduler.get_stats()
