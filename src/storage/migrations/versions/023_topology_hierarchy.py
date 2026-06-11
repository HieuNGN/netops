"""Migration 023: add hierarchy columns to topology_nodes.

Adds level (BFS depth), parent_id (tree parent), and role
(gateway/core/distribution/access/endpoint) for smart hierarchy view.

Revision ID: 023_topology_hierarchy
Revises: 022_alert_escalation
Create Date: 2026-06-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023_topology_hierarchy"
down_revision: Union[str, None] = "022_alert_escalation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("topology_nodes"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("topology_nodes")}

    if "level" not in existing_columns:
        op.add_column("topology_nodes", sa.Column("level", sa.Integer(), nullable=True))

    if "parent_id" not in existing_columns:
        op.add_column("topology_nodes", sa.Column("parent_id", sa.String(), nullable=True))

    if "role" not in existing_columns:
        op.add_column("topology_nodes", sa.Column("role", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("topology_nodes"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("topology_nodes")}

    if "role" in existing_columns:
        op.drop_column("topology_nodes", "role")

    if "parent_id" in existing_columns:
        op.drop_column("topology_nodes", "parent_id")

    if "level" in existing_columns:
        op.drop_column("topology_nodes", "level")
