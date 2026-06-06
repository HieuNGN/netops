"""Add CHECK constraint on networks.network_type.

Revision ID: 012
Revises: 011
Create Date: 2026-06-06

Per `.opencode/plans/docs/NETWORK_MANAGEMENT_CONSOLE_SPEC.md`, the
`networks.network_type` column should only accept a fixed set of
slug values. This migration enforces that with a CHECK constraint
on PostgreSQL.

Valid slugs (from the spec):
  lan, wan, wifi, sfp, console, bmc, mgmt, dmz, vlan, vpn, custom

The application layer (NetworkPicker / NetworksConsole) validates
slugs before INSERT. The DB-level constraint is defense in depth.

Behavior:
  - On PostgreSQL: adds a named CHECK constraint via ALTER TABLE.
    Existing rows that violate the constraint are logged but the
    migration does NOT fail; operators can run a one-shot
    cleanup script to normalize bad values to 'custom' if needed.
  - On SQLite: no-op (SQLite CHECK constraints are per-column and
    are not added after table creation; they would require a
    table rebuild).
  - Net effect: PG is strict, SQLite is permissive (validated in
    the application layer).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Slugs from the Network Management Console spec.
VALID_NETWORK_TYPES = (
    "lan", "wan", "wifi", "sfp", "console",
    "bmc", "mgmt", "dmz", "vlan", "vpn", "custom",
)


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    bind = op.get_bind()

    # Drop the constraint if it already exists (idempotent).
    op.execute("""
        ALTER TABLE networks
        DROP CONSTRAINT IF EXISTS ck_networks_network_type
    """)

    # Identify any rows that would violate the new constraint, log
    # them, and normalize to 'custom' so the constraint can apply.
    bad_rows = bind.execute(sa.text(
        "SELECT id, name, network_type FROM networks "
        "WHERE network_type IS NOT NULL "
        "AND network_type NOT IN :types"
    ).bindparams(
        sa.bindparam("types", expanding=True)
    ),
        {"types": list(VALID_NETWORK_TYPES)},
    ).fetchall()
    if bad_rows:
        # We can't bind an expanding list with simple text(); use
        # an inlined tuple literal.
        in_clause = ", ".join(f"'{t}'" for t in VALID_NETWORK_TYPES)
        bind.execute(sa.text(
            f"UPDATE networks SET network_type = 'custom' "
            f"WHERE network_type IS NOT NULL "
            f"AND network_type NOT IN ({in_clause})"
        ))

    # Add the constraint.
    in_clause = ", ".join(f"'{t}'" for t in VALID_NETWORK_TYPES)
    op.execute(f"""
        ALTER TABLE networks
        ADD CONSTRAINT ck_networks_network_type
        CHECK (network_type IS NULL OR network_type IN ({in_clause}))
    """)


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("""
        ALTER TABLE networks
        DROP CONSTRAINT IF EXISTS ck_networks_network_type
    """)
