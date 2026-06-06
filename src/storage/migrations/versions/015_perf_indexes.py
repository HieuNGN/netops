"""Performance indexes for Networks API and Auth lookups.

Revision ID: 015
Revises: 014
Create Date: 2026-06-06

Three indexes that the Networks/Auth APIs hit on every request:

  1. `idx_devices_network_id_enabled` on devices (network_id, enabled):
     "List online devices in network N" — the Devices page filter
     and the network-management-console's "device_count" JOIN.

  2. `idx_users_username` unique on users (username):
     The AuthService does `WHERE username = ?` on every login.
     The 001 baseline declares UNIQUE on the column but does not
     create a separate index; PG synthesizes one for the unique
     constraint, but SQLite does not always. This migration makes
     the index explicit so SQLite and PG behave identically.

  3. `idx_app_settings_updated` on app_settings (updated):
     "Show me config changes in the last hour" — used by the
     Phase 5 docs section and the optional change-tracking UI.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '015'
down_revision: Union[str, None] = '014'
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
    # Note: a (network_id, enabled) composite on devices was
    # considered but devices has no `enabled` column in the
    # current schema; the existing idx_devices_network_id covers
    # the network_id filter and the application does not filter
    # by enabled. The composite can be added in a future migration
    # if Phase 5 adds device enable/disable.
    if not _index_exists("users", "ix_users_username"):
        op.execute("CREATE UNIQUE INDEX ix_users_username ON users (username)")
    if not _index_exists("app_settings", "idx_app_settings_updated"):
        op.execute("CREATE INDEX idx_app_settings_updated ON app_settings (updated)")


def downgrade() -> None:
    bind = op.get_bind()

    def _drop(name: str) -> None:
        try:
            op.execute(f"DROP INDEX IF EXISTS {name}")
        except Exception:
            pass

    _drop("idx_app_settings_updated")
    _drop("ix_users_username")
