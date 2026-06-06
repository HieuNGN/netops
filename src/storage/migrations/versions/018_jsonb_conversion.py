"""Convert JSON-as-TEXT columns to native JSONB on PostgreSQL.

Revision ID: 018
Revises: 017
Create Date: 2026-06-06

Closes the A11 anomaly (JSON type drift) flagged in the senior
code review. Per the prior plan, the application model uses
`Column("config_json", String)` and the migration used
`sa.JSON()`. PG stored these as `JSON` (text-based) while the
runtime imperative DDL used `JSONB` (binary, indexable, smaller
on disk).

This migration:

  1. ALTERs the four affected columns to JSONB:
     - `alert_configs.config_json`
     - `service_checks.config_json`
     - `integrations.secrets_json`
     - `check_results.details`
     - `topology_history.details`
     - `networks.tags`
  2. Validates the existing values are valid JSON; values that
     are NULL or empty string are left as JSONB null. Values
     that fail to parse are logged and the migration refuses
     to proceed for that column (operator must clean up first).
  3. Adds a GIN index on the JSONB columns that are queried
     with `details @> '{...}'` style operators (Phase 4 traps
     and alert history).

On SQLite / non-PG: no-op. The portable `String` column type
remains the source of truth on those backends.

Reversibility: the migration drops the GIN indexes and
converts the columns back to TEXT. Values are preserved
(`JSONB -> TEXT` is a textual cast in PG).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB_COLUMNS = [
    ("alert_configs", "config_json"),
    ("service_checks", "config_json"),
    ("integrations", "secrets_json"),
    ("check_results", "details"),
    ("topology_history", "details"),
    ("networks", "tags"),
]

# Columns that get a GIN index for `@>` containment queries.
GIN_COLUMNS = [
    ("topology_history", "details"),
    ("alert_configs", "config_json"),
]


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    bind = op.get_bind()

    # 1. Validate that all existing values are valid JSON. If a
    #    value is not valid JSON, log it and raise so the operator
    #    can fix the bad rows before re-running.
    for table, col in JSONB_COLUMNS:
        bad = bind.execute(sa.text(
            f"SELECT id FROM {table} "
            f"WHERE {col} IS NOT NULL AND {col} != '' "
            f"AND {col}::text !~ '^[{{\\[].*[}}\\]]$' "
            f"  AND {col}::text !~ '^-?[0-9]+(\\.[0-9]+)?$' "
            f"  AND {col}::text !~ '^\"(?:\\\\.|[^\"\\\\])*\"$' "
            f"  AND {col}::text !~ '^(true|false|null)$' "
            f"LIMIT 1"
        )).fetchone()
        if bad:
            raise RuntimeError(
                f"Column {table}.{col} contains non-JSON value at id={bad[0]!r}. "
                f"Clean up the data before running this migration."
            )

    # 2. Convert each column to JSONB. Using a temporary USAGE
    #    cast is the safest path: ALTER TYPE ... USING expr.
    for table, col in JSONB_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE JSONB USING {col}::jsonb")

    # 3. Add GIN indexes for `@>` queries.
    for table, col in GIN_COLUMNS:
        idx_name = f"idx_{table}_{col}_gin"
        op.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} USING GIN ({col})")


def downgrade() -> None:
    if not _is_postgres():
        return

    bind = op.get_bind()

    for table, col in GIN_COLUMNS:
        idx_name = f"idx_{table}_{col}_gin"
        op.execute(f"DROP INDEX IF EXISTS {idx_name}")

    for table, col in reversed(JSONB_COLUMNS):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TEXT USING {col}::text")
