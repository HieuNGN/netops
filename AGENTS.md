# NetOps — Agent Guide

Auto-read on every session. Project facts only — keep it lean.

---

## Project

Network topology discovery + service monitoring. FastAPI backend, React/TypeScript SPA. Built for datacenter and homelab environments.

SNMPv2c/v3 device discovery, LLDP topology mapping, real-time SSE dashboard, multi-channel alerting, periodic service checks (HTTP/TCP/DNS/Ping/SSL), PostgreSQL DB.

---

## Layout

```
netops/
├── src/
│   ├── collector/                # FastAPI app + SNMP engine (entry: main.py)
│   │   ├── main.py               # routes, Pydantic models, lifespan, SSE
│   │   ├── snmp_poller.py        # periodic polling orchestrator
│   │   ├── spike_snmp.py         # low-level pysnmp queries + CLI
│   │   ├── host_state.py         # host network fingerprint + persistence
│   │   ├── network_watcher.py    # periodic (cidr, gateway) change detector
│   │   ├── topology_builder.py   # LLDP → node/link graph
│   │   ├── discovery.py          # subnet scanner (ICMP + SNMP)
│   │   ├── host_detect.py        # auto-detect host IP/CIDR/gateway
│   │   ├── config.py             # SNMPConfig / ServerConfig dataclasses
│   │   ├── utils.py              # logger
│   │   └── checks/               # service check engine
│   │       ├── base.py
│   │       ├── http_check.py
│   │       ├── tcp_check.py
│   │       ├── dns_check.py
│   │       ├── ping_check.py
│   │       ├── ssl_check.py
│   │       └── scheduler.py      # single-tick check loop
│   ├── storage/
│   │   ├── database.py           # async PostgreSQL (asyncpg + SQLAlchemy)
│   │   ├── sqlite_client.py      # async SQLite (aiosqlite) fallback
│   │   ├── alembic.ini
│   │   └── migrations/           # Alembic revisions
│   └── api/services/             # cross-cutting services
│       ├── auth.py               # JWT + PBKDF2 password hashing
│       ├── alert_service.py      # rule eval, dedup, state machine
│       └── notifications/        # channel impls
│           ├── base.py
│           ├── slack.py
│           ├── telegram.py
│           ├── whatsapp.py
│           ├── email.py
│           └── webhook.py
├── web/                          # React 19 + TypeScript + Vite SPA
│   ├── src/
│   │   ├── pages/                # Dashboard, Topology, Devices, Checks, Alerts, Settings, TopologyHistory, LoginPage
│   │   ├── components/           # NetworksConsole, NetworkPicker, TopologyDiff, ui/, layout/
│   │   ├── hooks/                # React Query hooks (useTopology, useDevices, useNetworks, useAuth, ...)
│   │   └── api/                  # axios client + typed endpoints
│   ├── vitest unit + playwright e2e
├── tests/                        # pytest + pytest-asyncio
├── docker/                       # compose, Dockerfiles, nginx
├── scripts/                      # dev helpers (test.sh, migrate.py, simulate_devices.py, autofix.sh, run_backend.sh)
├── docs/                         # current docs (DEPLOYMENT.md, SNMP_TRAP_SETUP.md)
└── docs_archive_2025/             # archived legacy plans (superseded — see README.md)
```

---

## Layer Map

| Concern | Where | Notes |
|---|---|---|
| SNMP walks, LLDP parse | `src/collector/{spike_snmp,snmp_poller,discovery}.py` | pysnmp is sync → wrap in `asyncio.to_thread` |
| Topology graph | `src/collector/topology_builder.py` | NetworkX, delta detection |
| Service checks | `src/collector/checks/*.py` + `scheduler.py` | stateless, `CheckResult` out |
| API | `src/collector/main.py` | all DB access through `src/storage/` |
| Auth | `src/api/services/auth.py` | JWT cookie + Bearer |
| Alerts | `src/api/services/alert_service.py` + `notifications/` | fire-and-forget background; never block API |
| Storage | `src/storage/database.py` (PostgreSQL) | Alembic migrations live in `storage/migrations/` |
| Frontend | `web/src/` | API base = relative `/api` in prod (nginx proxy) |

### Boundaries

- **Collector** never imports FastAPI models. Return plain dicts.
- **Checks** are stateless. Config in, `CheckResult` out.
- **API** does all DB access through `src/storage/`. No raw SQL in route handlers.
- **Notifications** are fire-and-forget background tasks.
- **Storage** migrations must be reversible — test `upgrade` + `downgrade`.

---

## Key Patterns

- **Config**: `SNMPConfig` / `ServerConfig` / `NetOpsConfig` dataclasses from `collector/config.py`. No global state.
- **DB bootstrap**: `main.py:87-120` connects to PostgreSQL (via `DATABASE_URL` or `POSTGRES_*` defaults). Auth and SNMP settings also read from DB (`db.get_settings()`) with env-var defaults.
- **Poller pattern**: `SNMPPoller` + `CheckScheduler` + `SNMPTrapListener` started in `lifespan`. Trap listener exposes `configure()/start()/stop()`; PUT `/api/config/traps` restarts it.
- **SSE streams**: `/topology/stream` (delta topology), `/events/stream` (device events + `trap_received`), `/poll-history/stream`. Subscriber queues live in module-level lists; drop on disconnect.
- **Async SNMP**: pysnmp is sync. Wrap calls in `asyncio.to_thread` to avoid blocking the event loop. Trap listener uses raw asyncio UDP + custom BER parser.
- **Error handling**: spike_snmp raises `SNMPRequestError` on poll timeouts / auth errors / parse errors. Poller's `_poll_device` catches it, sets `status='offline'` + `offline_since=now`, records the error in `poll_history`, and emits a `device_offline` SSE via `set_status_change_handler`. API returns 503 with retry headers. Trap listener drops malformed/mismatched-community packets silently.
- **Auth**: JWT in cookie + `Authorization: Bearer`. `JWT_SECRET` env required, fail-fast — no fallback.
- **Frontend API URL**: relative `/api` in production (nginx proxies). Direct backend URL in dev.
- **Environment profile**: `homelab` / `small_business` / `datacenter`. `detect_profile(n)` guesses on first boot (sets `is_guessed=true` until user confirms via `PUT /api/config/profile`). Poller + scheduler + retention loops re-read settings each tick — live update, no restart.
- **Merge discovery**: `POST /api/discover/rescan { mode: "merge" }` (default) preserves manual devices, marks missing as `offline`, emits `device_stale` SSE at >72h. `mode: "replace"` keeps legacy wipe behavior. Stale devices get a "Remove or Keep" modal in the FE.
- **New-network onboarding**: `_startup_auto_discover` reads `host_cidr`/`host_fingerprint` from `app_settings`; skips when fingerprint matches. On change/first boot, runs `rescan_and_merge` (default; `NETOPS_AUTO_DISCOVER_MODE=replace` for legacy wipe), registers a `networks` row for the new CIDR, persists the new fingerprint, and emits `profile_guessed` SSE **after** the scan. `NetworkWatcher` re-runs the same check at runtime (`NETOPS_NETWORK_CHECK_INTERVAL`, default 60s). `PUT /api/config/profile {confirmado: true}` sets `profile_confirmed=true` so the FE `is_guessed` flag clears; `confirmado: false` is a preview-only update of `profile_guess`.
- **Device status SSE**: `SNMPPoller` tracks `last_status[device_id]` and emits `device_online` / `device_offline` SSE on transitions via `set_status_change_handler` (wired in `lifespan`). FE `useDeviceEvents` invalidates `['devices']` + `['topology']` on these events.
- **Per-type check intervals**: `ServiceCheckCreate.interval_seconds` auto-populates from profile defaults via Pydantic `field_validator(mode="before")`. `GET /api/checks/defaults` returns the live matrix.
- **Startup auto-discover**: `main.py:290-504` detects host CIDR, compares fingerprint, skips on match or runs `rescan_and_merge` (default) / `rescan_and_replace` (env `NETOPS_AUTO_DISCOVER_MODE`). Registers `networks` row, persists host fingerprint, emits `profile_guessed` SSE after scan.

---

## Startup & Testing Checklist

Every dev session and every code-review gate MUST verify. Run in order:

```bash
# 1. PostgreSQL (required — no automatic SQLite fallback)
/usr/bin/pg_ctl -D data/pgdata -l data/pgdata/logfile start
# OR: ./scripts/run_backend.sh  (auto-starts PG + migrates + uvicorn)

# 2. Verify PG is reachable
psql -h $(pwd)/data/pgdata -U netops -d netops -c "SELECT 1"

# 3. Backend startup smoke
JWT_SECRET=dev uvicorn src.collector.main:app --host 127.0.0.1 --port 8000 &
sleep 4
# Must return status=ready, startup_complete=true, db_connected=true
curl -s http://127.0.0.1:8000/api/health/ready | python -m json.tool
# Must return postgresql (NOT sqlite)
curl -s http://127.0.0.1:8000/api/health/db | python -m json.tool
# Must show watcher.running=true, check_count>=1
curl -s http://127.0.0.1:8000/health | python -m json.tool | grep watcher

# 4. Auth smoke (cookie-based JWT)
curl -sv -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' 2>&1 | grep -i 'set-cookie'
# Must see: Set-Cookie: token=...; HttpOnly; Path=/; SameSite=lax

# 5. Full backend test suite
pytest tests/ -v --ignore=tests/test_api.py \
  --ignore='tests/test_alert_integrations_storage.py'

# 6. Frontend
cd web && npm run build        # tsc + vite — must exit 0
cd web && npm run dev &        # starts HTTPS on :3000
sleep 3
curl -sk https://localhost:3000/api/health/ready | python -m json.tool
```

**Foolproofing rules:**

- Cookie `secure` flag: `NETOPS_COOKIE_SECURE=1` for HTTPS prod, `0` for HTTP local dev.
- FE `apiClient` timeout is 30s. Do NOT reduce below 15s — startup scan can take time.
- `/api/health/ready` returns 503 until lifespan completes. FE should NOT gate on this; it's for operators.
- After any migration change: run both `alembic upgrade head` AND `alembic downgrade -1` to verify reversibility.
- Test login on EVERY session: cookie-based auth is the most fragile link.

```bash
# Backend (dev)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Ensure PostgreSQL is running (see step 1)
./scripts/run_backend.sh

# Frontend
cd web && npm install && npm run dev          # http://localhost:3000

# Backend tests
pytest tests/ -v
pytest tests/ -k "check or discovery"

# Frontend tests
cd web && npm run test:unit                    # vitest
cd web && npm run test:e2e                     # playwright

# Lint / typecheck
cd web && npm run lint
cd web && npm run build                        # tsc -b && vite build

# DB
alembic -c src/storage/alembic.ini upgrade head
alembic -c src/storage/alembic.ini revision --autogenerate -m "describe_change"

# Docker
docker compose -f docker/docker-compose.yml up --build
```

---

## Adding Things

**New check** → `src/collector/checks/<name>_check.py`, inherit `BaseCheck`, register in `checks/__init__.py`, add test in `tests/test_<name>_check.py` (or `tests/checks/`).

**New notification channel** → `src/api/services/notifications/<name>.py`, inherit `NotificationChannel`, register in `alert_service.py` factory, add config fields to `AlertConfigCreate` in `main.py`.

**New DB migration** → modify model in `src/storage/database.py` or `sqlite_client.py`, `alembic revision --autogenerate`, review generated migration, ensure `downgrade()` is correct.

**New API route** → add to `src/collector/main.py` (all routes live there). Use Pydantic models at the top of the file. SSE endpoints return `StreamingResponse` with an async generator.

**New React page** → `web/src/pages/<Name>.tsx`, register in `web/src/App.tsx` router, add typed endpoint in `web/src/api/endpoints.ts`, add React Query hook in `web/src/hooks/`.

---

## Reviewer Subagent

`.opencode/agents/senior-code-reviewer.md` is available. Spawn via Task tool as the final quality gate after non-trivial code changes (new features, auth, refactors, bug fixes touching shared state). It has elevated permissions and will fix issues directly.

---

## Communication Style

**Caveman mode — always on.** Ultra-compressed, terse, direct. Drop filler, articles, hedging. Keep technical substance exact.

```
Not: "Sure! I'd be happy to help you with that. The issue you're experiencing..."
Yes:  "Bug in auth middleware. Token expiry use `<` not `<=`. Fix:"
```

- Fragments OK. Short synonyms (fix not "implement a solution for"). Code unchanged.
- Drop caveman only for: security warnings, irreversible actions, multi-step sequences where order ambiguity risks misread, user asks to clarify.
- Resume caveman after clear part done.
- `/caveman lite|full|ultra` to adjust intensity. `stop caveman` or `normal mode` to disable.

## Skills Reference

| Skill | Path | Use for |
|---|---|---|
| `caveman` | `.agents/skills/caveman/SKILL.md` | **Default comm style.** Terse, compressed, always active. |
| `network-interface-health` | `.agents/skills/network-interface-health/SKILL.md` | Available, on-demand. Not wired into current checks (HTTP/TCP/DNS/Ping/SSL only). Load when adding SNMP interface-counter checks or debugging physical-link issues. |
| `docker-expert` | `.agents/skills/docker-expert/SKILL.md` | Dockerfile, compose, multi-stage, security hardening. Matches `docker/` layer. |
| `vercel-react-best-practices` | `.agents/skills/vercel-react-best-practices/SKILL.md` | React/Next.js perf, bundle, waterfalls. Use on `web/` reviews. |
| `frontend-design` | `.agents/skills/frontend-design/SKILL.md` | Distinctive UI/UX, aesthetic direction. New dashboards or page builds. |
| `python-performance-optimization` | `.agents/skills/python-performance-optimization/SKILL.md` | Profile Python bottlenecks. Relevant for poller / scheduler tuning. |
| `ai-sdk` | `.agents/skills/ai-sdk/SKILL.md` | Load when AI features added. |
| `strategic-compact` | `.agents/skills/strategic-compact/SKILL.md` | Manual `/compact` at logical boundaries. Use before/after major phases, not mid-implementation. |

Load via `skill` tool or read the `SKILL.md` directly. Pick the most specific match; project skills outrank generic troubleshooting for domain tasks.

---

## Security Posture

- SNMP community strings + SNMPv3 keys in `.env` only. Never commit. `.env.example` for template.
- SSL check validates cert chains — never disable verification.
- Notification credentials (Twilio, SMTP, Telegram bot token) are env vars. Validate in `config.py`.
- SQLite path is relative (`data/netops.db`). Ensure directory exists on startup.
- Never bind to `0.0.0.0` in production without a reverse proxy (nginx in `docker/`).
- Default admin bootstrap (`admin/admin`) is auto-created on first run. Force password change or disable before exposing.

---

## Troubleshooting

- `ModuleNotFoundError` → check venv activated (`source .venv/bin/activate`) and `pip install -r requirements.txt`.
- SNMP timeouts → check `SNMP_TIMEOUT` env (default 5s); tune `SNMP_RETRIES` (default 3). Verify target reachable.
- DB locked / async deadlock on SQLite → use `db_client` session wrapper, don't open parallel connections.
- WebSocket / SSE disconnect → topology stream auto-reconnects client-side; server drops queues on disconnect.
- Frontend can't reach backend in dev → set `VITE_API_URL` or rely on Vite proxy in `vite.config.ts`.
- Stale mock devices on startup → `_startup_auto_discover` in `main.py:115-188` wipes `simulated` discovery_method + known mock names; check logs for `Auto-removed N stale mock devices`.
