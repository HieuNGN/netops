#!/usr/bin/env python3
"""Run alembic migrations for NetOps.

Honors `DATABASE_URL` and `--database-url` so the same script works
for the legacy POSTGRES_* env vars (Phase 3's old contract) and the
new unified `DATABASE_URL` (the contract going forward).

Usage:
    # Default: read POSTGRES_* env vars
    python scripts/migrate.py upgrade head

    # Explicit DATABASE_URL
    DATABASE_URL=postgresql://netops:netops@db/netops \\
        python scripts/migrate.py upgrade head

    # Pass on the CLI (overrides everything)
    python scripts/migrate.py --database-url postgresql://... upgrade head
"""

import argparse
import os
import sys

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from alembic.config import Config
from alembic import command


def _resolve_database_url(cli_value: str | None) -> str | None:
    """Resolve the connection string in priority order.

    1. `--database-url` CLI flag.
    2. `DATABASE_URL` env var.
    3. Fall back to `AsyncPostgresClient._build_connection_string()`
       which reads `POSTGRES_*` env vars (legacy).
    """
    if cli_value:
        return cli_value
    env_dsn = os.environ.get("DATABASE_URL")
    if env_dsn:
        return env_dsn
    # Fall back: build from POSTGRES_* (legacy).
    from src.storage.database import AsyncPostgresClient
    return AsyncPostgresClient()._connection_string


def get_alembic_config(database_url: str | None = None) -> Config:
    """Get alembic config with proper paths and DSN override."""
    config = Config(os.path.join(
        _PROJECT_ROOT, 'src', 'storage', 'alembic.ini'
    ))
    config.set_main_option(
        'script_location',
        os.path.join(_PROJECT_ROOT, 'src', 'storage', 'migrations')
    )
    if database_url:
        # Alembic env.py loads .env; the runtime DSN is still what
        # asyncpg will read, but the alembic engine uses the sync
        # version (the env.py falls back to a sync engine when called
        # from a running asyncio loop, which happens during tests).
        config.set_main_option('sqlalchemy.url', database_url)
    return config


def upgrade(target: str = "head", database_url: str | None = None):
    """Run migrations upgrade."""
    dsn = _resolve_database_url(database_url)
    config = get_alembic_config(dsn)
    command.upgrade(config, target)
    print(f"Migration completed to {target}")


def downgrade(target: str = "-1", database_url: str | None = None):
    """Run migrations downgrade."""
    dsn = _resolve_database_url(database_url)
    config = get_alembic_config(dsn)
    command.downgrade(config, target)
    print(f"Downgrade completed to {target}")


def current(database_url: str | None = None):
    """Show current migration version."""
    dsn = _resolve_database_url(database_url)
    config = get_alembic_config(dsn)
    command.current(config)


def history(database_url: str | None = None):
    """Show migration history."""
    dsn = _resolve_database_url(database_url)
    config = get_alembic_config(dsn)
    command.history(config)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run alembic migrations for NetOps"
    )
    sub = parser.add_subparsers(dest="cmd", required=False)

    # Each subcommand carries its own --database-url so the flag
    # doesn't have to fight with the subcommand parser.
    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--database-url",
            default=None,
            help="PostgreSQL DSN (overrides $DATABASE_URL and $POSTGRES_*)",
        )

    up = sub.add_parser("upgrade", help="Upgrade (default: head)")
    _add_common(up)
    up.add_argument("target", nargs="?", default="head", help="Target revision")

    down = sub.add_parser("downgrade", help="Downgrade (default: -1)")
    _add_common(down)
    down.add_argument("target", nargs="?", default="-1", help="Target revision")

    cur = sub.add_parser("current", help="Show current revision")
    _add_common(cur)
    his = sub.add_parser("history", help="Show history")
    _add_common(his)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd or "upgrade"

    if cmd == "upgrade":
        upgrade(args.target, args.database_url)
    elif cmd == "downgrade":
        downgrade(args.target, args.database_url)
    elif cmd == "current":
        current(args.database_url)
    elif cmd == "history":
        history(args.database_url)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
