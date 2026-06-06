"""Add email and name to users.

Revision ID: 004
Revises: 003
Create Date: 2026-06-04

The `users` table is now created in 001 baseline with the `email`
and `name` columns already present, so this revision no longer needs
to add them. Preserved to keep the migration chain linear and the
revision IDs stable for any existing deployments that stamped this
rev before the 001 baseline was consolidated.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users table and email/name columns are in 001 baseline.
    pass


def downgrade() -> None:
    pass
