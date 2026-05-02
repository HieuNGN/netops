"""Add service checks tables.

Revision ID: 002
Revises: 001
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Service checks table
    op.create_table(
        'service_checks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('check_type', sa.String(), nullable=False),
        sa.Column('target', sa.String(), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=True, default=60),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True, default=10),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True, default=1),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_service_checks_type', 'service_checks', ['check_type'])
    op.create_index('idx_service_checks_enabled', 'service_checks', ['enabled'])

    # Check results table
    op.create_table(
        'check_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('check_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_check_results_check_id', 'check_results', ['check_id'])
    op.create_index('idx_check_results_checked_at', 'check_results', ['checked_at'])


def downgrade() -> None:
    op.drop_table('check_results')
    op.drop_table('service_checks')
