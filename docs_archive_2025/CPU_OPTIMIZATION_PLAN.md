# NetOps CPU Optimization Plan

Date: 2026-05-10
Scope: Cut poller + discovery + scheduler CPU usage (currently 30-40% via htop)
Status: **IMPLEMENTED**

---

## Fixes Applied

| # | Fix | File | Impact |
|---|---|---|---|
| 1 | Discovery batching (20 hosts per chunk + yield) | `discovery.py` | Smooths CPU spike during scan |
| 2 | SNMP semaphore(5) + TopologyBuilder reuse + skip empty changes | `snmp_poller.py`, `topology_builder.py` | Caps concurrent polls, saves object init |
| 3 | SSE emit only when topology changes exist | `main.py` | Skips idle JSON serialization |
| 4 | Single tick loop scheduler + check semaphore(10) + jitter | `checks/scheduler.py` | One task loop instead of N per-check tasks |

---

## Test Results

```
============================= 105 passed in 44.98s =============================
```

---

## Expected Impact

| Fix | CPU Reduction |
|---|---|
| Discovery batching | -10-15% during scan |
| SNMP semaphore | -10-15% steady state |
| Skip empty SSE | -5-8% steady state |
| Reuse TopologyBuilder | -2-3% steady state |
| Single tick scheduler | -5-10% steady state |
| **Combined** | **~30-40% total** |

---

*Implemented by OpenCode. Verify with htop after restart.*
