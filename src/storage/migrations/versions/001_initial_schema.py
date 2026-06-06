"""Initial schema for NetOps — all 14 tables in the canonical baseline.

Revision ID: 001
Revises:
Create Date: 2026-04-28

This is the single source of truth for the NetOps schema. It creates
every table the application needs so a fresh `alembic upgrade head`
against an empty database produces a fully working schema. Later
migrations (002-005) add columns or refactor; the baseline is
deliberately redundant with their original bodies so a database
that was bootstrapped imperatively can still be upgraded cleanly.

Tables (in creation order):
  1.  devices
  2.  topology_nodes
  3.  topology_links
  4.  poll_history
  5.  alert_configs
  6.  alert_history
  7.  users
  8.  app_settings
  9.  topology_history
 10.  integrations
 11.  service_checks
 12.  check_results
 13.  networks
 14.  maintenance_windows

Notes:
- `config_json` / `secrets_json` / `details` are stored as `String`
  for cross-DB portability (SQLite TEXT, PG TEXT-via-JSONB at the
  application layer). Application code round-trips through
  json.dumps/loads.
- All timestamps are timezone-aware (DateTime(timezone=True)).
- All index names are canonical. Imperative DDL in `init_db()` used
  alternate names (e.g. `idx_devices_network` vs `idx_devices_network_id`)
  which is why migration 006 drops the duplicates.
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    def _create(name: str, *args, **kwargs) -> None:
        """op.create_table guarded by an existing-table check for idempotency."""
        if name not in existing_tables:
            op.create_table(name, *args, **kwargs)

    def _create_index(name: str, table: str, columns: list[str], **kwargs) -> None:
        """op.create_index guarded by existing-index AND existing-column checks.

        The existing-column check protects legacy databases that were
        bootstrapped imperatively against a partial schema — creating
        an index on a column that doesn't exist would crash. Skip
        silently in that case; later migrations (006, 007, 008) will
        add the missing columns.
        """
        if not _columns_of(table).issuperset(columns):
            return
        try:
            existing = {idx["name"] for idx in inspector.get_indexes(table)}
        except Exception:
            existing = set()
        if name not in existing:
            op.create_index(name, table, columns, **kwargs)

    def _columns_of(table: str) -> set[str]:
        try:
            return {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return set()



    # ------------------------------------------------------------------
    # 1. devices
    # ------------------------------------------------------------------
    _create(
        'devices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=False),
        sa.Column('community', sa.String(), nullable=True, default='public'),
        sa.Column('status', sa.String(), nullable=True, default='unknown'),
        sa.Column('sys_descr', sa.Text(), nullable=True),
        sa.Column('discovery_method', sa.String(), nullable=True, default='manual'),
        sa.Column('snmp_version', sa.String(), nullable=True, default='2c'),
        sa.Column('snmpv3_username', sa.String(), nullable=True),
        sa.Column('snmpv3_auth_protocol', sa.String(), nullable=True),
        sa.Column('snmpv3_auth_key', sa.String(), nullable=True),
        sa.Column('snmpv3_priv_protocol', sa.String(), nullable=True),
        sa.Column('snmpv3_priv_key', sa.String(), nullable=True),
        sa.Column('network_id', sa.String(), nullable=True),
        sa.Column('offline_since', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_scanned', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_polled', sa.String(), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip_address'),
    )
    _create_index('idx_devices_ip', 'devices', ['ip_address'])
    _create_index('idx_devices_status', 'devices', ['status'])
    _create_index('idx_devices_discovery_method', 'devices', ['discovery_method'])
    _create_index('idx_devices_network_id', 'devices', ['network_id'])
    _create_index('idx_devices_offline_since', 'devices', ['offline_since'])
    _create_index('idx_devices_last_scanned', 'devices', ['last_scanned'])

    # ------------------------------------------------------------------
    # 2. topology_nodes
    # ------------------------------------------------------------------
    _create(
        'topology_nodes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('network_id', sa.String(), nullable=True),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('node_type', sa.String(), nullable=True, default='device'),
        sa.Column('status', sa.String(), nullable=True, default='unknown'),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_nodes_device_id', 'topology_nodes', ['device_id'])
    _create_index('idx_nodes_status', 'topology_nodes', ['status'])
    _create_index('idx_nodes_network_id', 'topology_nodes', ['network_id'])

    # ------------------------------------------------------------------
    # 3. topology_links
    # ------------------------------------------------------------------
    _create(
        'topology_links',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_id', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('network_id', sa.String(), nullable=True),
        sa.Column('source_port', sa.String(), nullable=True),
        sa.Column('target_port', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, default='active'),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_links_source', 'topology_links', ['source_id'])
    _create_index('idx_links_target', 'topology_links', ['target_id'])
    _create_index('idx_links_network_id', 'topology_links', ['network_id'])

    # ------------------------------------------------------------------
    # 4. poll_history
    # ------------------------------------------------------------------
    _create(
        'poll_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('polled_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_poll_history_device', 'poll_history', ['device_id'])
    _create_index('idx_poll_history_polled_at', 'poll_history', ['polled_at'])

    # ------------------------------------------------------------------
    # 5. alert_configs
    # ------------------------------------------------------------------
    _create(
        'alert_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('alert_type', sa.String(), nullable=False),
        sa.Column('channel', sa.String(), nullable=False),
        sa.Column('config_json', sa.String(), nullable=True),
        sa.Column('integration_id', sa.String(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True, default=1),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_alert_configs_enabled', 'alert_configs', ['enabled'])
    _create_index('idx_alert_configs_integration', 'alert_configs', ['integration_id'])

    # ------------------------------------------------------------------
    # 6. alert_history
    # ------------------------------------------------------------------
    _create(
        'alert_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('alert_config_id', sa.String(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, default='triggered'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_alert_history_config', 'alert_history', ['alert_config_id'])

    # ------------------------------------------------------------------
    # 7. users (moved from imperative DDL; 004 adds email/name)
    # ------------------------------------------------------------------
    _create(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=True, default='admin'),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    _create_index('ix_users_email', 'users', ['email'])

    # ------------------------------------------------------------------
    # 8. app_settings (key-value store for runtime configuration)
    # ------------------------------------------------------------------
    _create(
        'app_settings',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    # Seed the default config row so app code can read it without a
    # separate "first run" check. Idempotent.
    bind.execute(
        sa.text("INSERT INTO app_settings (key, value) VALUES ('config', '{}') "
                "ON CONFLICT (key) DO NOTHING")
    )

    # ------------------------------------------------------------------
    # 9. topology_history (audit log; high-volume under trap load)
    # ------------------------------------------------------------------
    _create(
        'topology_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('node_id', sa.String(), nullable=True),
        sa.Column('link_id', sa.String(), nullable=True),
        sa.Column('source_ip', sa.String(), nullable=True),
        sa.Column('old_status', sa.String(), nullable=True),
        sa.Column('new_status', sa.String(), nullable=True),
        sa.Column('details', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_topology_history_event', 'topology_history', ['event_type'])
    _create_index('idx_topology_history_recorded_at', 'topology_history', ['recorded_at'])
    _create_index('idx_topology_history_source_time', 'topology_history', ['source_ip', 'recorded_at'])
    _create_index('idx_topology_history_link_time', 'topology_history', ['link_id', 'recorded_at'])

    # ------------------------------------------------------------------
    # 10. integrations (alert channel credentials)
    # ------------------------------------------------------------------
    _create(
        'integrations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('secrets_json', sa.String(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True, default=1),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('type', 'name', name='uq_integrations_type_name'),
    )
    _create_index('idx_integrations_type', 'integrations', ['type'])

    # ------------------------------------------------------------------
    # 11. service_checks
    # ------------------------------------------------------------------
    _create(
        'service_checks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('check_type', sa.String(), nullable=False),
        sa.Column('target', sa.String(), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=True, default=60),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True, default=10),
        sa.Column('config_json', sa.String(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=True, default=1),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_service_checks_type', 'service_checks', ['check_type'])
    _create_index('idx_service_checks_enabled', 'service_checks', ['enabled'])

    # ------------------------------------------------------------------
    # 12. check_results
    # ------------------------------------------------------------------
    _create(
        'check_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('check_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('details', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_check_results_check_id', 'check_results', ['check_id'])
    _create_index('idx_check_results_checked_at', 'check_results', ['checked_at'])

    # ------------------------------------------------------------------
    # 13. networks
    # ------------------------------------------------------------------
    _create(
        'networks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('cidr', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Integer(), nullable=True, default=0),
        sa.Column('network_type', sa.String(), nullable=True),
        sa.Column('tags', sa.String(), nullable=True, default='[]'),
        sa.Column('last_scanned', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    _create_index('idx_networks_name', 'networks', ['name'])
    _create_index('idx_networks_default', 'networks', ['is_default'])

    # ------------------------------------------------------------------
    # 14. maintenance_windows
    # ------------------------------------------------------------------
    _create(
        'maintenance_windows',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index('idx_maintenance_windows_time', 'maintenance_windows', ['start_time', 'end_time'])


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_index('idx_maintenance_windows_time', table_name='maintenance_windows')
    op.drop_table('maintenance_windows')

    op.drop_index('idx_networks_default', table_name='networks')
    op.drop_index('idx_networks_name', table_name='networks')
    op.drop_table('networks')

    op.drop_index('idx_check_results_checked_at', table_name='check_results')
    op.drop_index('idx_check_results_check_id', table_name='check_results')
    op.drop_table('check_results')

    op.drop_index('idx_service_checks_enabled', table_name='service_checks')
    op.drop_index('idx_service_checks_type', table_name='service_checks')
    op.drop_table('service_checks')

    op.drop_index('idx_integrations_type', table_name='integrations')
    op.drop_table('integrations')

    op.drop_index('idx_topology_history_link_time', table_name='topology_history')
    op.drop_index('idx_topology_history_source_time', table_name='topology_history')
    op.drop_index('idx_topology_history_recorded_at', table_name='topology_history')
    op.drop_index('idx_topology_history_event', table_name='topology_history')
    op.drop_table('topology_history')

    op.drop_table('app_settings')

    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')

    op.drop_index('idx_alert_history_config', table_name='alert_history')
    op.drop_table('alert_history')

    op.drop_index('idx_alert_configs_integration', table_name='alert_configs')
    op.drop_index('idx_alert_configs_enabled', table_name='alert_configs')
    op.drop_table('alert_configs')

    op.drop_index('idx_poll_history_polled_at', table_name='poll_history')
    op.drop_index('idx_poll_history_device', table_name='poll_history')
    op.drop_table('poll_history')

    op.drop_index('idx_links_network_id', table_name='topology_links')
    op.drop_index('idx_links_target', table_name='topology_links')
    op.drop_index('idx_links_source', table_name='topology_links')
    op.drop_table('topology_links')

    op.drop_index('idx_nodes_network_id', table_name='topology_nodes')
    op.drop_index('idx_nodes_status', table_name='topology_nodes')
    op.drop_index('idx_nodes_device_id', table_name='topology_nodes')
    op.drop_table('topology_nodes')

    op.drop_index('idx_devices_last_scanned', table_name='devices')
    op.drop_index('idx_devices_offline_since', table_name='devices')
    op.drop_index('idx_devices_network_id', table_name='devices')
    op.drop_index('idx_devices_discovery_method', table_name='devices')
    op.drop_index('idx_devices_status', table_name='devices')
    op.drop_index('idx_devices_ip', table_name='devices')
    op.drop_table('devices')
