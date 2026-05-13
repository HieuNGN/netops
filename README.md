# NetOps

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.5-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue.svg)](https://typescriptlang.org)
[![Tests](https://img.shields.io/badge/tests-105%20passed-brightgreen.svg)](https://github.com)
Network topology discovery, real-time monitoring, and management console — built for datacenter and homelab environments.

---

## Features

- **SNMPv2c Discovery** — scan subnets, auto-detect devices via ICMP + community strings
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

- Python 3.11+, Node.js 20+, npm
- (Optional) PostgreSQL 15+ for production; SQLite used automatically otherwise

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.collector.main:app --host 0.0.0.0 --port 8000
```

API docs → http://localhost:8000/docs

### Frontend

```bash
cd web
npm install
npm run dev
```

Dashboard → http://localhost:3000

### Docker

```bash
cd docker
docker compose up -d --build
# Frontend → http://localhost:80
# API      → http://localhost:8000/docs
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with poller + alert stats |
| `GET` | `/metrics` | Prometheus metrics |
| **Topology** | | |
| `GET` | `/topology` | Current nodes & links |
| `GET` | `/topology/stream` | SSE stream for live updates |
| `POST` | `/topology/refresh` | Trigger immediate SNMP poll |
| `POST` | `/topology/simulate` | Generate demo network graph |
| `GET` | `/topology/history` | Topology change audit log |
| **Devices** | | |
| `GET` | `/devices` | List all devices |
| `POST` | `/devices` | Add device to monitor |
| `GET/PUT/DELETE` | `/devices/{id}` | CRUD operations |
| `POST` | `/devices/{dId}/network/{nId}` | Assign device to network |
| `POST` | `/discover` | Scan subnet for SNMP devices |
| **Networks** | | |
| `GET` | `/networks` | List networks with device counts |
| `GET/PUT/DELETE` | `/networks/{id}` | Manage network (name, type, tags, CIDR) |
| `POST` | `/networks` | Create network |
| `POST` | `/networks/{id}/default` | Set as default |
| **Service Checks** | | |
| `GET/POST` | `/checks` | List / create checks |
| `GET/PUT/DELETE` | `/checks/{id}` | CRUD operations |
| `POST` | `/checks/{id}/run` | Execute check immediately |
| `GET` | `/checks/{id}/results` | Check result history |
| `GET` | `/checks/stats` | Scheduler statistics |
| **Alerts** | | |
| `GET/POST` | `/alerts` | List / create alert configs |
| `GET` | `/alerts/history` | Recent alert activity |
| `GET` | `/alerts/active` | Currently firing alerts |
| `POST` | `/alerts/active/{k}/acknowledge` | Ack an alert |
| `POST` | `/alerts/active/{k}/resolve` | Resolve an alert |
| `POST` | `/alerts/{id}/test` | Send test notification |
| **Maintenance** | | |
| `GET/POST` | `/maintenance-windows` | List / schedule downtime |
| `DELETE` | `/maintenance-windows/{id}` | Remove window |
| `GET` | `/poll-history` | Recent SNMP poll results |
| `GET` | `/stats` | Poller throughput stats |

### Network Types

| Slug | Label | Description |
|------|-------|-------------|
| `lan` | LAN | Wired local area network |
| `wan` | WAN | Wide area / uplink |
| `wifi` | Wi-Fi | Wireless 802.11 |
| `sfp` | SFP / Fiber | Optical fiber |
| `console` | Console / Serial | RS-232 management port |
| `bmc` | BMC / IPMI | Out-of-band controller |
| `mgmt` | Management | OOB management network |
| `dmz` | DMZ | Perimeter zone |
| `vlan` | VLAN | Logical segment |
| `vpn` | VPN | Encrypted tunnel |
| `custom` | Custom | Unclassified |

### Service Check Types

| Type | Description |
|------|-------------|
| `http` | HTTP/HTTPS endpoint — status code, response body |
| `tcp` | Raw TCP port connectivity |
| `dns` | DNS resolution — record type, expected IPs |
| `ping` | ICMP echo — latency, packet loss |
| `ssl` | SSL certificate expiry — warning/critical day thresholds |

### Notification Channels

| Channel | Transport |
|---------|-----------|
| `slack` | Incoming webhook |
| `telegram` | Bot API |
| `whatsapp` | Twilio API |
| `email` | SMTP |
| `webhook` | Generic HTTP POST |

---

## Testing

```bash
pytest tests/ -v          # all 105 tests
pytest tests/test_api.py  # API integration
./scripts/test.sh         # full smoke test (starts/stops server)
```

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
| CPU optimization | Done | batching, semaphores, single-tick scheduler, `--reload-dir` fix (1.2% idle) |
| Network management | Done | slide-out drawer, 11 types, inline rename, tags, device counts |
| Docker | Done | multi-container compose, nginx, health checks |
| Auth & RBAC | Planned | JWT, login page, role-based access |
| SNMPv3 | Planned | auth + privacy protocols |
| Distributed agents | Planned | remote pollers, central aggregator |

---

---

## CLI

```bash
# Single-device SNMP query
python src/collector/spike_snmp.py <host> [-c community] [--action sysdescr|lldp|all]

# Simulate topology (offline demo)
curl -X POST http://localhost:8000/topology/simulate
```

---


