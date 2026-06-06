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

from .config import ServerConfig
from .discovery import add_discovered_devices, rescan_and_replace
from .host_detect import detect_host_network
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

# Global state
poller: Optional[SNMPPoller] = None
check_scheduler: Optional[Any] = None
db_client: Optional[Any] = None
alert_service: Optional[Any] = None
topology_subscribers: list[asyncio.Queue] = []
event_subscribers: list[asyncio.Queue] = []


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
    global poller, check_scheduler, db_client, alert_service

    # Startup
    logger.info("Starting NetOps API server...")

    # Auto-migrate: run Alembic upgrade head on startup (env-gated).
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
    # Priority (Phase 3 contract):
    #   1. `DATABASE_URL` env var -> PostgreSQL only, fail-fast on
    #      connection error (silent fallback is dangerous in prod).
    #   2. No DATABASE_URL -> try PG with POSTGRES_* defaults, then
    #      fall back to SQLite (with a warning log).
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        from src.storage.database import AsyncPostgresClient
        try:
            db_client = AsyncPostgresClient(connection_string=database_url)
            await db_client.connect()
            await db_client.init_db()
            logger.info("PostgreSQL connected via DATABASE_URL")
        except Exception as e:
            logger.error(f"DATABASE_URL set but PostgreSQL unavailable: {e}")
            raise RuntimeError(
                f"DATABASE_URL is set but PostgreSQL is unreachable: {e}"
            )
    else:
        try:
            from src.storage.database import AsyncPostgresClient
            db_client = AsyncPostgresClient()
            await db_client.connect()
            await db_client.init_db()
            logger.info("PostgreSQL connected with defaults")
        except Exception as e:
            logger.warning(f"PostgreSQL not available ({e}), falling back to SQLite")
            from src.storage.sqlite_client import AsyncSQLiteClient
            sqlite_path = os.environ.get("NETOPS_SQLITE_PATH", "./data/netops.db")
            db_client = AsyncSQLiteClient(db_path=sqlite_path)
            await db_client.connect()
            await db_client.init_db()
            logger.info(f"SQLite database initialized at {sqlite_path}")

    # Initialize alert service
    from src.api.services.alert_service import AlertService

    alert_service = AlertService(db_client)
    logger.info("Alert service initialized")

    # Bootstrap default admin user if none exists
    try:
        admin = await db_client.get_user_by_username("admin")
        if not admin:
            await db_client.create_user("admin", hash_password("admin"))
            logger.info("Default admin user created (admin / admin)")
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

    # Read config from DB, fall back to defaults
    config = {}
    try:
        config = await db_client.get_settings()
    except Exception:
        pass

    poll_interval = int(config.get("topology_interval", 30))
    snmp_timeout = int(config.get("snmp_timeout", 5))
    snmp_retries = int(config.get("snmp_retries", 3))

    # Initialize and start poller
    poller = SNMPPoller(db_client, poll_interval=poll_interval, timeout=snmp_timeout, retries=snmp_retries)
    poller.set_topology_change_handler(on_topology_change)
    await poller.start()
    logger.info(f"SNMP poller started with {poll_interval}s interval, timeout={snmp_timeout}s, retries={snmp_retries}")

    # Initialize and start service check scheduler
    from src.collector.checks.scheduler import CheckScheduler

    check_scheduler = CheckScheduler(db_client)
    check_scheduler.set_check_result_handler(on_check_result)
    await check_scheduler.start()
    logger.info("Service check scheduler initialized")

    # Auto-discover: detect host network, wipe stale mocks, scan for real devices
    async def _startup_auto_discover():
        try:
            host_info = await detect_host_network()
            host_ip = host_info.get("host_ip")
            cidr = host_info.get("cidr", "192.168.1.0/24")
            hostname = host_info.get("hostname") or "Current Device"
            gateway = host_info.get("gateway")

            logger.info(f"Host detected: {hostname} @ {host_ip}, CIDR {cidr}, gateway {gateway}")

            # Wipe stale mock/simulated devices and orphan topology
            existing = await db_client.list_devices()
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

            # Ensure host device exists in DB
            if host_ip:
                existing_host = await db_client.get_device(host_ip)
                if not existing_host:
                    await db_client.create_device({
                        "ip_address": host_ip,
                        "name": hostname,
                        "status": "online",
                        "discovery_method": "auto",
                        "sys_descr": f"NetOps host ({hostname})",
                    })
                    logger.info(f"Registered host device {hostname} ({host_ip})")

            # Fire background rescan on detected CIDR
            await broadcast_event("rescan_started", {"network_range": cidr, "source": "startup"})
            stats = await rescan_and_replace(db_client, cidr, timeout=2.0, max_concurrent=50, method="all")
            logger.info(f"Auto-rescan {cidr}: found {stats.get('found', 0)}, added {stats.get('added', 0)}")

            # Re-register host after rescan (rescan wipes all devices)
            if host_ip:
                existing_host = await db_client.get_device(host_ip)
                if not existing_host:
                    await db_client.create_device({
                        "ip_address": host_ip,
                        "name": hostname,
                        "status": "online",
                        "discovery_method": "auto",
                        "sys_descr": f"NetOps host ({hostname})",
                    })

            # Add gateway if discovered but missing
            if gateway:
                gw_existing = await db_client.get_device(gateway)
                if not gw_existing:
                    await db_client.create_device({
                        "ip_address": gateway,
                        "name": f"Gateway ({gateway})",
                        "status": "online",
                        "discovery_method": "auto",
                        "sys_descr": "Default gateway",
                    })

            await broadcast_event("devices_refresh", {"stats": stats, "source": "startup_auto"})
        except Exception as e:
            logger.warning(f"Startup auto-discover failed: {e}")

    asyncio.create_task(_startup_auto_discover())

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
    username: str
    password: str


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
    topology_interval: Optional[int] = None
    check_interval: Optional[int] = None
    snmp_timeout: Optional[int] = None
    snmp_retries: Optional[int] = None
    snmp_community: Optional[str] = None


@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    user = await db_client.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(req.username)
    resp = JSONResponse({"token": token, "username": req.username, "role": user.get("role", "admin")})
    resp.set_cookie("token", token, httponly=True, samesite="lax", max_age=86400)
    return resp


@app.post("/api/auth/signup", status_code=201)
async def auth_signup(req: SignupRequest):
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
            "token": token,
            "username": user["username"],
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role", "admin"),
        },
    )
    resp.set_cookie("token", token, httponly=True, samesite="lax", max_age=86400)
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


@app.get("/api/config")
async def get_config(user: str = Depends(need_auth)):
    if not db_client:
        raise HTTPException(status_code=503)
    return await db_client.get_settings()


@app.put("/api/config")
async def save_config(cfg: ConfigUpdate, user: str = Depends(need_auth)):
    if not db_client:
        raise HTTPException(status_code=503)
    existing = await db_client.get_settings()
    for key in ("topology_interval", "check_interval", "snmp_timeout", "snmp_retries", "snmp_community"):
        v = getattr(cfg, key, None)
        if v is not None:
            existing[key] = v
    await db_client.update_settings(existing)
    return {"saved": True, "config": existing}


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

    existing = await db_client.get_device(device.ip_address)
    if existing:
        raise HTTPException(status_code=409, detail="Device already exists")

    return await db_client.create_device(device.model_dump() | {"status": "unknown"})


@app.post("/devices/import")
async def bulk_import(req: BulkImportRequest):
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


# Network endpoints
@app.get("/networks")
async def list_networks():
    """List all networks."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.list_networks()


@app.get("/networks/{network_id}")
async def get_network(network_id: str):
    """Get network by ID."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    network = await db_client.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return network


@app.post("/networks")
async def create_network(network: NetworkCreate):
    """Create a new network."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    created = await db_client.create_network(network.model_dump())

    # If the network has a CIDR, auto-rescan it in the background and
    # emit a devices_refresh SSE event when discovery finishes.
    cidr = (created or {}).get("cidr")
    if cidr:
        async def _auto_scan():
            try:
                await broadcast_event(
                    "rescan_started",
                    {"network_range": cidr, "network_id": created.get("id")},
                )
                stats = await add_discovered_devices(
                    db_client, cidr, timeout=2.0, max_concurrent=50, method="all"
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
async def update_network(network_id: str, network: NetworkUpdate):
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
async def delete_network(network_id: str):
    """Delete a network."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    if not await db_client.delete_network(network_id):
        raise HTTPException(status_code=404, detail="Network not found")
    return {"status": "deleted"}


@app.post("/networks/{network_id}/default")
async def set_default_network(network_id: str):
    """Set a network as the default."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    existing = await db_client.get_network(network_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Network not found")
    await db_client.set_default_network(network_id)
    return await db_client.get_network(network_id)


@app.post("/devices/{device_id}/network/{network_id}")
async def assign_device_network(device_id: str, network_id: str):
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
):
    """Get topology change history for auditing and trend analysis."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    events = await db_client.get_topology_history(limit, event_type, from_time, to_time, offset)
    total = len(events)  # Simplified; ideally a separate COUNT query
    return {"events": events, "total": total}


@app.get("/topology/snapshot/{event_id}")
async def get_topology_snapshot(event_id: int):
    """Get topology nodes+links that existed at a specific history event."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    event = await db_client.get_topology_history(limit=1, offset=event_id - 1)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Return current topology as the "after" snapshot
    nodes = await db_client.get_topology_nodes()
    links = await db_client.get_topology_links()
    return {
        "event": event[0],
        "topology": {"nodes": nodes, "links": links},
    }


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

    await broadcast_event("devices_refresh", {"stats": stats, "source": "discover"})
    return stats


class RescanRequest(BaseModel):
    network_range: str
    community: str = "public"
    method: str = "all"
    replace: bool = True


@app.post("/discover/rescan")
async def rescan_network(request: RescanRequest):
    """Wipe stored devices/topology, then rediscover the supplied range."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    if request.replace:
        stats = await rescan_and_replace(
            db_client,
            request.network_range,
            request.community,
            timeout=2.0,
            max_concurrent=50,
            method=request.method,
        )
    else:
        stats = await add_discovered_devices(
            db_client,
            request.network_range,
            request.community,
            timeout=2.0,
            max_concurrent=50,
            method=request.method,
        )

    await broadcast_event(
        "devices_refresh",
        {"stats": stats, "source": "rescan", "network_range": request.network_range},
    )
    return stats


@app.get("/events/stream")
async def stream_events():
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
        }
    )


@app.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, alert: AlertConfigUpdate):
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
async def delete_alert(alert_id: str):
    """Delete an alert configuration and its history."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")

    deleted = await db_client.delete_alert_config(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "deleted", "id": alert_id}


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
async def list_integrations(type: Optional[str] = None):
    """List integrations, optionally filtered by type."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return await db_client.list_integrations(type=type)


@app.post("/integrations")
async def create_integration(data: IntegrationCreate):
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
async def get_integration(integration_id: str):
    """Get a single integration by ID."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    result = await db_client.get_integration(integration_id)
    if not result:
        raise HTTPException(status_code=404, detail="Integration not found")
    return result


@app.put("/integrations/{integration_id}")
async def update_integration(integration_id: str, data: IntegrationUpdate):
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
async def delete_integration(integration_id: str):
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
async def test_integration(integration_id: str):
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
