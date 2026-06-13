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
- **Database** — async PostgreSQL with connection pooling; SQLite fallback for dev
- **Docker** — production-ready multi-container deployment (backend, frontend, nginx)

---

## Quick Start

### Prerequisites

- Docker + Docker Compose

### Run

```bash
cd docker
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:80 |
| API docs | http://localhost:8000/docs |

Default admin: `admin` / `admin`. Rotate before exposing.

Dev setup (venv + Vite) → [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

## Documentation

- [API Reference](docs/API_REFERENCE.md) — endpoints, types, channels
- [Deployment](docs/DEPLOYMENT.md) — production setup

---

## Project Structure

```
netops/
├── src/
│   ├── collector/            # FastAPI app + SNMP engine
│   │   ├── main.py           # API routes, models, lifespan
│   │   ├── snmp_poller.py    # periodic polling orchestrator
│   │   ├── spike_snmp.py     # low-level SNMP queries (snmpwalk/get)
│   │   ├── topology_builder.py # LLDP → node/link graph
│   │   ├── discovery.py      # subnet scanner (ICMP + SNMP)
│   │   ├── config.py         # server configuration
│   │   ├── utils.py          # logging
│   │   └── checks/           # service check engine
│   │       ├── base.py       # abstract check + result classes
│   │       ├── http_check.py
│   │       ├── tcp_check.py
│   │       ├── dns_check.py
│   │       ├── ping_check.py
│   │       ├── ssl_check.py
│   │       └── scheduler.py  # single-tick check loop
│   ├── storage/
│   │   ├── database.py       # async PostgreSQL client
│   │   ├── sqlite_client.py  # async SQLite fallback
│   │   ├── alembic.ini       # migration config
│   │   └── migrations/       # Alembic revisions
│   └── api/services/
│       ├── alert_service.py  # alert eval, dedup, state machine
│       └── notifications/    # channel implementations
│           ├── base.py
│           ├── slack.py
│           ├── telegram.py
│           ├── whatsapp.py
│           ├── email.py
│           └── webhook.py
├── web/                      # React + TypeScript frontend
│   ├── src/
│   │   ├── pages/            # Dashboard, Topology, Devices, Checks, Alerts, Settings
│   │   ├── components/       # NetworksConsole, NetworkPicker, InlineEditableField, TagChips, etc.
│   │   ├── hooks/            # React Query hooks (useNetworks, useDevices, useTopology, etc.)
│   │   ├── api/              # axios client + typed endpoints
│   │   └── layouts/          # sidebar nav + shell
│   ├── package.json
│   └── vite.config.ts
├── tests/                    # pytest unit + integration tests
├── docker/                   # production compose + nginx
├── scripts/                  # dev helpers (test.sh, migrate.py, simulate_devices.py)
└── docs/                     # plans, specs, guides
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
| Docker | Building | multi-container compose, nginx, health checks |
| Auth & RBAC | Done | JWT login, protected routes, admin bootstrap |
| Dynamic config | Done | settings → DB → poller read on startup |
| SNMPv3 | Done | UsmUserData, auth/priv protocols, per-device version |
| Bulk device import | Done | CSV/JSON upload + paste, parse + POST /devices/import |
| Environment profiles | Done | homelab / small_business / datacenter with auto-detection |
| Per-type check intervals | Done | HTTP/TCP/DNS/Ping/SSL with profile-driven defaults |
| SNMP trap listener | Done | UDP trap receiver, linkUp/linkDown events, SSE broadcast |
| Cookie-only auth | Done | HttpOnly + SameSite=Strict + Secure cookies |
| Distributed agents | Planned | remote pollers, central aggregator |

---

## CLI

```bash
# Single-device SNMP query
python src/collector/spike_snmp.py <host> [-c community] [--action sysdescr|lldp|all]

# Simulate topology (offline demo)
curl -X POST http://localhost:8000/topology/simulate
```

---
