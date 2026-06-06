"""Phase 4: composite indexes for trap-driven queries.

Revision ID: 011
Revises: 010
Create Date: 2026-06-06

Adds indexes that match the trap-driven query patterns from
`.opencode/plans/PHASE4_SNMP_TRAPS_SPEC.md`:

  - `(source_ip, recorded_at DESC)` on topology_history:
    "Show me the last 24h of traps from source 10.0.0.5".
  - `(link_id, recorded_at DESC)` on topology_history:
    "Show me the last 100 topology changes for link L".
  - `(event_type, recorded_at DESC)` on topology_history:
    "Show me the last 24h of linkDown events".
  - `(device_id, recorded_at DESC)` on poll_history:
    "Show me the last hour of polls for device D".

For PG partitioned tables, the index propagates to child
partitions. SQLite silently creates plain B-tree indexes (no
DESC support on SQLite before 3.31, but DESC is implicit there).

The basic single-column indexes created in 001 (e.g.
`idx_topology_history_event`) are kept; the composite indexes
here supplement them for ordered scans.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Helper: create an index only if it doesn't already exist AND
    # the table has all the columns the index needs (defensive
    # against legacy schemas bootstrapped by imperative DDL).
    def _table_has_columns(table: str, columns: list[str]) -> bool:
        try:
            existing = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return False
        return all(c in existing for c in columns)

    def _index_exists(table: str, name: str) -> bool:
        try:
            return name in {idx["name"] for idx in inspector.get_indexes(table)}
        except Exception:
            return False

    # ------------------------------------------------------------------
    # topology_history composite indexes (Phase 4 trap queries)
    # Only create the source_ip and link_id indexes if the columns
    # exist (the 001 baseline already added source_ip; legacy
    # imperative-DB bootstraps may not have it).
    # ------------------------------------------------------------------
    if _table_has_columns("topology_history", ["source_ip", "recorded_at"]):
        if not _index_exists("topology_history", "idx_topology_history_source_time"):
            op.execute(
                "CREATE INDEX idx_topology_history_source_time "
                "ON topology_history (source_ip, recorded_at DESC)"
            )
    if _table_has_columns("topology_history", ["link_id", "recorded_at"]):
        if not _index_exists("topology_history", "idx_topology_history_link_time"):
            op.execute(
                "CREATE INDEX idx_topology_history_link_time "
                "ON topology_history (link_id, recorded_at DESC)"
            )
    if _table_has_columns("topology_history", ["event_type", "recorded_at"]):
        if not _index_exists("topology_history", "idx_topology_history_event_time"):
            op.execute(
                "CREATE INDEX idx_topology_history_event_time "
                "ON topology_history (event_type, recorded_at DESC)"
            )

    # ------------------------------------------------------------------
    # poll_history composite index
    # ------------------------------------------------------------------
    if _table_has_columns("poll_history", ["device_id", "polled_at"]):
        if not _index_exists("poll_history", "idx_poll_history_device_time"):
            op.execute(
                "CREATE INDEX idx_poll_history_device_time "
                "ON poll_history (device_id, polled_at DESC)"
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    # Helper: drop an index only if it exists, and the calling
    # migration owns it. Two of the four indexes listed here
    # (source_time, link_time) are also created by the 001 baseline;
    # 011's upgrade is a no-op for those, so 011's downgrade must
    # not drop them either. They will be dropped by 001's own
    # downgrade.
    indexes_topology = {idx["name"] for idx in inspector.get_indexes("topology_history")}
    indexes_poll = {idx["name"] for idx in inspector.get_indexes("poll_history")}

    if "idx_topology_history_event_time" in indexes_topology:
        op.execute("DROP INDEX IF EXISTS idx_topology_history_event_time")
    if "idx_poll_history_device_time" in indexes_poll:
        op.execute("DROP INDEX IF EXISTS idx_poll_history_device_time")
    # source_time and link_time are owned by 001; do not drop them here.
