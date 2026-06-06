"""Portable migration helpers.

SQLite does not support `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`,
and PostgreSQL uses `TIMESTAMPTZ` while SQLite stores everything as
TEXT. The helpers below provide dialect-aware, idempotent equivalents
that work on both.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op


def add_column_if_not_exists(
    table_name: str,
    column_name: str,
    column_type: Any,
    *,
    nullable: bool = True,
    server_default: Any = None,
) -> None:
    """Add a column to a table if it does not already exist.

    Works on both PostgreSQL and SQLite. Uses the SQLAlchemy inspector
    to check for column existence, then issues a dialect-appropriate
    ALTER TABLE.

    Args:
        table_name: Name of the table to alter.
        column_name: Name of the column to add.
        column_type: SQLAlchemy type (e.g. sa.String(), sa.Integer()).
        nullable: Whether the column allows NULLs.
        server_default: Optional server-side default (sa.text("...") or
            a Python literal).
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if column_name in {c["name"] for c in inspector.get_columns(table_name)}:
        return

    dialect = bind.dialect.name
    type_str = _render_type(column_type, dialect)
    nullable_str = "" if nullable else " NOT NULL"
    default_str = ""
    if server_default is not None:
        default_str = f" DEFAULT {_render_default(server_default, dialect)}"

    op.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {type_str}"
        f"{nullable_str}{default_str}"
    )


def create_index_if_not_exists(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    """Create an index if it does not already exist (cross-dialect)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}:
        return
    unique_str = "UNIQUE " if unique else ""
    cols = ", ".join(columns)
    op.execute(
        f"CREATE {unique_str}INDEX {index_name} ON {table_name} ({cols})"
    )


def _render_type(column_type: Any, dialect: str) -> str:
    """Render a SQLAlchemy type as a portable SQL string."""
    if isinstance(column_type, sa.String):
        return "TEXT"
    if isinstance(column_type, sa.Text):
        return "TEXT"
    if isinstance(column_type, sa.Integer):
        return "INTEGER"
    if isinstance(column_type, sa.Float):
        return "REAL"
    if isinstance(column_type, sa.DateTime):
        # Both PG (TIMESTAMPTZ) and SQLite (TEXT) accept TIMESTAMP.
        return "TIMESTAMP" if dialect == "sqlite" else "TIMESTAMPTZ"
    if isinstance(column_type, sa.Boolean):
        return "BOOLEAN"
    # Fallback: use the type's compile() if available.
    return str(column_type)


def _render_default(default: Any, dialect: str) -> str:
    """Render a server_default as a portable SQL string."""
    if isinstance(default, sa.TextClause):
        # Wrap text defaults in parens for safety.
        return f"({default.text})"
    if isinstance(default, str):
        escaped = default.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(default, (int, float)):
        return str(default)
    return str(default)
