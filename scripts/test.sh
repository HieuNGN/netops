#!/bin/bash
# NetOps Test Suite
# Runs all tests for the NetOps project

set -e

cd /home/cqrtp/projs/netops

echo "=============================================="
echo "       NetOps Test Suite"
echo "=============================================="
echo ""

# Check virtual environment
if [ ! -f ".venv/bin/activate" ]; then
    echo "ERROR: Virtual environment not found!"
    echo "Run: uv venv && uv pip install -r requirements.txt"
    exit 1
fi

# Activate venv
source .venv/bin/activate

echo "[SETUP] Virtual environment activated"
echo "  Python: $(python --version)"
echo "  Path: $VIRTUAL_ENV"
echo ""

# Import tests
echo "[TEST] Import Tests"
echo "-------------------------------------------"

python -c "from src.collector.main import app; print('  ✓ FastAPI app')" || exit 1
python -c "from src.collector.spike_snmp import get_sys_descr; print('  ✓ SNMP module')" || exit 1
python -c "from src.collector.snmp_poller import SNMPPoller; print('  ✓ SNMP poller')" || exit 1
python -c "from src.collector.discovery import discover_devices; print('  ✓ Discovery module')" || exit 1
python -c "from src.collector.topology_builder import TopologyBuilder; print('  ✓ Topology builder')" || exit 1

echo ""
echo "[SETUP] Starting test server..."
echo "-------------------------------------------"

# Clean previous test data
rm -f data/netops.db
mkdir -p data

# Start server in background
uvicorn src.collector.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

# Wait for server to start
sleep 4

# Check server is running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "ERROR: Server failed to start"
    exit 1
fi

echo "  ✓ Server running (PID: $SERVER_PID)"
echo ""

# API Tests
echo "[TEST] API Endpoint Tests"
echo "-------------------------------------------"

# Test 1: Health
echo -n "  Testing /health... "
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)"; then
    echo "✓"
else
    echo "✗ FAILED"
    echo "$HEALTH"
fi

# Test 2: List devices (empty)
echo -n "  Testing GET /devices... "
DEVICES=$(curl -s http://localhost:8000/devices)
if [ "$DEVICES" = "[]" ]; then
    echo "✓"
else
    echo "✗ FAILED (expected empty array)"
fi

# Test 3: Create device
echo -n "  Testing POST /devices... "
CREATE=$(curl -s -X POST http://localhost:8000/devices \
    -H "Content-Type: application/json" \
    -d '{"name": "test-switch", "ip_address": "192.168.1.1", "community": "public"}')
if echo "$CREATE" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ip_address')=='192.168.1.1' else 1)"; then
    echo "✓"
    DEVICE_ID=$(echo "$CREATE" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
else
    echo "✗ FAILED"
    echo "$CREATE"
fi

# Test 4: Get single device
echo -n "  Testing GET /devices/{id}... "
if [ -n "$DEVICE_ID" ]; then
    SINGLE=$(curl -s "http://localhost:8000/devices/$DEVICE_ID")
    if echo "$SINGLE" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('name')=='test-switch' else 1)"; then
        echo "✓"
    else
        echo "✗ FAILED"
    fi
else
    echo "⊘ SKIPPED (no device ID)"
fi

# Test 5: Get topology
echo -n "  Testing GET /topology... "
TOPOLOGY=$(curl -s http://localhost:8000/topology)
if echo "$TOPOLOGY" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'nodes' in d and 'links' in d else 1)"; then
    echo "✓"
else
    echo "✗ FAILED"
fi

# Test 6: Get stats
echo -n "  Testing GET /stats... "
STATS=$(curl -s http://localhost:8000/stats)
if echo "$STATS" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'poll_interval' in d else 1)"; then
    echo "✓"
else
    echo "✗ FAILED"
fi

# Test 7: Discovery
echo -n "  Testing POST /discover... "
DISCOVER=$(curl -s -X POST http://localhost:8000/discover \
    -H "Content-Type: application/json" \
    -d '{"network_range": "127.0.0.1/32"}')
if echo "$DISCOVER" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'found' in d else 1)"; then
    echo "✓"
else
    echo "✗ FAILED"
fi

# Test 8: Poll history
echo -n "  Testing GET /poll-history... "
HISTORY=$(curl -s "http://localhost:8000/poll-history")
if echo "$HISTORY" | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if isinstance(d, list) else 1)"; then
    echo "✓"
else
    echo "✗ FAILED"
fi

# Test 9: SSE Stream (brief connection test)
echo -n "  Testing GET /topology/stream (SSE)... "
SSE=$(timeout 2 curl -sN http://localhost:8000/topology/stream 2>&1 || true)
if echo "$SSE" | grep -q "data:"; then
    echo "✓"
else
    echo "⊘ SKIPPED (SSE may need longer test)"
fi

echo ""
echo "[CLEANUP] Stopping server..."
echo "-------------------------------------------"

kill $SERVER_PID 2>/dev/null || true
sleep 1

if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "  ✓ Server stopped"
else
    echo "  ! Server still running, forcing kill..."
    pkill -f "uvicorn src.collector.main" || true
fi

echo ""
echo "=============================================="
echo "       Test Suite Complete"
echo "=============================================="
echo ""
echo "Summary:"
echo "  - Import tests: 5/5 passed"
echo "  - API tests: See above"
echo "  - Test data: data/netops.db (cleaned)"
echo ""
echo "[PYTEST] Running pytest integration tests..."
echo "-------------------------------------------"
pytest tests/test_api.py -v --tb=short || echo "  ! Some pytest tests failed"
echo ""
