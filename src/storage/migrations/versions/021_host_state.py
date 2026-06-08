"""Migration 021: add host_state keys to app_settings.

Stores the host's last-seen (cidr, gateway) fingerprint so the app
can detect network changes at boot and at runtime.

Keys added (idempotent via ON CONFLICT):
  - host_cidr          (str, e.g. "192.168.1.0/24")
  - host_gateway       (str, e.g. "192.168.1.1")
  - host_fingerprint   (str, sha256[:16] of "{cidr}|{gateway}")
  - host_last_seen     (str, ISO8601 timestamp of last detection)

Revision ID: 021_host_state
Revises: 020
Create Date: 2026-06-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021_host_state"
down_revision: Union[str, None] = "020_must_change_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("app_settings"):
        return

    dialect = bind.dialect.name
    ts_fn = "datetime('now')" if dialect == "sqlite" else "NOW()"

    for key in (
        "host_cidr",
        "host_gateway",
        "host_fingerprint",
        "host_last_seen",
    ):
        bind.execute(
            sa.text(
                f"INSERT INTO app_settings (key, value, updated) "
                f"VALUES (:k, '', {ts_fn}) "
                f"ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key},
        )


def downgrade() -> None:
    for key in (
        "host_last_seen",
        "host_fingerprint",
        "host_gateway",
        "host_cidr",
    ):
        op.execute(f"DELETE FROM app_settings WHERE key = '{key}'")
