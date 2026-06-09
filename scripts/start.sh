#!/bin/bash
# NetOps unified service orchestrator.
# Starts PostgreSQL, backend (uvicorn), and frontend (vite dev) in the
# correct order with dependency checks, PID tracking, and clean shutdown.
#
# Usage:
#   scripts/start.sh [all|backend|frontend|postgres|migrate]
#   scripts/start.sh stop [all|backend|frontend|postgres]
#   scripts/start.sh status
#   scripts/start.sh restart [all|backend|frontend]
#
# Defaults to "all" if no argument given.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_ROOT/data/pids"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

# Load env
set -a
if [ -f "$PROJECT_ROOT/.env" ]; then
    . "$PROJECT_ROOT/.env"
fi
set +a

PGDATA="${PGDATA:-$PROJECT_ROOT/data/pgdata}"
PGLOG="${PGDATA}/logfile"
PG_PORT="${POSTGRES_PORT:-5432}"

BACKEND_PORT="${SERVER_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
DATABASE_URL="${DATABASE_URL:-postgresql://netops:netops@localhost:$PG_PORT/netops}"

# --- Helpers ---------------------------------------------------------------

_pidfile() { echo "$PID_DIR/$1.pid"; }
_save_pid() { echo "$2" > "$(_pidfile "$1")"; }
_read_pid() { cat "$(_pidfile "$1")" 2>/dev/null || echo ""; }
_is_running() {
    local pid
    pid="$(_read_pid "$1")"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}
_kill_wait() {
    local pid name
    name="$1"
    pid="$(_read_pid "$name")"
    if [ -n "$pid" ]; then
        echo "  Stopping $name (pid $pid)..."
        kill "$pid" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.5
        done
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$(_pidfile "$name")"
    fi
}

# --- Postgres --------------------------------------------------------------

_start_postgres() {
    if _is_running postgres; then
        echo "[postgres] Already running (pid $(_read_pid postgres))"
        return 0
    fi
    echo "[postgres] Starting PostgreSQL..."
    if ! /usr/bin/pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
        if [ ! -d "$PGDATA" ]; then
            echo "  ERROR: PGDATA directory not found: $PGDATA"
            echo "  Run initdb first: /usr/bin/initdb -D $PGDATA"
            exit 1
        fi
        /usr/bin/pg_ctl -D "$PGDATA" -l "$PGLOG" start
    fi
    # Wait for ready
    for i in {1..30}; do
        if pg_isready -h localhost -p "$PG_PORT" -U netops >/dev/null 2>&1; then
            break
        fi
        [ $i -eq 30 ] && { echo "  ERROR: PostgreSQL did not start"; exit 1; }
        sleep 0.5
    done
    # pg_ctl doesn't give a long-running PID; track the cluster process
    local pg_pid
    pg_pid=$(/usr/bin/pg_ctl -D "$PGDATA" status 2>&1 | grep -oP 'PID:\s*\K[0-9]+' || true)
    if [ -n "$pg_pid" ]; then
        _save_pid postgres "$pg_pid"
    fi
    echo "  PostgreSQL ready on port $PG_PORT"
}

# --- Backend ---------------------------------------------------------------

_start_backend() {
    if _is_running backend; then
        echo "[backend] Already running (pid $(_read_pid backend))"
        return 0
    fi
    echo "[backend] Starting uvicorn..."
    cd "$PROJECT_ROOT"
    # Activate venv if present
    if [ -f ".venv/bin/activate" ]; then
        source ".venv/bin/activate"
    fi
    # Verify PG reachable
    if ! pg_isready -h localhost -p "$PG_PORT" -U netops >/dev/null 2>&1; then
        echo "  ERROR: PostgreSQL not reachable on port $PG_PORT"
        exit 1
    fi
    # Run migrations
    echo "  Running alembic migrations..."
    python -m alembic -c src/storage/alembic.ini upgrade head >/dev/null 2>&1 || {
        echo "  WARNING: Migration failed or already current"
    }
    # Start uvicorn using python -m so $! is the real Python PID (no wrapper shell).
    export DATABASE_URL
    nohup "$PROJECT_ROOT/.venv/bin/python3" -m uvicorn src.collector.main:app \
        --host 127.0.0.1 --port "$BACKEND_PORT" > "$LOG_DIR/backend.log" 2>&1 &
    local pid=$!
    _save_pid backend "$pid"
    # Wait for health
    for i in {1..60}; do
        if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health/ready" >/dev/null 2>&1; then
            break
        fi
        [ $i -eq 60 ] && { echo "  WARNING: Backend health check timed out"; }
        sleep 0.5
    done
    echo "  Backend ready on http://127.0.0.1:$BACKEND_PORT (pid $pid)"
}

# --- Frontend --------------------------------------------------------------

_start_frontend() {
    if _is_running frontend; then
        echo "[frontend] Already running (pid $(_read_pid frontend))"
        return 0
    fi
    echo "[frontend] Starting Vite dev server..."
    cd "$PROJECT_ROOT/web"
    if ! command -v npm >/dev/null 2>&1; then
        echo "  ERROR: npm not found"
        exit 1
    fi
    # Check node_modules
    if [ ! -d "node_modules" ]; then
        echo "  Installing npm dependencies..."
        npm install
    fi
    (
        cd "$PROJECT_ROOT/web" && exec npx vite --port "$FRONTEND_PORT"
    ) > "$LOG_DIR/frontend.log" 2>&1 &
    local pid=$!
    _save_pid frontend "$pid"
    # Wait for ready
    for i in {1..30}; do
        if curl -fsSk "https://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || \
           curl -fsS "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
            break
        fi
        [ $i -eq 30 ] && { echo "  WARNING: Frontend did not respond in time"; }
        sleep 0.5
    done
    echo "  Frontend ready on https://localhost:$FRONTEND_PORT (pid $pid)"
}

# --- Migrate ---------------------------------------------------------------

_run_migrate() {
    echo "[migrate] Running alembic migrations..."
    cd "$PROJECT_ROOT"
    if [ -f ".venv/bin/activate" ]; then
        source ".venv/bin/activate"
    fi
    python -m alembic -c src/storage/alembic.ini upgrade head
    echo "  Done."
}

# --- Stop ------------------------------------------------------------------

_stop_all() {
    echo "[stop] Stopping services..."
    case "${1:-all}" in
        all)
            _kill_wait frontend
            _kill_wait backend
            _kill_wait postgres
            echo "[stop] All services stopped."
            ;;
        frontend) _kill_wait frontend ;;
        backend)  _kill_wait backend ;;
        postgres) _kill_wait postgres ;;
        *) echo "Usage: $0 stop [all|backend|frontend|postgres]"; exit 1 ;;
    esac
}

# --- Status ----------------------------------------------------------------

_status() {
    echo "=== NetOps Service Status ==="
    for svc in postgres backend frontend; do
        if _is_running "$svc"; then
            printf "  %-10s running (pid %s)\n" "$svc" "$(_read_pid "$svc")"
        else
            printf "  %-10s stopped\n" "$svc"
        fi
    done
    echo ""
    echo "Health endpoints:"
    if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health/ready" >/dev/null 2>&1; then
        echo "  Backend:  http://127.0.0.1:$BACKEND_PORT/api/health/ready  OK"
    else
        echo "  Backend:  http://127.0.0.1:$BACKEND_PORT/api/health/ready  --"
    fi
    if curl -fsSk "https://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || \
       curl -fsS "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
        echo "  Frontend: https://localhost:$FRONTEND_PORT  OK"
    else
        echo "  Frontend: https://localhost:$FRONTEND_PORT  --"
    fi
}

# --- Restart ---------------------------------------------------------------

_restart() {
    local target="${1:-all}"
    echo "[restart] Restarting $target..."
    _stop_all "$target"
    sleep 1
    case "$target" in
        all)
            _start_postgres
            _start_backend
            _start_frontend
            ;;
        backend) _start_backend ;;
        frontend) _start_frontend ;;
        postgres) _start_postgres ;;
        *) echo "Usage: $0 restart [all|backend|frontend|postgres]"; exit 1 ;;
    esac
}

# --- Main ------------------------------------------------------------------

CMD="${1:-all}"

if [ -n "${2:-}" ] && [ "$CMD" != "stop" ] && [ "$CMD" != "restart" ]; then
    echo "Usage: $0 [all|backend|frontend|postgres|migrate|stop|status|restart]"
    echo "       $0 stop [all|backend|frontend|postgres]"
    echo "       $0 restart [all|backend|frontend|postgres]"
    exit 1
fi

case "$CMD" in
    all)
        _start_postgres
        _start_backend
        _start_frontend
        echo ""
        _status
        ;;
    postgres) _start_postgres ;;
    backend) _start_backend ;;
    frontend) _start_frontend ;;
    migrate) _run_migrate ;;
    stop) _stop_all "${2:-all}" ;;
    status) _status ;;
    restart) _restart "${2:-all}" ;;
    *)
        echo "Usage: $0 [all|backend|frontend|postgres|migrate|stop|status|restart]"
        exit 1
        ;;
esac
