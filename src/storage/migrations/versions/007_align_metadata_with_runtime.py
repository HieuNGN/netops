"""Defensive alignment of metadata with runtime.

Revision ID: 007
Revises: 006
Create Date: 2026-06-06

This migration is a no-op on a clean schema that started at 001.
It exists to provide a safety net for databases that:
  - Skipped 003 (e.g. a hand-rolled `alembic stamp 002` then
    `alembic upgrade head` against a DB without a `networks` table).
  - Have a `networks` table missing one of the new columns.

The operations are idempotent (uses the portable add_column_if_not_exists
helper) so re-running this migration is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.storage.migrations._helpers import add_column_if_not_exists


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Ensure the `networks` table exists with all current columns.
    # If 003 was skipped for any reason, this fills the gap.
    if not inspector.has_table('networks'):
        op.create_table(
            'networks',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('cidr', sa.String(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_default', sa.Integer(), nullable=True, default=0),
            sa.Column('network_type', sa.String(), nullable=True),
            sa.Column('tags', sa.String(), nullable=True, default='[]'),
            sa.Column('last_scanned', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
        )
        op.create_index('idx_networks_name', 'networks', ['name'])
        op.create_index('idx_networks_default', 'networks', ['is_default'])

    # Ensure the three `networks.*` columns are present (idempotent).
    add_column_if_not_exists('networks', 'network_type', sa.String(), nullable=True)
    add_column_if_not_exists(
        'networks', 'tags', sa.String(), nullable=True, server_default='[]',
    )
    add_column_if_not_exists(
        'networks', 'last_scanned', sa.DateTime(timezone=True), nullable=True,
    )

    # Ensure the three `network_id` columns are present (idempotent).
    add_column_if_not_exists('devices', 'network_id', sa.String(), nullable=True)
    add_column_if_not_exists('topology_nodes', 'network_id', sa.String(), nullable=True)
    add_column_if_not_exists('topology_links', 'network_id', sa.String(), nullable=True)


def downgrade() -> None:
    # This migration is defensive. Downgrading does not remove the
    # networks table or columns — those are owned by 003 / 001.
    pass
