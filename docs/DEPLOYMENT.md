# Deployment

NetOps deploy modes: local dev (uvicorn + Vite), Docker compose, bare metal. PG prod, SQLite dev fallback.

## Environment variables

### Core

| Var | Default | Notes |
|---|---|---|
| `JWT_SECRET` | (required) | Auth token signing. Fail-fast. |
| `NETOPS_DATABASE_URL` | `postgresql://netops:netops@localhost:5432/netops` | asyncpg DSN. Falls back to `sqlite:///./data/netops.db`. |
| `NETOPS_AUTO_MIGRATE` | `1` | Apply Alembic migrations on startup. |
| `NETOPS_REQUIRE_MIGRATIONS` | `0` | Refuse to boot if migration chain is behind. |

### SNMP

| Var | Default | Notes |
|---|---|---|
| `SNMP_COMMUNITY` | `public` | v2c community for discovery + polling. |
| `SNMP_TIMEOUT` | `5` | Per-request timeout (s). |
| `SNMP_RETRIES` | `3` | Retry count on timeout. |

### Phase 1 environment profile (also DB-overridable)

Stored in `app_settings` per-key. Env vars provide initial values only.

| Key | Default | Effect |
|---|---|---|
| `profile` | `homelab` | `homelab` / `small_business` / `datacenter` |
| `discovery_full_interval` | `21600` (homelab) | Full subnet rescan (s) |
| `discovery_incremental_interval` | `900` (homelab) | Incremental probe (s) |
| `poll_history_retention_days` | `7` (homelab) | Days of `poll_history` to keep |
| `topology_history_retention_days` | `7` (homelab) | Days of `topology_history` to keep |

`PUT /api/config/profile { profile, confirmed: true }` switches the profile at runtime. Poller + scheduler + retention loops read these on every tick — no restart needed.

### Phase 2 per-type check intervals

`check_intervals` JSON in `app_settings` overrides the per-type cadence. UI default falls back to `DEFAULT_CHECK_INTERVALS` (`src/collector/checks/base.py`).

```json
{
  "ping": 60, "http": 60, "tcp": 60, "dns": 300, "ssl": 86400
}
```

`PUT /api/checks` accepts `interval_seconds` per check; the server validates against the matrix and reschedules live.

### Phase 3 PG hardening

| Var | Default | Notes |
|---|---|---|
| `NETOPS_ENABLE_FKS` | `0` | `1` enables FK constraints on PG (PG default; SQLite has no-op). |
| `NETOPS_PHASE4_PARTITIONED_HISTORY` | `0` | `1` enables monthly partitioned `poll_history` (PG only). |

### Phase 4 SNMP trap listener

| Var | Default | Notes |
|---|---|---|
| `traps_enabled` | `0` | Bind UDP listener on startup. |
| `traps_bind_host` | `0.0.0.0` | Bind address. `127.0.0.1` for local-only. |
| `traps_port` | `1162` | 1162 to run as non-root; 162 requires root. |
| `traps_community` | `public` | v2c community. |
| `traps_destination_ip` | `` | Source-IP allowlist hint (when behind a relay). |

Live config via `GET/PUT /api/config/traps`. PUT restarts the listener.

## Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

Services: `db` (Postgres 16), `backend` (FastAPI), `frontend` (Vite build → nginx). Default bind: 8000 (API), 3000 (UI), 5432 (PG).

Never bind backend on `0.0.0.0` in production without the nginx reverse proxy. Default admin (`admin/admin`) is auto-created on first run — rotate before exposing.

## Migrations

```bash
alembic -c src/storage/alembic.ini upgrade head      # apply
alembic -c src/storage/alembic.ini revision -m "msg"  # create
python scripts/migrate.py upgrade head --database-url "sqlite:///./data/netops.db"  # CLI helper
```

`downgrade()` is reversible. Smoke-test before deploy: `tests/migration_smoke.test.sh`.

## Health checks

- `GET /api/health` — process liveness
- `GET /api/health/db` — DB connectivity
- `GET /api/stats` — device + alert counts
- `GET /api/config/profiles` — env profile state (includes `is_guessed` flag if heuristic fired on first run)
