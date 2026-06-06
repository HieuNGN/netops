# NetOps — Agent Guide

Auto-read on every session. Project facts only — keep it lean.

---

## Project

Network topology discovery + service monitoring. FastAPI backend, React/TypeScript SPA. Built for datacenter and homelab environments.

SNMPv2c/v3 device discovery, LLDP topology mapping, real-time SSE dashboard, multi-channel alerting, periodic service checks (HTTP/TCP/DNS/Ping/SSL), Postgres with SQLite dev fallback.

---

## Layout

```
netops/
├── src/
│   ├── collector/                # FastAPI app + SNMP engine (entry: main.py)
│   │   ├── main.py               # routes, Pydantic models, lifespan, SSE
│   │   ├── snmp_poller.py        # periodic polling orchestrator
│   │   ├── spike_snmp.py         # low-level pysnmp queries + CLI
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
└── docs/                         # plans, specs, guides
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
| Storage | `src/storage/database.py` (PG) / `sqlite_client.py` (SQLite) | Alembic migrations live in `storage/migrations/` |
| Frontend | `web/src/` | API base = relative `/api` in prod (nginx proxy) |

### Boundaries

- **Collector** never imports FastAPI models. Return plain dicts.
- **Checks** are stateless. Config in, `CheckResult` out.
- **API** does all DB access through `src/storage/`. No raw SQL in route handlers.
- **Notifications** are fire-and-forget background tasks.
- **Storage** migrations must be reversible — test `upgrade` + `downgrade`.

---

## Key Patterns

- **Config**: `SNMPConfig` / `ServerConfig` dataclasses from `collector/config.py`. No global state.
- **DB bootstrap**: `main.py:50-90` tries PostgreSQL, falls back to SQLite. Auth and SNMP settings also read from DB (`db.get_settings()`) with env-var defaults.
- **Poller pattern**: `SNMPPoller` + `CheckScheduler` started in `lifespan`, both expose `start()/stop()`. Topology change handler fans out via `asyncio.gather` to SSE subscriber queues.
- **SSE streams**: `/topology/stream` (delta topology), `/events/stream` (device events), `/poll-history/stream`. Subscriber queues live in module-level lists; drop on disconnect.
- **Async SNMP**: pysnmp is sync. Wrap calls in `asyncio.to_thread` to avoid blocking the event loop.
- **Error handling**: `SNMPTimeoutError` on poll timeouts. API returns 503 with retry headers.
- **Auth**: JWT in cookie + `Authorization: Bearer`. `JWT_SECRET` env required, fail-fast — no fallback.
- **Frontend API URL**: relative `/api` in production (nginx proxies). Direct backend URL in dev.
- **Startup auto-discover**: `main.py:115-188` wipes stale mock devices, registers host, rescans detected CIDR via `rescan_and_replace`.

---

## Commands

```bash
# Backend (dev)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.collector.main:app --reload --host 127.0.0.1 --port 8000
# or
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
