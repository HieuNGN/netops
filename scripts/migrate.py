#!/usr/bin/env python3
"""Run alembic migrations for NetOps."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory

def get_alembic_config() -> Config:
    """Get alembic config with proper paths."""
    config = Config(os.path.join(
        os.path.dirname(__file__),
        '..', 'src', 'storage', 'alembic.ini'
    ))
    config.set_main_option(
        'script_location',
        os.path.join(os.path.dirname(__file__), '..', 'src', 'storage', 'migrations')
    )
    return config

def upgrade(target: str = "head"):
    """Run migrations upgrade."""
    config = get_alembic_config()

    # Override connection string from environment
    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    config.set_main_option('sqlalchemy.url', client._connection_string)

    command.upgrade(config, target)
    print(f"Migration completed to {target}")

def downgrade(target: str = "-1"):
    """Run migrations downgrade."""
    config = get_alembic_config()

    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    config.set_main_option('sqlalchemy.url', client._connection_string)

    command.downgrade(config, target)
    print(f"Downgrade completed to {target}")

def current():
    """Show current migration version."""
    config = get_alembic_config()

    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    config.set_main_option('sqlalchemy.url', client._connection_string)

    command.current(config)

def history():
    """Show migration history."""
    config = get_alembic_config()

    from src.storage.database import AsyncPostgresClient
    client = AsyncPostgresClient()
    config.set_main_option('sqlalchemy.url', client._connection_string)

    command.history(config)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
Usage: python scripts/migrate.py <command> [target]

Commands:
  upgrade [target]    - Migrate up to target (default: head)
  downgrade [target]  - Migrate down to target (default: -1)
  current             - Show current migration version
  history             - Show migration history

Examples:
  python scripts/migrate.py upgrade head
  python scripts/migrate.py upgrade 001
  python scripts/migrate.py downgrade -1
  python scripts/migrate.py current
""")
        sys.exit(1)

    cmd = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "upgrade":
        upgrade(target or "head")
    elif cmd == "downgrade":
        downgrade(target or "-1")
    elif cmd == "current":
        current()
    elif cmd == "history":
        history()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
