"""Add networks table for multi-network isolation.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Networks table
    op.create_table(
        'networks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('cidr', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Integer(), nullable=True, default=0),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_networks_name', 'networks', ['name'])
    op.create_index('idx_networks_default', 'networks', ['is_default'])

    # Add network_id to devices
    op.add_column('devices', sa.Column('network_id', sa.String(), nullable=True))
    op.create_index('idx_devices_network_id', 'devices', ['network_id'])

    # Add network_id to topology_nodes
    op.add_column('topology_nodes', sa.Column('network_id', sa.String(), nullable=True))
    op.create_index('idx_nodes_network_id', 'topology_nodes', ['network_id'])

    # Add network_id to topology_links
    op.add_column('topology_links', sa.Column('network_id', sa.String(), nullable=True))
    op.create_index('idx_links_network_id', 'topology_links', ['network_id'])


def downgrade() -> None:
    op.drop_index('idx_links_network_id', table_name='topology_links')
    op.drop_column('topology_links', 'network_id')

    op.drop_index('idx_nodes_network_id', table_name='topology_nodes')
    op.drop_column('topology_nodes', 'network_id')

    op.drop_index('idx_devices_network_id', table_name='devices')
    op.drop_column('devices', 'network_id')

    op.drop_index('idx_networks_default', table_name='networks')
    op.drop_index('idx_networks_name', table_name='networks')
    op.drop_table('networks')
