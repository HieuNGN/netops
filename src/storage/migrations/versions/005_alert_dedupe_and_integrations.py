"""Add integrations table and alert_configs.integration_id.

Revision ID: 005
Revises: 004
Create Date: 2026-06-04

The `integrations` table, `alert_configs.integration_id` column, and
related indexes are now created in 001 baseline. The dedup of
duplicate alert configs (previously inline in this migration) has
been moved to `scripts/dedupe_alert_configs.py` so the migration is
purely schema and operators can run the dedup independently.

Preserved to keep the migration chain linear and the revision IDs
stable for any existing deployments that stamped this rev before
the 001 baseline was consolidated.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema is in 001 baseline. Run scripts/dedupe_alert_configs.py
    # separately to remove duplicate alert configs.
    pass


def downgrade() -> None:
    pass
