"""Seed app_settings with phase defaults.

Revision ID: 013
Revises: 012
Create Date: 2026-06-06

The `app_settings` table is the runtime configuration store
(per PR A). This migration seeds the application with sensible
defaults for the keys added by Phases 1, 2, and 4:

  - profile (Phase 1)
  - discovery_full_interval (Phase 1)
  - discovery_incremental_interval (Phase 1)
  - poll_history_retention_days (Phase 1)
  - topology_history_retention_days (Phase 4, derived from
    poll_history_retention_days; defaults to 90)
  - traps_enabled (Phase 4)
  - traps_bind_host (Phase 4)
  - traps_port (Phase 4)
  - traps_community (Phase 4)
  - traps_destination_ip (Phase 4)
  - check_intervals (Phase 2, JSON)

These are stored as keys in the `app_settings` key-value table
where the value is a JSON string. The application layer reads
them via `db_client.get_settings()` and `db_client.get_setting(key)`.

The migration is idempotent: ON CONFLICT DO NOTHING ensures
re-running is a no-op. Existing deployments with non-default
values are NOT overwritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default values for each setting. These match the Phase 1
# spec's homelab profile; small_business and datacenter
# profiles override these values via the API.
DEFAULT_SETTINGS = {
    "profile": "homelab",
    "discovery_full_interval": 21600,  # 6h
    "discovery_incremental_interval": 900,  # 15m
    "poll_history_retention_days": 7,
    "topology_history_retention_days": 90,
    "traps_enabled": "false",
    "traps_bind_host": "0.0.0.0",
    "traps_port": 162,
    "traps_community": "public",
    "traps_destination_ip": "",  # auto-detected at runtime
    "check_intervals": {
        "ping": 60,
        "http": 60,
        "tcp": 60,
        "dns": 300,
        "ssl": 86400,
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("app_settings"):
        return  # 001 baseline not applied (shouldn't happen)

    # Use a portable timestamp function. PG: NOW(); SQLite: datetime('now').
    dialect = bind.dialect.name
    ts_fn = "datetime('now')" if dialect == "sqlite" else "NOW()"

    for key, value in DEFAULT_SETTINGS.items():
        import json
        if isinstance(value, (dict, list)):
            value_json = json.dumps(value)
        elif isinstance(value, bool):
            value_json = "true" if value else "false"
        else:
            value_json = str(value)
        bind.execute(
            sa.text(
                f"INSERT INTO app_settings (key, value, updated) "
                f"VALUES (:k, :v, {ts_fn}) "
                f"ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "v": value_json},
        )


def downgrade() -> None:
    # Downgrade does not remove the seeded rows. Operators who want
    # a clean slate can DELETE FROM app_settings WHERE key IN (...)
    # manually. Removing them on downgrade would surprise operators
    # by silently reverting their runtime config.
    pass
