#!/usr/bin/env python3
"""One-shot dedup of alert_configs.

Older deployments may have duplicate `alert_configs` rows created by
the same `(alert_type, channel, normalized config_json)` triple. The
old migration 005 used to dedupe inline as part of `upgrade head`,
but with PR A the dedup logic was moved to this standalone script
so the migration is purely schema.

Usage:
    # Dry run (default — shows what would be deleted)
    python scripts/dedupe_alert_configs.py

    # Actually delete
    python scripts/dedupe_alert_configs.py --apply

    # Target a specific database
    DATABASE_URL=postgresql://netops:netops@db/netops \\
        python scripts/dedupe_alert_configs.py --apply

    # Target a SQLite file
    SQLITE_PATH=./data/netops.db python scripts/dedupe_alert_configs.py --apply

The dedup keeps the *oldest* row for each duplicate triple (oldest
by `created` ASC, matching the original 005 logic) and deletes the
rest. Cascades to `alert_history.alert_config_id` for any deleted
alert.

Idempotent: re-running is a no-op once duplicates are cleared.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _normalize_config(config: Any) -> str:
    """Stable JSON signature for dedup matching."""
    if not config:
        return ""
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (TypeError, json.JSONDecodeError):
            return config
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def _signature(alert_type: str, channel: str, config: Any) -> tuple:
    return (alert_type.lower(), channel.lower(), _normalize_config(config))


async def _find_duplicates(conn) -> list[tuple]:
    """Return list of (id, alert_type, channel, config_json) rows that
    are NOT the oldest of their signature.
    """
    rows = await conn.fetch(
        "SELECT id, alert_type, channel, config_json, created "
        "FROM alert_configs ORDER BY created ASC"
    )
    seen: dict[tuple, Any] = {}
    to_delete: list[tuple] = []
    for row in rows:
        cfg = row["config_json"]
        try:
            cfg_obj = json.loads(cfg) if cfg else {}
        except (TypeError, json.JSONDecodeError):
            cfg_obj = {}
        key = _signature(row["alert_type"], row["channel"], cfg_obj)
        if key in seen:
            to_delete.append((row["id"], row["alert_type"], row["channel"]))
        else:
            seen[key] = row["id"]
    return to_delete


async def _apply_sqlite(sqlite_path: str, apply: bool) -> int:
    import aiosqlite
    conn = await aiosqlite.connect(sqlite_path)
    try:
        dups = await _find_duplicates_sqlite(conn)
        if not dups:
            print("No duplicates found.")
            return 0
        print(f"Found {len(dups)} duplicate alert_configs:")
        for id_, atype, channel in dups:
            print(f"  - id={id_} alert_type={atype} channel={channel}")
        if not apply:
            print()
            print("Dry run. Re-run with --apply to delete.")
            return 0
        for id_, _, _ in dups:
            await conn.execute(
                "DELETE FROM alert_history WHERE alert_config_id = ?", (id_,)
            )
            await conn.execute(
                "DELETE FROM alert_configs WHERE id = ?", (id_,)
            )
        await conn.commit()
        print(f"Deleted {len(dups)} duplicate alert_configs.")
        return len(dups)
    finally:
        await conn.close()


async def _find_duplicates_sqlite(conn) -> list[tuple]:
    """SQLite version: same logic as PG, but uses Row index by name."""
    conn.row_factory = None
    cursor = await conn.execute(
        "SELECT id, alert_type, channel, config_json, created "
        "FROM alert_configs ORDER BY created ASC"
    )
    rows = await cursor.fetchall()
    seen: dict[tuple, str] = {}
    to_delete: list[tuple] = []
    for row in rows:
        id_, atype, channel, cfg, _ = row
        try:
            cfg_obj = json.loads(cfg) if cfg else {}
        except (TypeError, json.JSONDecodeError):
            cfg_obj = {}
        key = _signature(atype, channel, cfg_obj)
        if key in seen:
            to_delete.append((id_, atype, channel))
        else:
            seen[key] = id_
    return to_delete


async def _apply_pg(database_url: str, apply: bool) -> int:
    import asyncpg
    conn = await asyncpg.connect(database_url)
    try:
        dups = await _find_duplicates(conn)
        if not dups:
            print("No duplicates found.")
            return 0
        print(f"Found {len(dups)} duplicate alert_configs:")
        for id_, atype, channel in dups:
            print(f"  - id={id_} alert_type={atype} channel={channel}")
        if not apply:
            print()
            print("Dry run. Re-run with --apply to delete.")
            return 0
        for id_, _, _ in dups:
            await conn.execute(
                "DELETE FROM alert_history WHERE alert_config_id = $1", id_
            )
            await conn.execute(
                "DELETE FROM alert_configs WHERE id = $1", id_
            )
        print(f"Deleted {len(dups)} duplicate alert_configs.")
        return len(dups)
    finally:
        await conn.close()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-shot dedup of alert_configs",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the duplicates (default: dry run)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL DSN (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("SQLITE_PATH", "./data/netops.db"),
        help="SQLite file path (used when --database-url is not set)",
    )
    args = parser.parse_args()

    if args.database_url:
        await _apply_pg(args.database_url, args.apply)
    else:
        await _apply_sqlite(args.sqlite, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
