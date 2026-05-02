"""NetOps FastAPI Application - Network topology discovery and monitoring."""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import ServerConfig
from .discovery import add_discovered_devices
from .snmp_poller import SNMPPoller
from .topology_builder import TopologyBuilder
from .utils import logger

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
    # Notify SSE subscribers
    message = json.dumps({"type": "topology_change", "changes": changes, "topology": topology})
    for queue in topology_subscribers:
        await queue.put(message)

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


app = FastAPI(
    title="NetOps API",
    description="Network topology discovery and monitoring",
    version="0.2.0",
    lifespan=lifespan,
)


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


# Topology endpoints
@app.get("/topology")
async def get_topology():
    """Get current network topology."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    topology = await db_client.list_topology()
    return topology


@app.get("/topology/stream")
async def stream_topology():
    """Stream topology updates via Server-Sent Events."""

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        topology_subscribers.append(queue)

        try:
            # Send initial topology
            current = await db_client.list_topology() if db_client else {"nodes": [], "links": []}
            yield f"data: {json.dumps({'type': 'initial', 'topology': current})}\n\n"

            # Stream updates
            while True:
                message = await queue.get()
                yield f"data: {message}\n\n"
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


# Device endpoints
@app.get("/devices")
async def list_devices():
    """List all configured devices."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_devices()


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
async def list_alerts():
    """List all alert configurations."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_alert_configs()


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

    async with db_client._get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT ah.*, ac.name as alert_name, ac.channel
            FROM alert_history ah
            LEFT JOIN alert_configs ac ON ah.alert_config_id = ac.id
            ORDER BY ah.triggered_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]


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


# Poll history endpoint
@app.get("/poll-history")
async def get_poll_history(limit: int = 100):
    """Get recent poll history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    async with db_client._get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT ph.*, d.ip_address, d.name
            FROM poll_history ph
            LEFT JOIN devices d ON ph.device_id = d.id
            ORDER BY ph.polled_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]


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
async def list_service_checks():
    """List all service checks."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return await db_client.list_service_checks()


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
