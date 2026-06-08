# NetOps Feature Enhancement Plan

## Executive Summary

This plan addresses 5 critical feature gaps identified through competitive analysis of PRTG, SolarWinds NPM, and Datadog Network Monitoring. These features will elevate NetOps from a functional prototype to a presentable, production-ready network monitoring platform.

**Target completion:** 2-3 weeks  
**Priority:** Must-have for academic presentation  
**Total estimated effort:** 80-120 hours

---

## Feature Overview

| # | Feature | Impact | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Device Detail Page with Poll History Chart | **Critical** — Core UX gap | 16-24h | P0 |
| 2 | Topology Filtering (network/status/type) | **High** — Demo polish | 6-8h | P0 |
| 3 | CSV Export for Devices | **Medium** — Practical utility | 4-6h | P1 |
| 4 | Alert Severity Escalation | **High** — Enterprise feature | 12-16h | P0 |
| 5 | Basic Anomaly Detection | **High** — "Wow factor" | 20-28h | P1 |

---

## Implementation Order

**Phase 1 (Week 1): Quick wins + core UX**
1. Topology Filtering (6h) — Immediate visual improvement
2. CSV Export (4h) — Simple, high perceived value
3. Device Detail Page (16h) — Biggest UX gap

**Phase 2 (Week 2): Intelligence features**
4. Alert Severity Escalation (14h) — Backend-heavy
5. Anomaly Detection (24h) — Most complex, highest impact

---

## Cross-Cutting Concerns

### Database Migrations
- **Migration 022:** Add `escalation_minutes`, `escalated_severity` to `alert_configs`
- **Migration 023:** Add `anomaly_baselines` table for metric tracking
- Both migrations must be reversible (upgrade + downgrade tested)

### API Versioning
- No breaking changes to existing endpoints
- New endpoints follow existing patterns: `/api/devices/{id}/history`, `/api/anomalies`
- All new endpoints require auth (`Depends(need_auth)`)

### Frontend Architecture
- New page: `DeviceDetail.tsx` (route: `/devices/:id`)
- New components: `PollHistoryChart`, `AnomalyBadge`, `EscalationConfig`
- Reuse existing Recharts patterns from Dashboard
- Follow existing Tailwind CSS + IBM Plex design system

### Testing Strategy
- Backend: pytest for all new endpoints and services
- Frontend: vitest for components, playwright for device detail flow
- Manual testing: demo workflow (discover → alert → drill-down → export)

---

## Success Criteria

### For Presentation
✅ Can click any device and see poll history chart  
✅ Can filter topology by network/status/type  
✅ Can export device list to CSV  
✅ Alert escalates from warning → critical after timeout  
✅ Dashboard shows "Anomaly Detected" badge when metrics spike  

### For Code Quality
✅ All new code passes `npm run lint` and `npm run build`  
✅ All new endpoints have pytest coverage  
✅ Database migrations are reversible  
✅ No TypeScript `any` types in new code (except API responses)  
✅ Responsive design works on 1280px+ screens  

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Poll history data sparse for charts | Show "Not enough data" state; backfill with simulated data for demo |
| Anomaly detection false positives | Use conservative 3-sigma threshold; show confidence % |
| Topology filtering breaks SSE stream | Filter client-side only; don't modify backend stream |
| Alert escalation breaks existing rules | Make escalation opt-in; default `escalation_minutes = null` |
| Device detail page performance with 1000+ history rows | Paginate API; show last 100 by default; add time range filter |

---

## Dependencies

- **Recharts:** Already installed (used in Dashboard)
- **react-router-dom:** Already installed (v6)
- **date-fns:** Already installed (for time formatting)
- **No new npm packages required** for features 1-4
- **Feature 5 (Anomaly):** May add `simple-statistics` for stddev calculations (2KB gzipped)

---

## File Structure Changes

```
NEW FILES:
├── web/src/pages/DeviceDetail.tsx
├── web/src/components/PollHistoryChart.tsx
├── web/src/components/AnomalyBadge.tsx
├── web/src/components/EscalationConfig.tsx
├── web/src/hooks/useDeviceDetail.ts
├── web/src/hooks/useAnomalies.ts
├── src/storage/migrations/versions/022_alert_escalation.py
├── src/storage/migrations/versions/023_anomaly_baselines.py
├── src/api/services/anomaly_detector.py
└── plan/
    ├── 01_device_detail_page.md
    ├── 02_topology_filtering.md
    ├── 03_csv_export.md
    ├── 04_alert_escalation.md
    └── 05_anomaly_detection.md

MODIFIED FILES:
├── web/src/App.tsx (add DeviceDetail route)
├── web/src/pages/Devices.tsx (add click-to-detail, export button)
├── web/src/pages/Topology.tsx (add filter dropdowns)
├── web/src/pages/Alerts.tsx (add escalation config UI)
├── web/src/pages/Dashboard.tsx (add anomaly badge)
├── web/src/api/endpoints.ts (add new API methods)
├── src/collector/main.py (add new endpoints)
├── src/storage/database.py (add new query methods)
├── src/storage/sqlite_client.py (mirror PG methods)
└── src/api/services/alert_service.py (add escalation logic)
```

---

## Demo Workflow (Post-Implementation)

1. **Auto-discover network** → Topology map appears
2. **Apply topology filter** → Show only "offline" devices
3. **Click device** → Navigate to DeviceDetail page
4. **View poll history chart** → See response time spike
5. **Check anomaly badge** → "Response time 3.2x above baseline"
6. **Add alert rule** → Configure escalation: warning → critical after 5min
7. **Trigger failure** → Alert fires as warning
8. **Wait 5 minutes** → Alert escalates to critical (Slack notification)
9. **Export device list** → Download CSV with all device data
10. **Show professor** → "This is what enterprise tools cost $10k/year for"

---

## Notes for Implementation

- **Start with topology filtering** — easiest win, immediate visual impact
- **Device detail page is the centerpiece** — spend time on UX polish
- **Anomaly detection can be simple** — rolling average + stddev is enough
- **Don't over-engineer** — this is a prototype, not production SaaS
- **Test on every commit** — `npm run build` + `pytest tests/` before pushing

---

## References

- PRTG sensor library: https://www.paessler.com/prtg/features/sensors
- SolarWinds NetPath: https://www.solarwinds.com/network-performance-monitorer/use-cases/netpath
- Datadog anomaly detection: https://docs.datadoghq.com/monitors/types/anomaly/
- Recharts documentation: https://recharts.org/en-US/api
- FastAPI best practices: https://fastapi.tiangolo.com/tutorial/
