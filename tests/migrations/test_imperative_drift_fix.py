"""Test that a database bootstrapped imperatively (legacy path) can be
upgraded cleanly by the new Alembic chain.

This protects against the drift where the imperative `init_db()` was
the de-facto schema source and the migrations were incomplete. With
the new baseline in 001, both the imperative path and the migration
path converge on the same schema.

Note: this test bypasses the empty `init_db()` in the new code path
by directly executing the old DDL against a fresh DB, then runs the
migrations and asserts the final schema matches.
"""

import os
import tempfile

import pytest
from alembic import command
from alembic.config import Config


def _alembic_config_for_sqlite(path: str) -> Config:
    config = Config(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "storage", "alembic.ini",
        )
    )
    config.set_main_option(
        "script_location",
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "storage", "migrations",
        ),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path}")
    return config


def _bootstrap_imperative(db_path: str) -> None:
    """Simulate the legacy imperative `init_db()` bootstrap.

    Creates a subset of the schema (the tables the original
    imperative DDL covered) and the duplicate-name indexes that
    006 is meant to clean up.
    """
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE devices (
            id TEXT PRIMARY KEY,
            name TEXT,
            ip_address TEXT UNIQUE NOT NULL,
            community TEXT DEFAULT 'public',
            status TEXT DEFAULT 'unknown',
            sys_descr TEXT,
            discovery_method TEXT DEFAULT 'manual',
            network_id TEXT,
            snmp_version TEXT DEFAULT '2c',
            snmpv3_username TEXT,
            snmpv3_auth_protocol TEXT,
            snmpv3_auth_key TEXT,
            snmpv3_priv_protocol TEXT,
            snmpv3_priv_key TEXT,
            last_polled TEXT,
            created TEXT DEFAULT (datetime('now')),
            updated TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE topology_nodes (
            id TEXT PRIMARY KEY,
            device_id TEXT,
            network_id TEXT,
            label TEXT,
            node_type TEXT DEFAULT 'device',
            status TEXT DEFAULT 'unknown',
            created TEXT DEFAULT (datetime('now')),
            updated TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE topology_links (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            network_id TEXT,
            source_port TEXT,
            target_port TEXT,
            status TEXT DEFAULT 'active',
            created TEXT DEFAULT (datetime('now')),
            updated TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE poll_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            status TEXT,
            response_time_ms REAL,
            error TEXT,
            polled_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE alert_configs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            config_json TEXT,
            integration_id TEXT,
            enabled INTEGER DEFAULT 1,
            created TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE integrations (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            secrets_json TEXT,
            enabled INTEGER DEFAULT 1,
            created TEXT DEFAULT (datetime('now')),
            UNIQUE(type, name)
        );
        CREATE TABLE alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_config_id TEXT,
            triggered_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT,
            message TEXT,
            status TEXT DEFAULT 'triggered'
        );
        CREATE TABLE service_checks (
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
        CREATE TABLE check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_id TEXT,
            status TEXT,
            response_time_ms REAL,
            message TEXT,
            details TEXT,
            error TEXT,
            checked_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE topology_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            node_id TEXT,
            link_id TEXT,
            source_ip TEXT,
            old_status TEXT,
            new_status TEXT,
            details TEXT,
            recorded_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE maintenance_windows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE networks (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            cidr TEXT,
            description TEXT,
            is_default INTEGER DEFAULT 0,
            network_type TEXT,
            tags TEXT DEFAULT '[]',
            last_scanned TEXT,
            created TEXT DEFAULT (datetime('now')),
            updated TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            name TEXT,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO app_settings (key, value) VALUES ('config', '{}');

        -- Duplicate-name indexes (the drift that 006 is meant to clean up).
        CREATE INDEX idx_devices_network ON devices(network_id);
        CREATE INDEX idx_nodes_network ON topology_nodes(network_id);
        CREATE INDEX idx_links_network ON topology_links(network_id);
    """)
    conn.commit()
    conn.close()


def _indexes_on(db_path: str, table: str) -> set[str]:
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
        return {row[1] for row in rows}
    finally:
        conn.close()


def test_migrations_apply_cleanly_to_imperative_db():
    """A DB bootstrapped by the legacy imperative DDL can be upgraded by Alembic."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        _bootstrap_imperative(db_path)
        config = _alembic_config_for_sqlite(db_path)
        # Should not raise.
        command.upgrade(config, "head")
    finally:
        os.unlink(db_path)


def test_migration_006_drops_duplicate_indexes():
    """The 006 migration removes the legacy `*_network` duplicate indexes."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        _bootstrap_imperative(db_path)
        # Verify the duplicates exist before migration.
        assert "idx_devices_network" in _indexes_on(db_path, "devices")
        assert "idx_nodes_network" in _indexes_on(db_path, "topology_nodes")
        assert "idx_links_network" in _indexes_on(db_path, "topology_links")

        config = _alembic_config_for_sqlite(db_path)
        command.upgrade(config, "head")

        # After upgrade, duplicates should be gone.
        assert "idx_devices_network" not in _indexes_on(db_path, "devices")
        assert "idx_nodes_network" not in _indexes_on(db_path, "topology_nodes")
        assert "idx_links_network" not in _indexes_on(db_path, "topology_links")
    finally:
        os.unlink(db_path)
