"""Async PostgreSQL database layer for NetOps."""

import asyncio
import json
import os
import time
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
    UniqueConstraint,
    select,
    insert,
    update,
    delete,
)
from sqlalchemy.sql import func


def _config_signature(alert_type: str, channel: str, config: dict[str, Any]) -> str:
    """Stable signature for (alert_type, channel, normalized config) dedup."""
    normalized = json.dumps(config or {}, sort_keys=True, separators=(",", ":"))
    return f"{alert_type.lower()}|{channel.lower()}|{normalized}"


# SQLAlchemy metadata for schema definition
Base = type("Base", (), {"metadata": MetaData()})

# ---------------------------------------------------------------------------
# Table definitions
#
# These mirror the schema declared in src/storage/migrations/versions/001_*
# (the canonical baseline). Keeping them registered on `Base.metadata` is
# what makes `alembic revision --autogenerate` produce a no-op when the
# schema is in sync.
# ---------------------------------------------------------------------------

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
    Column("snmp_version", String, default="2c"),
    Column("snmpv3_username", String),
    Column("snmpv3_auth_protocol", String),
    Column("snmpv3_auth_key", String),
    Column("snmpv3_priv_protocol", String),
    Column("snmpv3_priv_key", String),
    Column("network_id", String),
    Column("offline_since", DateTime),
    Column("last_scanned", DateTime),
    Column("last_polled", String),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_devices_ip", "ip_address"),
    Index("idx_devices_status", "status"),
    Index("idx_devices_discovery_method", "discovery_method"),
    Index("idx_devices_network_id", "network_id"),
    Index("idx_devices_offline_since", "offline_since"),
    Index("idx_devices_last_scanned", "last_scanned"),
)

topology_nodes_table = Table(
    "topology_nodes",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("device_id", String),
    Column("network_id", String),
    Column("label", String),
    Column("node_type", String, default="device"),
    Column("status", String, default="unknown"),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_nodes_device_id", "device_id"),
    Index("idx_nodes_status", "status"),
    Index("idx_nodes_network_id", "network_id"),
)

topology_links_table = Table(
    "topology_links",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("source_id", String, nullable=False),
    Column("target_id", String, nullable=False),
    Column("network_id", String),
    Column("source_port", String),
    Column("target_port", String),
    Column("status", String, default="active"),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_links_source", "source_id"),
    Index("idx_links_target", "target_id"),
    Index("idx_links_network_id", "network_id"),
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
    Column("integration_id", String),
    Column("enabled", Integer, default=1),
    Column("created", DateTime, server_default=func.now()),
    Index("idx_alert_configs_enabled", "enabled"),
    Index("idx_alert_configs_integration", "integration_id"),
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
    Index("idx_alert_history_config", "alert_config_id"),
)

users_table = Table(
    "users",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("username", String, unique=True, nullable=False),
    Column("email", String, unique=True),
    Column("name", String),
    Column("password_hash", String, nullable=False),
    Column("role", String, default="admin"),
    Column("created", DateTime, server_default=func.now()),
    Column("created_at", DateTime, server_default=func.now()),
    Index("ix_users_email", "email", unique=True),
)

app_settings_table = Table(
    "app_settings",
    Base.metadata,
    Column("key", String, primary_key=True),
    Column("value", String, nullable=False),
    Column("updated", DateTime, server_default=func.now()),
)

topology_history_table = Table(
    "topology_history",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_type", String, nullable=False),
    Column("node_id", String),
    Column("link_id", String),
    Column("source_ip", String),
    Column("old_status", String),
    Column("new_status", String),
    Column("details", String),
    Column("recorded_at", DateTime, server_default=func.now()),
    Index("idx_topology_history_event", "event_type"),
    Index("idx_topology_history_recorded_at", "recorded_at"),
    Index("idx_topology_history_source_time", "source_ip", "recorded_at"),
    Index("idx_topology_history_link_time", "link_id", "recorded_at"),
)

integrations_table = Table(
    "integrations",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("type", String, nullable=False),
    Column("name", String, nullable=False),
    Column("secrets_json", String),
    Column("enabled", Integer, default=1),
    Column("created", DateTime, server_default=func.now()),
    UniqueConstraint("type", "name", name="uq_integrations_type_name"),
    Index("idx_integrations_type", "type"),
)

service_checks_table = Table(
    "service_checks",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("check_type", String, nullable=False),
    Column("target", String, nullable=False),
    Column("interval_seconds", Integer, default=60),
    Column("timeout_seconds", Integer, default=10),
    Column("config_json", String),
    Column("enabled", Integer, default=1),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_service_checks_type", "check_type"),
    Index("idx_service_checks_enabled", "enabled"),
)

check_results_table = Table(
    "check_results",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("check_id", String),
    Column("status", String),
    Column("response_time_ms", Float),
    Column("message", Text),
    Column("details", String),
    Column("error", Text),
    Column("checked_at", DateTime, server_default=func.now()),
    Index("idx_check_results_check_id", "check_id"),
    Index("idx_check_results_checked_at", "checked_at"),
)

networks_table = Table(
    "networks",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("name", String, unique=True, nullable=False),
    Column("cidr", String),
    Column("description", Text),
    Column("is_default", Integer, default=0),
    Column("network_type", String),
    Column("tags", String, default="[]"),
    Column("last_scanned", DateTime),
    Column("created", DateTime, server_default=func.now()),
    Column("updated", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_networks_name", "name"),
    Index("idx_networks_default", "is_default"),
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
    Index("idx_maintenance_windows_time", "start_time", "end_time"),
)


class AsyncPostgresClient:
    """Async PostgreSQL client with connection pooling."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        min_pool_size: Optional[int] = None,
        max_pool_size: Optional[int] = None,
    ):
        self._pool: Optional[asyncpg.Pool] = None
        # Env-var-driven defaults (Phase 3 contract). Operators can
        # tune without code changes for homelab (4/10) up to
        # datacenter (8/50) deployments.
        self._min_pool_size = (
            min_pool_size
            if min_pool_size is not None
            else int(os.getenv("PG_POOL_MIN", "4"))
        )
        self._max_pool_size = (
            max_pool_size
            if max_pool_size is not None
            else int(os.getenv("PG_POOL_MAX", "25"))
        )

        # Build connection string from env or use default
        if connection_string is None:
            self._connection_string = self._build_connection_string()
        else:
            self._connection_string = connection_string

    def _build_connection_string(self) -> str:
        """Build PostgreSQL connection string from environment."""
        # DATABASE_URL takes priority over the legacy POSTGRES_* vars.
        url = os.getenv("DATABASE_URL")
        if url:
            return url

        host = os.getenv("POSTGRES_HOST", "localhost")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        database = os.getenv("POSTGRES_DB", "netops")
        user = os.getenv("POSTGRES_USER", "netops")
        password = os.getenv("POSTGRES_PASSWORD", "netops")

        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

    async def connect(self):
        """Initialize connection pool."""
        if self._pool is None:
            pool_kwargs = dict(
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
            )
            # Optional tuning knobs (Phase 3: prevent runaway queries)
            try:
                command_timeout = int(os.getenv("PG_COMMAND_TIMEOUT", "60"))
                pool_kwargs["command_timeout"] = command_timeout
            except ValueError:
                pass
            self._pool = await asyncpg.create_pool(
                self._connection_string.replace("postgresql+asyncpg://", "postgresql://"),
                **pool_kwargs,
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

    async def healthcheck(self) -> dict[str, Any]:
        """Return connection pool stats and a probe-query latency.

        Used by `/api/health/db`. If the pool is not initialized
        or the probe fails, returns a status of `disconnected` or
        `error` with the message.
        """
        if self._pool is None:
            return {"status": "disconnected", "backend": "postgresql"}
        try:
            start = time.time()
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            latency_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "connected",
                "backend": "postgresql",
                "latency_ms": latency_ms,
                "pool_size": self._pool.get_size(),
                "pool_free": self._pool.get_idle_size(),
                "pool_min": self._min_pool_size,
                "pool_max": self._max_pool_size,
            }
        except Exception as e:
            return {
                "status": "error",
                "backend": "postgresql",
                "message": str(e),
            }

    async def init_db(self):
        """No-op. Schema is owned by Alembic migrations.

        See src/storage/migrations/versions/001_initial_schema.py for the
        canonical baseline. The app lifespan calls `alembic upgrade head`
        on startup (env-gated by NETOPS_AUTO_MIGRATE) before reaching
        this point, so the schema is guaranteed to be current.

        Kept as a method so existing call sites (lifespan, tests) do not
        need to change.
        """
        return None

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

    async def bulk_delete_devices(self, device_ids: list[str]) -> int:
        """Delete many devices by id or ip_address. Returns rows removed."""
        if not device_ids:
            return 0
        total = 0
        async with self._get_connection() as conn:
            async with conn.transaction():
                for did in device_ids:
                    result = await conn.execute(
                        "DELETE FROM devices WHERE id = $1 OR ip_address = $1",
                        did,
                    )
                    total += int(result.split()[-1]) if result.startswith("DELETE") else 0
                # Drop topology nodes/links whose device vanished
                if total:
                    await conn.execute(
                        """
                        DELETE FROM topology_nodes
                        WHERE device_id IS NULL
                           OR NOT EXISTS (SELECT 1 FROM devices d WHERE d.id = topology_nodes.device_id)
                        """
                    )
                    await conn.execute(
                        """
                        DELETE FROM topology_links
                        WHERE NOT EXISTS (SELECT 1 FROM topology_nodes n WHERE n.id = topology_links.source_id)
                           OR NOT EXISTS (SELECT 1 FROM topology_nodes n WHERE n.id = topology_links.target_id)
                        """
                    )
        return total

    async def clear_all_devices(self) -> int:
        """Wipe every device and prune orphan topology. Returns rows removed."""
        async with self._get_connection() as conn:
            async with conn.transaction():
                result = await conn.execute("DELETE FROM devices")
                total = int(result.split()[-1]) if result.startswith("DELETE") else 0
                await conn.execute("DELETE FROM topology_nodes")
                await conn.execute("DELETE FROM topology_links")
                return total

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
                removed_nodes = []
                for i in removed_ids:
                    row = await conn.fetchrow("SELECT * FROM topology_nodes WHERE id = $1", i)
                    if row: removed_nodes.append(dict(row))
                removed_links = []
                for i in removed_link_ids:
                    row = await conn.fetchrow("SELECT * FROM topology_links WHERE id = $1", i)
                    if row: removed_links.append(dict(row))
                await self._record_topology_changes(conn, changes, added_nodes, added_links, removed_nodes, removed_links)

            return changes

    async def _record_topology_changes(
        self, conn, changes: dict, added_nodes: list, added_links: list,
        removed_nodes: list = None, removed_links: list = None
    ):
        """Record topology changes in history table for auditing."""
        event_type = "topology_change"
        if added_nodes:
            node_values = [
                (event_type, n["id"], n.get("status", "unknown"),
                 json.dumps({"action": "added", "type": "node", "data": n}))
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
                 json.dumps({"action": "added", "type": "link", "data": l}))
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
                json.dumps({
                    "action": "removed", "type": "nodes",
                    "count": changes["nodes_removed"],
                    "ids": [n.get("id") for n in (removed_nodes or [])]
                }),
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
        self, limit: Optional[int] = None, offset: Optional[int] = None,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        """List alert configurations with optional pagination."""
        query = "SELECT * FROM alert_configs"
        params: list[Any] = []
        if not include_disabled:
            query += " WHERE enabled = 1"
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
                INSERT INTO alert_configs
                    (id, name, alert_type, channel, config_json, integration_id, enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                alert_id,
                data["name"],
                data["alert_type"],
                data["channel"],
                config_json,
                data.get("integration_id"),
                1 if data.get("enabled", True) else 0,
            )
        return await self._get_alert_config(alert_id)

    async def update_alert_config(
        self, alert_id: str, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update an existing alert config. Returns updated row or None."""
        existing = await self._get_alert_config(alert_id)
        if not existing:
            return None

        sets: list[str] = []
        params_list: list[Any] = []
        if "name" in data:
            sets.append(f"name = ${len(params_list) + 1}")
            params_list.append(data["name"])
        if "alert_type" in data:
            sets.append(f"alert_type = ${len(params_list) + 1}")
            params_list.append(data["alert_type"])
        if "channel" in data:
            sets.append(f"channel = ${len(params_list) + 1}")
            params_list.append(data["channel"])
        if "config" in data:
            sets.append(f"config_json = ${len(params_list) + 1}")
            params_list.append(json.dumps(data["config"]))
        if "integration_id" in data:
            sets.append(f"integration_id = ${len(params_list) + 1}")
            params_list.append(data["integration_id"])
        if "enabled" in data:
            sets.append(f"enabled = ${len(params_list) + 1}")
            params_list.append(1 if data["enabled"] else 0)

        if not sets:
            return existing

        params_list.append(alert_id)
        query = f"UPDATE alert_configs SET {', '.join(sets)} WHERE id = ${len(params_list)}"
        async with self._get_connection() as conn:
            await conn.execute(query, *params_list)
        return await self._get_alert_config(alert_id)

    async def delete_alert_config(self, alert_id: str) -> bool:
        """Delete an alert config and its history. Returns True if deleted."""
        async with self._get_connection() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM alert_configs WHERE id = $1", alert_id
            )
            if not existing:
                return False
            await conn.execute(
                "DELETE FROM alert_history WHERE alert_config_id = $1", alert_id
            )
            await conn.execute(
                "DELETE FROM alert_configs WHERE id = $1", alert_id
            )
            return True

    async def find_alert_config_by_signature(
        self, alert_type: str, channel: str, config: dict[str, Any],
        exclude_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Find an alert config matching (alert_type, channel, normalized config)."""
        all_configs = await self.list_alert_configs(include_disabled=True)
        signature = _config_signature(alert_type, channel, config)
        for cfg in all_configs:
            if cfg.get("id") == exclude_id:
                continue
            if _config_signature(
                cfg.get("alert_type", ""),
                cfg.get("channel", ""),
                cfg.get("config_json") or {},
            ) == signature:
                return cfg
        return None

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

    # Integration methods
    async def list_integrations(
        self, type: Optional[str] = None, include_disabled: bool = True
    ) -> list[dict[str, Any]]:
        """List integrations, optionally filtered by type."""
        query = "SELECT * FROM integrations"
        params_list: list[Any] = []
        clauses: list[str] = []
        if type:
            clauses.append(f"type = ${len(params_list) + 1}")
            params_list.append(type)
        if not include_disabled:
            clauses.append("enabled = 1")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created DESC"
        async with self._get_connection() as conn:
            rows = await conn.fetch(query, *params_list)
            result = []
            for row in rows:
                d = dict(row)
                if d.get("secrets_json"):
                    d["secrets_json"] = json.loads(d["secrets_json"]) if isinstance(d["secrets_json"], str) else d["secrets_json"]
                result.append(d)
            return result

    async def create_integration(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new integration. Returns the created row."""
        integration_id = str(uuid.uuid4())
        secrets_json = json.dumps(data.get("secrets_json", {}))
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO integrations (id, type, name, secrets_json, enabled)
                VALUES ($1, $2, $3, $4, $5)
                """,
                integration_id,
                data["type"],
                data["name"],
                secrets_json,
                1 if data.get("enabled", True) else 0,
            )
        result = await self.get_integration(integration_id)
        if not result:
            raise RuntimeError("Failed to create integration")
        return result

    async def get_integration(
        self, integration_id: str
    ) -> Optional[dict[str, Any]]:
        """Get integration by ID."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM integrations WHERE id = $1", integration_id
            )
            if row:
                d = dict(row)
                if d.get("secrets_json"):
                    d["secrets_json"] = json.loads(d["secrets_json"]) if isinstance(d["secrets_json"], str) else d["secrets_json"]
                return d
            return None

    async def update_integration(
        self, integration_id: str, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update an existing integration. Returns updated row or None."""
        existing = await self.get_integration(integration_id)
        if not existing:
            return None

        sets: list[str] = []
        params_list: list[Any] = []
        if "type" in data:
            sets.append(f"type = ${len(params_list) + 1}")
            params_list.append(data["type"])
        if "name" in data:
            sets.append(f"name = ${len(params_list) + 1}")
            params_list.append(data["name"])
        if "secrets_json" in data:
            sets.append(f"secrets_json = ${len(params_list) + 1}")
            params_list.append(json.dumps(data["secrets_json"]))
        if "enabled" in data:
            sets.append(f"enabled = ${len(params_list) + 1}")
            params_list.append(1 if data["enabled"] else 0)

        if not sets:
            return existing

        params_list.append(integration_id)
        query = f"UPDATE integrations SET {', '.join(sets)} WHERE id = ${len(params_list)}"
        async with self._get_connection() as conn:
            await conn.execute(query, *params_list)
        return await self.get_integration(integration_id)

    async def delete_integration(self, integration_id: str) -> tuple[bool, str]:
        """Delete an integration. Returns (success, error_message)."""
        async with self._get_connection() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM integrations WHERE id = $1", integration_id
            )
            if not existing:
                return False, "not found"
            ref = await conn.fetchrow(
                "SELECT id FROM alert_configs WHERE integration_id = $1 LIMIT 1",
                integration_id,
            )
            if ref:
                return False, "integration is referenced by one or more alert rules"
            await conn.execute(
                "DELETE FROM integrations WHERE id = $1", integration_id
            )
            return True, ""

    async def get_integration_for_alert(
        self, alert_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge integration secrets with alert config. Returns effective config dict.

        If alert_config has integration_id, fetches integration and merges:
        integration.secrets_json (base) <- alert_config.config_json (overrides).
        Otherwise returns alert_config.config_json as-is.
        """
        base_config: dict[str, Any] = {}
        if alert_config.get("integration_id"):
            integration = await self.get_integration(alert_config["integration_id"])
            if integration and integration.get("secrets_json"):
                base_config = dict(integration["secrets_json"])
        rule_config = alert_config.get("config_json") or {}
        if not isinstance(rule_config, dict):
            rule_config = {}
        merged = {**base_config, **rule_config}
        return merged

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

    async def clear_alert_history(self) -> int:
        """Delete all rows from alert_history. Returns count deleted."""
        async with self._get_connection() as conn:
            result = await conn.execute("DELETE FROM alert_history")
            return int(result.split()[-1]) if hasattr(result, 'split') else 0

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
        """List all networks with device_count."""
        async with self._get_connection() as conn:
            rows = await conn.fetch("""
                SELECT n.*, COUNT(d.id) AS device_count
                FROM networks n
                LEFT JOIN devices d ON d.network_id = n.id
                GROUP BY n.id
                ORDER BY n.created DESC
            """)
            result = []
            for row in rows:
                d = dict(row)
                if d.get("tags"):
                    d["tags"] = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
                else:
                    d["tags"] = []
                result.append(d)
            return result

    async def get_network(self, network_id: str) -> Optional[dict[str, Any]]:
        """Get network by ID with device_count."""
        async with self._get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT n.*, COUNT(d.id) AS device_count
                FROM networks n
                LEFT JOIN devices d ON d.network_id = n.id
                WHERE n.id = $1
                GROUP BY n.id
            """, network_id)
            if row:
                d = dict(row)
                if d.get("tags"):
                    d["tags"] = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
                else:
                    d["tags"] = []
                return d
            return None

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

    async def cleanup_poll_history(self, retention_days: int = 30):
        """Delete poll history older than retention_days.

        On PG with the partitioned parent from migration 014, this
        DETACHes + DROPs whole partitions whose upper bound is
        older than the cutoff. On SQLite (or PG without 014
        applied), this is a row-level DELETE.
        """
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            # PG path: drop whole partitions.
            try:
                row = await conn.fetchrow(
                    "SELECT relkind FROM pg_class WHERE relname = 'poll_history'"
                )
                if row and row["relkind"] == "p":
                    from datetime import datetime, timedelta
                    cutoff = datetime.utcnow() - timedelta(days=retention_days)
                    partitions = await conn.fetch(
                        "SELECT inhrelid::regclass::text AS part_name, "
                        "pg_get_expr(c.relpartbound, c.oid) AS bound "
                        "FROM pg_inherits i "
                        "JOIN pg_class c ON c.oid = i.inhrelid "
                        "JOIN pg_class p ON p.oid = i.inhparent "
                        "WHERE p.relname = 'poll_history'"
                    )
                    for p in partitions:
                        bound = p["bound"] or ""
                        if "DEFAULT" in bound.upper():
                            continue
                        import re
                        m = re.search(r"TO\s*\('([^']+)'\)", bound, re.IGNORECASE)
                        if not m:
                            continue
                        try:
                            to_ts = datetime.fromisoformat(
                                m.group(1).replace(" ", "T").split("+")[0]
                            )
                        except (TypeError, ValueError):
                            continue
                        if to_ts < cutoff:
                            await conn.execute(
                                f"ALTER TABLE poll_history "
                                f"DETACH PARTITION {p['part_name']}"
                            )
                            await conn.execute(
                                f"DROP TABLE {p['part_name']}"
                            )
                    return
            except Exception:
                pass

            # Fallback: row-level DELETE.
            await conn.execute(
                "DELETE FROM poll_history WHERE polled_at < NOW() - make_interval(days => $1)",
                retention_days,
            )

    # ------------------------------------------------------------------
    # Phase 4: topology_history partitioning support.
    # The partition machinery is created by migration 010; the
    # methods below maintain it at runtime. They are gated by
    # `NETOPS_PHASE4_PARTITIONED_HISTORY=1` so existing deployments
    # can opt in once the schema is verified.
    # ------------------------------------------------------------------
    @property
    def phase4_partitioning_enabled(self) -> bool:
        """Whether Phase 4 partitioning maintenance is enabled."""
        return os.environ.get("NETOPS_PHASE4_PARTITIONED_HISTORY", "0") == "1"

    async def maintain_topology_partitions(self, months_ahead: int = 3) -> int:
        """Ensure topology_history has partitions for the current
        month plus `months_ahead` future months.

        On PostgreSQL with the partitioned parent from migration 010,
        this is a no-op if the partitions already exist (CREATE
        TABLE IF NOT EXISTS); otherwise it creates them.

        On non-PG backends (e.g. SQLite), this is a no-op.

        Returns the number of partitions created (0 if everything
        was already in place or the dialect is not PG).
        """
        if not self.phase4_partitioning_enabled:
            return 0
        if not self._pool:
            return 0

        return await self._maintain_partitions(
            "topology_history", months_ahead
        )

    async def maintain_poll_history_partitions(self, months_ahead: int = 3) -> int:
        """Ensure poll_history has partitions for the current
        month plus `months_ahead` future months.

        Mirror of `maintain_topology_partitions` for migration 014.
        Same gate, same return value semantics.
        """
        if not self.phase4_partitioning_enabled:
            return 0
        if not self._pool:
            return 0

        return await self._maintain_partitions(
            "poll_history", months_ahead
        )

    async def _maintain_partitions(
        self, table: str, months_ahead: int
    ) -> int:
        """Shared implementation for partition maintenance.

        Idempotent: skips a partition if it already exists.
        """
        from datetime import date

        today = date.today()
        created = 0
        async with self._pool.acquire() as conn:
            # Confirm the parent is partitioned.
            row = await conn.fetchrow(
                "SELECT relkind FROM pg_class WHERE relname = $1", table
            )
            if not row or row["relkind"] != "p":
                return 0

            for offset in range(0, months_ahead + 1):
                year = today.year
                month = today.month + offset
                while month < 1:
                    month += 12
                    year -= 1
                while month > 12:
                    month -= 12
                    year += 1
                start = f"{year:04d}-{month:02d}-01"
                if month == 12:
                    next_year, next_month = year + 1, 1
                else:
                    next_year, next_month = year, month + 1
                end = f"{next_year:04d}-{next_month:02d}-01"
                partition = f"{table}_{year}_{month:02d}"

                exists = await conn.fetchval(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM pg_inherits i"
                    "  JOIN pg_class c ON c.oid = i.inhrelid"
                    "  WHERE c.relname = $1"
                    ")", partition,
                )
                if exists:
                    continue
                await conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {partition} "
                    f"PARTITION OF {table} "
                    f"FOR VALUES FROM ('{start}') TO ('{end}')"
                )
                created += 1
        return created

    async def cleanup_topology_history(self, retention_days: int = 90) -> int:
        """Drop topology_history partitions older than retention_days.

        On PostgreSQL with the partitioned parent: identifies
        partitions whose upper bound is older than the cutoff and
        DETACHES + DROPS them. Row-level DELETE is not used; whole
        partitions are removed.

        On non-PG backends: a row-level DELETE is used (the SQLite
        table is not partitioned).

        Returns the number of partitions dropped (PG) or rows
        deleted (SQLite).
        """
        if not self._pool:
            return 0
        async with self._pool.acquire() as conn:
            # PG path: drop whole partitions.
            try:
                # Detect partitioned parent.
                row = await conn.fetchrow(
                    "SELECT relkind FROM pg_class WHERE relname = 'topology_history'"
                )
                if row and row["relkind"] == "p":
                    cutoff = (
                        f"(CURRENT_DATE - INTERVAL '{int(retention_days)} days')"
                    )
                    partitions = await conn.fetch(
                        "SELECT inhrelid::regclass::text AS part_name, "
                        "pg_get_expr(c.relpartbound, c.oid) AS bound "
                        "FROM pg_inherits i "
                        "JOIN pg_class c ON c.oid = i.inhrelid "
                        "JOIN pg_class p ON p.oid = i.inhparent "
                        "WHERE p.relname = 'topology_history'"
                    )
                    dropped = 0
                    for p in partitions:
                        # Parse the bound to find the upper limit.
                        # PG returns something like:
                        #   FOR VALUES FROM ('2025-06-01 00:00:00+00') TO ('2025-07-01 00:00:00+00')
                        # We just need the second timestamp; the
                        # SQL parser will reject anything we miss.
                        bound = p["bound"] or ""
                        if "DEFAULT" in bound.upper():
                            continue  # never drop the catch-all
                        # Try to extract the TO timestamp.
                        import re
                        m = re.search(r"TO\s*\('([^']+)'\)", bound, re.IGNORECASE)
                        if not m:
                            continue
                        try:
                            from datetime import datetime
                            to_ts = datetime.fromisoformat(
                                m.group(1).replace(" ", "T").split("+")[0]
                            )
                        except (TypeError, ValueError):
                            continue
                        from datetime import datetime, timedelta
                        if to_ts < datetime.utcnow() - timedelta(days=retention_days):
                            await conn.execute(
                                f"ALTER TABLE topology_history "
                                f"DETACH PARTITION {p['part_name']}"
                            )
                            await conn.execute(
                                f"DROP TABLE {p['part_name']}"
                            )
                            dropped += 1
                    return dropped
            except Exception:
                pass

            # SQLite / fallback path: row-level DELETE.
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
            result = await conn.execute(
                "DELETE FROM topology_history WHERE recorded_at < $1", cutoff
            )
            # asyncpg returns a status string like "DELETE 42".
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0


    async def create_user(self, username: str, password_hash: str, email: Optional[str] = None, name: Optional[str] = None) -> dict[str, Any]:
        async with self._get_connection() as conn:
            import uuid as _uuid
            uid = str(_uuid.uuid4())
            await conn.execute(
                "INSERT INTO users (id, username, email, name, password_hash) VALUES ($1, $2, $3, $4, $5)",
                uid, username, email, name, password_hash,
            )
            return {"id": uid, "username": username, "email": email, "name": name, "role": "admin"}

    async def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        async with self._get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
            return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        async with self._get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
            return dict(row) if row else None

    async def get_settings(self) -> dict[str, Any]:
        async with self._get_connection() as conn:
            row = await conn.fetchrow("SELECT value FROM app_settings WHERE key = 'config'")
            if row:
                return json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
            return {}

    async def update_settings(self, data: dict[str, Any]):
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE app_settings SET value = $1, updated = NOW() WHERE key = 'config'",
                json.dumps(data),
            )

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

    async def get_topology_history(
        self, limit: int = 100, event_type: str = None,
        from_time: str = None, to_time: str = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get recent topology change history with optional filters."""
        async with self._get_connection() as conn:
            where = []
            params = []
            if event_type:
                where.append(f"event_type = ${len(params)+1}")
                params.append(event_type)
            if from_time:
                where.append(f"recorded_at >= ${len(params)+1}")
                params.append(from_time)
            if to_time:
                where.append(f"recorded_at <= ${len(params)+1}")
                params.append(to_time)
            q = "SELECT * FROM topology_history"
            if where:
                q += " WHERE " + " AND ".join(where)
            q += f" ORDER BY recorded_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
            params.extend([limit, offset])
            rows = await conn.fetch(q, *params)
            result = []
            for row in rows:
                d = dict(row)
                if d.get("details"):
                    d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
                result.append(d)
            return result

    async def get_topology_at_event(self, event_id: int) -> dict[str, list[dict[str, Any]]]:
        """Get topology state that existed just before a given history event."""
        async with self._get_connection() as conn:
            # Get the event timestamp
            row = await conn.fetchrow(
                "SELECT recorded_at FROM topology_history WHERE id = $1", event_id
            )
            if not row:
                return {"nodes": [], "links": []}
            recorded_at = row["recorded_at"]
            # Get all topology changes up to this point, reconstruct state
            # Simplified: return current topology minus the changes from this event
            nodes = await conn.fetch("SELECT * FROM topology_nodes")
            links = await conn.fetch("SELECT * FROM topology_links")
            return {"nodes": [dict(n) for n in nodes], "links": [dict(l) for l in links]}
