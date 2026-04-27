"""NetOps FastAPI Application - Network topology discovery and monitoring."""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import ServerConfig
from .discovery import add_discovered_devices
from .snmp_poller import SNMPPoller
from .topology_builder import TopologyBuilder
from .utils import logger

# Global state
poller: Optional[SNMPPoller] = None
db_client: Optional[Any] = None
topology_subscribers: list[asyncio.Queue] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global poller, db_client

    # Startup
    logger.info("Starting NetOps API server...")

    # Initialize database client
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from src.pb.client import EmbeddedPocketBase

    db_client = EmbeddedPocketBase(db_path="./data/netops.db")
    logger.info("Database initialized at ./data/netops.db")

    # Initialize and start poller
    poller = SNMPPoller(db_client, poll_interval=30)
    poller.set_topology_change_handler(on_topology_change)
    await poller.start()
    logger.info("SNMP poller started with 30s interval")

    yield

    # Shutdown
    logger.info("Shutting down NetOps API server...")
    if poller:
        await poller.stop()
    if db_client:
        db_client.close()


async def on_topology_change(changes: dict[str, int], topology: dict[str, list]):
    """Handle topology changes - notify subscribers."""
    message = json.dumps({"type": "topology_change", "changes": changes, "topology": topology})
    for queue in topology_subscribers:
        await queue.put(message)


app = FastAPI(
    title="NetOps API",
    description="Network topology discovery and monitoring",
    version="0.1.0",
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
    alert_type: str  # device_down, link_down, topology_change
    channel: str  # webhook, email, slack, discord
    config: dict[str, Any] = {}
    enabled: bool = True


class DiscoveryRequest(BaseModel):
    network_range: str
    community: str = "public"


# Health endpoint
@app.get("/health")
def health_check():
    """Health check endpoint."""
    result = {"status": "ok"}
    if poller:
        result["poller"] = poller.get_stats()
    return result


# Topology endpoints
@app.get("/topology")
def get_topology():
    """Get current network topology."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    topology = db_client.list_topology()
    return topology


@app.get("/topology/stream")
async def stream_topology():
    """Stream topology updates via Server-Sent Events."""

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        topology_subscribers.append(queue)

        try:
            # Send initial topology
            current = db_client.list_topology() if db_client else {"nodes": [], "links": []}
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
    return {"status": "refreshed", "topology": db_client.list_topology() if db_client else {}}


# Device endpoints
@app.get("/devices")
def list_devices():
    """List all configured devices."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return db_client.list_devices()


@app.get("/devices/{device_id}")
def get_device(device_id: str):
    """Get a specific device by ID or IP."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    device = db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@app.post("/devices")
def create_device(device: DeviceCreate):
    """Add a new device to monitor."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Check if device already exists
    existing = db_client.get_device(device.ip_address)
    if existing:
        raise HTTPException(status_code=409, detail="Device already exists")

    return db_client.create_device(
        {
            "name": device.name,
            "ip_address": device.ip_address,
            "community": device.community,
            "status": "unknown",
        }
    )


@app.put("/devices/{device_id}")
def update_device(device_id: str, device: DeviceUpdate):
    """Update an existing device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    existing = db_client.get_device(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = {k: v for k, v in device.model_dump().items() if v is not None}
    return db_client.update_device(device_id, update_data)


@app.delete("/devices/{device_id}")
def delete_device(device_id: str):
    """Delete a device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    if not db_client.delete_device(device_id):
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
def list_alerts():
    """List all alert configurations."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return db_client.list_alert_configs()


@app.post("/alerts")
def create_alert(alert: AlertConfigCreate):
    """Create a new alert configuration."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    return db_client.create_alert_config(
        {
            "name": alert.name,
            "alert_type": alert.alert_type,
            "channel": alert.channel,
            "config": alert.config,
            "enabled": alert.enabled,
        }
    )


# Poll history endpoint
@app.get("/poll-history")
def get_poll_history(limit: int = 100):
    """Get recent poll history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    conn = db_client.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ph.*, d.ip_address, d.name
        FROM poll_history ph
        LEFT JOIN devices d ON ph.device_id = d.id
        ORDER BY ph.polled_at DESC
        LIMIT ?
    """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# Import sqlite3 for poll history
import sqlite3
