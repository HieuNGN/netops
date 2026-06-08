# Feature 5: Basic Anomaly Detection

## Problem Statement

All alerting in NetOps is threshold-based: "alert if response_time > 500ms". No ability to detect when metrics deviate from their normal pattern. PRTG has AI-driven baselines, Datadog has Watchdog (automatic anomaly detection), SolarWinds has AIOps anomaly alerts.

Even a simple statistical approach (rolling average + standard deviation) will look impressive and demonstrate understanding of modern monitoring concepts.

**Impact on presentation:** "Does it detect anomalies automatically?" → Yes! Dashboard shows "Anomaly Detected" when response time spikes 3σ above baseline. Professor impressed.

---

## Current State

### Data Available
- `poll_history` table: `device_id, status, response_time_ms, polled_at`
- `check_results` table: `check_id, status, response_time_ms, checked_at`
- Data collected every 30-60s per device/check
- Dashboard already shows aggregate poll success chart

### What's Missing
- No baseline computation (what's "normal" for this device?)
- No anomaly scoring
- No anomaly storage
- No anomaly UI
- No anomaly alerts

---

## Target State

### Anomaly Detection Model

**Approach: Rolling Z-Score (3-sigma)**

For each device, maintain a rolling baseline of `response_time_ms`:
```
baseline_avg = avg(response_time_ms for last 100 polls)
baseline_std = stddev(response_time_ms for last 100 polls)
z_score = (current_value - baseline_avg) / baseline_std

if z_score > 3.0:
    ANOMALY DETECTED (confidence: z_score / max_z * 100%)
```

**Why Z-Score?**
- Simple, well-understood statistical method
- No ML library needed (just avg + stddev)
- Works for any metric with numeric values
- 3-sigma catches top 0.3% outliers (conservative, low false positives)

### What Gets Monitored
1. **Device response time** — poll_history.response_time_ms per device
2. **Check response time** — check_results.response_time_ms per check
3. **Poll success rate** — rolling % of successful polls per device (anomaly if drops suddenly)

### User Experience

**Dashboard Anomaly Badge:**
```
┌──────────────────────────────────────────────────────────┐
│  Devices                                    47           │
│  ● 42 online · 3 offline · 2 unknown                    │
│                                                         │
│  ⚡ 2 anomalies detected                                │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Router-1: Response time 4.2x above baseline      │  │
│  │ Switch-7: Poll success rate dropped to 60%       │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Device Detail Anomaly Indicator:**
```
Response Time (ms)
┌──────────────────────────────────────────────────────────┐
│  120 ─                                        ·──· ← 🔴  │
│   80 ─         ·──·              ·──·                    │
│   40 ─    ·──·      ·──·    ·──·                         │
│    0 ─────┴──┴──────┴──┴────┴──┴──────────────────────   │
│  ─ ─ ─ ─ ─ ─ ─ ─ baseline: 45ms ± 12ms ─ ─ ─ ─ ─ ─   │
└──────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Step 1: Backend — Anomaly Detector Service

**File:** `src/api/services/anomaly_detector.py` (NEW)

```python
"""Basic anomaly detection using rolling Z-score analysis."""

import math
import time
from typing import Any, Optional
from collections import deque


class AnomalyDetector:
    """Detects anomalies in time-series metrics using rolling statistics.
    
    Maintains per-metric rolling windows and computes z-scores.
    Thread-safe for concurrent access from poller and API.
    """
    
    def __init__(self, window_size: int = 100, z_threshold: float = 3.0):
        self.window_size = window_size
        self.z_threshold = z_threshold
        # metric_key -> deque of recent values
        self._windows: dict[str, deque[float]] = {}
        # metric_key -> last anomaly info
        self._anomalies: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None
    
    def _key(self, metric_type: str, target_id: str) -> str:
        return f"{metric_type}:{target_id}"
    
    async def record_value(self, metric_type: str, target_id: str, value: float) -> Optional[dict[str, Any]]:
        """Record a metric value and check for anomaly.
        
        Returns anomaly info if detected, None otherwise.
        """
        key = self._key(metric_type, target_id)
        
        if self._lock:
            async with self._lock:
                return self._record_and_check(key, value, metric_type, target_id)
        return self._record_and_check(key, value, metric_type, target_id)
    
    def _record_and_check(
        self, key: str, value: float, metric_type: str, target_id: str
    ) -> Optional[dict[str, Any]]:
        """Internal: record value and check for anomaly."""
        # Initialize window if needed
        if key not in self._windows:
            self._windows[key] = deque(maxlen=self.window_size)
        
        window = self._windows[key]
        window.append(value)
        
        # Need at least 20 samples for meaningful baseline
        if len(window) < 20:
            return None
        
        # Compute baseline statistics
        values = list(window)
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0
        
        # Avoid division by zero for constant metrics
        if std < 0.001:
            return None
        
        # Compute z-score
        z_score = (value - avg) / std
        
        if abs(z_score) >= self.z_threshold:
            anomaly = {
                "metric_type": metric_type,
                "target_id": target_id,
                "current_value": value,
                "baseline_avg": round(avg, 2),
                "baseline_std": round(std, 2),
                "z_score": round(z_score, 2),
                "magnitude": round(abs(value - avg) / avg * 100, 1) if avg > 0 else 0,
                "direction": "spike" if z_score > 0 else "drop",
                "confidence": min(round(abs(z_score) / self.z_threshold * 100), 100),
                "detected_at": time.time(),
                "sample_count": len(window),
            }
            self._anomalies[key] = anomaly
            return anomaly
        
        # Clear anomaly if value returns to normal
        if key in self._anomalies:
            del self._anomalies[key]
        
        return None
    
    def get_active_anomalies(self) -> list[dict[str, Any]]:
        """Return all currently active anomalies."""
        return list(self._anomalies.values())
    
    def get_anomaly(self, metric_type: str, target_id: str) -> Optional[dict[str, Any]]:
        """Get anomaly status for a specific metric."""
        key = self._key(metric_type, target_id)
        return self._anomalies.get(key)
    
    def get_baseline(self, metric_type: str, target_id: str) -> Optional[dict[str, Any]]:
        """Get current baseline stats for a metric."""
        key = self._key(metric_type, target_id)
        window = self._windows.get(key)
        if not window or len(window) < 5:
            return None
        
        values = list(window)
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0
        
        return {
            "metric_type": metric_type,
            "target_id": target_id,
            "avg": round(avg, 2),
            "std": round(std, 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "sample_count": len(window),
            "window_size": self.window_size,
        }
    
    def clear(self):
        """Reset all windows and anomalies."""
        self._windows.clear()
        self._anomalies.clear()
```

### Step 2: Integrate with Poller

**File:** `src/collector/snmp_poller.py`

Add anomaly detector instance and feed it poll results:

```python
# In __init__:
from src.api.services.anomaly_detector import AnomalyDetector
self.anomaly_detector = AnomalyDetector(window_size=100, z_threshold=3.0)

# In _poll_device, after recording poll_history:
if result.response_time_ms is not None:
    anomaly = await self.anomaly_detector.record_value(
        "response_time", device_id, result.response_time_ms
    )
    if anomaly:
        logger.warning(
            f"Anomaly detected for {device_id}: "
            f"response_time={anomaly['current_value']}ms "
            f"(baseline={anomaly['baseline_avg']}±{anomaly['baseline_std']}ms, "
            f"z={anomaly['z_score']})"
        )
        # Emit SSE event
        if self._sse_handler:
            await self._sse_handler({
                "type": "anomaly_detected",
                "anomaly": anomaly,
            })
```

### Step 3: Integrate with Check Scheduler

**File:** `src/collector/checks/scheduler.py`

Feed check results to anomaly detector:

```python
# After recording check result:
if result.response_time_ms is not None and hasattr(self, 'anomaly_detector'):
    anomaly = await self.anomaly_detector.record_value(
        f"check_{result.check_type}", result.target_id, result.response_time_ms
    )
```

### Step 4: Backend API Endpoints

**File:** `src/collector/main.py`

```python
# Anomaly detector instance (shared with poller)
anomaly_detector: Optional[AnomalyDetector] = None


@app.get("/api/anomalies")
async def list_anomalies(user: str = Depends(need_auth)):
    """Get all currently active anomalies."""
    if not anomaly_detector:
        return {"anomalies": []}
    return {"anomalies": anomaly_detector.get_active_anomalies()}


@app.get("/api/anomalies/{metric_type}/{target_id}")
async def get_anomaly(metric_type: str, target_id: str, user: str = Depends(need_auth)):
    """Get anomaly status for a specific metric."""
    if not anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detector not initialized")
    anomaly = anomaly_detector.get_anomaly(metric_type, target_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="No active anomaly")
    return anomaly


@app.get("/api/anomalies/{metric_type}/{target_id}/baseline")
async def get_baseline(metric_type: str, target_id: str, user: str = Depends(need_auth)):
    """Get baseline statistics for a metric."""
    if not anomaly_detector:
        raise HTTPException(status_code=503, detail="Anomaly detector not initialized")
    baseline = anomaly_detector.get_baseline(metric_type, target_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Not enough data for baseline")
    return baseline
```

### Step 5: Wire Anomaly Detector in Lifespan

**File:** `src/collector/main.py`

In the `lifespan` function, after poller creation:
```python
global anomaly_detector
anomaly_detector = poller.anomaly_detector
```

### Step 6: SSE Event for Anomalies

**File:** `src/collector/main.py`

Add `anomaly_detected` to the SSE event stream:
```python
# In events/stream endpoint, the SSE handler already broadcasts all events
# Just need to ensure poller emits anomaly_detected events (done in step 2)
```

### Step 7: Frontend — API Methods

**File:** `web/src/api/endpoints.ts`

```typescript
export interface Anomaly {
  metric_type: string;
  target_id: string;
  current_value: number;
  baseline_avg: number;
  baseline_std: number;
  z_score: number;
  magnitude: number;
  direction: 'spike' | 'drop';
  confidence: number;
  detected_at: number;
  sample_count: number;
}

export interface Baseline {
  metric_type: string;
  target_id: string;
  avg: number;
  std: number;
  min: number;
  max: number;
  sample_count: number;
  window_size: number;
}

export const anomaliesApi = {
  list: () => apiClient.get<{ anomalies: Anomaly[] }>('/api/anomalies'),
  get: (metricType: string, targetId: string) =>
    apiClient.get<Anomaly>(`/api/anomalies/${metricType}/${targetId}`),
  baseline: (metricType: string, targetId: string) =>
    apiClient.get<Baseline>(`/api/anomalies/${metricType}/${targetId}/baseline`),
};
```

### Step 8: Frontend — useAnomalies Hook

**File:** `web/src/hooks/useAnomalies.ts` (NEW)

```typescript
import { useQuery } from '@tanstack/react-query';
import { anomaliesApi, type Anomaly } from '../api';

export function useAnomalies() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['anomalies'],
    queryFn: async () => {
      const res = await anomaliesApi.list();
      return res.data.anomalies;
    },
    refetchInterval: 30000,  // Check every 30s
  });

  return {
    anomalies: data || [],
    isLoading,
    error,
    count: data?.length || 0,
  };
}
```

### Step 9: Frontend — AnomalyBadge Component

**File:** `web/src/components/AnomalyBadge.tsx` (NEW)

```typescript
import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';
import type { Anomaly } from '../api';

export function AnomalyBadge({ anomaly }: { anomaly: Anomaly }) {
  const isSpike = anomaly.direction === 'spike';
  
  return (
    <div className="inline-flex items-center gap-2 px-3 py-2 rounded-sm bg-ibm-yellow/10 border border-ibm-yellow/30">
      <AlertTriangle className="h-4 w-4 text-ibm-yellow" />
      <div className="text-sm">
        <span className="font-medium text-foreground">
          {isSpike ? '↑' : '↓'} {anomaly.magnitude}% {anomaly.direction}
        </span>
        <span className="text-muted-foreground ml-1">
          (baseline: {anomaly.baseline_avg}±{anomaly.baseline_std}ms)
        </span>
      </div>
      <div className="text-xs text-muted-foreground">
        z={anomaly.z_score} · {anomaly.confidence}% confidence
      </div>
    </div>
  );
}

export function AnomalyCount({ count }: { count: number }) {
  if (count === 0) return null;
  
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-sm bg-ibm-yellow/10 border border-ibm-yellow/30">
      <AlertTriangle className="h-4 w-4 text-ibm-yellow" />
      <span className="text-sm font-medium text-foreground">
        {count} anomal{count === 1 ? 'y' : 'ies'} detected
      </span>
    </div>
  );
}
```

### Step 10: Dashboard Integration

**File:** `web/src/pages/Dashboard.tsx`

Add anomaly section after stat cards:
```typescript
import { useAnomalies } from '../hooks/useAnomalies';
import { AnomalyCount, AnomalyBadge } from '../components/AnomalyBadge';

function Dashboard() {
  const { anomalies, count: anomalyCount } = useAnomalies();
  
  // ... existing code ...
  
  // After stat cards, before charts:
  {anomalyCount > 0 && (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <AnomalyCount count={anomalyCount} />
      </div>
      <div className="space-y-2">
        {anomalies.slice(0, 5).map((anomaly, i) => (
          <AnomalyBadge key={i} anomaly={anomaly} />
        ))}
      </div>
    </div>
  )}
```

### Step 11: Device Detail Integration

**File:** `web/src/pages/DeviceDetail.tsx`

Show anomaly badge + baseline on poll history chart:
```typescript
import { anomaliesApi, type Baseline } from '../api';

// In DeviceDetail:
const { data: baseline } = useQuery({
  queryKey: ['baseline', 'response_time', deviceId],
  queryFn: async () => {
    const res = await anomaliesApi.baseline('response_time', deviceId);
    return res.data as Baseline;
  },
});

const currentAnomaly = anomalies.find(
  (a) => a.metric_type === 'response_time' && a.target_id === deviceId
);

// On chart: draw baseline as horizontal dashed line
// Show AnomalyBadge if currentAnomaly exists
```

### Step 12: SSE Integration

**File:** `web/src/hooks/useDeviceEvents.ts`

Handle `anomaly_detected` SSE event:
```typescript
case 'anomaly_detected':
  queryClient.invalidateQueries({ queryKey: ['anomalies'] });
  break;
```

---

## Database Changes

**No migration required.** Anomaly state lives in memory (AnomalyDetector class). Baselines computed from existing `poll_history` and `check_results` tables.

**Trade-off:** Anomalies lost on restart. Acceptable for prototype. Future: persist to `anomaly_events` table.

---

## Algorithm Details

### Z-Score Calculation
```
z = (x - μ) / σ

where:
  x = current value
  μ = rolling average (last 100 samples)
  σ = rolling standard deviation

Anomaly if |z| > 3.0 (3-sigma)
```

### Minimum Samples
- Need ≥20 samples before computing baseline
- Below 20: return "not enough data" (no anomaly detection)
- At 100 samples: window is full, oldest values drop off

### Edge Cases
- **Constant metric** (std = 0): Skip anomaly check (no variation to detect)
- **Zero average**: Use absolute difference instead of percentage magnitude
- **Sudden permanent change**: After 100 new samples at new level, baseline adapts

### Performance
- O(1) per value insertion (deque append)
- O(window_size) per z-score computation (iterating 100 values)
- Total: ~100 operations per poll → negligible overhead

---

## Testing

### Unit Tests
```python
# tests/test_anomaly_detector.py
def test_no_anomaly_within_normal_range():
    """Values within 2σ don't trigger anomaly."""

def test_anomaly_detected_at_3_sigma():
    """Value > 3σ from mean triggers anomaly."""

def test_minimum_samples_required():
    """No anomaly detection with < 20 samples."""

def test_constant_metric_no_anomaly():
    """All-same values (std=0) don't trigger."""

def test_anomaly_clears_on_recovery():
    """Anomaly removed when value returns to normal."""

def test_baseline_computation():
    """Baseline avg/std computed correctly."""
```

### Manual Testing
1. Start backend with 5+ devices
2. Wait 20+ poll cycles (~10 min at 30s interval)
3. Simulate response time spike (modify device to return slow responses)
4. Dashboard shows anomaly badge
5. Device detail shows baseline line on chart
6. Anomaly clears when response time normalizes

---

## Estimated Effort

| Task | Hours |
|------|-------|
| `AnomalyDetector` class | 3h |
| Integrate with poller | 2h |
| Integrate with check scheduler | 1h |
| Backend API endpoints (3) | 2h |
| Wire in lifespan | 0.5h |
| Unit tests | 3h |
| Frontend: API methods + types | 1h |
| Frontend: `useAnomalies` hook | 1h |
| Frontend: `AnomalyBadge` component | 2h |
| Frontend: Dashboard integration | 2h |
| Frontend: DeviceDetail integration | 2h |
| Frontend: SSE event handling | 1h |
| Polish + edge cases | 2h |
| **Total** | **22.5h** |

---

## Future Enhancements

1. **Persistent anomalies** — Store in `anomaly_events` table for historical view
2. **Anomaly-based alerts** — Wire anomaly detection into alert_service (trigger alert rule on anomaly)
3. **Seasonal baselines** — Time-of-day aware baselines (e.g., high traffic at 9am is normal)
4. **Multi-metric correlation** — Detect when multiple devices spike simultaneously (network-wide event)
5. **Configurable sensitivity** — Let users set z_threshold per device (1.5σ for critical devices, 4σ for noisy ones)
6. **Anomaly history page** — Timeline of all past anomalies with drill-down

---

## Notes

- **In-memory only** — anomalies lost on restart. Acceptable for prototype.
- **3-sigma is conservative** — low false positive rate, may miss subtle anomalies
- **No ML required** — pure statistics, no TensorFlow/PyTorch dependency
- **Works for any numeric metric** — response time, bandwidth, error rate, etc.
- **Demo tip:** Pre-seed with simulated data to show anomaly immediately (don't wait 10 min for 20 samples)
