"""Async SQLite database layer for NetOps (fallback for dev/testing)."""

import asyncio
import aiosqlite
import json
import os
import uuid
from datetime import datetime
from typing import Any, Optional


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
        await self._db.execute("PRAGMA busy_timeout=30000")
        await self._db.commit()

    async def disconnect(self):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def init_db(self):
        """Initialize database schema."""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT,
                ip_address TEXT UNIQUE NOT NULL,
                community TEXT DEFAULT 'public',
                status TEXT DEFAULT 'unknown',
                sys_descr TEXT,
                discovery_method TEXT DEFAULT 'manual',
                last_polled TEXT,
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS topology_nodes (
                id TEXT PRIMARY KEY,
                device_id TEXT,
                label TEXT,
                node_type TEXT DEFAULT 'device',
                status TEXT DEFAULT 'unknown',
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS topology_links (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                source_port TEXT,
                target_port TEXT,
                status TEXT DEFAULT 'active',
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS poll_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                status TEXT,
                response_time_ms REAL,
                error TEXT,
                polled_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alert_configs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                config_json TEXT,
                enabled INTEGER DEFAULT 1,
                created TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_config_id TEXT,
                triggered_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                message TEXT,
                status TEXT DEFAULT 'triggered'
            );

            CREATE TABLE IF NOT EXISTS service_checks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                check_type TEXT NOT NULL,
                target TEXT NOT NULL,
                interval_seconds INTEGER DEFAULT 60,
                timeout_seconds INTEGER DEFAULT 10,
                config_json TEXT,
                enabled INTEGER DEFAULT 1,
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                check_id TEXT,
                status TEXT,
                response_time_ms REAL,
                message TEXT,
                details TEXT,
                error TEXT,
                checked_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip_address);
            CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
            CREATE INDEX IF NOT EXISTS idx_nodes_device_id ON topology_nodes(device_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_status ON topology_nodes(status);
            CREATE INDEX IF NOT EXISTS idx_links_source ON topology_links(source_id);
            CREATE INDEX IF NOT EXISTS idx_links_target ON topology_links(target_id);
            CREATE INDEX IF NOT EXISTS idx_poll_history_device ON poll_history(device_id);
            CREATE INDEX IF NOT EXISTS idx_poll_history_polled_at ON poll_history(polled_at);
            CREATE INDEX IF NOT EXISTS idx_alert_configs_enabled ON alert_configs(enabled);
            CREATE INDEX IF NOT EXISTS idx_alert_history_config ON alert_history(alert_config_id);
            CREATE INDEX IF NOT EXISTS idx_service_checks_type ON service_checks(check_type);
            CREATE INDEX IF NOT EXISTS idx_service_checks_enabled ON service_checks(enabled);
            CREATE INDEX IF NOT EXISTS idx_check_results_check_id ON check_results(check_id);
            CREATE INDEX IF NOT EXISTS idx_check_results_checked_at ON check_results(checked_at);

            -- Topology change history for auditing and trend analysis
            CREATE TABLE IF NOT EXISTS topology_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                node_id TEXT,
                link_id TEXT,
                old_status TEXT,
                new_status TEXT,
                details TEXT,
                recorded_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_topology_history_event ON topology_history(event_type);
            CREATE INDEX IF NOT EXISTS idx_topology_history_recorded_at ON topology_history(recorded_at);

            CREATE TABLE IF NOT EXISTS maintenance_windows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_maintenance_windows_time ON maintenance_windows(start_time, end_time);
        """)
        # Migrate existing tables: add discovery_method if missing
        try:
            await self._db.execute(
                "ALTER TABLE devices ADD COLUMN discovery_method TEXT DEFAULT 'manual'"
            )
        except Exception:
            pass  # Column already exists
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
        return [dict(row) for row in rows]

    async def get_device(self, device_id: str) -> Optional[dict[str, Any]]:
        """Get device by ID or IP."""
        cursor = await self._db.execute(
            "SELECT * FROM devices WHERE id = ? OR ip_address = ?",
            (device_id, device_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new device."""
        device_id = data.get("id") or str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO devices (id, name, ip_address, community, status, sys_descr, discovery_method, last_polled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (device_id, data.get("name", ""), data["ip_address"],
             data.get("community", "public"), data.get("status", "unknown"),
             data.get("sys_descr", ""), data.get("discovery_method", "manual"),
             data.get("last_polled"))
        )
        await self._db.commit()
        return await self.get_device(device_id)

    async def update_device(self, device_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing device."""
        fields = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values()) + [device_id, device_id]
        await self._db.execute(
            f"UPDATE devices SET {fields}, updated = datetime('now') WHERE id = ? OR ip_address = ?",
            values
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

            # Upsert nodes
            for node in nodes:
                await self._db.execute(
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
                    (node["id"], node.get("device_id"), node.get("label", ""),
                     node.get("node_type", "device"), node.get("status", "unknown"))
                )
                if node["id"] not in existing_node_ids:
                    changes["nodes_added"] += 1

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

            # Upsert links
            for link in links:
                await self._db.execute(
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
                    (link["id"], link["source"], link["target"],
                     link.get("source_port", ""), link.get("target_port", ""),
                     link.get("status", "active"))
                )
                if link["id"] not in existing_link_ids:
                    changes["links_added"] += 1

            # Delete removed links
            if removed_link_ids:
                placeholders = ",".join("?" * len(removed_link_ids))
                await self._db.execute(
                    f"DELETE FROM topology_links WHERE id IN ({placeholders})",
                    list(removed_link_ids)
                )

            # Record topology changes in history
            if changes["nodes_added"] > 0 or changes["nodes_removed"] > 0 or changes["links_added"] > 0 or changes["links_removed"] > 0:
                await self._record_topology_changes(changes, nodes, links)

            await self._db.commit()
            return changes

    async def _record_topology_changes(self, changes: dict, nodes: list, links: list):
        """Record topology changes in history table for auditing."""
        event_type = "topology_change"
        if changes["nodes_added"] > 0:
            for node in nodes:
                await self._db.execute(
                    "INSERT INTO topology_history (event_type, node_id, new_status, details) VALUES (?, ?, ?, ?)",
                    (event_type, node["id"], node.get("status", "unknown"), json.dumps({"action": "added", "type": "node"}))
                )
        if changes["links_added"] > 0:
            for link in links:
                await self._db.execute(
                    "INSERT INTO topology_history (event_type, link_id, new_status, details) VALUES (?, ?, ?, ?)",
                    (event_type, link.get("id"), link.get("status", "active"), json.dumps({"action": "added", "type": "link"}))
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
        await self._db.execute(
            "INSERT INTO poll_history (device_id, status, response_time_ms, error) VALUES (?, ?, ?, ?)",
            (device_id, status, response_time_ms, error)
        )
        await self._db.commit()

    # Alert methods
    async def list_alert_configs(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List alert configurations with optional pagination."""
        query = "SELECT * FROM alert_configs WHERE enabled = 1"
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

    async def create_alert_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create an alert configuration."""
        alert_id = str(uuid.uuid4())
        config_json = json.dumps(data.get("config", {}))
        await self._db.execute(
            "INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled) VALUES (?, ?, ?, ?, ?, ?)",
            (alert_id, data["name"], data["alert_type"], data["channel"], config_json,
             1 if data.get("enabled", True) else 0)
        )
        await self._db.commit()
        return await self._get_alert_config(alert_id)

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
