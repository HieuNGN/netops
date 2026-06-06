"""Composite indexes for integrations, alerts, maintenance windows.

Revision ID: 016
Revises: 015
Create Date: 2026-06-06

Indexes the application layer hits but weren't covered by 001
baseline or 015:

  1. `idx_integrations_type_enabled` on integrations (type, enabled):
     "List enabled slack integrations" — used by the alert
     dispatch path when merging integration secrets with alert
     config.

  2. `idx_alert_configs_enabled_alert_type` on alert_configs
     (enabled, alert_type):
     "List enabled device_down alerts" — alert evaluation loop.

  3. `idx_maintenance_windows_active` on maintenance_windows
     (start_time, end_time):
     "Is there an active maintenance window right now?" — the
     is_in_maintenance_window() check.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return name in {idx["name"] for idx in inspector.get_indexes(table)}
    except Exception:
        return False


def upgrade() -> None:
    if not _index_exists("integrations", "idx_integrations_type_enabled"):
        op.execute(
            "CREATE INDEX idx_integrations_type_enabled "
            "ON integrations (type, enabled)"
        )
    if not _index_exists(
        "alert_configs", "idx_alert_configs_enabled_alert_type"
    ):
        op.execute(
            "CREATE INDEX idx_alert_configs_enabled_alert_type "
            "ON alert_configs (enabled, alert_type)"
        )
    # idx_maintenance_windows_time was created in 001 baseline
    # on (start_time, end_time); the same composite covers the
    # "active now?" query. No additional index needed.


def downgrade() -> None:
    bind = op.get_bind()

    def _drop(name: str) -> None:
        try:
            op.execute(f"DROP INDEX IF EXISTS {name}")
        except Exception:
            pass

    _drop("idx_alert_configs_enabled_alert_type")
    _drop("idx_integrations_type_enabled")
