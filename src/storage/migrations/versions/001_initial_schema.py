"""Initial schema for NetOps PostgreSQL.

Revision ID: 001
Revises:
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=False),
        sa.Column('community', sa.String(), nullable=True, default='public'),
        sa.Column('status', sa.String(), nullable=True, default='unknown'),
        sa.Column('sys_descr', sa.Text(), nullable=True),
        sa.Column('last_polled', sa.String(), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip_address')
    )
    op.create_index('idx_devices_ip', 'devices', ['ip_address'])
    op.create_index('idx_devices_status', 'devices', ['status'])

    # Topology nodes table
    op.create_table(
        'topology_nodes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('node_type', sa.String(), nullable=True, default='device'),
        sa.Column('status', sa.String(), nullable=True, default='unknown'),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_nodes_device_id', 'topology_nodes', ['device_id'])
    op.create_index('idx_nodes_status', 'topology_nodes', ['status'])

    # Topology links table
    op.create_table(
        'topology_links',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_id', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('source_port', sa.String(), nullable=True),
        sa.Column('target_port', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, default='active'),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_links_source', 'topology_links', ['source_id'])
    op.create_index('idx_links_target', 'topology_links', ['target_id'])

    # Poll history table
    op.create_table(
        'poll_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('polled_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_poll_history_device', 'poll_history', ['device_id'])
    op.create_index('idx_poll_history_polled_at', 'poll_history', ['polled_at'])

    # Alert configs table
    op.create_table(
        'alert_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('alert_type', sa.String(), nullable=False),
        sa.Column('channel', sa.String(), nullable=False),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True, default=1),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alert_configs_enabled', 'alert_configs', ['enabled'])

    # Alert history table
    op.create_table(
        'alert_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('alert_config_id', sa.String(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, default='triggered'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alert_history_config', 'alert_history', ['alert_config_id'])


def downgrade() -> None:
    op.drop_table('alert_history')
    op.drop_table('alert_configs')
    op.drop_table('poll_history')
    op.drop_table('topology_links')
    op.drop_table('topology_nodes')
    op.drop_table('devices')
