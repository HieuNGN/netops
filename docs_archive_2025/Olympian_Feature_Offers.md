# NetOps Olympian Feature Offers

Date: 2026-05-09
Status: Proposed — pending consideration

---

## Current Project Scan

- **Frontend:** 17 TSX files, 0 unit tests, 7 stray `console.*` logs
- **Styling:** 347 hardcoded `dark:` Tailwind classes — no centralized design system
- **Security:** No auth layer — root access via URL only
- **Persistence:** Settings save to `localStorage`; backend ignores user-defined intervals
- **Backend:** FastAPI + PostgreSQL + SNMP/LLDP polling engine
- **Testing:** 19 tests (notification channels only), Playwright present but unused
- **Real-time:** SSE stream for topology — no dedup, no backpressure

---

## Olympian Recommendations

| God | Domain | Proposed Fix | Why |
|---|---|---|---|
| Athena | Strategy | **Auth + RBAC** | Foundation. Unauthenticated access allows anyone to delete topology, trigger discovery, or modify alerts. |
| Hephaestus | Craft | **Design system + comprehensive tests** | 347 `dark:` classes are unmaintainable; zero unit tests make refactors fragile. |
| Hermes | Reach | **SNMPv3 + bulk device import** | Modern networks enforce v3. Single-device manual addition fails past ~50 nodes. |
| Apollo | Vision | **Topology visual diff + SSL expiry timeline** | History API exists but no visual diff view; SSL checks lack a dashboard timeline. |
| Zeus | Power | **SSE backpressure + health badge** | Stream floods under many clients; `/health` endpoint is invisible in the UI. |

---

## Top 3 Recommendations

1. **Auth Layer (Athena)**  
   Implement JWT cookie/session auth, a login page, and protected React routes. This is the highest-risk gap.

2. **Design System Consolidation (Hephaestus)**  
   Extract Carbon Design System tokens into CSS custom properties. Compress the 347 `dark:` overrides down to a small token set. Add `vitest` unit tests for logic-heavy hooks and utilities.

3. **Configuration Wire-Up (Zeus)**  
   Make Settings intervals (`topology_interval`, `check_interval`) dynamic. POST changes to backend; poller reads current values from DB/cache instead of hardcoded defaults.

---

## Notes
- Backend should validate settings writes to prevent invalid intervals.
- Consider exposing `/config` endpoint for frontend consumption to keep intervals in sync.
- Auth choice: start simple (API key or basic session cookie), evolve to OAuth/LDAP if needed.

---

*Saved by OpenCode for later consideration.*
