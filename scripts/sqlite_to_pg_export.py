#!/usr/bin/env python3
"""One-shot data migration: SQLite -> PostgreSQL.

Copies every table that lives in the canonical baseline
(src/storage/migrations/versions/001_initial_schema.py) from a SQLite
file to a PostgreSQL database. The target database must already have
the migration chain applied (run `scripts/migrate.py upgrade head`
first).

Usage:
    DATABASE_URL=postgresql://netops:netops@db/netops \\
        python scripts/sqlite_to_pg_export.py --sqlite data/netops.db

The script is **not idempotent**: re-running it will create duplicate
rows. The recommended sequence is:

    1. Stop the NetOps app.
    2. Run `scripts/migrate.py upgrade head` against the target PG.
    3. Run this script.
    4. Start the NetOps app with `DATABASE_URL` pointing at PG.
    5. Optionally delete the SQLite file.

Notes:
- Tables are copied in dependency order (parents before children).
  The current schema has no FKs, so this is best-effort rather than
  strict.
- `ON CONFLICT DO NOTHING` is used for every INSERT so a partial
  previous run does not produce duplicates. Primary-key violations
  are silently dropped, but every other column-type mismatch will
  raise.
- JSON columns (`config_json`, `secrets_json`, `details`, `tags`) are
  parsed from TEXT and re-serialized; the receiving PG column is
  TEXT (per the model) and the application layer handles JSON.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

# Add project root to path so `from src...` resolves.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# asyncpg is imported at module level (not lazily inside main) so
# tests can monkeypatch the symbol reliably.
try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]


# Order matters: copy parent tables before children. The current
# schema has no FKs, but ordering still reduces the risk of a
# foreign-key error if a future migration adds them.
EXPORT_ORDER = [
    "users",
    "app_settings",
    "networks",
    "devices",
    "topology_nodes",
    "topology_links",
    "integrations",
    "alert_configs",
    "alert_history",
    "service_checks",
    "check_results",
    "poll_history",
    "topology_history",
    "maintenance_windows",
]

# Columns stored as JSON-as-TEXT in both backends. The application
# layer does the json.dumps/loads round-trip; this script just
# ensures the value is valid JSON before inserting.
JSON_COLUMNS = {"config_json", "secrets_json", "details", "tags"}


def _coerce_json(value: Any, col: str) -> Any:
    """If value is a JSON string, return the parsed object; else value.

    PG accepts a Python dict via asyncpg's JSON adapter; passing the
    parsed object lets asyncpg serialize it. If the value is already
    a dict (some SQLite drivers return parsed JSON), pass through.
    """
    if col not in JSON_COLUMNS or value is None:
        return value
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value
    return value


async def _read_sqlite_table(sqlite_conn, table: str) -> tuple[list[str], list[tuple]]:
    """Read all rows from a SQLite table. Returns (column_names, rows)."""
    cursor = await sqlite_conn.execute(f"SELECT * FROM {table}")
    rows = await cursor.fetchall()
    if not rows:
        # Still return column names so the caller can emit a skip
        # message instead of an INSERT with no column info.
        cols_cursor = await sqlite_conn.execute(
            f"PRAGMA table_info({table})"
        )
        col_info = await cols_cursor.fetchall()
        col_names = [row[1] for row in col_info]
        return col_names, []
    # aiosqlite rows are tuples; first row gives column ordering
    # only if aiosqlite.Row is enabled. Easiest: PRAGMA once.
    cols_cursor = await sqlite_conn.execute(f"PRAGMA table_info({table})")
    col_info = await cols_cursor.fetchall()
    col_names = [row[1] for row in col_info]
    return col_names, [tuple(r) for r in rows]


async def _export_one_table(pg_conn, sqlite_conn, table: str) -> int:
    """Copy one table from SQLite to PG. Returns row count copied."""
    col_names, rows = await _read_sqlite_table(sqlite_conn, table)
    if not col_names:
        print(f"  {table}: (no columns) skipping")
        return 0
    if not rows:
        print(f"  {table}: 0 rows, skipping")
        return 0

    placeholders = ", ".join(f"${i+1}" for i in range(len(col_names)))
    col_list = ", ".join(f'"{c}"' for c in col_names)
    insert_sql = (
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
        f"ON CONFLICT DO NOTHING"
    )

    copied = 0
    for row in rows:
        # Coerce JSON columns to native Python objects so asyncpg
        # serializes them correctly. Other columns pass through.
        values = [
            _coerce_json(v, col_names[i]) for i, v in enumerate(row)
        ]
        await pg_conn.execute(insert_sql, *values)
        copied += 1

    print(f"  {table}: {copied} rows copied")
    return copied


async def _ensure_target_schema(pg_conn) -> None:
    """Check that alembic_version exists; raise with a clear message if not."""
    row = await pg_conn.fetchrow(
        "SELECT to_regclass('public.alembic_version')"
    )
    if not row or row[0] is None:
        raise RuntimeError(
            "Target PostgreSQL database has no alembic_version table. "
            "Run `python scripts/migrate.py upgrade head` first."
        )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-shot data migration: SQLite -> PostgreSQL",
    )
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("SQLITE_PATH", "./data/netops.db"),
        help="Path to source SQLite file (default: ./data/netops.db)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Target PostgreSQL DSN (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Restrict export to a specific table (repeatable).",
    )
    args = parser.parse_args()

    if not args.database_url:
        print(
            "ERROR: target database URL not set. Pass --database-url or "
            "set DATABASE_URL environment variable.",
            file=sys.stderr,
        )
        return 1

    if not os.path.exists(args.sqlite):
        print(
            f"ERROR: source SQLite file not found: {args.sqlite}",
            file=sys.stderr,
        )
        return 1

    if asyncpg is None:
        print("ERROR: asyncpg is not installed. Run `pip install asyncpg`.",
              file=sys.stderr)
        return 1

    import aiosqlite

    tables = args.only or EXPORT_ORDER

    print(f"SQLite source:  {args.sqlite}")
    print(f"PostgreSQL target: {args._get_kwargs()[1][1] if False else args.database_url}")
    print(f"Tables: {', '.join(tables)}")
    print()

    sqlite_conn = await aiosqlite.connect(args.sqlite)
    sqlite_conn.row_factory = None  # tuples, not Row
    try:
        pg_conn = await asyncpg.connect(args.database_url)
        try:
            await _ensure_target_schema(pg_conn)
            print("Target schema verified (alembic_version present).")
            print()

            total = 0
            for table in tables:
                try:
                    copied = await _export_one_table(
                        pg_conn, sqlite_conn, table
                    )
                    total += copied
                except Exception as e:
                    print(f"  {table}: ERROR {e}", file=sys.stderr)
                    raise

            print()
            print(f"Done. {total} rows copied across {len(tables)} tables.")
        finally:
            await pg_conn.close()
    finally:
        await sqlite_conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
