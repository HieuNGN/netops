# Phase 1 Review: Inconsistencies and Issues

**Date:** 2026-04-28  
**Status:** Issues identified, fixes planned for Phase 2

---

## Critical Issues

### 1. Import Path Hack in main.py (Line 33-36)

**Problem:**
```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.pb.client import EmbeddedPocketBase
```

**Issue:** This is a hack to work around the `src/pb/` directory being at project root, not inside `src/collector/`.

**Fix:** Move the import to module level with proper path, or restructure to `src/collector/pb/`.

**Decision:** Keep `src/pb/` at project level (cleaner separation), fix import properly.

---

### 2. sqlite3 Import at Bottom of main.py (Line 313)

**Problem:**
```python
# Import sqlite3 for poll history
import sqlite3
```

**Issue:** Import is at the bottom of the file, should be at the top with other imports.

**Fix:** Move to top of file with standard library imports.

---

### 3. Inconsistent Channel Names in AlertConfigCreate (Line 88)

**Problem:**
```python
channel: str  # webhook, email, slack, discord
```

**Issue:** Documentation says "discord" but user requested Telegram/WhatsApp instead.

**Fix:** Update to: `# webhook, email, slack, telegram, whatsapp`

---

### 4. Duplicate `import sqlite3` in snmp_poller.py and client.py

**Problem:** Both files have `import sqlite3` at module level AND inside methods.

**Issue:** Redundant imports, inside-method imports are unnecessary.

**Fix:** Keep only module-level imports, remove inline imports.

---

### 5. asyncio.run() Inside Sync Function (spike_snmp.py)

**Problem:**
```python
def get_sys_descr(host: str, community: str = "public") -> Optional[str]:
    async def _get():
        ...
    error_indication, ... = asyncio.run(_get())
```

**Issue:** Using `asyncio.run()` inside a sync wrapper is fine for CLI, but problematic when called from async context (poller). The poller uses `run_in_executor()` which works around this.

**Current Workaround:** Poller calls via `run_in_executor()` which runs in a thread.

**Better Fix:** Provide both sync and async versions, or make poller use native async throughout.

**Decision:** For Phase 2, keep current workaround (works), document limitation.

---

### 6. Missing Alert Dispatch Logic

**Problem:** The `on_topology_change()` function in main.py only notifies SSE subscribers:

```python
async def on_topology_change(changes: dict[str, int], topology: dict[str, list]):
    message = json.dumps({"type": "topology_change", "changes": changes, "topology": topology})
    for queue in topology_subscribers:
        await queue.put(message)
```

**Issue:** No alert evaluation or notification dispatch happens here.

**Fix:** Add `AlertService` that evaluates rules and dispatches notifications.

---

### 7. Alert Endpoints Don't Validate Channel

**Problem:**
```python
@app.post("/alerts")
def create_alert(alert: AlertConfigCreate):
    ...
    return db_client.create_alert_config({...})
```

**Issue:** No validation that channel is one of the supported types.

**Fix:** Add validation in Pydantic model or endpoint.

---

### 8. Poll History Has No Retention Policy

**Problem:** `poll_history` table grows unbounded.

**Issue:** No cleanup of old records.

**Fix:** Add retention policy (e.g., delete records older than 30 days).

---

### 9. No Device Status Change Detection

**Problem:** Poller detects topology changes but not device status changes specifically.

**Issue:** A device going offline should trigger an alert even if topology doesn't change.

**Fix:** Track previous device status, compare with current, trigger `device_down`/`device_up` alerts.

---

### 10. LLDP Topology Correlation Is Weak

**Problem:**
```python
if neighbor_name.lower() in d.get("name", "").lower():
    target_device = d
```

**Issue:** Only matches by name substring. Won't work if device names don't match sysName.

**Fix:** Add IP-based matching, manual link configuration option.

---

## Phase 2 Action Items

| Issue | Priority | Action |
|-------|----------|--------|
| 1. Import path hack | High | Fix with proper module-level import |
| 2. sqlite3 at bottom | Medium | Move to top |
| 3. Channel names | High | Update to Telegram/WhatsApp |
| 4. Duplicate imports | Low | Clean up |
| 5. asyncio.run() | Medium | Document, provide async versions |
| 6. Alert dispatch | Critical | Implement AlertService |
| 7. Channel validation | Medium | Add Pydantic validation |
| 8. Retention policy | Low | Add cleanup job |
| 9. Device status detection | High | Track and alert on status changes |
| 10. LLDP correlation | Low | Enhance matching logic |

---

## Files to Modify for Phase 2

1. `src/collector/main.py` - Fix imports, add alert service integration
2. `src/collector/snmp_poller.py` - Add device status change detection
3. `src/pb/client.py` - Clean up imports, add retention
4. `src/api/services/alert_service.py` - NEW: Alert evaluation and dispatch
5. `src/api/services/notifications/` - NEW: Notification channel implementations
