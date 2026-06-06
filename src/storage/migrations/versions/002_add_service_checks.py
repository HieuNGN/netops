"""Add service checks tables.

Revision ID: 002
Revises: 001
Create Date: 2026-04-29

`service_checks` and `check_results` are now created in 001 baseline
so a fresh `alembic upgrade head` against an empty database produces
the full schema. This revision is preserved to keep the migration
chain linear and the revision IDs stable for any existing deployments
that stamped this rev before the 001 baseline was consolidated.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables moved to 001 baseline.
    pass


def downgrade() -> None:
    pass
