"""Phase 1: discovery lifecycle + environment profile.

Revision ID: 008
Revises: 007
Create Date: 2026-06-06

Phase 1 (per `.opencode/plans/PHASE1_DISCOVERY_PROFILE_SPEC.md`)
introduces:

  - `devices.offline_since` — when a device was last seen offline.
    Used by the 72h stale-device lifecycle.
  - `devices.last_scanned` — when discovery last successfully scanned
    the device. Separate from `last_polled` (SNMP poll) so the
    rescan cadence and the polling cadence can be reasoned about
    independently.
  - `devices.discovery_method` — auto | snmp | ping | port | manual.
    Note: this column was already added in 001 baseline; this
    migration only ensures the default is set on legacy rows.
  - `app_settings.profile` — homelab | small_business | datacenter.
  - `app_settings.discovery_full_interval` — seconds.
  - `app_settings.discovery_incremental_interval` — seconds.
  - `app_settings.poll_history_retention_days` — days.

All operations are idempotent via the portable add_column_if_not_exists
helper.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.storage.migrations._helpers import (
    add_column_if_not_exists,
    create_index_if_not_exists,
)


# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # devices columns
    # ------------------------------------------------------------------
    add_column_if_not_exists(
        'devices', 'offline_since', sa.DateTime(timezone=True), nullable=True,
    )
    add_column_if_not_exists(
        'devices', 'last_scanned', sa.DateTime(timezone=True), nullable=True,
    )
    # discovery_method was added in 001 baseline; set the default on
    # existing rows that may have NULL.
    op.execute("UPDATE devices SET discovery_method = 'auto' WHERE discovery_method IS NULL")

    # ------------------------------------------------------------------
    # devices indexes
    # ------------------------------------------------------------------
    create_index_if_not_exists('idx_devices_offline_since', 'devices', ['offline_since'])
    create_index_if_not_exists('idx_devices_last_scanned', 'devices', ['last_scanned'])
    # idx_devices_discovery_method is in 001 baseline; create_index_if_not_exists
    # makes this a safe no-op for legacy schemas.

    # ------------------------------------------------------------------
    # app_settings columns (profile + per-profile interval settings)
    # ------------------------------------------------------------------
    add_column_if_not_exists(
        'app_settings', 'profile', sa.String(),
        nullable=True, server_default='homelab',
    )
    add_column_if_not_exists(
        'app_settings', 'discovery_full_interval', sa.Integer(),
        nullable=True, server_default='21600',
    )
    add_column_if_not_exists(
        'app_settings', 'discovery_incremental_interval', sa.Integer(),
        nullable=True, server_default='900',
    )
    add_column_if_not_exists(
        'app_settings', 'poll_history_retention_days', sa.Integer(),
        nullable=True, server_default='7',
    )


def downgrade() -> None:
    # Drop the four app_settings columns. devices.* columns remain
    # (they were also in 001 baseline for some, added here for others).
    bind = op.get_bind()
    dialect = bind.dialect.name

    def _drop_column(table: str, col: str) -> None:
        if dialect == "sqlite":
            # SQLite ALTER DROP COLUMN requires recreating the table.
            # For Phase 1 downgrade, simplest is to skip; the columns
            # are nullable and unused by older code.
            return
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

    for col in (
        'poll_history_retention_days',
        'discovery_incremental_interval',
        'discovery_full_interval',
        'profile',
    ):
        _drop_column('app_settings', col)
