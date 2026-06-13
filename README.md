# NetOps

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.5-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue.svg)](https://typescriptlang.org)
Network topology discovery, real-time monitoring, and management console — built for datacenter and homelab environments.

---

## Features

- **SNMPv2c & v3 Discovery** — scan subnets, auto-detect devices via ICMP + community strings
- **LLDP Topology Mapping** — build interactive force-graphs from LLDP neighbor data
- **Real-time Dashboard** — live SSE streaming, status distribution charts, uptime bars, poll history
- **Network Management Console** — slide-out drawer for renaming, typing (11 types), tagging, per-network device counts
- **Service Checks** — HTTP, TCP, DNS, Ping, SSL cert expiry monitoring with configurable intervals
- **Multi-Channel Alerts** — Slack, Telegram, WhatsApp, Email, Webhook with deduplication and maintenance windows
- **Database** — async PostgreSQL with connection pooling
- **Docker** — production-ready multi-container deployment (backend, frontend, nginx)

---

## Quick Start

Requires **Docker + Docker Compose**.

```bash
# Clone and enter the project
git clone https://github.com/HieuNGN/netops.git
cd netops

# Copy env template (edit is optional)
cp docker/.env.example docker/.env

# Build and start everything
./docker/build.sh dev
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost |
| API docs | http://localhost:8000/docs |
| Prometheus metrics | http://localhost:8000/metrics |

Default admin: `admin` / `admin`. Account creation is optional

### Fast start script (super handy)

`docker/build.sh` wraps compose for the usual workflow:

```bash
./docker/build.sh dev     # dev build with live-reload overrides
./docker/build.sh prod    # production build
./docker/build.sh logs    # tail all service logs
./docker/build.sh stop    # stop containers
./docker/build.sh clean   # stop and remove containers + volumes
```

---

## Documentation

- [docker/README.md](docker/README.md) — Docker build, dev/prod modes, env reference
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — detailed deployment guide
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) — endpoints, types, channels

---

## Project Structure

```
netops/
├── src/
│   ├── collector/                # FastAPI app + SNMP engine
│   │   ├── main.py               # API routes, Pydantic models, lifespan, SSE
│   │   ├── snmp_poller.py        # periodic SNMP polling orchestrator
│   │   ├── snmp_trap_listener.py # UDP trap receiver + SSE broadcast
│   │   ├── spike_snmp.py         # low-level SNMP queries (snmpwalk/get)
│   │   ├── topology_builder.py   # LLDP → node/link graph
│   │   ├── discovery.py          # subnet scanner (ICMP + SNMP)
│   │   ├── host_detect.py        # auto-detect host IP/CIDR/gateway
│   │   ├── host_state.py         # host network fingerprint
│   │   ├── network_watcher.py    # runtime network-change detector
│   │   ├── config.py             # server configuration
│   │   ├── utils.py              # logging
│   │   └── checks/               # service check engine
│   │       ├── base.py
│   │       ├── http_check.py
│   │       ├── tcp_check.py
│   │       ├── dns_check.py
│   │       ├── ping_check.py
│   │       ├── ssl_check.py
│   │       └── scheduler.py      # single-tick check loop
│   ├── storage/
│   │   ├── database.py           # async PostgreSQL client
│   │   ├── sqlite_client.py      # async SQLite fallback
│   │   ├── alembic.ini           # migration config
│   │   └── migrations/           # Alembic revisions
│   └── api/services/
│       ├── alert_service.py      # alert eval, dedup, state machine
│       ├── anomaly_detector.py   # Z-score based anomaly detection
│       ├── auth.py               # JWT + PBKDF2 password hashing
│       ├── encryption.py         # Fernet at-rest encryption
│       └── notifications/        # channel implementations
│           ├── base.py
│           ├── slack.py
│           ├── telegram.py
│           ├── whatsapp.py
│           ├── email.py
│           └── webhook.py
├── web/                          # React 19 + TypeScript + Vite SPA
│   ├── src/
│   │   ├── pages/                # Dashboard, Topology, Devices, Checks, Alerts, Settings, ...
│   │   ├── components/           # NetworksConsole, NetworkPicker, TopologyDiff, ui/, layout/
│   │   ├── hooks/                # React Query hooks (useTopology, useDevices, useAuth, ...)
│   │   ├── api/                  # axios client + typed endpoints
│   │   ├── lib/                  # shared helpers (e.g. integrations)
│   │   └── test/                 # test setup
│   ├── tests/e2e/                # Playwright end-to-end tests
│   ├── package.json
│   ├── vite.config.ts
│   └── playwright.config.ts
├── tests/                        # pytest + pytest-asyncio
├── docker/                       # compose, Dockerfiles, nginx, build script
│   ├── build.sh                  # quick docker build/start helper
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml
│   ├── docker-compose.prod.yml
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── nginx.conf
│   └── .env.example
├── scripts/                      # dev helpers (test.sh, migrate.py, simulate_devices.py, ...)
└── docs/                         # plans, specs, guides
```

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Core backend | Done | SNMP polling, API, persistence |
| Alerting | Done | Multi-channel notifications, dedup, state machine |
| PostgreSQL | Done | asyncpg, connection pooling, Alembic migrations |
| Service checks | Done | HTTP, TCP, DNS, Ping, SSL |
| React dashboard | Done | SSE streaming, charts, topology graph, full CRUD |
| CPU optimization | In Progress | batching, semaphores, single-tick scheduler |
| Network management | Done | slide-out drawer, 11 types, inline rename, tags, device counts |
| Poll history retention | Done | 30-day TTL, hourly cleanup loop |
| LLDP correlation | Done | multi-strategy matching (IP, name, substring) |
| Docker | Consolidated | multi-container compose, nginx, health checks |
| Auth & RBAC | Done | JWT login, protected routes, admin bootstrap |
| Dynamic config | Done | settings → DB → poller read on startup |
| SNMPv3 | Done | UsmUserData, auth/priv protocols, per-device version |
| Bulk device import | Done | CSV/JSON upload + paste, parse + POST /devices/import |
| Environment profiles | Done | homelab / small_business / datacenter with auto-detection |
| Per-type check intervals | Done | HTTP/TCP/DNS/Ping/SSL with profile-driven defaults |
| SNMP trap listener | Done | UDP trap receiver, linkUp/linkDown events, SSE broadcast |
| Cookie-only auth | Done | HttpOnly + SameSite=Strict + Secure cookies |
| Distributed agents | Planned | remote pollers, central aggregator |
