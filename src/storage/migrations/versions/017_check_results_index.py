"""Composite index on check_results for the checks dashboard.

Revision ID: 017
Revises: 016
Create Date: 2026-06-06

The `/api/checks/{id}/results` endpoint queries
`WHERE check_id = ? ORDER BY checked_at DESC LIMIT N`. The 001
baseline indexes are on (check_id) and (checked_at) separately.
This migration adds a composite that covers both predicates in
one B-tree lookup:

  `idx_check_results_check_time` on (check_id, checked_at DESC)

The descending order matches the dashboard's "newest first" sort.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        existing = {idx["name"] for idx in inspector.get_indexes("check_results")}
    except Exception:
        existing = set()
    if "idx_check_results_check_time" not in existing:
        op.execute(
            "CREATE INDEX idx_check_results_check_time "
            "ON check_results (check_id, checked_at DESC)"
        )


def downgrade() -> None:
    try:
        op.execute("DROP INDEX IF EXISTS idx_check_results_check_time")
    except Exception:
        pass
