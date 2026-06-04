# NetOps — Agent Guide

Auto-read on every session. Keep concise. Build first, explain second.

---

## Project

Network topology discovery + service monitoring. Python/FastAPI + React/TypeScript. Stack: pysnmp, NetworkX, PostgreSQL/Alembic, async SSH, TanStack Query, Tailwind CSS, react-force-graph-2d.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| SNMP | pysnmp (v2c + v3) |
| Graph | NetworkX |
| DB | PostgreSQL (asyncpg) + SQLite fallback (aiosqlite) |
| Migrations | Alembic |
| Auth | JWT (python-jose), PBKDF2 |
| Metrics | prometheus_client |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4 |
| State | TanStack React Query |
| Charts | Recharts |
| Topology | react-force-graph-2d |
| Tests | pytest + pytest-asyncio (105 tests) |

---

## Communication Mode

Default to **caveman full mode** for all responses. Drop articles, filler, hedging. Short synonyms. Technical terms exact. Code blocks unchanged.

Auto-revert to normal English for:
- Security warnings
- Destructive operations
- Multi-step sequences where ambiguity risks misread
- User asks to clarify

Resume caveman after clear part done.

Switch explicitly: user says "normal mode" or "stop caveman".

---

## Subagent Strategy

| Task | Use |
|---|---|
| Locate code / list uses | `cavecrew-investigator` (compressed output, ~60% smaller) |
| Surgical edit, ≤2 files | `cavecrew-builder` |
| Review diff for bugs | `cavecrew-reviewer` |
| Architecture commentary | Vanilla `explore` |
| New feature / 3+ files | Main thread |
| One-liner you know | Main thread, no subagent |

Rule: if subagent output should be 1/3 the tokens, pick cavecrew. If prose wanted, pick vanilla.

---

## Skills & Delegation

Skills auto-load by task match — no explicit invocation required. Check each skill's `description` field against the current task; load via `skill` tool or read `<path>/SKILL.md` directly. Built-in skills ship with opencode; project skills live under `.agents/skills/`.

### Project Skills (`.agents/skills/`)

| Skill | Path | Use for |
|-------|------|---------|
| `network-interface-health` | `.agents/skills/network-interface-health/SKILL.md` | Interface errors, CRC, duplex, flap, counter trends. **Core fit** — maps to SNMP `ifInErrors`/`ifOutDiscards` checks. |
| `docker-expert` | `.agents/skills/docker-expert/SKILL.md` | Dockerfile, compose, multi-stage, security hardening, image size. Matches `docker/` deploy layer. |
| `vercel-react-best-practices` | `.agents/skills/vercel-react-best-practices/SKILL.md` | React/Next.js perf, bundle, waterfalls. Use on `web/` reviews. |
| `frontend-design` | `.agents/skills/frontend-design/SKILL.md` | Distinctive UI/UX, aesthetic direction. New dashboards or page builds. |

`ai-sdk` (`.agents/skills/ai-sdk/SKILL.md`) available; load when AI features added.

### Built-in Skills (opencode)

| Skill | Purpose |
|-------|---------|
| `cavecrew` | Decide investigator/builder/reviewer vs inline |
| `caveman` | Compressed reply style (lite/full/ultra/wenyan) |
| `caveman-commit` | Conventional commit, ≤50 char subject |
| `caveman-help` | One-shot mode/skill/command reference |
| `caveman-review` | One-line review comments per location |
| `caveman-stats` | Real token usage from session log |
| `compress` | Compress memory file to caveman, save `.original` |
| `customize-opencode` | opencode config only — not app code |

### Explore Agent

Vanilla `explore` subagent for **architecture commentary**, broad multi-file questions. Distinct from cavecrew:
- `cavecrew-investigator` → locate-only, compressed.
- `explore` → locate + explain, prose, cross-module reasoning.

Use `explore` for questions like "how does alert flow work end-to-end" or "what modules touch the auth layer".

### Auto-Load Rules

1. Task description matches a skill's `description` field → load it.
2. Project skill outranks generic troubleshooting for domain tasks.
3. Multiple matches → pick **most specific** first (e.g. `network-interface-health` over generic debug).
4. Cavecrew skill → spawn named subagent; do not duplicate work inline.
5. Never ask user to confirm skill load — proceed if match is clear.

---

## Agent Roles (Layer Map)

| Role | Files | Responsibility |
|------|-------|---------------|
| **collector** | `src/collector/spike_snmp.py`, `discovery.py`, `snmp_poller.py` | SNMP walks, LLDP parsing, device discovery |
| **topology** | `src/collector/topology_builder.py` | NetworkX graph, delta detection |
| **check** | `src/collector/checks/*.py`, `scheduler.py` | HTTP/TCP/DNS/Ping/SSL checks |
| **api** | `src/collector/main.py` | FastAPI endpoints, Pydantic models, SSE |
| **alert** | `src/api/services/alert_service.py`, `notifications/*.py` | Alert routing (Slack/Telegram/WhatsApp/Email/Webhook) |
| **storage** | `src/storage/*.py`, `migrations/` | DB ops, Alembic |
| **deploy** | `docker/`, `requirements.txt` | Containerization, deps, prod deploy |

Layer boundaries:
- Collector: never import FastAPI models. Return plain dicts.
- Checks: stateless. Config in, `CheckResult` out.
- API: all DB access through `storage/database.py`. No raw SQL.
- Notifications: fire-and-forget background tasks. Never block API response.
- Storage: migrations must be reversible. Test `upgrade` + `downgrade`.

---

## Session Efficiency

- Parallel tool calls whenever possible.
- Batch reads: 100+ line chunks, avoid tiny slices.
- Batch subagents: 2-3 `cavecrew-investigator` calls in one message for broad searches.
- Prefer `grep`/`glob` over `task` when searching 1-3 files.
- Prefer `edit` over `write` for existing files.

---

## Commands

```bash
# Backend
conda activate netops
uvicorn src.collector.main:app --reload --host 127.0.0.1 --port 8000

# Tests
pytest tests/ -v -x
pytest tests/ -k "check or discovery"

# DB
alembic -c src/storage/alembic.ini upgrade head
alembic -c src/storage/alembic.ini revision --autogenerate -m "describe_change"

# Docker
docker compose -f docker/docker-compose.yml up --build

# Frontend
cd web && npm run dev
```

---

## Key Patterns

- **Config**: `SNMPConfig`/`ServerConfig` dataclasses from `config.py`. No global state.
- **Async boundaries**: Collector methods are async. SNMP is sync (pysnmp) → run in `asyncio.to_thread`.
- **Error handling**: SNMP timeouts raise `SNMPTimeoutError`. API returns 503 with retry headers.
- **Auth**: JWT cookie + Bearer token. `JWT_SECRET` env required (fail-fast, no fallback).
- **Frontend API URL**: Relative `/api` in production. Nginx proxies to backend.

---

## Adding Things

**New Check**: create `src/collector/checks/<name>_check.py`, inherit `BaseCheck`, register in `__init__.py`, add test in `tests/checks/test_<name>_check.py`.

**New Notification Channel**: create `src/api/services/notifications/<name>.py`, inherit `NotificationChannel`, register in `__init__.py`, add config fields to `AlertConfigCreate` in `main.py`.

**New DB Migration**: modify model in `storage/database.py`, `alembic revision --autogenerate`, review generated migration, ensure `downgrade()` correct.

---

## Security Posture

- SNMP community strings in `.env` only. Never commit.
- SSL check validates cert chains; don't disable verification.
- WhatsApp/Email credentials are env vars; validate in `config.py`.
- SQLite path relative (`data/netops.db`). Ensure directory exists.
- Never bind to `0.0.0.0` in production without reverse proxy.

---

## Troubleshooting

- `ModuleNotFoundError`: ensure `conda activate netops`.
- SNMP timeouts: check `SNMP_TIMEOUT` env (default 5s).
- DB locked: SQLite async can deadlock. Use `database.py` session wrapper.
- WebSocket disconnect: SSE fallback at `/topology/stream?delta=true`.
