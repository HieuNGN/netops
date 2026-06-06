"""Add networks table and network_id columns.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09

Adds the `networks` table and `network_id` columns on the three
device/topology tables. Also adds the three new columns on
`networks` (`network_type`, `tags`, `last_scanned`) that were
previously only in the imperative DDL of `init_db()`.

The `network_id` columns and the canonical `idx_*_network_id`
indexes are also added in 001 baseline; this revision is preserved
to keep the chain linear for any existing deployments.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.storage.migrations._helpers import add_column_if_not_exists


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `networks` is now in 001 baseline. Skip the CREATE if the table
    # already exists (which it will for any DB stamped past 001).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('networks'):
        op.create_table(
            'networks',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False, unique=True),
            sa.Column('cidr', sa.String(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_default', sa.Integer(), nullable=True, default=0),
            sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('idx_networks_name', 'networks', ['name'])
        op.create_index('idx_networks_default', 'networks', ['is_default'])

    # Add the three new columns on networks (idempotent, dialect-aware).
    add_column_if_not_exists('networks', 'network_type', sa.String(), nullable=True)
    add_column_if_not_exists(
        'networks', 'tags', sa.String(), nullable=True, server_default='[]',
    )
    add_column_if_not_exists(
        'networks', 'last_scanned', sa.DateTime(timezone=True), nullable=True,
    )

    # The `network_id` columns are also in 001 baseline.
    # Idempotent: skip if already present.
    devices_cols = {c["name"] for c in inspector.get_columns("devices")}
    nodes_cols = {c["name"] for c in inspector.get_columns("topology_nodes")}
    links_cols = {c["name"] for c in inspector.get_columns("topology_links")}
    if "network_id" not in devices_cols:
        op.add_column('devices', sa.Column('network_id', sa.String(), nullable=True))
    if "network_id" not in nodes_cols:
        op.add_column('topology_nodes', sa.Column('network_id', sa.String(), nullable=True))
    if "network_id" not in links_cols:
        op.add_column('topology_links', sa.Column('network_id', sa.String(), nullable=True))


def downgrade() -> None:
    # The `network_id` columns and `networks` table are part of the
    # 001 baseline; only the three new columns are removed here.
    # SQLite does not support `DROP COLUMN IF EXISTS` until 3.35+, and
    # the `IF EXISTS` clause is not portable. Use raw SQL guarded by
    # dialect check.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE networks DROP COLUMN IF EXISTS last_scanned")
        op.execute("ALTER TABLE networks DROP COLUMN IF EXISTS tags")
        op.execute("ALTER TABLE networks DROP COLUMN IF EXISTS network_type")
    # On SQLite, leave the columns in place; they are nullable and
    # harmless, and recreating the table to drop them is more risk
    # than reward.
