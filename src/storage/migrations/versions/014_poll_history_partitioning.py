"""Phase 4: poll_history monthly range partitioning (PG only).

Revision ID: 014
Revises: 013
Create Date: 2026-06-06

Mirror of migration 010 for the `poll_history` table. At 200+
devices polled every 30-60 seconds, the `poll_history` table
sees 200-400 inserts/min sustained. Monthly partitions keep
B-tree indexes small and let `cleanup_poll_history()` use
`DETACH PARTITION` instead of a row-level DELETE.

Behavior mirrors 010:
  - On PostgreSQL: renames `poll_history` to `poll_history_legacy`,
    creates a partitioned parent, copies legacy rows into a
    `poll_history_default` catch-all partition, pre-creates
    partitions for the current month + 2 future months.
  - On SQLite / other dialects: no-op. The SQLite path keeps
    the plain `poll_history` table from 001.
  - `maintain_poll_history_partitions(months_ahead=3)` is the
    runtime equivalent of migration 010's
    `maintain_topology_partitions()`. It is gated by
    `NETOPS_PHASE4_PARTITIONED_HISTORY=1`.
  - `cleanup_poll_history(retention_days)` is updated to use
    `DETACH PARTITION` for old partitions on PG; falls back to
    row-level DELETE on SQLite.

Operators opt in by setting `NETOPS_PHASE4_PARTITIONED_HISTORY=1`
in the environment. The migration is reversible: rollback
restores the flat `poll_history` table from `poll_history_legacy`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    op.execute("ALTER TABLE poll_history RENAME TO poll_history_legacy")

    op.execute("""
        CREATE TABLE poll_history (
            id SERIAL,
            device_id TEXT,
            status TEXT,
            response_time_ms REAL,
            error TEXT,
            polled_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (id, polled_at)
        ) PARTITION BY RANGE (polled_at)
    """)

    # Recreate the indexes (propagate to children).
    op.execute("CREATE INDEX idx_poll_history_device ON poll_history (device_id)")
    op.execute("CREATE INDEX idx_poll_history_polled_at ON poll_history (polled_at)")

    # The 011 composite index on poll_history. Recreate on the
    # partitioned parent so it propagates to children.
    op.execute(
        "CREATE INDEX idx_poll_history_device_time "
        "ON poll_history (device_id, polled_at DESC)"
    )

    op.execute("""
        CREATE TABLE poll_history_default
        PARTITION OF poll_history DEFAULT
    """)

    op.execute("""
        INSERT INTO poll_history
            (id, device_id, status, response_time_ms, error, polled_at)
        SELECT id, device_id, status, response_time_ms, error, polled_at
        FROM poll_history_legacy
    """)

    op.execute("""
        SELECT setval(
            pg_get_serial_sequence('poll_history', 'id'),
            COALESCE((SELECT MAX(id) FROM poll_history), 1)
        )
    """)

    for offset in range(0, 3):
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS poll_history_{_month_suffix(offset)}
            PARTITION OF poll_history
            FOR VALUES FROM ('{_month_start(offset)}') TO ('{_month_start(offset + 1)}')
        """)


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("DROP TABLE IF EXISTS poll_history CASCADE")
    op.execute("ALTER TABLE poll_history_legacy RENAME TO poll_history")


def _month_start(months_offset: int) -> str:
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
