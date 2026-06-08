"""Async SQLite database layer for NetOps (fallback for dev/testing)."""

import asyncio
import aiosqlite
import json
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from src.api.services.encryption import encrypt_field, decrypt_field


def _config_signature(alert_type: str, channel: str, config: dict[str, Any]) -> str:
    """Stable signature for (alert_type, channel, normalized config) dedup."""
    normalized = json.dumps(config or {}, sort_keys=True, separators=(",", ":"))
    return f"{alert_type.lower()}|{channel.lower()}|{normalized}"


class AsyncSQLiteClient:
    """Async SQLite client for development and testing."""

    def __init__(self, db_path: str = "./data/netops.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    async def connect(self):
        """Initialize database connection."""
        self._db = await aiosqlite.connect(self._db_path, timeout=30.0)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA busy_timeout=30000")
        await self._db.commit()

    async def disconnect(self):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def init_db(self):
        """Ensure the schema is current.

        Two cases:
          1. Empty DB (no `alembic_version` table) -> run `alembic
             upgrade head` to bring the schema to current.
          2. DB with `alembic_version` -> no-op; the lifespan's
             auto-migrate has already ensured the schema is current.

        This dual behavior lets test fixtures and the lifespan
        startup code call `init_db()` without knowing whether
        migrations have run, while keeping the application code
        path simple (migrations are the source of truth).

        See src/storage/migrations/versions/001_initial_schema.py for
        the canonical baseline.
        """
        if self._db is None:
            return
        try:
            cursor = await self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )
            row = await cursor.fetchone()
            if row is not None:
                return  # Schema is managed by Alembic; nothing to do.
        except Exception:
            return  # If we can't tell, the lifespan's auto-migrate will handle it.

        # No alembic_version table. Run migrations synchronously.
        # This is a one-time bootstrap; subsequent restarts no-op here.
        def _run_sync() -> None:
            from alembic import command
            from alembic.config import Config

            config = Config(
                os.path.join(
                    os.path.dirname(__file__),
                    "..", "storage", "alembic.ini",
                )
            )
            config.set_main_option(
                "script_location",
                os.path.join(
                    os.path.dirname(__file__),
                    "..", "storage", "migrations",
                ),
            )
            config.set_main_option("sqlalchemy.url", f"sqlite:///{self._db_path}")
            command.upgrade(config, "head")

        try:
            await asyncio.to_thread(_run_sync)
        except Exception:
            # Re-raise so the caller knows schema setup failed.
            raise

    async def healthcheck(self) -> dict[str, Any]:
        """Return SQLite probe latency.

        Used by `/api/health/db`. Returns `error` status with the
        exception message if the probe fails.
        """
        if self._db is None:
            return {"status": "disconnected", "backend": "sqlite", "path": self._db_path}
        try:
            import time
            start = time.time()
            await self._db.execute("SELECT 1")
            latency_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "connected",
                "backend": "sqlite",
                "latency_ms": latency_ms,
                "path": self._db_path,
            }
        except Exception as e:
            return {
                "status": "error",
                "backend": "sqlite",
                "path": self._db_path,
                "message": str(e),
            }

    async def cleanup_poll_history(self, retention_days: int = 30):
        """Delete poll history older than retention_days."""
        import datetime
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=retention_days)).isoformat()
        await self._db.execute("DELETE FROM poll_history WHERE polled_at < ?", (cutoff,))
        await self._db.commit()

    async def cleanup_topology_history(self, retention_days: int = 90) -> int:
        """Delete topology_history rows older than retention_days.

        Mirror of the PG partition-drop path. On SQLite the
        topology_history table is not partitioned, so we do a
        row-level DELETE. The retention loop in the poller calls
        this hourly.
        """
        import datetime
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=retention_days)).isoformat()
        cursor = await self._db.execute(
            "DELETE FROM topology_history WHERE recorded_at < ?", (cutoff,),
        )
        await self._db.commit()
        return cursor.rowcount

    @property
    def phase4_partitioning_enabled(self) -> bool:
        """SQLite fallback does not support partitioning.

        Always returns False on this client; the lifespan's
        `maintain_topology_partitions()` call is a no-op here.
        """
        return False

    async def _execute_with_retry(self, op, *args, **kwargs):
        """Run a DB op and retry on transient 'database is locked' / 'busy' errors.

        Other writers (e.g. the SNMP poller) hold short write transactions on the
        same connection. SQLite can return SQLITE_BUSY between the read snapshot
        and the write even with busy_timeout set, so we retry a few times.
        """
        import sqlite3
        import asyncio
        last_exc: Optional[Exception] = None
        for attempt in range(8):
            try:
                return await op(*args, **kwargs)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "locked" not in msg and "busy" not in msg:
                    raise
                last_exc = e
                await asyncio.sleep(0.05 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def create_user(self, username: str, password_hash: str, email: Optional[str] = None, name: Optional[str] = None, must_change_password: bool = False) -> dict[str, Any]:
        uid = str(uuid.uuid4())
        await self._execute_with_retry(
            self._db.execute,
            "INSERT INTO users (id, username, email, name, password_hash, must_change_password) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, username, email, name, password_hash, must_change_password),
        )
        await self._db.commit()
        return {"id": uid, "username": username, "email": email, "name": name, "role": "admin", "must_change_password": must_change_password}

    async def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        cursor = await self._execute_with_retry(
            self._db.execute, "SELECT * FROM users WHERE username = ?", (username,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        cursor = await self._execute_with_retry(
            self._db.execute, "SELECT * FROM users WHERE email = ?", (email,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_user_password(self, username: str, password_hash: str) -> bool:
        """Update user password and clear must_change_password flag."""
        cursor = await self._execute_with_retry(
            self._db.execute,
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE username = ?",
            (password_hash, username),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_settings(self) -> dict[str, Any]:
        cursor = await self._db.execute("SELECT value FROM app_settings WHERE key = 'config'")
        row = await cursor.fetchone()
        if row:
            v = row[0]
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except (TypeError, json.JSONDecodeError):
                    return v
            return v
        return {}

    async def update_settings(self, data: dict[str, Any]):
        await self._db.execute(
            "UPDATE app_settings SET value = ?, updated = datetime('now') WHERE key = 'config'",
            (json.dumps(data),),
        )
        await self._db.commit()

    async def get_setting(self, key: str, default: Any = None) -> Any:
        cursor = await self._db.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if not row:
            return default
        v = row[0]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (TypeError, json.JSONDecodeError):
                return v
        return v

    async def set_setting(self, key: str, value: Any) -> None:
        if isinstance(value, (dict, list)):
            raw = json.dumps(value)
        elif isinstance(value, bool):
            raw = "true" if value else "false"
        elif value is None:
            raw = None
        else:
            raw = str(value)
        await self._db.execute(
            """
            INSERT INTO app_settings (key, value, updated)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT (key) DO UPDATE
            SET value = excluded.value, updated = datetime('now')
            """,
            (key, raw),
        )
        await self._db.commit()

    async def close(self):
        """Close database connections."""
        await self.disconnect()

    # Helper methods
    async def _row_to_dict(self, cursor, row) -> dict:
        """Convert sqlite3.Row to dict."""
        if row is None:
            return None
        return dict(row)

    async def _rows_to_dicts(self, cursor, rows) -> list:
        """Convert list of sqlite3.Row to list of dicts."""
        return [dict(row) for row in rows]

    # Device methods
    async def list_devices(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List devices with optional pagination."""
        query = "SELECT * FROM devices ORDER BY created DESC"
        params: list[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)
        cursor = await self._db.execute(query, tuple(params) if params else ())
        rows = await cursor.fetchall()
        devices = []
        for row in rows:
            device = dict(row)
            # Decrypt sensitive fields
            for field in ("community", "snmpv3_auth_key", "snmpv3_priv_key"):
                if field in device and device[field]:
                    device[field] = decrypt_field(device[field])
            devices.append(device)
        return devices

    async def get_device(self, device_id: str) -> Optional[dict[str, Any]]:
        """Get device by ID or IP."""
        cursor = await self._db.execute(
            "SELECT * FROM devices WHERE id = ? OR ip_address = ?",
            (device_id, device_id)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        device = dict(row)
        # Decrypt sensitive fields
        for field in ("community", "snmpv3_auth_key", "snmpv3_priv_key"):
            if field in device and device[field]:
                device[field] = decrypt_field(device[field])
        return device

    async def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new device."""
        device_id = data.get("id") or str(uuid.uuid4())
        # Encrypt sensitive fields
        community = encrypt_field(data.get("community", "public"))
        snmpv3_auth_key = encrypt_field(data.get("snmpv3_auth_key"))
        snmpv3_priv_key = encrypt_field(data.get("snmpv3_priv_key"))
        
        await self._db.execute(
            """
            INSERT INTO devices (id, name, ip_address, community, status, sys_descr, discovery_method, last_polled, snmpv3_auth_key, snmpv3_priv_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (device_id, data.get("name", ""), data["ip_address"],
             community, data.get("status", "unknown"),
             data.get("sys_descr", ""), data.get("discovery_method", "manual"),
             data.get("last_polled"), snmpv3_auth_key, snmpv3_priv_key)
        )
        await self._db.commit()
        return await self.get_device(device_id)

    async def update_device(self, device_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing device."""
        encrypted_data = data.copy()
        for field in ("community", "snmpv3_auth_key", "snmpv3_priv_key"):
            if field in encrypted_data and encrypted_data[field] is not None:
                encrypted_data[field] = encrypt_field(encrypted_data[field])
        
        fields = ", ".join(f"{k} = ?" for k in encrypted_data.keys())
        values = list(encrypted_data.values()) + [device_id, device_id]
        await self._execute_with_retry(
            self._db.execute,
            f"UPDATE devices SET {fields}, updated = datetime('now') WHERE id = ? OR ip_address = ?",
            values,
        )
        await self._db.commit()
        return await self.get_device(device_id)

    async def delete_device(self, device_id: str) -> bool:
        """Delete a device."""
        cursor = await self._db.execute(
            "DELETE FROM devices WHERE id = ? OR ip_address = ?",
            (device_id, device_id)
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def bulk_delete_devices(self, device_ids: list[str]) -> int:
        """Delete many devices by id or ip_address. Returns rows removed."""
        if not device_ids:
            return 0
        total = 0
        async with self._lock:
            for did in device_ids:
                cursor = await self._db.execute(
                    "DELETE FROM devices WHERE id = ? OR ip_address = ?",
                    (did, did),
                )
                total += cursor.rowcount
            if total:
                await self._db.execute(
                    """
                    DELETE FROM topology_nodes
                    WHERE device_id IS NULL
                       OR NOT EXISTS (SELECT 1 FROM devices d WHERE d.id = topology_nodes.device_id)
                    """
                )
                await self._db.execute(
                    """
                    DELETE FROM topology_links
                    WHERE NOT EXISTS (SELECT 1 FROM topology_nodes n WHERE n.id = topology_links.source_id)
                       OR NOT EXISTS (SELECT 1 FROM topology_nodes n WHERE n.id = topology_links.target_id)
                    """
                )
            await self._db.commit()
        return total

    async def clear_all_devices(self) -> int:
        """Wipe every device and prune orphan topology. Returns rows removed."""
        async with self._lock:
            cursor = await self._db.execute("DELETE FROM devices")
            total = cursor.rowcount
            await self._db.execute("DELETE FROM topology_nodes")
            await self._db.execute("DELETE FROM topology_links")
            await self._db.commit()
        return total

    # Network methods
    async def list_networks(self) -> list[dict[str, Any]]:
        """List all networks with device_count."""
        cursor = await self._db.execute("""
            SELECT n.*, COUNT(d.id) AS device_count
            FROM networks n
            LEFT JOIN devices d ON d.network_id = n.id
            GROUP BY n.id
            ORDER BY n.name
        """)
        rows = await cursor.fetchall()
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
        """Get network by id or name with device_count."""
        cursor = await self._db.execute("""
            SELECT n.*, COUNT(d.id) AS device_count
            FROM networks n
            LEFT JOIN devices d ON d.network_id = n.id
            WHERE n.id = ? OR n.name = ?
            GROUP BY n.id
        """, (network_id, network_id))
        row = await cursor.fetchone()
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
        await self._db.execute(
            """
            INSERT INTO networks (id, name, cidr, description, is_default)
            VALUES (?, ?, ?, ?, ?)
            """,
            (network_id, data["name"], data.get("cidr"), data.get("description", ""),
             1 if data.get("is_default") else 0)
        )
        await self._db.commit()
        return await self.get_network(network_id)

    async def update_network(self, network_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing network."""
        fields = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values()) + [network_id, network_id]
        await self._db.execute(
            f"UPDATE networks SET {fields}, updated = datetime('now') WHERE id = ? OR name = ?",
            values
        )
        await self._db.commit()
        return await self.get_network(network_id)

    async def delete_network(self, network_id: str) -> bool:
        """Delete a network."""
        cursor = await self._db.execute(
            "DELETE FROM networks WHERE id = ? OR name = ?",
            (network_id, network_id)
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def set_device_network(self, device_id: str, network_id: str) -> dict[str, Any]:
        """Update device's network assignment."""
        await self._db.execute(
            "UPDATE devices SET network_id = ?, updated = datetime('now') WHERE id = ? OR ip_address = ?",
            (network_id, device_id, device_id)
        )
        await self._db.commit()
        return await self.get_device(device_id)

    async def set_default_network(self, network_id: str) -> Optional[dict[str, Any]]:
        """Set is_default=1 for one network, clear others."""
        await self._db.execute(
            "UPDATE networks SET is_default = 0, updated = datetime('now') WHERE is_default = 1"
        )
        await self._db.execute(
            "UPDATE networks SET is_default = 1, updated = datetime('now') WHERE id = ? OR name = ?",
            (network_id, network_id)
        )
        await self._db.commit()
        return await self.get_network(network_id)

    # Topology methods
    async def clear_topology(self):
        """Clear all topology data (nodes and links)."""
        async with self._lock:
            await self._db.execute("DELETE FROM topology_links")
            await self._db.execute("DELETE FROM topology_nodes")
            await self._db.commit()

    async def list_topology(self) -> dict[str, list[dict[str, Any]]]:
        """Get current topology as nodes/links."""
        cursor = await self._db.execute("SELECT * FROM topology_nodes")
        nodes = [dict(row) for row in await cursor.fetchall()]
        cursor = await self._db.execute("SELECT * FROM topology_links")
        links = [dict(row) for row in await cursor.fetchall()]
        return {"nodes": nodes, "links": links}

    async def upsert_topology(
        self, nodes: list[dict[str, Any]], links: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Upsert topology data, detecting changes."""
        async with self._lock:
            changes = {
                "nodes_added": 0, "nodes_removed": 0,
                "links_added": 0, "links_removed": 0,
            }

            # Get existing node IDs
            cursor = await self._db.execute("SELECT id FROM topology_nodes")
            existing_node_ids = {row["id"] for row in await cursor.fetchall()}
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
                await self._db.executemany(
                    """
                    INSERT INTO topology_nodes (id, device_id, label, node_type, status)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        device_id = excluded.device_id,
                        label = excluded.label,
                        node_type = excluded.node_type,
                        status = excluded.status,
                        updated = datetime('now')
                    """,
                    node_values,
                )
            changes["nodes_added"] = len(new_node_ids - existing_node_ids)

            # Delete removed nodes
            if removed_ids:
                placeholders = ",".join("?" * len(removed_ids))
                await self._db.execute(
                    f"DELETE FROM topology_nodes WHERE id IN ({placeholders})",
                    list(removed_ids)
                )

            # Get existing link IDs
            cursor = await self._db.execute("SELECT id FROM topology_links")
            existing_link_ids = {row["id"] for row in await cursor.fetchall()}

            # Generate link IDs if not present
            for link in links:
                if "id" not in link:
                    link["id"] = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"{link['source']}:{link['target']}:{link.get('source_port', '')}:{link.get('target_port', '')}"
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
                await self._db.executemany(
                    """
                    INSERT INTO topology_links (id, source_id, target_id, source_port, target_port, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        source_id = excluded.source_id,
                        target_id = excluded.target_id,
                        source_port = excluded.source_port,
                        target_port = excluded.target_port,
                        status = excluded.status,
                        updated = datetime('now')
                    """,
                    link_values,
                )
            changes["links_added"] = len(new_link_ids - existing_link_ids)

            # Delete removed links
            if removed_link_ids:
                placeholders = ",".join("?" * len(removed_link_ids))
                await self._db.execute(
                    f"DELETE FROM topology_links WHERE id IN ({placeholders})",
                    list(removed_link_ids)
                )

            # Record topology changes in history
            if any(changes.values()):
                added_nodes = [n for n in nodes if n["id"] in (new_node_ids - existing_node_ids)]
                added_links = [l for l in links if l["id"] in (new_link_ids - existing_link_ids)]
                await self._record_topology_changes(changes, added_nodes, added_links)

            await self._db.commit()
            return changes

    async def _record_topology_changes(self, changes: dict, added_nodes: list, added_links: list):
        """Record topology changes in history table for auditing."""
        event_type = "topology_change"
        if added_nodes:
            node_values = [
                (event_type, n["id"], n.get("status", "unknown"),
                 json.dumps({"action": "added", "type": "node"}))
                for n in added_nodes
            ]
            await self._db.executemany(
                "INSERT INTO topology_history (event_type, node_id, new_status, details) VALUES (?, ?, ?, ?)",
                node_values,
            )
        if added_links:
            link_values = [
                (event_type, l.get("id"), l.get("status", "active"),
                 json.dumps({"action": "added", "type": "link"}))
                for l in added_links
            ]
            await self._db.executemany(
                "INSERT INTO topology_history (event_type, link_id, new_status, details) VALUES (?, ?, ?, ?)",
                link_values,
            )
        if changes["nodes_removed"] > 0:
            await self._db.execute(
                "INSERT INTO topology_history (event_type, details) VALUES (?, ?)",
                (event_type, json.dumps({"action": "removed", "type": "nodes", "count": changes["nodes_removed"]}))
            )
        if changes["links_removed"] > 0:
            await self._db.execute(
                "INSERT INTO topology_history (event_type, details) VALUES (?, ?)",
                (event_type, json.dumps({"action": "removed", "type": "links", "count": changes["links_removed"]}))
            )

    async def get_topology_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent topology change history."""
        cursor = await self._db.execute(
            "SELECT * FROM topology_history ORDER BY recorded_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("details"):
                d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
            result.append(d)
        return result

    async def add_poll_result(
        self, device_id: str, status: str, response_time_ms: float = 0, error: str = ""
    ):
        """Record a poll result."""
        await self._execute_with_retry(
            self._db.execute,
            "INSERT INTO poll_history (device_id, status, response_time_ms, error) VALUES (?, ?, ?, ?)",
            (device_id, status, response_time_ms, error),
        )
        await self._db.commit()

    # Alert methods
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
            query += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)
        cursor = await self._db.execute(query, tuple(params) if params else ())
        rows = await cursor.fetchall()
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
        await self._db.execute(
            "INSERT INTO alert_configs (id, name, alert_type, channel, config_json, integration_id, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (alert_id, data["name"], data["alert_type"], data["channel"], config_json,
             data.get("integration_id"),
             1 if data.get("enabled", True) else 0)
        )
        await self._db.commit()
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
            sets.append("name = ?")
            params_list.append(data["name"])
        if "alert_type" in data:
            sets.append("alert_type = ?")
            params_list.append(data["alert_type"])
        if "channel" in data:
            sets.append("channel = ?")
            params_list.append(data["channel"])
        if "config" in data:
            sets.append("config_json = ?")
            params_list.append(json.dumps(data["config"]))
        if "integration_id" in data:
            sets.append("integration_id = ?")
            params_list.append(data["integration_id"])
        if "enabled" in data:
            sets.append("enabled = ?")
            params_list.append(1 if data["enabled"] else 0)

        if not sets:
            return existing

        params_list.append(alert_id)
        query = f"UPDATE alert_configs SET {', '.join(sets)} WHERE id = ?"
        await self._db.execute(query, tuple(params_list))
        await self._db.commit()
        return await self._get_alert_config(alert_id)

    async def delete_alert_config(self, alert_id: str) -> bool:
        """Delete an alert config and its history. Returns True if deleted."""
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT id FROM alert_configs WHERE id = ?", (alert_id,)
            )
            existing = await cursor.fetchone()
            if not existing:
                return False
            await self._db.execute(
                "DELETE FROM alert_history WHERE alert_config_id = ?", (alert_id,)
            )
            await self._db.execute(
                "DELETE FROM alert_configs WHERE id = ?", (alert_id,)
            )
            await self._db.commit()
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
        cursor = await self._db.execute(
            "SELECT * FROM alert_configs WHERE id = ?", (alert_id,)
        )
        row = await cursor.fetchone()
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
            clauses.append("type = ?")
            params_list.append(type)
        if not include_disabled:
            clauses.append("enabled = 1")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created DESC"
        cursor = await self._db.execute(query, tuple(params_list) if params_list else ())
        rows = await cursor.fetchall()
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
        await self._db.execute(
            "INSERT INTO integrations (id, type, name, secrets_json, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            (integration_id, data["type"], data["name"], secrets_json,
             1 if data.get("enabled", True) else 0),
        )
        await self._db.commit()
        result = await self.get_integration(integration_id)
        if not result:
            raise RuntimeError("Failed to create integration")
        return result

    async def get_integration(
        self, integration_id: str
    ) -> Optional[dict[str, Any]]:
        """Get integration by ID."""
        cursor = await self._db.execute(
            "SELECT * FROM integrations WHERE id = ?", (integration_id,)
        )
        row = await cursor.fetchone()
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
            sets.append("type = ?")
            params_list.append(data["type"])
        if "name" in data:
            sets.append("name = ?")
            params_list.append(data["name"])
        if "secrets_json" in data:
            sets.append("secrets_json = ?")
            params_list.append(json.dumps(data["secrets_json"]))
        if "enabled" in data:
            sets.append("enabled = ?")
            params_list.append(1 if data["enabled"] else 0)

        if not sets:
            return existing

        params_list.append(integration_id)
        query = f"UPDATE integrations SET {', '.join(sets)} WHERE id = ?"
        await self._db.execute(query, tuple(params_list))
        await self._db.commit()
        return await self.get_integration(integration_id)

    async def delete_integration(self, integration_id: str) -> tuple[bool, str]:
        """Delete an integration. Returns (success, error_message)."""
        cursor = await self._db.execute(
            "SELECT id FROM integrations WHERE id = ?", (integration_id,)
        )
        existing = await cursor.fetchone()
        if not existing:
            return False, "not found"
        ref_cursor = await self._db.execute(
            "SELECT id FROM alert_configs WHERE integration_id = ? LIMIT 1",
            (integration_id,),
        )
        ref = await ref_cursor.fetchone()
        if ref:
            return False, "integration is referenced by one or more alert rules"
        await self._db.execute(
            "DELETE FROM integrations WHERE id = ?", (integration_id,)
        )
        await self._db.commit()
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
        await self._db.execute(
            "INSERT INTO alert_history (alert_config_id, message, status) VALUES (?, ?, ?)",
            (alert_config_id, message, status),
        )
        await self._db.commit()

    async def get_alert_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent alert history with alert config details."""
        cursor = await self._db.execute(
            """
            SELECT ah.*, ac.name as alert_name, ac.channel
            FROM alert_history ah
            LEFT JOIN alert_configs ac ON ah.alert_config_id = ac.id
            ORDER BY ah.triggered_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def clear_alert_history(self) -> int:
        """Delete all rows from alert_history. Returns count deleted."""
        cursor = await self._db.execute("DELETE FROM alert_history")
        await self._db.commit()
        return cursor.rowcount

    async def get_poll_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent poll history with device details."""
        cursor = await self._db.execute(
            """
            SELECT ph.*, d.ip_address, d.name
            FROM poll_history ph
            LEFT JOIN devices d ON ph.device_id = d.id
            ORDER BY ph.polled_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_maintenance_windows(self) -> list[dict[str, Any]]:
        """List all maintenance windows ordered by start time."""
        cursor = await self._db.execute("SELECT * FROM maintenance_windows ORDER BY start_time DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def create_maintenance_window(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a maintenance window."""
        window_id = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO maintenance_windows (id, name, start_time, end_time, description) VALUES (?, ?, ?, ?, ?)",
            (window_id, data["name"], data["start_time"], data["end_time"], data.get("description", "")),
        )
        await self._db.commit()
        return {"id": window_id, **data}

    async def delete_maintenance_window(self, window_id: str) -> bool:
        """Delete a maintenance window."""
        cursor = await self._db.execute("DELETE FROM maintenance_windows WHERE id = ?", (window_id,))
        await self._db.commit()
        return cursor.rowcount == 1

    async def is_in_maintenance_window(self) -> bool:
        """Check if current time falls within any active maintenance window."""
        import datetime
        now = datetime.datetime.now().isoformat()
        cursor = await self._db.execute(
            "SELECT 1 FROM maintenance_windows WHERE start_time <= ? AND end_time >= ? LIMIT 1",
            (now, now),
        )
        row = await cursor.fetchone()
        return row is not None

    # Service check methods
    async def list_service_checks(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List service checks with optional pagination."""
        query = "SELECT * FROM service_checks ORDER BY created DESC"
        params: list[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)
        cursor = await self._db.execute(query, tuple(params) if params else ())
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("config_json"):
                d["config_json"] = json.loads(d["config_json"]) if isinstance(d["config_json"], str) else d["config_json"]
            result.append(d)
        return result

    async def get_service_check(self, check_id: str) -> Optional[dict[str, Any]]:
        """Get service check by ID."""
        cursor = await self._db.execute(
            "SELECT * FROM service_checks WHERE id = ?", (check_id,)
        )
        row = await cursor.fetchone()
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
        await self._db.execute(
            """
            INSERT INTO service_checks (id, name, check_type, target, interval_seconds, timeout_seconds, config_json, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (check_id, data["name"], data["check_type"], data["target"],
             data.get("interval_seconds", 60), data.get("timeout_seconds", 10),
             config_json, 1 if data.get("enabled", True) else 0)
        )
        await self._db.commit()
        return await self.get_service_check(check_id)

    async def update_service_check(self, check_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a service check."""
        fields = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values()) + [check_id]
        await self._db.execute(
            f"UPDATE service_checks SET {fields}, updated = datetime('now') WHERE id = ?",
            values
        )
        await self._db.commit()
        return await self.get_service_check(check_id)

    async def delete_service_check(self, check_id: str) -> bool:
        """Delete a service check."""
        cursor = await self._db.execute(
            "DELETE FROM service_checks WHERE id = ?", (check_id,)
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def add_check_result(
        self, check_id: str, status: str, response_time_ms: float,
        message: str = "", details: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Record a check result."""
        details_json = json.dumps(details) if details else None
        await self._db.execute(
            """
            INSERT INTO check_results (check_id, status, response_time_ms, message, details, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (check_id, status, response_time_ms, message, details_json, error)
        )
        await self._db.commit()

    async def get_check_results(self, check_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent check results for a specific check."""
        cursor = await self._db.execute(
            """
            SELECT * FROM check_results
            WHERE check_id = ?
            ORDER BY checked_at DESC
            LIMIT ?
            """,
            (check_id, limit)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("details"):
                d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
            result.append(d)
        return result
