"""Add integrations table and alert_configs.integration_id with dedupe.

Revision ID: 005
Revises: 004
Create Date: 2026-06-04

"""
import json
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


log = logging.getLogger("alembic.migration.005")

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_config(config: dict | None) -> str:
    """Stable JSON signature for dedup."""
    if not config:
        return ""
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def upgrade() -> None:
    op.add_column(
        'alert_configs',
        sa.Column('integration_id', sa.String(), nullable=True),
    )
    op.create_index(
        'idx_alert_configs_integration',
        'alert_configs',
        ['integration_id'],
    )

    op.create_table(
        'integrations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('secrets_json', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True, default=1),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('type', 'name', name='uq_integrations_type_name'),
    )
    op.create_index('idx_integrations_type', 'integrations', ['type'])

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('alert_configs'):
        result = bind.execute(sa.text(
            "SELECT id, alert_type, channel, config_json, created FROM alert_configs "
            "ORDER BY created ASC"
        ))
        rows = result.fetchall()
        seen: dict[tuple, str] = {}
        to_delete: list[str] = []
        for row in rows:
            try:
                cfg = json.loads(row.config_json) if row.config_json else {}
            except (TypeError, json.JSONDecodeError):
                cfg = {}
            key = (row.alert_type, row.channel, _normalize_config(cfg))
            if key in seen:
                to_delete.append(row.id)
                log.info(
                    "dedup: removing duplicate alert id=%s alert_type=%s channel=%s",
                    row.id, row.alert_type, row.channel,
                )
            else:
                seen[key] = row.id
        for dup_id in to_delete:
            bind.execute(
                sa.text("DELETE FROM alert_history WHERE alert_config_id = :id"),
                {"id": dup_id},
            )
            bind.execute(
                sa.text("DELETE FROM alert_configs WHERE id = :id"),
                {"id": dup_id},
            )
        log.info("dedup: removed %d duplicate alert configs", len(to_delete))


def downgrade() -> None:
    op.drop_index('idx_integrations_type', table_name='integrations')
    op.drop_table('integrations')
    op.drop_index('idx_alert_configs_integration', table_name='alert_configs')
    op.drop_column('alert_configs', 'integration_id')
