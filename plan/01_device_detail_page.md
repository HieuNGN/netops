# Feature 1: Device Detail Page with Poll History Chart

## Problem Statement

NetOps currently shows devices as a flat list. Clicking a device only allows inline name editing. There is no way to drill into a single device to see its poll history, response time trends, associated checks, or topology context. This is the #1 UX gap — every enterprise tool (PRTG, SolarWinds, Datadog) makes device drill-down the core interaction model.

**Impact on presentation:** Professor will try to click a device to see details. Nothing happens except inline edit. Looks broken.

---

## Current State

### Backend
- `GET /api/devices/{id}` — returns device metadata (name, IP, status, sys_descr, etc.)
- `GET /api/poll-history?limit=100` — returns **global** poll history (all devices), no per-device filter
- `GET /api/checks/{id}/results` — returns check results for a specific check
- No endpoint to get poll history for a **specific device**
- No endpoint to get all checks associated with a device

### Frontend
- `Devices.tsx` — flat table with inline name edit on click
- `usePollHistory.ts` — fetches global poll history, used only by Dashboard
- No `useDeviceDetail` hook
- No device detail page or route
- Router (`App.tsx`) has no `/devices/:id` route

### Database
- `poll_history` table has `device_id` column → can filter per-device
- `check_results` table linked to `service_checks` by `check_id`, not directly to devices
- `topology_nodes` has `device_id` → can find topology node for a device

---

## Target State

### User Flow
1. User sees device list on `/devices`
2. Clicks device name (or a new "View" button) → navigates to `/devices/{id}`
3. Device detail page shows:
   - **Header:** Device name, IP, status badge, sys_descr, network, discovery method
   - **Poll History Chart:** Line chart of response_time_ms over time (Recharts)
   - **Poll Status Timeline:** Bar chart showing online/offline status over time
   - **Associated Checks:** List of service checks targeting this device's IP
   - **Topology Context:** Mini topology view showing this device's neighbors
   - **Recent Events:** Last 10 poll history entries in a table
4. Time range selector: 1h / 6h / 24h / 7d / 30d
5. Back button returns to device list

### Wireframe

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back to Devices                                               │
├─────────────────────────────────────────────────────────────────┤
│  ● Router-1                          [online]                   │
│  192.168.1.1 · Linux 5.15 · Network: LAN · SNMP v2c            │
│  Last polled: 2 min ago · Discovered via: snmp                  │
├─────────────────────────────────────────────────────────────────┤
│  [1h] [6h] [24h] [7d] [30d]                                    │
├─────────────────────────────────────────────────────────────────┤
│  Response Time (ms)                                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  120 ─                              ·──·                 │   │
│  │   80 ─         ·──·              ·──·                    │   │
│  │   40 ─    ·──·      ·──·    ·──·                         │   │
│  │    0 ─────┴──┴──────┴──┴────┴──┴──────────────────────   │   │
│  │       10:00   10:30   11:00   11:30   12:00              │   │
│  └──────────────────────────────────────────────────────────┘   │
├──────────────────────────────┬──────────────────────────────────┤
│  Status Timeline             │  Associated Checks               │
│  ┌──────────────────────────┐│  ┌────────────────────────────┐  │
│  │ ████░░████████████░░████ ││  │ ● HTTP Check  google.com   │  │
│  │ 12:00    12:30    13:00  ││  │   Status: UP · 45ms       │  │
│  └──────────────────────────┘│  │   Interval: 60s            │  │
│                              │  ├────────────────────────────┤  │
│                              │  │ ● Ping Check  192.168.1.1  │  │
│                              │  │   Status: UP · 2ms         │  │
│                              │  │   Interval: 60s            │  │
│                              │  └────────────────────────────┘  │
├──────────────────────────────┴──────────────────────────────────┤
│  Recent Poll History                                            │
│  ┌──────────┬────────┬──────────────┬──────────────────────┐   │
│  │ Time     │ Status │ Response (ms)│ Error                │   │
│  ├──────────┼────────┼──────────────┼──────────────────────┤   │
│  │ 13:00:30 │ online │ 45           │                      │   │
│  │ 13:00:00 │ online │ 42           │                      │   │
│  │ 12:59:30 │ offline│ —            │ Request timed out    │   │
│  └──────────┴────────┴──────────────┴──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Step 1: Backend — Per-Device Poll History Endpoint

**File:** `src/collector/main.py`

Add new endpoint:
```python
@app.get("/api/devices/{device_id}/history")
async def get_device_poll_history(
    device_id: str,
    limit: int = 200,
    hours: int = 24,  # time range filter
    user: str = Depends(need_auth),
):
    """Get poll history for a specific device."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    # Verify device exists
    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return await db_client.get_device_poll_history(device_id, limit=limit, hours=hours)
```

**File:** `src/storage/database.py` — Add method to `AsyncPostgresClient`:
```python
async def get_device_poll_history(
    self, device_id: str, limit: int = 200, hours: int = 24
) -> list[dict[str, Any]]:
    """Get poll history for a specific device within time range."""
    async with self._get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, device_id, status, response_time_ms, error, polled_at
            FROM poll_history
            WHERE device_id = $1
              AND polled_at >= NOW() - make_interval(hours => $2)
            ORDER BY polled_at DESC
            LIMIT $3
            """,
            device_id, hours, limit,
        )
        return [dict(row) for row in rows]
```

**File:** `src/storage/sqlite_client.py` — Mirror method:
```python
async def get_device_poll_history(
    self, device_id: str, limit: int = 200, hours: int = 24
) -> list[dict[str, Any]]:
    async with self._lock:
        cursor = await self._db.execute(
            """
            SELECT id, device_id, status, response_time_ms, error, polled_at
            FROM poll_history
            WHERE device_id = ? AND polled_at >= datetime('now', ? || ' hours')
            ORDER BY polled_at DESC
            LIMIT ?
            """,
            (device_id, f"-{hours}", limit),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in await cursor.fetchall()]
```

### Step 2: Backend — Device's Associated Checks Endpoint

**File:** `src/collector/main.py`

```python
@app.get("/api/devices/{device_id}/checks")
async def get_device_checks(device_id: str, user: str = Depends(need_auth)):
    """Get service checks associated with a device (by IP match on target)."""
    if not db_client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    device = await db_client.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Find checks whose target matches device IP or hostname
    all_checks = await db_client.list_service_checks()
    ip = device.get("ip_address", "")
    name = device.get("name", "")
    associated = [
        c for c in all_checks
        if ip and ip in str(c.get("target", ""))
        or name and name in str(c.get("target", ""))
    ]
    return associated
```

### Step 3: Frontend — API Endpoint Methods

**File:** `web/src/api/endpoints.ts`

Add to `devicesApi`:
```typescript
export interface DevicePollHistoryEntry {
  id: number;
  device_id: string;
  status: string;
  response_time_ms: number | null;
  error: string | null;
  polled_at: string;
}

// Add to devicesApi object:
history: (id: string, params?: { limit?: number; hours?: number }) =>
  apiClient.get<DevicePollHistoryEntry[]>(`/api/devices/${id}/history`, { params }),
checks: (id: string) =>
  apiClient.get<ServiceCheck[]>(`/api/devices/${id}/checks`),
```

### Step 4: Frontend — useDeviceDetail Hook

**File:** `web/src/hooks/useDeviceDetail.ts` (NEW)

```typescript
import { useQuery } from '@tanstack/react-query';
import { devicesApi, type Device, type DevicePollHistoryEntry, type ServiceCheck } from '../api';

export function useDeviceDetail(deviceId: string) {
  const deviceQuery = useQuery({
    queryKey: ['device', deviceId],
    queryFn: async () => {
      const res = await devicesApi.get(deviceId);
      return res.data as Device;
    },
    enabled: !!deviceId,
  });

  const historyQuery = useQuery({
    queryKey: ['deviceHistory', deviceId, 24],
    queryFn: async () => {
      const res = await devicesApi.history(deviceId, { limit: 500, hours: 24 });
      return res.data as DevicePollHistoryEntry[];
    },
    enabled: !!deviceId,
    refetchInterval: 30000,
  });

  const checksQuery = useQuery({
    queryKey: ['deviceChecks', deviceId],
    queryFn: async () => {
      const res = await devicesApi.checks(deviceId);
      return res.data as ServiceCheck[];
    },
    enabled: !!deviceId,
  });

  return {
    device: deviceQuery.data,
    isLoadingDevice: deviceQuery.isLoading,
    history: historyQuery.data || [],
    isLoadingHistory: historyQuery.isLoading,
    checks: checksQuery.data || [],
    isLoadingChecks: checksQuery.isLoading,
    refetch: () => {
      deviceQuery.refetch();
      historyQuery.refetch();
      checksQuery.refetch();
    },
  };
}
```

### Step 5: Frontend — PollHistoryChart Component

**File:** `web/src/components/PollHistoryChart.tsx` (NEW)

```typescript
// Recharts LineChart showing response_time_ms over time
// - X axis: polled_at (formatted as HH:mm)
// - Y axis: response_time_ms
// - Color: IBM Blue line, red dots for offline entries
// - Tooltip showing timestamp, status, response time
// - "No data" state when history is empty
// - Time range selector: 1h / 6h / 24h / 7d / 30d (calls hook with different hours param)
```

### Step 6: Frontend — DeviceDetail Page

**File:** `web/src/pages/DeviceDetail.tsx` (NEW)

Key sections:
1. **Header** — device name, IP, status badge, breadcrumbs (← Back to Devices)
2. **Metadata bar** — sys_descr, network, discovery method, last polled, SNMP version
3. **Time range selector** — button group: 1h / 6h / 24h / 7d / 30d
4. **Poll History Chart** — `PollHistoryChart` component
5. **Two-column layout:**
   - Left: Status timeline (bar chart of online/offline over time)
   - Right: Associated checks list (link to check detail)
6. **Recent poll history table** — last 20 entries with status, response time, error

### Step 7: Router + Navigation

**File:** `web/src/App.tsx`
```typescript
const DeviceDetail = lazy(() => import('./pages/DeviceDetail'));
// In Routes:
<Route path="/devices/:id" element={isAuthenticated ? <DeviceDetail /> : <Navigate to="/login" replace />} />
```

**File:** `web/src/pages/Devices.tsx`
- Change device name click from `startEditName` to `navigate(`/devices/${device.id}`)`
- Keep inline edit as right-click or pencil icon only
- Add eye icon button for "View details"

---

## Database Changes

**No migration required.** Uses existing `poll_history` table with `device_id` filter.

---

## Testing

### Backend Tests
```python
# tests/test_device_detail.py
async def test_get_device_poll_history():
    """Test per-device poll history returns only that device's entries."""

async def test_get_device_poll_history_time_range():
    """Test hours parameter filters correctly."""

async def test_get_device_checks():
    """Test associated checks returned by IP match."""

async def test_device_not_found():
    """Test 404 for non-existent device."""
```

### Frontend Tests
```typescript
// web/src/hooks/__tests__/useDeviceDetail.test.ts
// Test: returns empty arrays when no data
// Test: refetch works

// web/src/pages/__tests__/DeviceDetail.test.tsx (if time permits)
```

### Manual Testing
1. Navigate to `/devices`, click a device → detail page loads
2. Poll history chart renders with data (or "No data" state)
3. Time range buttons change data range
4. Associated checks show correct checks
5. Back button returns to device list
6. URL `/devices/{id}` is shareable/bookmarkable

---

## Estimated Effort

| Task | Hours |
|------|-------|
| Backend: `get_device_poll_history` (PG + SQLite) | 2h |
| Backend: `get_device_checks` endpoint | 1h |
| Backend: tests | 1h |
| Frontend: API methods + types | 1h |
| Frontend: `useDeviceDetail` hook | 2h |
| Frontend: `PollHistoryChart` component | 3h |
| Frontend: `DeviceDetail` page | 4h |
| Frontend: Router + navigation changes | 1h |
| Frontend: polish + responsive + dark mode | 2h |
| **Total** | **17h** |
