#!/bin/bash
# NetOps Build Fixer & Inconsistency Watcher
# Runs continuously via cron to test, discover issues, and attempt fixes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/home/cqrtp/projs/netops"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_FILE="$LOG_DIR/fix-runner-$TIMESTAMP.log"

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ============================================
# 1. CHECKSERVICES
# ============================================
log "=== Starting NetOps Fix Runner ==="

# Check backend
BACKEND_UP=0
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
    log "Backend: UP"
    BACKEND_UP=1
else
    log "Backend: DOWN — restarting..."
    pkill -f "uvicorn src.collector.main" 2>/dev/null || true
    sleep 1
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    nohup uvicorn src.collector.main:app --host 127.0.0.1 --port 8000 --reload > /tmp/netops-backend.log 2>&1 &
    sleep 3
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
        log "Backend: RESTORED"
        BACKEND_UP=1
    else
        log "Backend: FAILED TO START"
    fi
fi

# Check frontend
FRONTEND_UP=0
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200"; then
    log "Frontend: UP"
    FRONTEND_UP=1
else
    log "Frontend: DOWN — restarting..."
    pkill -f "vite" 2>/dev/null || true
    sleep 1
    cd "$PROJECT_DIR/web"
    nohup npm run dev > /tmp/netops-frontend.log 2>&1 &
    sleep 3
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200"; then
        log "Frontend: RESTORED"
        FRONTEND_UP=1
    else
        log "Frontend: FAILED TO START"
    fi
fi

# ============================================
# 2. TYPE-CHECK FRONTEND
# ============================================
log "=== Frontend TypeScript Check ==="
cd "$PROJECT_DIR/web"
if npm run build > /tmp/netops-build-check.log 2>&1; then
    log "Frontend build: CLEAN"
else
    log "Frontend build: FAILED — collecting errors..."
    grep -E "error TS|Error: |Could not resolve" /tmp/netops-build-check.log | head -20 >> "$LOG_FILE" || true
    # Try auto-fix: npm install missing deps if any
    if grep -q "Cannot find module" /tmp/netops-build-check.log; then
        MODULE=$(grep -oP "Cannot find module '\K[^']+" /tmp/netops-build-check.log | head -1)
        log "Attempting npm install for missing module: $MODULE"
        npm install "$MODULE" >> "$LOG_FILE" 2>&1 || true
    fi
fi

# ============================================
# 3. PYTHON IMPORT TESTS
# ============================================
log "=== Python Module Import Checks ==="
cd "$PROJECT_DIR"
source .venv/bin/activate

IMPORTS_OK=0
if python -c "from src.collector.main import app; print('OK')" >> "$LOG_FILE" 2>&1; then
    log "Import app: OK"
    IMPORTS_OK=1
else
    log "Import app: FAILED"
fi

python -c "from src.collector.snmp_poller import SNMPPoller; print('OK')" >> "$LOG_FILE" 2>&1 && log "Import SNMPPoller: OK" || log "Import SNMPPoller: FAILED"
python -c "from src.collector.discovery import discover_devices; print('OK')" >> "$LOG_FILE" 2>&1 && log "Import discovery: OK" || log "Import discovery: FAILED"
python -c "from src.api.services.alert_service import AlertService; print('OK')" >> "$LOG_FILE" 2>&1 && log "Import AlertService: OK" || log "Import AlertService: FAILED"

# ============================================
# 4. QUICK API SMOKE TESTS
# ============================================
if [ $BACKEND_UP -eq 1 ]; then
    log "=== API Smoke Tests ==="
    
    # Health
    HEALTH=$(curl -s http://localhost:8000/health)
    if echo "$HEALTH" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)" >> "$LOG_FILE" 2>&1; then
        log "/health: OK"
    else
        log "/health: FAILED"
    fi

    # Topology
    TOPO=$(curl -s http://localhost:8000/topology)
    if echo "$TOPO" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'nodes' in d and 'links' in d else 1)" >> "$LOG_FILE" 2>&1; then
        log "/topology: OK"
    else
        log "/topology: FAILED"
    fi

    # Devices
    DEVICES=$(curl -s http://localhost:8000/devices)
    if echo "$DEVICES" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,list) else 1)" >> "$LOG_FILE" 2>&1; then
        log "/devices: OK"
    else
        log "/devices: FAILED"
    fi

    # Checks
    CHECKS=$(curl -s http://localhost:8000/checks)
    if echo "$CHECKS" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,list) else 1)" >> "$LOG_FILE" 2>&1; then
        log "/checks: OK"
    else
        log "/checks: FAILED"
    fi

    # Alerts
    ALERTS=$(curl -s http://localhost:8000/alerts)
    if echo "$ALERTS" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,list) else 1)" >> "$LOG_FILE" 2>&1; then
        log "/alerts: OK"
    else
        log "/alerts: FAILED"
    fi
fi

# ============================================
# 5. PYTEST SUITE
# ============================================
if [ $BACKEND_UP -eq 1 ]; then
    log "=== Running Pytest Suite ==="
    cd "$PROJECT_DIR"
    if pytest tests/ -v --tb=short > /tmp/netops-pytest.log 2>&1; then
        PASSED=$(grep -oP '\d+(?= passed)' /tmp/netops-pytest.log | tail -1 || echo "?")
        log "Pytest: ALL PASSED ($PASSED tests)"
    else
        FAILED=$(grep -oP '\d+(?= failed)' /tmp/netops-pytest.log | tail -1 || echo "?")
        log "Pytest: FAILURES ($FAILED failed) — see /tmp/netops-pytest.log"
    fi
fi

# ============================================
# 6. DISK / RESOURCE CHECKS
# ============================================
log "=== Resource Checks ==="
DB_SIZE=$(du -sh "$PROJECT_DIR/data/netops.db" 2>/dev/null | cut -f1 || echo "N/A")
log "Database size: $DB_SIZE"

# Check for uncommitted dirty files
cd "$PROJECT_DIR"
DIRTY=$(git status --short 2>/dev/null | wc -l)
if [ "$DIRTY" -gt 0 ]; then
    log "Git dirty files: $DIRTY"
    git status --short >> "$LOG_FILE" 2>&1 || true
else
    log "Git: clean"
fi

# ============================================
# 7. SUMMARY
# ============================================
log "=== Fix Runner Complete ==="
log "Log saved to: $LOG_FILE"

# Keep only last 20 logs
cd "$LOG_DIR"
ls -1t fix-runner-*.log 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true
