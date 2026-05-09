"""Async PostgreSQL database layer for NetOps."""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

import asyncpg
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
    insert,
    update,
    delete,
)
from sqlalchemy.sql import func


# SQLAlchemy metadata for schema definition
Base = type("Base", (), {"metadata": MetaData()})

# Schema definition matching SQLite but with PostgreSQL types
devices_table = Table(
    "devices",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("name", String),
    Column("ip_address", String, unique=True, nullable=False),
    Column("community", String, default="public"),
    Column("status", String, default="unknown"),
    Column("sys_descr", Text),
    Column("discovery_method", String, default="manual"),
    Column("last_polled", String),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
)

topology_nodes_table = Table(
    "topology_nodes",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("device_id", String),
    Column("label", String),
    Column("node_type", String, default="device"),
    Column("status", String, default="unknown"),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
)

topology_links_table = Table(
    "topology_links",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("source_id", String, nullable=False),
    Column("target_id", String, nullable=False),
    Column("source_port", String),
    Column("target_port", String),
    Column("status", String, default="active"),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
)

poll_history_table = Table(
    "poll_history",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", String),
    Column("status", String),
    Column("response_time_ms", Float),
    Column("error", Text),
    Column("polled_at", DateTime, server_default=func.now()),
    Index("idx_poll_history_device", "device_id"),
    Index("idx_poll_history_polled_at", "polled_at"),
)

alert_configs_table = Table(
    "alert_configs",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("alert_type", String, nullable=False),
    Column("channel", String, nullable=False),
    Column("config_json", String),
    Column("enabled", Integer, default=1),
    Column("created", DateTime, server_default=func.now()),
)

alert_history_table = Table(
    "alert_history",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("alert_config_id", String),
    Column("triggered_at", DateTime, server_default=func.now()),
    Column("resolved_at", DateTime),
    Column("message", Text),
    Column("status", String, default="triggered"),
)

maintenance_windows_table = Table(
    "maintenance_windows",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("start_time", DateTime, nullable=False),
    Column("end_time", DateTime, nullable=False),
    Column("description", Text),
    Column("created_at", DateTime, server_default=func.now()),
)


class AsyncPostgresClient:
    """Async PostgreSQL client with connection pooling."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ):
        self._pool: Optional[asyncpg.Pool] = None
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size

        # Build connection string from env or use default
        if connection_string is None:
            self._connection_string = self._build_connection_string()
        else:
            self._connection_string = connection_string

    def _build_connection_string(self) -> str:
        """Build PostgreSQL connection string from environment."""
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        database = os.getenv("POSTGRES_DB", "netops")
        user = os.getenv("POSTGRES_USER", "netops")
        password = os.getenv("POSTGRES_PASSWORD", "netops")

        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

    async def connect(self):
        """Initialize connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._connection_string.replace("postgresql+asyncpg://", "postgresql://"),
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
            )

    async def disconnect(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def _get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get a connection from the pool."""
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        async with self._pool.acquire() as conn:
            yield conn

    async def init_db(self):
        """Initialize database schema."""
        async with self._get_connection() as conn:
            # Create tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    ip_address TEXT UNIQUE NOT NULL,
                    community TEXT DEFAULT 'public',
                    status TEXT DEFAULT 'unknown',
                    sys_descr TEXT,
                    discovery_method TEXT DEFAULT 'manual',
                    last_polled TEXT,
                    created TIMESTAMPTZ DEFAULT NOW(),
                    updated TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                ALTER TABLE devices ADD COLUMN IF NOT EXISTS discovery_method TEXT DEFAULT 'manual'
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS topology_nodes (
                    id TEXT PRIMARY KEY,
                    device_id TEXT,
                    label TEXT,
                    node_type TEXT DEFAULT 'device',
                    status TEXT DEFAULT 'unknown',
                    created TIMESTAMPTZ DEFAULT NOW(),
                    updated TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS topology_links (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    source_port TEXT,
                    target_port TEXT,
                    status TEXT DEFAULT 'active',
                    created TIMESTAMPTZ DEFAULT NOW(),
                    updated TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS poll_history (
                    id SERIAL PRIMARY KEY,
                    device_id TEXT,
                    status TEXT,
                    response_time_ms REAL,
                    error TEXT,
                    polled_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_configs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    config_json JSONB,
                    enabled INTEGER DEFAULT 1,
                    created TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_history (
                    id SERIAL PRIMARY KEY,
                    alert_config_id TEXT,
                    triggered_at TIMESTAMPTZ DEFAULT NOW(),
                    resolved_at TIMESTAMPTZ,
                    message TEXT,
                    status TEXT DEFAULT 'triggered'
                )
            """)

            # Service check tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS service_checks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    interval_seconds INTEGER DEFAULT 60,
                    timeout_seconds INTEGER DEFAULT 10,
                    config_json JSONB,
                    enabled INTEGER DEFAULT 1,
                    created TIMESTAMPTZ DEFAULT NOW(),
                    updated TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS check_results (
                    id SERIAL PRIMARY KEY,
                    check_id TEXT,
                    status TEXT,
                    response_time_ms REAL,
                    message TEXT,
                    details JSONB,
                    error TEXT,
                    checked_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create indexes for performance
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip_address)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_device_id ON topology_nodes(device_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_status ON topology_nodes(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_links_source ON topology_links(source_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_links_target ON topology_links(target_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_poll_history_device ON poll_history(device_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_poll_history_polled_at ON poll_history(polled_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_configs_enabled ON alert_configs(enabled)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_history_config ON alert_history(alert_config_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_service_checks_type ON service_checks(check_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_service_checks_enabled ON service_checks(enabled)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_check_results_check_id ON check_results(check_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_check_results_checked_at ON check_results(checked_at)")

            # Topology change history for auditing and trend analysis
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS topology_history (
                    id SERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    node_id TEXT,
                    link_id TEXT,
                    old_status TEXT,
                    new_status TEXT,
                    details JSONB,
                    recorded_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_topology_history_event ON topology_history(event_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_topology_history_recorded_at ON topology_history(recorded_at)")

            # Maintenance windows for suppressing alerts during planned downtime
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_windows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    start_time TIMESTAMPTZ NOT NULL,
                    end_time TIMESTAMPTZ NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_windows_time ON maintenance_windows(start_time, end_time)")

            # Networks
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS networks (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    cidr TEXT,
                    description TEXT,
                    is_default INTEGER DEFAULT 0,
                    created TIMESTAMPTZ DEFAULT NOW(),
                    updated TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_networks_name ON networks(name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_networks_default ON networks(is_default)")

            # Network associations on existing tables
            await conn.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS network_id TEXT")
            await conn.execute("ALTER TABLE topology_nodes ADD COLUMN IF NOT EXISTS network_id TEXT")
            await conn.execute("ALTER TABLE topology_links ADD COLUMN IF NOT EXISTS network_id TEXT")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_network ON devices(network_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_network ON topology_nodes(network_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_links_network ON topology_links(network_id)")

    async def list_devices(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List devices with optional pagination."""
        query = "SELECT * FROM devices ORDER BY created DESC"
        params: list[Any] = []
        if limit is not None:
            query += f" LIMIT ${len(params) + 1}"
            params.append(limit)
        if offset is not None:
            query += f" OFFSET ${len(params) + 1}"
            params.append(offset)
        async with self._get_connection() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_device(self, device_id: str) -> Optional[dict[str, Any]]:
        """Get device by ID or IP."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM devices WHERE id = $1 OR ip_address = $1",
                device_id,
            )
            return dict(row) if row else None

    async def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new device."""
        device_id = data.get("id") or str(uuid.uuid4())
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO devices (id, name, ip_address, community, status, sys_descr, discovery_method, last_polled)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (ip_address) DO UPDATE SET
                    name = EXCLUDED.name,
                    community = EXCLUDED.community,
                    status = EXCLUDED.status,
                    sys_descr = EXCLUDED.sys_descr,
                    discovery_method = EXCLUDED.discovery_method,
                    last_polled = EXCLUDED.last_polled,
                    updated = NOW()
                """,
                device_id,
                data.get("name", ""),
                data["ip_address"],
                data.get("community", "public"),
                data.get("status", "unknown"),
                data.get("sys_descr", ""),
                data.get("discovery_method", "manual"),
                data.get("last_polled"),
            )
        return await self.get_device(device_id)

    async def update_device(self, device_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing device."""
        fields = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(data.keys()))
        num_fields = len(data)
        param1 = f"${num_fields + 1}"
        param2 = f"${num_fields + 2}"
        values = list(data.values()) + [device_id, device_id]

        async with self._get_connection() as conn:
            await conn.execute(
                f"""
                UPDATE devices SET {fields}, updated = NOW()
                WHERE id = {param1} OR ip_address = {param2}
                """,
                *values,
            )
        return await self.get_device(device_id)

    async def delete_device(self, device_id: str) -> bool:
        """Delete a device."""
        async with self._get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM devices WHERE id = $1 OR ip_address = $1",
                device_id,
            )
            return result == "DELETE 1"

    async def list_topology(self) -> dict[str, list[dict[str, Any]]]:
        """Get current topology as nodes/links."""
        async with self._get_connection() as conn:
            nodes = await conn.fetch("SELECT * FROM topology_nodes")
            links = await conn.fetch("SELECT * FROM topology_links")
            return {"nodes": [dict(n) for n in nodes], "links": [dict(l) for l in links]}

    async def upsert_topology(
        self, nodes: list[dict[str, Any]], links: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Upsert topology data, detecting changes."""
        async with self._get_connection() as conn:
            changes = {
                "nodes_added": 0,
                "nodes_removed": 0,
                "links_added": 0,
                "links_removed": 0,
            }

            # Get existing node IDs
            existing = await conn.fetch("SELECT id FROM topology_nodes")
            existing_node_ids = {row["id"] for row in existing}
            new_node_ids = {n["id"] for n in nodes}

            # Detect removed nodes
            removed_ids = existing_node_ids - new_node_ids
            changes["nodes_removed"] = len(removed_ids)

            # Upsert nodes in batch
            if nodes:
                node_values = [
                    (n["id"], n.get("device_id"), n.get("label", ""),
                     n.get("node_type", "device"), n.get("status", "unknown"))
                    for n in nodes
                ]
                await conn.executemany(
                    """
                    INSERT INTO topology_nodes (id, device_id, label, node_type, status)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (id) DO UPDATE SET
                        device_id = EXCLUDED.device_id,
                        label = EXCLUDED.label,
                        node_type = EXCLUDED.node_type,
                        status = EXCLUDED.status,
                        updated = NOW()
                    """,
                    node_values,
                )
            changes["nodes_added"] = len(new_node_ids - existing_node_ids)

            # Delete removed nodes
            if removed_ids:
                await conn.execute(
                    f"DELETE FROM topology_nodes WHERE id = ANY($1::text[])",
                    list(removed_ids),
                )

            # Get existing link IDs
            existing = await conn.fetch("SELECT id FROM topology_links")
            existing_link_ids = {row["id"] for row in existing}

            # Generate link IDs if not present
            for link in links:
                if "id" not in link:
                    link["id"] = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"{link['source']}:{link['target']}:{link.get('source_port', '')}:{link.get('target_port', '')}",
                        )
                    )

            new_link_ids = {link["id"] for link in links}

            # Detect removed links
            removed_link_ids = existing_link_ids - new_link_ids
            changes["links_removed"] = len(removed_link_ids)

            # Upsert links in batch
            if links:
                link_values = [
                    (link["id"], link["source"], link["target"],
                     link.get("source_port", ""), link.get("target_port", ""),
                     link.get("status", "active"))
                    for link in links
                ]
                await conn.executemany(
                    """
                    INSERT INTO topology_links (id, source_id, target_id, source_port, target_port, status)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO UPDATE SET
                        source_id = EXCLUDED.source_id,
                        target_id = EXCLUDED.target_id,
                        source_port = EXCLUDED.source_port,
                        target_port = EXCLUDED.target_port,
                        status = EXCLUDED.status,
                        updated = NOW()
                    """,
                    link_values,
                )
            changes["links_added"] = len(new_link_ids - existing_link_ids)

            # Delete removed links
            if removed_link_ids:
                await conn.execute(
                    f"DELETE FROM topology_links WHERE id = ANY($1::text[])",
                    list(removed_link_ids),
                )

            # Record topology changes in history
            if any(changes.values()):
                added_nodes = [n for n in nodes if n["id"] in (new_node_ids - existing_node_ids)]
                added_links = [l for l in links if l["id"] in (new_link_ids - existing_link_ids)]
                await self._record_topology_changes(conn, changes, added_nodes, added_links)

            return changes

    async def _record_topology_changes(
        self, conn, changes: dict, added_nodes: list, added_links: list
    ):
        """Record topology changes in history table for auditing."""
        event_type = "topology_change"
        if added_nodes:
            node_values = [
                (event_type, n["id"], n.get("status", "unknown"),
                 json.dumps({"action": "added", "type": "node"}))
                for n in added_nodes
            ]
            await conn.executemany(
                """
                INSERT INTO topology_history (event_type, node_id, new_status, details)
                VALUES ($1, $2, $3, $4)
                """,
                node_values,
            )
        if added_links:
            link_values = [
                (event_type, l.get("id"), l.get("status", "active"),
                 json.dumps({"action": "added", "type": "link"}))
                for l in added_links
            ]
            await conn.executemany(
                """
                INSERT INTO topology_history (event_type, link_id, new_status, details)
                VALUES ($1, $2, $3, $4)
                """,
                link_values,
            )
        if changes["nodes_removed"] > 0:
            await conn.execute(
                """
                INSERT INTO topology_history (event_type, details)
                VALUES ($1, $2)
                """,
                event_type,
                json.dumps({"action": "removed", "type": "nodes", "count": changes["nodes_removed"]}),
            )
        if changes["links_removed"] > 0:
            await conn.execute(
                """
                INSERT INTO topology_history (event_type, details)
                VALUES ($1, $2)
                """,
                event_type,
                json.dumps({"action": "removed", "type": "links", "count": changes["links_removed"]}),
            )

    async def add_poll_result(
        self, device_id: str, status: str, response_time_ms: float = 0, error: str = ""
    ):
        """Record a poll result."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO poll_history (device_id, status, response_time_ms, error)
                VALUES ($1, $2, $3, $4)
                """,
                device_id,
                status,
                response_time_ms,
                error,
            )

    async def list_alert_configs(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List alert configurations with optional pagination."""
        query = "SELECT * FROM alert_configs WHERE enabled = 1"
        params: list[Any] = []
        if limit is not None:
            query += f" LIMIT ${len(params) + 1}"
            params.append(limit)
        if offset is not None:
            query += f" OFFSET ${len(params) + 1}"
            params.append(offset)
        async with self._get_connection() as conn:
            rows = await conn.fetch(query, *params)
            result = []
            for row in rows:
                d = dict(row)
                if d.get("config_json"):
                    d["config_json"] = json.loads(d["config_json"]) if isinstance(d["config_json"], str) else d["config_json"]
                result.append(d)
            return result

    async def create_alert_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create an alert configuration."""
        alert_id = str(uuid.uuid4())
        config_json = json.dumps(data.get("config", {}))

        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                alert_id,
                data["name"],
                data["alert_type"],
                data["channel"],
                config_json,
                1 if data.get("enabled", True) else 0,
            )
        return await self._get_alert_config(alert_id)

    async def _get_alert_config(self, alert_id: str) -> Optional[dict[str, Any]]:
        """Get alert config by ID."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM alert_configs WHERE id = $1", alert_id)
            if row:
                d = dict(row)
                if d.get("config_json"):
                    d["config_json"] = json.loads(d["config_json"]) if isinstance(d["config_json"], str) else d["config_json"]
                return d
            return None

    async def record_alert_history(
        self, alert_config_id: str, message: str, status: str = "triggered"
    ):
        """Record an alert in history."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO alert_history (alert_config_id, message, status)
                VALUES ($1, $2, $3)
                """,
                alert_config_id, message, status,
            )

    async def get_alert_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent alert history with alert config details."""
        async with self._get_connection() as conn:
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

    async def get_poll_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent poll history with device details."""
        async with self._get_connection() as conn:
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

    async def list_maintenance_windows(self) -> list[dict[str, Any]]:
        """List all maintenance windows ordered by start time."""
        async with self._get_connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM maintenance_windows ORDER BY start_time DESC"
            )
            return [dict(row) for row in rows]

    async def create_maintenance_window(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a maintenance window."""
        window_id = str(uuid.uuid4())
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO maintenance_windows (id, name, start_time, end_time, description)
                VALUES ($1, $2, $3, $4, $5)
                """,
                window_id,
                data["name"],
                data["start_time"],
                data["end_time"],
                data.get("description", ""),
            )
        return {"id": window_id, **data}

    async def delete_maintenance_window(self, window_id: str) -> bool:
        """Delete a maintenance window."""
        async with self._get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM maintenance_windows WHERE id = $1", window_id
            )
            return result == "DELETE 1"

    async def is_in_maintenance_window(self) -> bool:
        """Check if current time falls within any active maintenance window."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM maintenance_windows
                WHERE start_time <= NOW() AND end_time >= NOW()
                LIMIT 1
                """
            )
            return row is not None

    # Network methods

    async def list_networks(self) -> list[dict[str, Any]]:
        """List all networks."""
        async with self._get_connection() as conn:
            rows = await conn.fetch("SELECT * FROM networks ORDER BY created DESC")
            return [dict(row) for row in rows]

    async def get_network(self, network_id: str) -> Optional[dict[str, Any]]:
        """Get network by ID."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM networks WHERE id = $1", network_id)
            return dict(row) if row else None

    async def create_network(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new network."""
        network_id = data.get("id") or str(uuid.uuid4())
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO networks (id, name, cidr, description, is_default)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO UPDATE SET
                    cidr = EXCLUDED.cidr,
                    description = EXCLUDED.description,
                    is_default = EXCLUDED.is_default,
                    updated = NOW()
                """,
                network_id,
                data["name"],
                data.get("cidr"),
                data.get("description"),
                1 if data.get("is_default", False) else 0,
            )
        return await self.get_network(network_id)

    async def update_network(self, network_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing network."""
        fields = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(data.keys()))
        values = list(data.values()) + [network_id]
        async with self._get_connection() as conn:
            await conn.execute(
                f"""
                UPDATE networks SET {fields}, updated = NOW()
                WHERE id = ${len(data) + 1}
                """,
                *values,
            )
        return await self.get_network(network_id)

    async def delete_network(self, network_id: str) -> bool:
        """Delete a network."""
        async with self._get_connection() as conn:
            result = await conn.execute("DELETE FROM networks WHERE id = $1", network_id)
            return result == "DELETE 1"

    async def set_device_network(self, device_id: str, network_id: str) -> dict[str, Any]:
        """Set the network for a device."""
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE devices SET network_id = $1, updated = NOW() WHERE id = $2",
                network_id,
                device_id,
            )
        return await self.get_device(device_id)

    async def set_default_network(self, network_id: str) -> dict[str, Any]:
        """Set a network as the default and unset all others."""
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE networks SET is_default = 0 WHERE id != $1",
                network_id,
            )
            await conn.execute(
                "UPDATE networks SET is_default = 1, updated = NOW() WHERE id = $1",
                network_id,
            )
        return await self.get_network(network_id)

    async def close(self):
        """Close database connections."""
        await self.disconnect()

    # Service check methods

    async def list_service_checks(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List service checks with optional pagination."""
        query = "SELECT * FROM service_checks ORDER BY created DESC"
        params: list[Any] = []
        if limit is not None:
            query += f" LIMIT ${len(params) + 1}"
            params.append(limit)
        if offset is not None:
            query += f" OFFSET ${len(params) + 1}"
            params.append(offset)
        async with self._get_connection() as conn:
            rows = await conn.fetch(query, *params)
            result = []
            for row in rows:
                d = dict(row)
                if d.get("config_json"):
                    d["config_json"] = json.loads(d["config_json"]) if isinstance(d["config_json"], str) else d["config_json"]
                result.append(d)
            return result

    async def get_service_check(self, check_id: str) -> Optional[dict[str, Any]]:
        """Get service check by ID."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM service_checks WHERE id = $1", check_id)
            if row:
                d = dict(row)
                if d.get("config_json"):
                    d["config_json"] = json.loads(d["config_json"]) if isinstance(d["config_json"], str) else d["config_json"]
                return d
            return None

    async def create_service_check(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a service check."""
        check_id = data.get("id") or str(uuid.uuid4())
        config_json = json.dumps(data.get("config", {}))

        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO service_checks (id, name, check_type, target, interval_seconds, timeout_seconds, config_json, enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                check_id,
                data["name"],
                data["check_type"],
                data["target"],
                data.get("interval_seconds", 60),
                data.get("timeout_seconds", 10),
                config_json,
                1 if data.get("enabled", True) else 0,
            )
        return await self.get_service_check(check_id)

    async def update_service_check(self, check_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a service check."""
        async with self._get_connection() as conn:
            fields = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(data.keys()))
            values = list(data.values()) + [check_id]
            await conn.execute(
                f"""
                UPDATE service_checks SET {fields}, updated = NOW()
                WHERE id = ${len(data) + 1}
                """,
                *values,
            )
        return await self.get_service_check(check_id)

    async def delete_service_check(self, check_id: str) -> bool:
        """Delete a service check."""
        async with self._get_connection() as conn:
            result = await conn.execute("DELETE FROM service_checks WHERE id = $1", check_id)
            return result == "DELETE 1"

    async def add_check_result(
        self,
        check_id: str,
        status: str,
        response_time_ms: float,
        message: str = "",
        details: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Record a check result."""
        async with self._get_connection() as conn:
            details_json = json.dumps(details) if details else None
            await conn.execute(
                """
                INSERT INTO check_results (check_id, status, response_time_ms, message, details, error)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                check_id,
                status,
                response_time_ms,
                message,
                details_json,
                error,
            )

    async def get_check_results(self, check_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent check results for a specific check."""
        async with self._get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM check_results
                WHERE check_id = $1
                ORDER BY checked_at DESC
                LIMIT $2
                """,
                check_id,
                limit,
            )
            result = []
            for row in rows:
                d = dict(row)
                if d.get("details"):
                    d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
                result.append(d)
            return result

    async def record_topology_change(
        self,
        event_type: str,
        node_id: Optional[str] = None,
        link_id: Optional[str] = None,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        """Record a topology change event in history."""
        async with self._get_connection() as conn:
            details_json = json.dumps(details) if details else None
            await conn.execute(
                """
                INSERT INTO topology_history (event_type, node_id, link_id, old_status, new_status, details)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                event_type, node_id, link_id, old_status, new_status, details_json,
            )

    async def get_topology_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent topology change history."""
        async with self._get_connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM topology_history ORDER BY recorded_at DESC LIMIT $1",
                limit,
            )
            result = []
            for row in rows:
                d = dict(row)
                if d.get("details"):
                    d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
                result.append(d)
            return result
