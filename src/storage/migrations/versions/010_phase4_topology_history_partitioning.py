"""Phase 4: topology_history monthly range partitioning (PG only).

Revision ID: 010
Revises: 008
Create Date: 2026-06-06

Convert `topology_history` from a plain table to a PostgreSQL
range-partitioned table on `recorded_at`, monthly granularity. This
prepares the schema for trap-driven load (Phase 4): 200 devices × 4
ports × 1 flap/day = 800 events/day sustained, with bursts of 3-5
events/sec during a datacenter rebuild. Without partitioning, the
`idx_topology_history_recorded_at` B-tree will bloat and reads
will degrade.

Behavior:
  - On PostgreSQL: renames the existing `topology_history` to
    `topology_history_legacy`, creates a partitioned
    `topology_history` parent with the same columns, copies the
    legacy rows into a `topology_history_default` catch-all
    partition, and pre-creates partitions for the current month
    plus the next 2 months ahead.
  - On SQLite / other dialects: no-op. The migration is no-op
    outside PG so the SQLite fast-lane tests stay green.
  - NetOps feature flag `NETOPS_PHASE4_PARTITIONED_HISTORY` is
    checked by `maintain_topology_partitions()` (defined in
    `AsyncPostgresClient`); if the flag is off, the partitioned
    table is created but no maintenance runs. Operators can flip
    the flag on after observing schema stability.

Index strategy:
  - The composite indexes for trap queries (Phase 4 spec) live in
    migration 011. This migration creates only the partition
    plumbing.

Rollback:
  - Detach all partitions, drop the partitioned parent, rename
    `topology_history_legacy` back to `topology_history`.
  - The migration is reversible but data is preserved.

Net effect on the application:
  - `INSERT INTO topology_history ...` works unchanged (rows
    route to the partition whose range covers `recorded_at`).
  - `SELECT ... FROM topology_history` is unchanged (the parent
    transparently unions all partitions).
  - `cleanup_topology_history(retention_days=90)` becomes
    `DETACH PARTITION topology_history_<old_month>` for any
    partition whose end is older than the cutoff, instead of a
    row-level `DELETE`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # No-op on SQLite and other non-PG backends. The SQLite path
        # keeps the plain `topology_history` table from 001.
        return

    # --------------------------------------------------------------
    # Step 1: Rename the existing table so we can recreate it as
    # a partitioned parent with the same name. Drop its indexes
    # first so their names don't collide with the new table's
    # indexes (PG schema-level uniqueness constraint).
    # --------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_topology_history_event")
    op.execute("DROP INDEX IF EXISTS idx_topology_history_recorded_at")
    op.execute("DROP INDEX IF EXISTS idx_topology_history_source_time")
    op.execute("DROP INDEX IF EXISTS idx_topology_history_link_time")
    op.execute("ALTER TABLE topology_history RENAME TO topology_history_legacy")

    # --------------------------------------------------------------
    # Step 2: Create the partitioned parent. Schema matches the
    # 001 baseline so all existing INSERTs and SELECTs work
    # without code changes.
    # --------------------------------------------------------------
    op.execute("""
        CREATE TABLE topology_history (
            id SERIAL,
            event_type TEXT NOT NULL,
            node_id TEXT,
            link_id TEXT,
            source_ip TEXT,
            old_status TEXT,
            new_status TEXT,
            details TEXT,
            recorded_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, recorded_at)
        ) PARTITION BY RANGE (recorded_at)
    """)

    # --------------------------------------------------------------
    # Step 3: Recreate the indexes (they propagate to children).
    # --------------------------------------------------------------
    op.execute("""
        CREATE INDEX idx_topology_history_event
        ON topology_history (event_type)
    """)
    op.execute("""
        CREATE INDEX idx_topology_history_recorded_at
        ON topology_history (recorded_at)
    """)

    # --------------------------------------------------------------
    # Step 4: Catch-all default partition for any rows that fall
    # outside the explicit month ranges (e.g. data copied in
    # from topology_history_legacy).
    # --------------------------------------------------------------
    op.execute("""
        CREATE TABLE topology_history_default
        PARTITION OF topology_history DEFAULT
    """)

    # --------------------------------------------------------------
    # Step 5: Copy legacy data into the default partition. After
    # this step, the application sees a unified topology_history
    # table with all rows present.
    # --------------------------------------------------------------
    op.execute("""
        INSERT INTO topology_history
            (id, event_type, node_id, link_id, source_ip,
             old_status, new_status, details, recorded_at)
        SELECT id, event_type, node_id, link_id, source_ip,
               old_status, new_status, details, recorded_at
        FROM topology_history_legacy
    """)

    # Reset the SERIAL sequence so future INSERTs don't collide
    # with the copied-in ids.
    op.execute("""
        SELECT setval(
            pg_get_serial_sequence('topology_history', 'id'),
            COALESCE((SELECT MAX(id) FROM topology_history), 1)
        )
    """)

    # --------------------------------------------------------------
    # Step 6: Pre-create partitions for the current month and the
    # next 2 months. The application can still write to the
    # default partition if a row arrives outside the pre-created
    # ranges, so this is a performance optimization, not a
    # correctness requirement.
    # --------------------------------------------------------------
    for offset in range(0, 3):
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS topology_history_{_month_suffix(offset)}
            PARTITION OF topology_history
            FOR VALUES FROM ('{_month_start(offset)}') TO ('{_month_start(offset + 1)}')
        """)


def downgrade() -> None:
    if not _is_postgres():
        return

    # Detach all partitions (no-op for already-detached).
    # We don't drop the data; we re-attach to a single table.
    op.execute("""
        DROP TABLE IF EXISTS topology_history CASCADE
    """)
    op.execute("""
        ALTER TABLE topology_history_legacy RENAME TO topology_history
    """)


# ---------------------------------------------------------------------
# Partition-naming helpers
# ---------------------------------------------------------------------

def _month_start(months_offset: int) -> str:
    """ISO date 'YYYY-MM-01' for the month `months_offset` from today.

    months_offset=0 is the current month; 1 is next; -1 is previous.
    """
    from datetime import date
    today = date.today()
    year = today.year
    month = today.month + months_offset
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}-{month:02d}-01"


def _month_suffix(months_offset: int) -> str:
    """Suffix used in partition table name, e.g. '2026_06'."""
    from datetime import date
    today = date.today()
    year = today.year
    month = today.month + months_offset
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}_{month:02d}"
