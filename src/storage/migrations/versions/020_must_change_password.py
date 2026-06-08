"""Add must_change_password flag to users table.

Revision ID: 020_must_change_password
Revises: 019
Create Date: 2026-06-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020_must_change_password'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add must_change_password column to users table
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=True, server_default='false'))
    
    # Set must_change_password=true for existing admin user (bootstrap admin)
    op.execute("UPDATE users SET must_change_password = true WHERE username = 'admin'")


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
