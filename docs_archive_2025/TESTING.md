# NetOps Testing Guide

**Last Updated:** 2026-04-28  
**Version:** 1.0

---

## Quick Start: Run All Tests

```bash
cd /home/cqrtp/projs/netops

# 1. Ensure virtual environment exists and is active
source .venv/bin/activate

# 2. Run the test server and API tests
./scripts/test.sh

# Or manually:
uvicorn src.collector.main:app --host 0.0.0.0 --port 8000 &
sleep 4
curl http://localhost:8000/health
```

---

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [Import Tests](#import-tests)
3. [API Endpoint Tests](#api-endpoint-tests)
4. [SNMP CLI Tests](#snmp-cli-tests)
5. [Integration Tests](#integration-tests)
6. [Troubleshooting](#troubleshooting)

---

## Environment Setup

### Prerequisites

- Python 3.11+ 
- `uv` package manager (or pip)
- Network devices with SNMP enabled (optional, for live testing)

### Step 1: Create/Verify Virtual Environment

```bash
cd /home/cqrtp/projs/netops

# Check if venv exists
ls -la .venv/bin/python

# If missing or broken, recreate:
rm -rf .venv
uv venv
# or: python -m venv .venv
```

### Step 2: Install Dependencies

```bash
source .venv/bin/activate
uv pip install -r requirements.txt
# or: pip install -r requirements.txt
```

**Expected Output:**
```
+ fastapi==0.115.0
+ pysnmp==7.1.26
+ networkx==3.6.1
+ uvicorn==0.46.0
+ pydantic==2.13.3
+ httpx==0.28.1
+ pytest==9.0.3
...
```

### Step 3: Verify Installation

```bash
python --version           # Should show Python 3.11.x
which python               # Should point to .venv/bin/python
pip list | grep fastapi    # Should show fastapi
```

---

## Import Tests

Run these to verify all modules can be imported without errors:

```bash
source .venv/bin/activate

# Test 1: FastAPI app
python -c "from src.collector.main import app; print('✓ FastAPI app imports OK')"

# Test 2: SNMP module
python -c "from src.collector.spike_snmp import get_sys_descr, walk_lldp_neighbors; print('✓ SNMP module imports OK')"

# Test 3: PocketBase client
python -c "from src.pb.client import EmbeddedPocketBase; print('✓ PocketBase client imports OK')"

# Test 4: Poller service
python -c "from src.collector.snmp_poller import SNMPPoller; print('✓ SNMP poller imports OK')"

# Test 5: Discovery module
python -c "from src.collector.discovery import discover_devices; print('✓ Discovery module imports OK')"

# Test 6: Topology builder
python -c "from src.collector.topology_builder import TopologyBuilder; print('✓ Topology builder imports OK')"
```

**Expected Output:**
```
✓ FastAPI app imports OK
✓ SNMP module imports OK
✓ PocketBase client imports OK
✓ SNMP poller imports OK
✓ Discovery module imports OK
✓ Topology builder imports OK
```

**If you see `ModuleNotFoundError`:**
1. Ensure you're in the project directory: `pwd` should be `/home/cqrtp/projs/netops`
2. Ensure venv is activated: `echo $VIRTUAL_ENV` should show the path
3. Reinstall dependencies: `uv pip install -r requirements.txt`

---

## API Endpoint Tests

### Start the Server

```bash
source .venv/bin/activate

# Clean previous test data (optional)
rm -f data/netops.db

# Start server in background
uvicorn src.collector.main:app --host 0.0.0.0 --port 8000 &

# Wait for startup
sleep 4

# Verify server is running
curl http://localhost:8000/health
```

### Test 1: Health Check

```bash
curl http://localhost:8000/health | python -m json.tool
```

**Expected Response:**
```json
{
    "status": "ok",
    "poller": {
        "total_polls": 0,
        "successful_polls": 0,
        "failed_polls": 0,
        "success_rate": 0,
        "last_poll_time": null,
        "avg_response_time_ms": 0,
        "poll_interval": 30,
        "running": true
    }
}
```

### Test 2: List Devices (Empty)

```bash
curl http://localhost:8000/devices
```

**Expected Response:**
```json
[]
```

### Test 3: Create Device

```bash
curl -X POST http://localhost:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"name": "test-switch", "ip_address": "192.168.1.1", "community": "public"}'
```

**Expected Response:**
```json
{
    "id": "uuid-here",
    "name": "test-switch",
    "ip_address": "192.168.1.1",
    "community": "public",
    "status": "unknown",
    ...
}
```

### Test 4: Get Topology

```bash
curl http://localhost:8000/topology
```

**Expected Response:**
```json
{
    "nodes": [],
    "links": []
}
```

### Test 5: Get Poller Stats

```bash
curl http://localhost:8000/stats
```

**Expected Response:**
```json
{
    "total_polls": 0,
    "successful_polls": 0,
    "failed_polls": 0,
    "success_rate": 0,
    "poll_interval": 30,
    "running": true
}
```

### Test 6: Network Discovery

```bash
curl -X POST http://localhost:8000/discover \
  -H "Content-Type: application/json" \
  -d '{"network_range": "127.0.0.1/32", "community": "public"}'
```

**Expected Response:**
```json
{
    "found": 0,
    "added": 0
}
```

### Test 7: SSE Stream (Server-Sent Events)

```bash
# Test SSE connection (will hang, press Ctrl+C after 5 seconds)
timeout 5 curl -N http://localhost:8000/topology/stream 2>&1 | head -10
```

**Expected Output:**
```
data: {"type": "initial", "topology": {"nodes": [], "links": []}}
```

### Stop the Server

```bash
pkill -f "uvicorn src.collector.main"
```

---

## SNMP CLI Tests

### Test SNMP Connectivity (Single Device)

```bash
source .venv/bin/activate

# Test against a real SNMP device
python src/collector/spike_snmp.py <DEVICE_IP> --action sysdescr

# Example (if you have a device at 192.168.1.1):
python src/collector/spike_snmp.py 192.168.1.1 --action sysdescr
```

**Expected Output (with working device):**
```
=== System Description ===
sysDescr: Cisco IOS Software, C2960X Software (C2960X-UNIVERSALK9-M)
```

**Expected Output (no device):**
```
=== System Description ===
Error: Timeout
```

### Test LLDP Discovery

```bash
python src/collector/spike_snmp.py <DEVICE_IP> --action lldp
```

**Expected Output (with LLDP neighbors):**
```
=== LLDP Neighbor Map ===
  Index 12345: switch-core-01 via Gi0/1
  Index 12346: proxmox-node via Gi0/2
```

### Test All Actions

```bash
python src/collector/spike_snmp.py <DEVICE_IP> --action all
```

---

## Integration Tests

### Full Workflow Test

```bash
source .venv/bin/activate

# 1. Clean database
rm -f data/netops.db

# 2. Start server
uvicorn src.collector.main:app --reload &
sleep 4

# 3. Add a device
curl -X POST http://localhost:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"name": "lab-switch", "ip_address": "192.168.1.1"}'

# 4. Trigger discovery
curl -X POST http://localhost:8000/discover \
  -H "Content-Type: application/json" \
  -d '{"network_range": "192.168.1.0/24"}'

# 5. Check devices
curl http://localhost:8000/devices | python -m json.tool

# 6. Check topology
curl http://localhost:8000/topology | python -m json.tool

# 7. Stop server
pkill -f "uvicorn src.collector.main"
```

---

## Troubleshooting

### Error: `ModuleNotFoundError: No module named 'fastapi'`

**Cause:** Dependencies not installed or venv not activated.

**Fix:**
```bash
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Error: `ModuleNotFoundError: No module named 'src.pb'`

**Cause:** Import path issue. The `pb` module is at `src/pb/`, not `src/collector/pb/`.

**Fix:** Ensure you're running from the project root:
```bash
cd /home/cqrtp/projs/netops
pwd  # Should show /home/cqrtp/projs/netops
```

### Error: `Address already in use` when starting server

**Cause:** Another process is using port 8000.

**Fix:**
```bash
# Find and kill the process
lsof -i :8000
kill <PID>

# Or use a different port
uvicorn src.collector.main:app --port 8001
```

### Error: `Database not initialized` in API responses

**Cause:** Server started but database initialization failed.

**Fix:**
1. Check logs for errors during startup
2. Ensure `data/` directory exists: `mkdir -p data`
3. Delete corrupted DB: `rm data/netops.db`
4. Restart server

### Error: SNMP timeout on all queries

**Cause:** No SNMP-enabled devices on network, or firewall blocking port 161.

**Fix:**
1. Enable SNMP on a test device (Proxmox, router, etc.)
2. Check firewall: `sudo iptables -L | grep 161`
3. Test with snmpwalk: `snmpwalk -v2c -c public <IP>`

### Error: `sqlite3.Row` undefined

**Cause:** Missing sqlite3 import in `src/pb/client.py`.

**Fix:**
```python
# Add to top of src/pb/client.py
import sqlite3
```

### pytest fails with import errors

**Fix:**
```bash
source .venv/bin/activate
pytest --import-mode=importlib
```

---

## Test Script

Create `scripts/test.sh`:

```bash
#!/bin/bash
set -e

cd /home/cqrtp/projs/netops

echo "=== NetOps Test Suite ==="
echo ""

# Activate venv
source .venv/bin/activate

# Clean test data
rm -f data/netops.db

# Start server
echo "Starting server..."
uvicorn src.collector.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 4

# Run tests
echo ""
echo "Running API tests..."
./scripts/api-tests.sh

# Stop server
kill $SERVER_PID 2>/dev/null || true

echo ""
echo "=== Tests Complete ==="
```

---

## Test Checklist

Before marking Phase 1 complete, verify:

- [ ] All import tests pass
- [ ] Health endpoint returns 200 OK
- [ ] Device CRUD operations work
- [ ] Topology endpoint returns valid JSON
- [ ] Discovery endpoint runs without errors
- [ ] Server starts and stops cleanly
- [ ] Database file is created in `data/`
- [ ] Poller starts on server init
- [ ] SSE stream connects (even if no updates)

---

## Contact

For issues or questions, check:
- Project README: `/home/cqrtp/projs/netops/README.md`
- Architecture docs: `~/Documents/Obsidian Vault/Projs/netops/02-ARCHITECTURE.md`
- Weekly progress: `~/Documents/Obsidian Vault/Projs/netops/progress/week-1-2026-04-21.md`
