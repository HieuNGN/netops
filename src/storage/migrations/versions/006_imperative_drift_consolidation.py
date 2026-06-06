"""Consolidate imperative-DDL drift into Alembic.

Revision ID: 006
Revises: 005
Create Date: 2026-06-06

Database bootstraps that used the imperative `init_db()` path (pre-PR-A)
may have:
  - Alternate-named indexes (`idx_devices_network`, `idx_nodes_network`,
    `idx_links_network` — no `_id` suffix) that are duplicates of the
    canonical `*_network_id` indexes created in 001/003.
  - Missing SNMPv3 columns on `devices` (the imperative DDL adds them
    via ALTER, so SQLite-DB's bootstrapped imperatively already have
    them, but a fresh PG-DB without the imperative DDL won't).

This migration:
  1. Drops the duplicate `*_network` indexes if they exist.
  2. Adds the SNMPv3 columns on `devices` if they don't exist
     (idempotent — no-op on a clean DB).

All operations are dialect-aware and no-op on a clean schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.storage.migrations._helpers import add_column_if_not_exists


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Drop duplicate indexes created by the legacy imperative DDL.
    #    These have the same columns as `*_network_id` (created in
    #    001/003) but a different name; keeping both wastes write IO
    #    and clutters `pg_indexes`. IF EXISTS makes the drop idempotent.
    for dup_name, table in (
        ('idx_devices_network', 'devices'),
        ('idx_nodes_network', 'topology_nodes'),
        ('idx_links_network', 'topology_links'),
    ):
        try:
            indexes = inspector.get_indexes(table)
            if any(idx.get('name') == dup_name for idx in indexes):
                op.drop_index(dup_name, table_name=table)
        except Exception:
            # Some dialects / versions may not support get_indexes for
            # missing tables. Swallow and continue.
            pass

    # 2. Add SNMPv3 columns to devices (defensive — present in 001
    #    baseline already, but a DB bootstrapped before 001 may lack
    #    them). Use portable add_column_if_not_exists helper.
    add_column_if_not_exists(
        'devices', 'snmp_version', sa.String(),
        nullable=True, server_default='2c',
    )
    add_column_if_not_exists('devices', 'snmpv3_username', sa.String(), nullable=True)
    add_column_if_not_exists('devices', 'snmpv3_auth_protocol', sa.String(), nullable=True)
    add_column_if_not_exists('devices', 'snmpv3_auth_key', sa.String(), nullable=True)
    add_column_if_not_exists('devices', 'snmpv3_priv_protocol', sa.String(), nullable=True)
    add_column_if_not_exists('devices', 'snmpv3_priv_key', sa.String(), nullable=True)


def downgrade() -> None:
    # The duplicate indexes were created by legacy imperative DDL and
    # are not part of the new migration chain. If they were dropped in
    # upgrade, we do not recreate them on downgrade (they were drift,
    # not source-of-truth schema).
    #
    # The SNMPv3 columns are part of 001 baseline; do not drop them
    # here either (downgrade past 006 should not lose schema).
    pass
