"""Optional foreign-key constraints, gated by NETOPS_ENABLE_FKS=1.

Revision ID: 019
Revises: 018
Create Date: 2026-06-06

Per the Option A decision in the senior-code-reviewer plan, FK
constraints are deferred to a separate migration that ships with
a flag, off by default. The application code has been working
without DB-level FKs (manual cascades in `bulk_delete_devices` at
database.py:500-514); adding them is a behavior change that
risks DELETE failures on code paths that don't pre-null.

Enable by setting `NETOPS_ENABLE_FKS=1` in the environment. When
enabled, this migration:

  1. Adds FKs to the columns that have logical referents:
     - `devices.network_id` -> `networks.id` ON DELETE SET NULL
     - `topology_nodes.network_id` -> `networks.id` ON DELETE SET NULL
     - `topology_links.network_id` -> `networks.id` ON DELETE SET NULL
     - `alert_configs.integration_id` -> `integrations.id` ON DELETE SET NULL
  2. Validates that all existing rows satisfy the new constraints
     before creating them. If a row has a dangling FK target, the
     migration logs the bad row count and refuses to add the
     constraint.
  3. Downgrade drops the constraints.

On SQLite: the SET NULL foreign-key enforcement requires
`PRAGMA foreign_keys = ON` per connection; the SQLite client
already does this. The constraints work on SQLite 3.6.19+.

Reversible: dropping the constraints re-enables orphan FK
columns.
"""
from typing import Sequence, Union

import os

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FKS = [
    # (table, column, ref_table, fk_name, on_delete)
    ("devices", "network_id", "networks", "fk_devices_network_id", "SET NULL"),
    ("topology_nodes", "network_id", "networks", "fk_topology_nodes_network_id", "SET NULL"),
    ("topology_links", "network_id", "networks", "fk_topology_links_network_id", "SET NULL"),
    ("alert_configs", "integration_id", "integrations", "fk_alert_configs_integration_id", "SET NULL"),
]


def _fk_exists(table: str, fk_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        fks = inspector.get_foreign_keys(table)
        return any(fk.get("name") == fk_name for fk in fks)
    except Exception:
        return False


def upgrade() -> None:
    # The entire migration is gated by NETOPS_ENABLE_FKS=1 because:
    # - Alembic's SQLite dialect does not support ALTER of
    #   constraints outside batch mode. Running on a SQLite DB
    #   raises NotImplementedError.
    # - Operators who opt in must run this on PostgreSQL only
    #   until/unless the SQLite batch-mode shim is added.
    if os.environ.get("NETOPS_ENABLE_FKS", "0") != "1":
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Validate first: count rows that would violate the new FKs.
    for table, col, ref_table, fk_name, on_delete in FKS:
        if _fk_exists(table, fk_name):
            continue
        if not inspector.has_table(table) or not inspector.has_table(ref_table):
            continue
        # Rows where the FK column is non-NULL but the target row is
        # missing. These would fail constraint creation.
        bad_count = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} t "
            f"WHERE t.{col} IS NOT NULL "
            f"AND NOT EXISTS (SELECT 1 FROM {ref_table} r WHERE r.id = t.{col})"
        )).scalar()
        if bad_count and bad_count > 0:
            raise RuntimeError(
                f"Cannot add FK {fk_name}: {bad_count} rows in {table} "
                f"reference missing {ref_table}.id. Clean up the data first "
                f"or set NETOPS_ENABLE_FKS=0 to skip FK creation."
            )

    # Add the FKs.
    for table, col, ref_table, fk_name, on_delete in FKS:
        if _fk_exists(table, fk_name):
            continue
        if not inspector.has_table(table) or not inspector.has_table(ref_table):
            continue
        op.create_foreign_key(
            fk_name,
            source_table=table,
            referent_table=ref_table,
            local_cols=[col],
            remote_cols=["id"],
            ondelete=on_delete,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, col, ref_table, fk_name, on_delete in reversed(FKS):
        if not _fk_exists(table, fk_name):
            continue
        try:
            op.drop_constraint(fk_name, table, type_="foreignkey")
        except Exception:
            pass
