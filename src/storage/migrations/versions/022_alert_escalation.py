"""Migration 022: add alert escalation fields.

Add escalation support to alert_configs:
  - escalation_minutes: minutes before auto-escalate (null = disabled)
  - escalated_severity: severity to escalate to (e.g., "critical")

Revision ID: 022_alert_escalation
Revises: 021_host_state
Create Date: 2026-06-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022_alert_escalation"
down_revision: Union[str, None] = "021_host_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    if not inspector.has_table("alert_configs"):
        return
    
    existing_columns = {col["name"] for col in inspector.get_columns("alert_configs")}
    
    if "escalation_minutes" not in existing_columns:
        op.add_column("alert_configs", sa.Column("escalation_minutes", sa.Integer(), nullable=True))
    
    if "escalated_severity" not in existing_columns:
        op.add_column("alert_configs", sa.Column("escalated_severity", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    if not inspector.has_table("alert_configs"):
        return
    
    existing_columns = {col["name"] for col in inspector.get_columns("alert_configs")}
    
    if "escalated_severity" in existing_columns:
        op.drop_column("alert_configs", "escalated_severity")
    
    if "escalation_minutes" in existing_columns:
        op.drop_column("alert_configs", "escalation_minutes")
