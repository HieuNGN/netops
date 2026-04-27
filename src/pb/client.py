"""PocketBase client wrapper for NetOps."""

import json
import os
import sqlite3
from typing import Any, Optional

import httpx


class PocketBaseClient:
    """PocketBase REST client for Python."""

    def __init__(self, base_url: str = "http://127.0.0.1:8090"):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.client = httpx.AsyncClient(timeout=30.0)

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate as superuser."""
        response = await self.client.post(
            f"{self.base_url}/api/admins/auth-with-password",
            json={"identity": email, "password": password},
        )
        response.raise_for_status()
        data = response.json()
        self.token = data.get("token")
        self.client.headers["Authorization"] = self.token
        return data

    async def list_records(
        self, collection: str, filter_expr: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        """List records from a collection."""
        params = {"perPage": limit}
        if filter_expr:
            params["filter"] = filter_expr
        response = await self.client.get(
            f"{self.base_url}/api/collections/{collection}/records",
            params=params,
        )
        response.raise_for_status()
        return response.json().get("items", [])

    async def get_record(
        self, collection: str, record_id: str
    ) -> Optional[dict[str, Any]]:
        """Get a single record by ID."""
        response = await self.client.get(
            f"{self.base_url}/api/collections/{collection}/records/{record_id}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def create_record(
        self, collection: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new record."""
        response = await self.client.post(
            f"{self.base_url}/api/collections/{collection}/records",
            json=data,
        )
        response.raise_for_status()
        return response.json()

    async def update_record(
        self, collection: str, record_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing record."""
        response = await self.client.patch(
            f"{self.base_url}/api/collections/{collection}/records/{record_id}",
            json=data,
        )
        response.raise_for_status()
        return response.json()

    async def delete_record(self, collection: str, record_id: str) -> bool:
        """Delete a record."""
        response = await self.client.delete(
            f"{self.base_url}/api/collections/{collection}/records/{record_id}"
        )
        return response.status_code == 204

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class EmbeddedPocketBase:
    """Embedded PocketBase using SQLite directly."""

    def __init__(self, db_path: str = "./data/netops.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite schema for NetOps collections."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Devices collection
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT,
                ip_address TEXT UNIQUE NOT NULL,
                community TEXT DEFAULT 'public',
                status TEXT DEFAULT 'unknown',
                sys_descr TEXT,
                last_polled TEXT,
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            )
        """
        )

        # Topology nodes
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS topology_nodes (
                id TEXT PRIMARY KEY,
                device_id TEXT,
                label TEXT,
                node_type TEXT DEFAULT 'device',
                status TEXT DEFAULT 'unknown',
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            )
        """
        )

        # Topology links
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS topology_links (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                source_port TEXT,
                target_port TEXT,
                status TEXT DEFAULT 'active',
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            )
        """
        )

        # Poll history
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS poll_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                status TEXT,
                response_time_ms REAL,
                error TEXT,
                polled_at TEXT DEFAULT (datetime('now'))
            )
        """
        )

        # Alert configurations
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_configs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                config_json TEXT,
                enabled INTEGER DEFAULT 1,
                created TEXT DEFAULT (datetime('now'))
            )
        """
        )

        # Alert history
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_config_id TEXT,
                triggered_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                message TEXT,
                status TEXT DEFAULT 'triggered'
            )
        """
        )

        conn.commit()
        conn.close()

    def get_connection(self):
        """Get a database connection."""
        import sqlite3

        return sqlite3.connect(self.db_path)

    def list_devices(self) -> list[dict[str, Any]]:
        """List all devices."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY created DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_device(self, device_id: str) -> Optional[dict[str, Any]]:
        """Get device by ID or IP."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM devices WHERE id = ? OR ip_address = ?",
            (device_id, device_id),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_device(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new device."""
        import uuid

        conn = self.get_connection()
        cursor = conn.cursor()
        device_id = data.get("id") or str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO devices (id, name, ip_address, community, status, sys_descr, last_polled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                device_id,
                data.get("name", ""),
                data["ip_address"],
                data.get("community", "public"),
                data.get("status", "unknown"),
                data.get("sys_descr", ""),
                data.get("last_polled"),
            ),
        )
        conn.commit()
        conn.close()
        return self.get_device(device_id)

    def update_device(self, device_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing device."""
        conn = self.get_connection()
        cursor = conn.cursor()
        fields = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values())
        cursor.execute(
            f"""
            UPDATE devices SET {fields}, updated = datetime('now')
            WHERE id = ? OR ip_address = ?
        """,
            values + [device_id, device_id],
        )
        conn.commit()
        conn.close()
        return self.get_device(device_id)

    def delete_device(self, device_id: str) -> bool:
        """Delete a device."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM devices WHERE id = ? OR ip_address = ?",
            (device_id, device_id),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def list_topology(self) -> dict[str, list[dict[str, Any]]]:
        """Get current topology as nodes/links."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM topology_nodes")
        nodes = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM topology_links")
        links = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return {"nodes": nodes, "links": links}

    def upsert_topology(
        self, nodes: list[dict[str, Any]], links: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upsert topology data, detecting changes."""
        import uuid

        conn = self.get_connection()
        cursor = conn.cursor()

        changes = {"nodes_added": 0, "nodes_removed": 0, "links_added": 0, "links_removed": 0}

        # Get existing node IDs
        cursor.execute("SELECT id FROM topology_nodes")
        existing_node_ids = {row[0] for row in cursor.fetchall()}
        new_node_ids = {n["id"] for n in nodes}

        # Detect removed nodes
        removed_ids = existing_node_ids - new_node_ids
        changes["nodes_removed"] = len(removed_ids)

        # Upsert nodes
        for node in nodes:
            cursor.execute(
                """
                INSERT INTO topology_nodes (id, device_id, label, node_type, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    device_id = excluded.device_id,
                    label = excluded.label,
                    node_type = excluded.node_type,
                    status = excluded.status,
                    updated = datetime('now')
            """,
                (
                    node["id"],
                    node.get("device_id"),
                    node.get("label", ""),
                    node.get("node_type", "device"),
                    node.get("status", "unknown"),
                ),
            )
            if node["id"] not in existing_node_ids:
                changes["nodes_added"] += 1

        # Delete removed nodes
        if removed_ids:
            cursor.execute(
                f"DELETE FROM topology_nodes WHERE id IN ({','.join('?' * len(removed_ids))})",
                tuple(removed_ids),
            )

        # Get existing link IDs
        cursor.execute("SELECT id FROM topology_links")
        existing_link_ids = {row[0] for row in cursor.fetchall()}

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

        # Upsert links
        for link in links:
            cursor.execute(
                """
                INSERT INTO topology_links (id, source_id, target_id, source_port, target_port, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_id = excluded.source_id,
                    target_id = excluded.target_id,
                    source_port = excluded.source_port,
                    target_port = excluded.target_port,
                    status = excluded.status,
                    updated = datetime('now')
            """,
                (
                    link["id"],
                    link["source"],
                    link["target"],
                    link.get("source_port", ""),
                    link.get("target_port", ""),
                    link.get("status", "active"),
                ),
            )
            if link["id"] not in existing_link_ids:
                changes["links_added"] += 1

        # Delete removed links
        if removed_link_ids:
            cursor.execute(
                f"DELETE FROM topology_links WHERE id IN ({','.join('?' * len(removed_link_ids))})",
                tuple(removed_link_ids),
            )

        conn.commit()
        conn.close()

        return changes

    def add_poll_result(
        self, device_id: str, status: str, response_time_ms: float = 0, error: str = ""
    ):
        """Record a poll result."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO poll_history (device_id, status, response_time_ms, error)
            VALUES (?, ?, ?, ?)
        """,
            (device_id, status, response_time_ms, error),
        )
        conn.commit()
        conn.close()

    def list_alert_configs(self) -> list[dict[str, Any]]:
        """List all alert configurations."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_configs WHERE enabled = 1")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def create_alert_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create an alert configuration."""
        import uuid
        import json

        conn = self.get_connection()
        cursor = conn.cursor()
        alert_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO alert_configs (id, name, alert_type, channel, config_json, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                alert_id,
                data["name"],
                data["alert_type"],
                data["channel"],
                json.dumps(data.get("config", {})),
                1 if data.get("enabled", True) else 0,
            ),
        )
        conn.commit()
        conn.close()
        return self._get_alert_config(alert_id)

    def _get_alert_config(self, alert_id: str) -> Optional[dict[str, Any]]:
        """Get alert config by ID."""
        import json

        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_configs WHERE id = ?", (alert_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            result = dict(row)
            result["config_json"] = json.loads(result["config_json"])
            return result
        return None

    def close(self):
        """Close database connections (no-op for SQLite)."""
        pass
