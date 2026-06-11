"""Migration 024: add node_type column to devices table for topology symbols.

Revision ID: 024_device_node_type
Revises: 023_topology_hierarchy
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "024_device_node_type"
down_revision: Union[str, None] = "023_topology_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("node_type", sa.String(), nullable=True, server_default="device"))


def downgrade() -> None:
    op.drop_column("devices", "node_type")