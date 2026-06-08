#!/bin/bash
set -a
. ./.env
set +a

PGDATA="${PGDATA:-$(dirname "$0")/../data/pgdata}"
PGLOG="${PGDATA}/logfile"

# Fail fast if PostgreSQL is not running
/usr/bin/pg_ctl -D "$PGDATA" status >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: PostgreSQL not running at $PGDATA"
    echo "Start it first: /usr/bin/pg_ctl -D $PGDATA -l $PGLOG start"
    exit 1
fi

echo "=== Running Alembic migrations ==="
python -m alembic -c src/storage/alembic.ini upgrade head

echo "=== Starting NetOps API server ==="
exec uvicorn src.collector.main:app --host 127.0.0.1 --port 8000
